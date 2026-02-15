import os
import requests
from PIL import Image, ImageDraw
from io import BytesIO
from datetime import datetime, timedelta, timezone
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
TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()
API_KEY_ALERTS = os.getenv("ALERT_API_KEY", "").strip()

print("TOKEN CHECK:", repr(TOKEN))
print("CHAT_ID CHECK:", repr(CHAT_ID))

if not TOKEN or not CHAT_ID:
    print("❌ ERROR: BOT_TOKEN или CHAT_ID не заданы!")
else:
    print("✅ Переменные окружения загружены")

# ---------- Основные переменные ----------
last_alert_start = None

# ---------- Отправка фото ----------
def send_photo(photo_bytes, caption):
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    files = {"photo": photo_bytes}
    data = {
        "chat_id": CHAT_ID,
        "caption": caption,
        "parse_mode": "Markdown"
    }

    try:
        resp = requests.post(url, files=files, data=data)
        print("Telegram response:", resp.text)
    except Exception as e:
        print("Ошибка при отправке фото:", e)

# ---------- Тестовый режим (без API) ----------
def get_alert_status():
    get_alert_status.counter += 1

    # каждые 5 минут будет тревога
    if get_alert_status.counter % 5 == 0:
        return [{
            "type": "air_raid",
            "places": ["Салтівка", "ХТЗ"]
        }]

    return []

get_alert_status.counter = 0

# ---------- Координаты районов ----------
COORDS = {
    "Салтівка": (500, 200),
    "ХТЗ": (600, 400),
    "Центр": (400, 300),
    "Олексіївка": (480, 220)
}

# ---------- Генерация карты ----------
def generate_map(alerts):
    map_url = "https://raid.fly.dev/map.png"

    try:
        response = requests.get(map_url)
        base_map = Image.open(BytesIO(response.content)).convert("RGBA")
    except:
        print("⚠ Не удалось загрузить карту, создаю фон")
        base_map = Image.new("RGBA", (800, 600), (0, 255, 0, 255))

    draw = ImageDraw.Draw(base_map)

    for alert in alerts:
        for place in alert.get("places", []):
            if place in COORDS:
                x, y = COORDS[place]
                draw.ellipse((x-12, y-12, x+12, y+12),
                             fill=(255, 0, 0, 200))

    output = BytesIO()
    base_map.save(output, format="PNG")
    output.seek(0)
    return output

# ---------- Формирование подписи ----------
def format_caption(alerts):
    # корректное время UTC+2
    now = datetime.now(timezone.utc) + timedelta(hours=2)
    now_str = now.strftime("%H:%M")

    text = "🚨 *Повітряна тривога*\n\n"
    text += f"📍 *Харківська область*\n"
    text += f"🕒 {now_str}\n\n"

    places = []
    for alert in alerts:
        places.extend(alert.get("places", []))

    if places:
        text += f"🏘 *Локально:* {', '.join(sorted(set(places)))}"

    return text

# ---------- Основной цикл ----------
while True:
    alerts = get_alert_status()

    if alerts:
        print("🚨 ТЕСТОВА ТРИВОГА")
        photo = generate_map(alerts)
        caption = format_caption(alerts)
        send_photo(photo, caption)
        last_alert_start = datetime.now(timezone.utc) + timedelta(hours=2)
    else:
        print("Нет активных тревог")

    time.sleep(60)
