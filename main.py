import os
import requests
from datetime import datetime
from flask import Flask, jsonify
from threading import Thread
import time
import logging
from zoneinfo import ZoneInfo

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
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

KYIV_TZ = ZoneInfo("Europe/Kyiv")

# -------------------------------------------------
# Типы тревог
# -------------------------------------------------

ALERT_TYPES = {
    "air_raid": ("🚨", "повітряної тривоги"),
    "rocket": ("🚀", "ракетної загрози"),
    "drone": ("🛸", "небезпеки БПЛА"),
    "artillery_shelling": ("💣", "артилерійського обстрілу"),
    "urban_fights": ("🛡", "бойових дій"),
    "default": ("⚠️", "небезпеки"),
}

START_MESSAGES = {
    "air_raid": "🛡 <b>Повітряна тривога!</b>\nНегайно прямуйте в укриття.",
    "rocket": "🚀 <b>Ракетна загроза!</b>\nЧас реагування мінімальний — терміново в укриття.",
    "drone": "🛸 <b>Загроза БПЛА!</b>\nПеребувайте в укритті та обмежте світло.",
    "artillery_shelling": "💣 <b>Артилерійський обстріл!</b>\nПеребувайте подалі від вікон.",
    "urban_fights": "🛡 <b>Бойові дії!</b>\nУникайте пересування.",
    "default": "⚠️ <b>Небезпека!</b>\nСлідкуйте за офіційними повідомленнями.",
}

END_MESSAGES = {
    "air_raid": "Можна залишити укриття.",
    "rocket": "Ракетну загрозу скасовано.",
    "drone": "Небезпеку БПЛА знято.",
    "artillery_shelling": "Обстріли припинились.",
    "urban_fights": "Ситуація стабілізувалась.",
    "default": "Загрозу скасовано.",
}

# -------------------------------------------------
# Telegram защита
# -------------------------------------------------

def send_message(text, retries=5):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}

    delay = 2

    for attempt in range(retries):
        try:
            r = requests.post(url, data=data, timeout=10)

            if r.status_code == 200:
                return True

            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(delay)
                delay *= 2
                continue

            logging.error(f"Telegram error: {r.status_code} | {r.text}")
            return False

        except Exception as e:
            logging.error(f"Telegram connection error: {e}")
            time.sleep(delay)
            delay *= 2

    return False


# -------------------------------------------------
# API
# -------------------------------------------------

def get_alerts_struct():
    try:
        r = requests.get(
            "https://api.alerts.in.ua/v1/alerts/active.json",
            headers={"Authorization": f"Bearer {ALERTS_TOKEN}"},
            timeout=10,
        )

        if r.status_code != 200:
            return {}

        data = r.json()
        alerts = data.get("alerts", [])

        result = {}

        for a in alerts:
            if "харків" not in a.get("location_oblast", "").lower():
                continue

            if a.get("location_type") == "raion":
                result[a["location_title"]] = a.get("alert_type", "air_raid")

        return result

    except Exception as e:
        logging.error(f"alerts.in.ua error: {e}")
        return {}


# -------------------------------------------------
# Формирование сообщений
# -------------------------------------------------

def build_start_message(alert_type, raions):
    emoji, _ = ALERT_TYPES.get(alert_type, ALERT_TYPES["default"])
    body = START_MESSAGES.get(alert_type, START_MESSAGES["default"])
    time_now = datetime.now(KYIV_TZ).strftime("%H:%M")

    location_block = "📍 <b>Райони:</b>\n" + "\n".join(f"• {r}" for r in sorted(raions))

    return (
        f"{emoji} {body}\n\n"
        f"{location_block}\n\n"
        f"🕒 <code>{time_now}</code>"
    )


def build_full_end_message(duration_min, alert_type):
    time_now = datetime.now(KYIV_TZ).strftime("%H:%M")
    extra = END_MESSAGES.get(alert_type, END_MESSAGES["default"])

    msg = f"✅ <b>ВІДБІЙ ТРИВОГИ</b>\n\n🕒 <code>{time_now}</code>"
    if duration_min:
        msg += f"\n⏱ <b>Тривалість:</b> {duration_min} хв"
    msg += f"\n\n{extra}"
    return msg


def build_partial_end_message(raion, alert_type):
    time_now = datetime.now(KYIV_TZ).strftime("%H:%M")
    emoji, text_type = ALERT_TYPES.get(alert_type, ALERT_TYPES["default"])
    return f"<code>{time_now}</code>, {raion} — {emoji} <b>відбій {text_type}!</b>"


# -------------------------------------------------
# Состояние
# -------------------------------------------------

active_raions = {}
alert_session_active = False
last_alert_start = None
last_reminder = None
current_alert_type = "default"


# -------------------------------------------------
# Основной цикл (без флуда)
# -------------------------------------------------

def loop():
    global active_raions, alert_session_active
    global last_alert_start, last_reminder, current_alert_type

    while True:
        try:
            new_raions = get_alerts_struct()
            now = datetime.now(KYIV_TZ)

            # ---- ЧАСТИЧНЫЕ ОТБОИ ----
            ended = set(active_raions.keys()) - set(new_raions.keys())
            for raion in sorted(ended):
                send_message(build_partial_end_message(raion, active_raions[raion]))

            # ---- СТАРТ ----
            if not alert_session_active and new_raions:
                alert_session_active = True
                last_alert_start = now
                last_reminder = now

                # берём самый опасный тип (первый)
                current_alert_type = list(new_raions.values())[0]
                send_message(build_start_message(current_alert_type, new_raions.keys()))

            # ---- ПОЛНЫЙ ОТБОЙ ----
            if alert_session_active and not new_raions:
                duration = int((now - last_alert_start).total_seconds() // 60) if last_alert_start else 0
                send_message(build_full_end_message(duration, current_alert_type))

                alert_session_active = False
                current_alert_type = "default"

            # ---- НАПОМИНАНИЕ 15 мин ----
            if alert_session_active and last_reminder:
                if (now - last_reminder).total_seconds() >= 900:
                    send_message("⏰ <b>ТРИВОГА ТРИВАЄ</b>\nЗалишайтесь в укритті.")
                    last_reminder = now

            active_raions = new_raions

        except Exception as e:
            logging.error(f"Main loop error: {e}")
            time.sleep(10)

        time.sleep(5)


Thread(target=loop, daemon=True).start()


@app.route("/api/alerts")
def api_alerts():
    return jsonify({"active": bool(active_raions)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
