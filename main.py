import os
import requests
from PIL import Image, ImageDraw
from io import BytesIO
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import time

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
TOKEN = os.getenv("BOT_TOKEN", "").strip()          # Токен бота
CHAT_ID = os.getenv("CHAT_ID", "").strip()          # ID канала
API_KEY_ALERTS = os.getenv("ALERT_API_KEY", "").strip()  # Ключ API (можно оставить пустым)

# ---------- Основные переменные ----------
last_alert_start = None
last_status = None
daily_alerts = []
last_daily_report = datetime.now().date()
last_alerts_active = []

# ---------- Советы по безопасности ----------
ALERT_ADVICE = {
    "air_raid": "🚨 *Повiтряна тривога* — Знайдіть найближче укриття, закрийте вікна, тримайте телефон поруч для оповіщень.",
    "artillery": "💣 *Артилерійська загроза* — Не перебувайте на відкритих просторах, сховайтеся у будинку, майте під рукою аптечку.",
    "rocket": "🔥 *Ракетна загроза* — Негайно спускайтеся в підвал або захищене приміщення, не підходьте до вікон.",
    "street_fighting": "🛡️ *Вуличні бої* — По можливості уникайте вулиць, залишайтеся вдома, повідомляйте про підозрілі переміщення.",
    "drone": "🛸 *БПЛА* — Не наближайтесь до підозрілих дронів, перебувайте в приміщенні.",
    "default": "⚠️ *Інша загроза* — Дотримуйтесь загальних правил безпеки, слідкуйте за оновленнями від влади."
}

# ---------- Отправка фото ----------
def send_photo(photo_bytes, caption):
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    files = {"photo": photo_bytes}
    data = {"chat_id": CHAT_ID, "caption": caption, "parse_mode": "Markdown"}
    try:
        resp = requests.post(url, files=files, data=data)
        print("Telegram response:", resp.text)
    except Exception as e:
        print("Ошибка при отправке фото:", e)

# ---------- Отправка текста (без карты) ----------
def send_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        resp = requests.post(url, data=data)
        print("Telegram response:", resp.text)
    except Exception as e:
        print("Ошибка при отправке сообщения:", e)

# ---------- Тестовый режим (без API) ----------
def get_alert_status():
    get_alert_status.counter += 1
    if get_alert_status.counter % 5 == 0:
        return [{"type": "air_raid", "places": ["Салтівка", "ХТЗ"]}]
    return []

get_alert_status.counter = 0

# ---------- Координаты районов Харькова ----------
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
        response = requests.get(map_url)
        base_map = Image.open(BytesIO(response.content)).convert("RGBA")
    except Exception as e:
        print("Ошибка при загрузке карты:", e)
        base_map = Image.new("RGBA", (800, 600), (0, 255, 0, 255))

    draw = ImageDraw.Draw(base_map)
    for alert in alerts:
        places = alert.get("places", [])
        for place in places:
            if place in COORDS:
                x, y = COORDS[place]
                draw.ellipse((x-10, y-10, x+10, y+10), fill=(255,0,0,180))
    output = BytesIO()
    base_map.save(output, format="PNG")
    output.seek(0)
    return output

# ---------- Формирование подписи ----------
def format_caption(alerts=None, active=True, duration=None):
    now = datetime.utcnow() + timedelta(hours=2)
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
            types_text += ALERT_ADVICE.get(t, ALERT_ADVICE["default"]) + "\n"
        caption += types_text
        if places_text:
            caption += f"\n🏘 *Локально:* {', '.join(sorted(set(places_text)))}"
    elif not active:
        caption += "✅ *Відбій повітряної тривоги*\n"
        if alerts:
            for alert in alerts:
                t = alert.get("type")
                caption += f"\n{ALERT_ADVICE.get(t, ALERT_ADVICE['default'])}"
        else:
            caption += "\nДотримуйтесь загальних правил безпеки, залишайтеся уважними."
        if duration:
            caption += f"\n⏱ Тривала: {duration} хвилин"

    return caption

# ---------- Основной цикл ----------
while True:
    try:
        alerts = get_alert_status()
        current_status = bool(alerts)

        if last_status is None:
            last_status = current_status

        if current_status != last_status:
            if current_status:
                # Активная тревога — с картой
                photo = generate_map(alerts)
                caption = format_caption(alerts, active=True)
                send_photo(photo, caption)
                last_alert_start = datetime.utcnow() + timedelta(hours=2)
                daily_alerts.append(datetime.utcnow())
                last_alerts_active = alerts.copy()
            else:
                # Отбой — только текст с советами
                dur = None
                if last_alert_start:
                    dur = int((datetime.utcnow() + timedelta(hours=2) - last_alert_start).total_seconds() // 60)
                caption = format_caption(alerts=last_alerts_active, active=False, duration=dur)
                send_message(caption)

            last_status = current_status

        # Ежедневная статистика
        today = (datetime.utcnow() + timedelta(hours=2)).date()
        if today != last_daily_report:
            count = len(daily_alerts)
            send_message(f"📊 *Статистика повітряних тривог за день:* {count} тривог")
            daily_alerts = []
            last_daily_report = today

    except Exception as e:
        print("Ошибка в основном цикле:", e)

    time.sleep(60)
