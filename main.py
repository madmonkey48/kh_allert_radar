import os
import requests
from PIL import Image, ImageDraw
from io import BytesIO
from datetime import datetime, timedelta, timezone
from flask import Flask
from threading import Thread
import time
import logging

# ---------- Логирование в stdout (для Railway) ----------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

# ---------- Keep Alive ----------
app = Flask('')

@app.route('/')
def home():
    return "Bot is running"


def run():
    app.run(host='0.0.0.0', port=8080)


def keep_alive():
    Thread(target=run, daemon=True).start()


keep_alive()

logging.info("=== BOT STARTED ===")

# ---------- Переменные окружения ----------
TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()
ALERTS_TOKEN = os.getenv("ALERTS_TOKEN", "").strip()

if not TOKEN or not CHAT_ID:
    logging.error("BOT_TOKEN или CHAT_ID не заданы!")
    raise SystemExit("BOT_TOKEN или CHAT_ID не заданы!")

if not ALERTS_TOKEN:
    logging.error("ALERTS_TOKEN не задан!")
    raise SystemExit("ALERTS_TOKEN не задан!")

# ---------- Основные переменные ----------
last_alert_start = None
last_status = None
daily_alerts = []
last_daily_report = datetime.now(timezone.utc).date()
last_alerts_active = []
last_reminder_sent = None

# ---------- Советы по безопасности ----------
ALERT_ADVICE = {
    "air_raid": "🚨 Повітряна тривога — Знайдіть найближче укриття.",
    "artillery": "💣 Артилерійська загроза — Уникайте відкритих місць.",
    "rocket": "🔥 Ракетна загроза — Негайно спускайтеся в укриття.",
    "street_fighting": "🛡️ Вуличні бої — Залишайтеся вдома.",
    "drone": "🛸 БПЛА — Перебувайте в приміщенні.",
    "default": "⚠️ Інша загроза — Дотримуйтесь правил безпеки."
}

# ---------- Telegram ----------

def send_message(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": text},
            timeout=10
        )
        logging.info("Message sent")
    except Exception:
        logging.exception("Telegram send_message error")


def send_photo(photo_bytes, caption):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendPhoto",
            files={"photo": photo_bytes},
            data={"chat_id": CHAT_ID, "caption": caption},
            timeout=10
        )
        logging.info("Photo sent")
    except Exception:
        logging.exception("Telegram send_photo error")

# ---------- alerts.in.ua ----------

def get_alert_status():
    url = "https://api.alerts.in.ua/v1/alerts/active.json"
    headers = {"Authorization": f"Bearer {ALERTS_TOKEN}"}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        logging.info(f"alerts.in.ua status: {resp.status_code}")

        if resp.status_code != 200:
            return []

        data = resp.json()
        logging.info(f"API regions count: {len(data)}")

        alerts = []

        for region in data:
            name = region.get("regionName", "")

            if "Хар" not in name:
                continue

            for a in region.get("activeAlerts", []):
                alerts.append({
                    "type": a.get("type", "air_raid"),
                    "places": [a.get("locationTitle", name)]
                })

        logging.info(f"Active alerts found: {len(alerts)}")
        return alerts

    except Exception:
        logging.exception("alerts.in.ua request failed")
        return []

# ---------- Карта ----------
COORDS = {
    "Салтівка": (500, 200),
    "ХТЗ": (600, 400),
    "Центр": (400, 300)
}


def generate_map(alerts):
    try:
        base_map = Image.new("RGBA", (800, 600), (0, 0, 0, 255))
        draw = ImageDraw.Draw(base_map)

        for alert in alerts:
            for place in alert.get("places", []):
                if place in COORDS:
                    x, y = COORDS[place]
                    draw.ellipse((x-10, y-10, x+10, y+10), fill=(255, 0, 0, 180))

        output = BytesIO()
        base_map.save(output, format="PNG")
        output.seek(0)
        return output

    except Exception:
        logging.exception("Map generation failed")
        return None

# ---------- Основной цикл с защитой ----------

def main_loop():
    global last_status, last_alert_start, daily_alerts, last_daily_report, last_alerts_active, last_reminder_sent

    error_delay = 5

    while True:
        try:
            logging.info("tick")

            alerts = get_alert_status()
            current_status = bool(alerts)
            now_utc = datetime.now(timezone.utc)

            if last_status is None:
                last_status = current_status

            if current_status != last_status:
                if current_status:
                    photo = generate_map(alerts)
                    if photo:
                        send_photo(photo, "🚨 ТРИВОГА")
                    last_alert_start = now_utc
                    daily_alerts.append(now_utc)
                    last_alerts_active = alerts.copy()
                    last_reminder_sent = now_utc
                else:
                    send_message("✅ Відбій тривоги")

                last_status = current_status

            today = (now_utc + timedelta(hours=2)).date()
            if today != last_daily_report:
                send_message(f"📊 Тривог за день: {len(daily_alerts)}")
                daily_alerts = []
                last_daily_report = today

            error_delay = 5
            time.sleep(60)

        except Exception:
            logging.exception("Main loop crash")
            time.sleep(error_delay)
            error_delay = min(error_delay * 2, 300)


if __name__ == "__main__":
    main_loop()
