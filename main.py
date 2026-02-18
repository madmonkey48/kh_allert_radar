import os
import requests
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify
from threading import Thread
import time
import logging

# ---------- Логирование ----------
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logging.info("=== BOT STARTED ===")

# ---------- Flask ----------
app = Flask(__name__)

# ---------- ПОДКЛЮЧАЕМ КАРТУ ----------
from map import map_bp
app.register_blueprint(map_bp)


@app.route("/")
def home():
    return "Bot is running"


# ---------- Переменные окружения ----------
TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()
ALERTS_TOKEN = os.getenv("ALERTS_TOKEN", "").strip()

if not TOKEN or not CHAT_ID:
    raise SystemExit("BOT_TOKEN или CHAT_ID не заданы!")

if not ALERTS_TOKEN:
    raise SystemExit("ALERTS_TOKEN не задан!")


# ---------- Советы безопасности ----------
ALERT_ADVICE = {
    "air_raid": "Знайдіть найближче укриття.",
    "artillery": "Уникайте відкритих місць.",
    "rocket": "Негайно прямуйте в укриття.",
    "drone": "Залишайтесь у приміщенні.",
    "street_fighting": "Не виходьте на вулицю.",
    "default": "Дотримуйтесь правил безпеки."
}

# ---------- Дизайн уведомлений ----------
ALERT_META = {
    "air_raid":  {"emoji": "🚨", "title": "ПОВІТРЯНА ТРИВОГА"},
    "rocket":    {"emoji": "🚀", "title": "РАКЕТНА НЕБЕЗПЕКА"},
    "artillery": {"emoji": "💣", "title": "АРТИЛЕРІЙСЬКА ЗАГРОЗА"},
    "drone":     {"emoji": "🛸", "title": "ЗАГРОЗА БПЛА"},
    "street_fighting": {"emoji": "🛡️", "title": "ВУЛИЧНІ БОЇ"},
    "default":   {"emoji": "⚠️", "title": "НЕБЕЗПЕКА"},
}


def format_alert_start(alert_type: str, start_time: datetime) -> str:
    meta = ALERT_META.get(alert_type, ALERT_META["default"])
    advice = ALERT_ADVICE.get(alert_type, ALERT_ADVICE["default"])

    return (
        f"{meta['emoji']} *{meta['title']}*\n"
        f"📍 *Харківська область*\n"
        f"🕒 Початок: *{start_time.strftime('%H:%M')}*\n\n"
        f"_{advice}_"
    )


def format_alert_reminder(minutes: int) -> str:
    return (
        "⏰ *ТРИВОГА ТРИВАЄ*\n"
        f"⏱ Вже: *{minutes} хв*\n\n"
        "Перебувайте в укритті."
    )


def format_alert_end(duration: int | None) -> str:
    msg = (
        "✅ *ВІДБІЙ ПОВІТРЯНОЇ ТРИВОГИ*\n"
        "📍 *Харківська область*"
    )

    if duration:
        msg += f"\n⏱ Тривала: *{duration} хв*"

    msg += "\n\nБудьте обережні."

    return msg


def format_daily_report(count: int) -> str:
    return (
        "📊 *СТАТИСТИКА ЗА ДОБУ*\n"
        f"🔔 Тривог: *{count}*\n\n"
        "Бережіть себе."
    )


# ---------- Telegram ----------
def send_message(text, retries=3):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}

    for _ in range(retries):
        try:
            if requests.post(url, data=data, timeout=10).status_code == 200:
                return True
        except Exception as e:
            logging.error(f"Telegram error: {e}")
        time.sleep(5)
    return False


# ---------- Alerts API ----------
def get_alerts():
    try:
        r = requests.get(
            "https://api.alerts.in.ua/v1/alerts/active.json",
            headers={"Authorization": f"Bearer {ALERTS_TOKEN}"},
            timeout=10,
        )

        if r.status_code != 200:
            return []

        data = r.json()
        regions = data.get("regions", []) if isinstance(data, dict) else data

        alerts = []
        for region in regions:
            if isinstance(region, dict) and region.get("regionName") == "Харківська область":
                for a in region.get("activeAlerts", []):
                    alerts.append(a.get("type", "air_raid"))

        return alerts

    except Exception as e:
        logging.error(f"alerts.in.ua error: {e}")
        return []


@app.route("/api/alerts")
def api_alerts():
    """Используется картой"""
    return jsonify({"active": bool(get_alerts())})


# ---------- Основная логика ----------
last_status = None
last_alert_start = None
last_daily_report = datetime.now(timezone.utc).date()
daily_alerts = []
last_reminder_sent = None


def loop():
    global last_status, last_alert_start, last_daily_report, daily_alerts, last_reminder_sent

    while True:
        try:
            alerts = get_alerts()
            current_status = bool(alerts)
            now = datetime.now(timezone.utc)

            if last_status is None:
                last_status = current_status

            # --- начало / конец тревоги ---
            if current_status != last_status:
                if current_status:
                    alert_type = alerts[0] if alerts else "air_raid"

                    send_message(format_alert_start(alert_type, now))

                    last_alert_start = now
                    daily_alerts.append(now)
                    last_reminder_sent = now
                else:
                    duration = None
                    if last_alert_start:
                        duration = int((now - last_alert_start).total_seconds() // 60)

                    send_message(format_alert_end(duration))

                last_status = current_status

            # --- напоминание каждые 15 минут ---
            if current_status and last_alert_start and last_reminder_sent:
                if (now - last_reminder_sent).total_seconds() >= 900:
                    minutes = int((now - last_alert_start).total_seconds() // 60)
                    send_message(format_alert_reminder(minutes))
                    last_reminder_sent = now

            # --- суточная статистика ---
            today = (now + timedelta(hours=2)).date()
            if today != last_daily_report:
                send_message(format_daily_report(len(daily_alerts)))
                daily_alerts = []
                last_daily_report = today

        except Exception as e:
            logging.error(f"Main loop error: {e}")
            time.sleep(10)

        time.sleep(60)


Thread(target=loop, daemon=True).start()


# ---------- Запуск ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
