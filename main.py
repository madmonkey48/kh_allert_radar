import os
import requests
from PIL import Image, ImageDraw
from io import BytesIO
from datetime import datetime, timedelta, timezone
from flask import Flask
from threading import Thread
import time
import logging

# ---------- Логирование в stdout (ВАЖНО для Railway) ----------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

logging.info("=== BOT STARTED ===")

# ---------- Keep Alive ----------
app = Flask('')

@app.route('/')
def home():
    return "Bot is running"


def run():
    app.run(host='0.0.0.0', port=8080)


def keep_alive():
    Thread(target=run).start()


keep_alive()

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
    "air_raid": "🚨 *Повітряна тривога* — Знайдіть найближче укриття, закрийте вікна, тримайте телефон поруч для оповіщень.",
    "artillery": "💣 *Артилерійська загроза* — Не перебувайте на відкритих просторах, сховайтеся у будинку, майте під рукою аптечку.",
    "rocket": "🔥 *Ракетна загроза* — Негайно спускайтеся в підвал або захищене приміщення, не підходьте до вікон.",
    "street_fighting": "🛡️ *Вуличні бої* — По можливості уникайте вулиць, залишайтеся вдома, повідомляйте про підозрілі переміщення.",
    "drone": "🛸 *БПЛА* — Не наближайтесь до підозрілих дронів, перебувайте в приміщенні.",
    "default": "⚠️ *Інша загроза* — Дотримуйтесь загальних правил безпеки, слідкуйте за оновленнями від влади."
}

# ---------- Отправка сообщений ----------

def send_message(text, retries=3):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "MarkdownV2"}

    for attempt in range(retries):
        try:
            resp = requests.post(url, data=data, timeout=10)
            if resp.status_code == 200:
                logging.info("Сообщение отправлено")
                return True
            else:
                logging.warning(f"Ошибка Telegram: {resp.text}")
        except Exception as e:
            logging.error(f"Ошибка при отправке сообщения: {e}")

        time.sleep(5)

    return False


def send_photo(photo_bytes, caption, retries=3):
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    files = {"photo": photo_bytes}
    data = {"chat_id": CHAT_ID, "caption": caption, "parse_mode": "MarkdownV2"}

    for attempt in range(retries):
        try:
            resp = requests.post(url, files=files, data=data, timeout=10)
            if resp.status_code == 200:
                logging.info("Фото отправлено")
                return True
            else:
                logging.warning(f"Ошибка Telegram: {resp.text}")
        except Exception as e:
            logging.error(f"Ошибка при отправке фото: {e}")

        time.sleep(5)

    return False

# ---------- Реальное получение тревог (ИСПРАВЛЕНО) ----------

def get_alert_status():
    url = "https://api.alerts.in.ua/v1/alerts/active.json"
    headers = {"Authorization": f"Bearer {ALERTS_TOKEN}"}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        logging.info(f"alerts.in.ua status: {resp.status_code}")

        if resp.status_code != 200:
            logging.error(f"alerts.in.ua bad response: {resp.text}")
            return []

        data = resp.json()

        # API может вернуть dict или list
        if isinstance(data, dict):
            regions = data.get("regions", [])
        else:
            regions = data

        logging.info(f"API regions count: {len(regions)}")

        alerts = []

        for region in regions:
            if not isinstance(region, dict):
                continue

            if region.get("regionName") != "Харківська область":
                continue

            for a in region.get("activeAlerts", []):
                alerts.append({
                    "type": a.get("type", "air_raid"),
                    "places": [a.get("locationTitle", "Харківська область")]
                })

        return alerts

    except Exception as e:
        logging.error(f"alerts.in.ua request failed: {e}")
        return []

# ---------- Координаты ----------
COORDS = {
    "Салтівка": (500, 200),
    "ХТЗ": (600, 400),
    "Центр": (400, 300),
    "Шевченківський": (380, 280),
    "Новобаварський": (450, 380),
    "Комінтернівський": (420, 350),
    "Московський": (360, 360),
    "Олексіївка": (480, 220),
    "Індустріальний": (550, 450),
    "Основ'янський": (300, 320)
}

# ---------- Генерация карты ----------

def generate_map(alerts):
    map_url = "https://raid.fly.dev/map.png"

    try:
        response = requests.get(map_url, timeout=10)
        base_map = Image.open(BytesIO(response.content)).convert("RGBA")
    except Exception as e:
        logging.warning(f"Ошибка при загрузке карты: {e}")
        base_map = Image.new("RGBA", (800, 600), (0, 255, 0, 255))

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

# ---------- Форматирование подписи ----------

def escape_md(text):
    special_chars = r"_*[]()~`>#+-=|{}.!"
    for c in special_chars:
        text = text.replace(c, f"\\{c}")
    return text


def format_caption(alerts=None, active=True, duration=None):
    now = datetime.now(timezone.utc) + timedelta(hours=2)
    now_str = now.strftime("%H:%M")

    caption = f"📍 *Харківська область*\n🕒 {now_str}\n\n"

    if active and alerts:
        types_text = ""
        places_text = []

        for alert in alerts:
            t = alert.get("type")
            places = alert.get("places", [])

            if places:
                places_text.extend(places)

            types_text += escape_md(ALERT_ADVICE.get(t, ALERT_ADVICE["default"])) + "\n"

        caption += types_text

        if places_text:
            caption += f"\n🏘 *Локально:* {', '.join(sorted(set(places_text)))}"

    elif not active:
        caption += "✅ *Відбій повітряної тривоги*\n"

        if duration:
            caption += f"\n⏱ Тривала: {duration} хвилин"
        else:
            caption += "\nДотримуйтесь загальних правил безпеки, залишайтеся уважними."

    return caption

# ---------- Основной цикл с защитой ----------
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
                caption = format_caption(alerts, active=True)
                send_photo(photo, caption)

                last_alert_start = now_utc
                daily_alerts.append(now_utc)
                last_alerts_active = alerts.copy()
                last_reminder_sent = now_utc
            else:
                dur = None
                if last_alert_start:
                    dur = int((now_utc - last_alert_start).total_seconds() // 60)

                caption = format_caption(alerts=last_alerts_active, active=False, duration=dur)
                send_message(caption)

            last_status = current_status

        # Напоминание каждые 15 минут
        if current_status and last_alert_start:
            if last_reminder_sent is None or (now_utc - last_reminder_sent).total_seconds() >= 15 * 60:
                caption = format_caption(alerts=alerts, active=True)
                send_photo(generate_map(alerts), caption)
                last_reminder_sent = now_utc

        # Ежедневная статистика
        today = (now_utc + timedelta(hours=2)).date()
        if today != last_daily_report:
            count = len(daily_alerts)
            send_message(f"📊 *Статистика повітряних тривог за день:* {count} тривог")
            daily_alerts = []
            last_daily_report = today

    except Exception as e:
        logging.error(f"Ошибка в основном цикле: {e}")
        time.sleep(10)
        continue

    time.sleep(60)
