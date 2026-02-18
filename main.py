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


ALERT_TYPES = {
    "air_raid": ("🚨", "ПОВІТРЯНА ТРИВОГА"),
    "rocket": ("🚀", "РАКЕТНА ЗАГРОЗА"),
    "drone": ("🛸", "ЗАГРОЗА БПЛА"),
    "artillery_shelling": ("💣", "АРТИЛЕРІЙСЬКИЙ ОБСТРІЛ"),
    "urban_fights": ("🛡️", "ВУЛИЧНІ БОЇ"),
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


# ---------- НОВЫЙ ПАРСИНГ С РАЗДЕЛЕНИЕМ ----------
def get_alerts_struct():
    try:
        r = requests.get(
            "https://api.alerts.in.ua/v1/alerts/active.json",
            headers={"Authorization": f"Bearer {ALERTS_TOKEN}"},
            timeout=5,
        )

        if r.status_code != 200:
            return None

        data = r.json()
        alerts = data.get("alerts", [])

        result = {
            "types": [],
            "cities": set(),
            "raions": set(),
            "oblast": False,
        }

        for a in alerts:
            if "харків" not in a.get("location_oblast", "").lower():
                continue

            result["types"].append(a.get("alert_type", "air_raid"))

            loc_type = a.get("location_type")
            title = a.get("location_title")

            if loc_type == "city":
                result["cities"].add(title)
            elif loc_type == "raion":
                result["raions"].add(title)
            elif loc_type == "oblast":
                result["oblast"] = True

        return result

    except Exception as e:
        logging.error(f"alerts.in.ua error: {e}")
        return None


@app.route("/api/alerts")
def api_alerts():
    data = get_alerts_struct()
    return jsonify({"active": bool(data and data["types"])})


last_status = None
last_alert_start = None
last_daily_report = datetime.now(timezone.utc).date()
last_reminder_sent = None

daily_alerts_count = 0
daily_duration_total = 0
daily_types = {k: 0 for k in ALERT_TYPES.keys()}


# ---------- ТЕКСТ С РАЗДЕЛЕНИЕМ ----------
def build_location_text(info):
    if info["oblast"]:
        return "📍 Харківська область"

    if info["raions"]:
        return "📍 Райони:\n" + "\n".join(f"• {r}" for r in sorted(info["raions"]))

    if info["cities"]:
        return "📍 Міста:\n" + "\n".join(f"• {c}" for c in sorted(info["cities"]))

    return "📍 Харківська область"


def build_start_message(info):
    alert_type = info["types"][0] if info["types"] else "air_raid"
    emoji, title = ALERT_TYPES.get(alert_type, ALERT_TYPES["default"])
    time_now = datetime.now().strftime("%H:%M")

    return (
        f"{emoji} *{title}*\n"
        f"{build_location_text(info)}\n"
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

    avg = int(daily_duration_total / daily_alerts_count)

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
            info = get_alerts_struct()
            current_status = bool(info and info["types"])
            now = datetime.now(timezone.utc)

            if last_status is None:
                last_status = False  # важно для старта во время тревоги

            if current_status != last_status:
                if current_status:
                    send_message(build_start_message(info))

                    last_alert_start = now
                    last_reminder_sent = now

                    daily_alerts_count += 1
                    for t in info["types"]:
                        daily_types[t] = daily_types.get(t, 0) + 1
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
