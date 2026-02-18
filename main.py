import os
import requests
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify
from threading import Thread
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logging.info("=== BOT STARTED ===")

app = Flask(__name__)

from map import map_bp
app.register_blueprint(map_bp)


@app.route("/")
def home():
    return "Bot is running"


TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()
ALERTS_TOKEN = os.getenv("ALERTS_TOKEN", "").strip()

if not TOKEN or not CHAT_ID:
    raise SystemExit("BOT_TOKEN или CHAT_ID не заданы!")

if not ALERTS_TOKEN:
    raise SystemExit("ALERTS_TOKEN не задан!")


# ---------- РАСШИРЕННЫЕ ТИПЫ УГРОЗ ----------
ALERT_TYPES = {
    "air_raid": ("🚨", "ПОВІТРЯНА ТРИВОГА"),
    "rocket": ("🚀", "РАКЕТНА ЗАГРОЗА"),
    "missile": ("🚀", "РАКЕТНА АТАКА"),
    "drone": ("🛸", "ЗАГРОЗА БПЛА"),
    "aircraft": ("✈️", "ЗАГРОЗА АВІАЦІЇ"),
    "artillery": ("💣", "АРТИЛЕРІЙСЬКА НЕБЕЗПЕКА"),
    "tank": ("🪖", "ЗАГРОЗА БРОНЕТЕХНІКИ"),
    "street_fighting": ("🛡️", "ВУЛИЧНІ БОЇ"),
    "naval": ("🚢", "ЗАГРОЗА З МОРЯ"),
    "explosion": ("💥", "ПОВІДОМЛЕННЯ ПРО ВИБУХИ"),
    "chemical": ("☣️", "ХІМІЧНА НЕБЕЗПЕКА"),
    "radiation": ("☢️", "РАДІАЦІЙНА НЕБЕЗПЕКА"),
    "unknown": ("⚠️", "НЕВІДОМА ЗАГРОЗА"),
    "default": ("⚠️", "НЕБЕЗПЕКА"),
}


def send_message(text, retries=3):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}

    for _ in range(retries):
        try:
            r = requests.post(url, data=data, timeout=5)
            if r.status_code == 200:
                logging.info("Telegram message sent")
                return True
            else:
                logging.error(f"Telegram status: {r.status_code} | {r.text}")
        except Exception as e:
            logging.error(f"Telegram error: {e}")
        time.sleep(2)
    return False


def get_alerts():
    try:
        r = requests.get(
            "https://api.alerts.in.ua/v1/alerts/active.json",
            headers={"Authorization": f"Bearer {ALERTS_TOKEN}"},
            timeout=5,
        )

        logging.info(f"Alerts API status: {r.status_code}")

        if r.status_code != 200:
            return []

        data = r.json()
        regions = data.get("regions", []) if isinstance(data, dict) else data

        alerts = []

        for region in regions:
            if not isinstance(region, dict):
                continue

            name = region.get("regionName", "").lower()

            if "харків" in name:
                for a in region.get("activeAlerts", []):
                    alerts.append(a.get("type", "air_raid"))

        logging.info(f"Detected alerts: {alerts}")
        return alerts

    except Exception as e:
        logging.error(f"alerts.in.ua error: {e}")
        return []


@app.route("/api/alerts")
def api_alerts():
    return jsonify({"active": bool(get_alerts())})


last_status = None
last_alert_start = None
last_daily_report = datetime.now(timezone.utc).date()
last_reminder_sent = None

daily_alerts_count = 0
daily_duration_total = 0
daily_types = {k: 0 for k in ALERT_TYPES.keys()}


def build_start_message(alert_type):
    emoji, title = ALERT_TYPES.get(alert_type, ALERT_TYPES["default"])
    time_now = datetime.now().strftime("%H:%M")

    return (
        f"{emoji} *{title}*\n"
        f"📍 Харківська область\n"
        f"🕒 {time_now}\n\n"
        f"➡️ *Негайно прямуйте в укриття*"
    )


def build_end_message(duration_min):
    time_now = datetime.now().strftime("%H:%M")

    msg = "✅ *ВІДБІЙ ТРИВОГИ*\n"
    msg += f"🕒 {time_now}"

    if duration_min:
        msg += f"\n⏱ Тривалість: {duration_min} хв"

    return msg


def build_daily_report():
    if daily_alerts_count == 0:
        return "📊 *За добу тривог не було*"

    avg = int(daily_duration_total / daily_alerts_count) if daily_alerts_count else 0

    report = "📊 *СТАТИСТИКА ЗА ДОБУ*\n\n"
    report += f"🔔 Тривог: {daily_alerts_count}\n"
    report += f"⏱ Середня тривалість: {avg} хв\n\n"

    for t, count in daily_types.items():
        if t == "default" or count == 0:
            continue
        emoji, title = ALERT_TYPES[t]
        report += f"{emoji} {title.title()}: {count}\n"

    return report


def loop():
    global last_status, last_alert_start, last_daily_report, last_reminder_sent
    global daily_alerts_count, daily_duration_total, daily_types

    while True:
        try:
            alerts = get_alerts()
            current_status = bool(alerts)
            now = datetime.now(timezone.utc)

            if last_status is None:
                last_status = current_status

            if current_status != last_status:
                if current_status:
                    alert_type = alerts[0] if alerts else "air_raid"

                    send_message(build_start_message(alert_type))

                    last_alert_start = now
                    last_reminder_sent = now

                    daily_alerts_count += 1
                    daily_types[alert_type] = daily_types.get(alert_type, 0) + 1

                else:
                    duration = 0
                    if last_alert_start:
                        duration = int((now - last_alert_start).total_seconds() // 60)
                        daily_duration_total += duration

                    send_message(build_end_message(duration))

                last_status = current_status

            if current_status and last_reminder_sent:
                if (now - last_reminder_sent).total_seconds() >= 900:
                    send_message("⏰ *ТРИВОГА ТРИВАЄ*\nБудьте в укритті.")
                    last_reminder_sent = now

            today = (now + timedelta(hours=2)).date()
            if today != last_daily_report:
                send_message(build_daily_report())

                daily_alerts_count = 0
                daily_duration_total = 0
                daily_types = {k: 0 for k in ALERT_TYPES.keys()}
                last_daily_report = today

        except Exception as e:
            logging.error(f"Main loop error: {e}")
            time.sleep(10)

        time.sleep(3)


Thread(target=loop, daemon=True).start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
