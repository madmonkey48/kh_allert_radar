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
TOKEN = os.getenv("BOT_TOKEN", "").strip()       # Токен бота
CHAT_ID = os.getenv("CHAT_ID", "").strip()       # ID канала
API_KEY_ALERTS = os.getenv("ALERT_API_KEY", "").strip()  # Пока можно оставить пустым

print("TOKEN CHECK:", repr(TOKEN))
print("CHAT_ID CHECK:", repr(CHAT_ID))
print("✅ Переменные окружения загружены")

# ---------- Основные переменные ----------
last_alert_start = None

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

# ---------- Тестовый режим (без API) ----------
def get_alert_status():
    get_alert_status.counter += 1
    # Каждые 5 минут "тревога" с локальными районами
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
        base_map = Image.new("RGBA", (800, 600), (0, 255, 0, 255))  # зелёный фон

    draw = ImageDraw.Draw(base_map)
    for alert in alerts:
        places = alert.get("places", [])
        for place in places:
            if place in COORDS:
                x, y = COORDS[place]
                draw.ellipse((x-10, y-10, x+10, y+10), fill=(255,0,0,180))  # красная точка

    output = BytesIO()
    base_map.save(output, format="PNG")
    output.seek(0)
    return output

# ---------- Формирование подписи ----------
def format_caption(alerts):
    now = datetime.utcnow() + timedelta(hours=2)
    now_str = now.strftime("%H:%M")
    types_text = ""
    places_text = []

    for alert in alerts:
        t = alert.get("type")
        places = alert.get("places", [])
        if places:
            places_text.extend(places)

        if t == "air_raid":
            types_text += "🚨 *Повiтряна тривога! - активность боевых петухов*\n"
        elif t == "artillery":
            types_text += "💣 *Возможны вылеты петушиной артиллерии*\n"
        elif t == "rocket":
            types_text += "🔥 *Ракетная опасность*\n"
        elif t == "street_fighting":
            types_text += "🛡️ *Вуличні бої*\n"
        elif t == "drone":
            types_text += "🛸 *БПЛА АНАЛоговНет в небе*\n"
        else:
            types_text += f"⚠️ *Інша загроза*: {t}\n"

    caption = f"📍 *Харківська область*\n🕒 {now_str}\n\n{types_text}"
    if places_text:
        caption += f"\n🏘 *Локально:* {', '.join(sorted(set(places_text)))}"
    return caption

# ---------- Основной цикл ----------
while True:
    alerts = get_alert_status()
    if alerts:
        photo = generate_map(alerts)
        caption = format_caption(alerts)
        send_photo(photo, caption)
        last_alert_start = datetime.utcnow() + timedelta(hours=2)
    else:
        print("Нет активных тревог")
    time.sleep(60)
