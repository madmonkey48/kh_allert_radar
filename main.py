import os
import requests
from datetime import datetime
from flask import Flask, jsonify
from threading import Thread
import time
import logging
from zoneinfo import ZoneInfo

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


KYIV_TZ = ZoneInfo("Europe/Kyiv")


# -------------------------------------------------
# Типы тревог
# -------------------------------------------------

ALERT_TYPES = {
    "air_raid": ("🚨", "ПОВІТРЯНА ТРИВОГА"),
    "rocket": ("🚀", "РАКЕТНА ЗАГРОЗА"),
    "drone": ("🛸", "ЗАГРОЗА БПЛА"),
    "artillery_shelling": ("💣", "АРТИЛЕРІЙСЬКИЙ ОБСТРІЛ"),
    "urban_fights": ("🛡", "ВУЛИЧНІ БОЇ"),
    "default": ("⚠️", "НЕБЕЗПЕКА"),
}


START_MESSAGES = {
    "air_raid": "🛡 <b>Зафіксовано повітряну небезпеку.</b>\nНегайно прямуйте в укриття.",
    "rocket": "🚀 <b>Існує ризик ракетного удару.</b>\nЧас реагування мінімальний — терміново в укриття.",
    "drone": "🛸 <b>Зафіксовано активність ударних БПЛА.</b>\nПеребувайте в укритті та обмежте світло.",
    "artillery_shelling": "💣 <b>Фіксується артилерійська активність.</b>\nПеребувайте в укритті та тримайтесь подалі від вікон.",
    "urban_fights": "🛡 <b>Повідомляється про бойові дії в межах населених пунктів.</b>\nУникайте пересування.",
    "default": "⚠️ <b>Зафіксовано небезпеку.</b>\nСлідкуйте за офіційними повідомленнями."
}


END_MESSAGES = {
    "air_raid": "🛡 Загроза повітряної атаки минула.",
    "rocket": "🚀 Ракетна загроза більше не актуальна.",
    "drone": "🛸 Активність БПЛА не фіксується.",
    "artillery_shelling": "💣 Артилерійський обстріл припинено.",
    "urban_fights": "🛡 Активні бойові дії завершено.",
    "default": "ℹ️ Загроза більше не активна."
}


# -------------------------------------------------
# PRO состояние
# -------------------------------------------------

current_alert_type = None
current_locations_hash = None
alert_session_active = False
last_alert_start = None
last_reminder_sent = None

RESTART_GRACE_PERIOD = 300
MIN_ALERT_DURATION = 60

last_daily_report = datetime.now(KYIV_TZ).date()
daily_alerts_count = 0
daily_duration_total = 0
daily_types = {k: 0 for k in ALERT_TYPES.keys()}


# -------------------------------------------------
# ЗАЩИЩЁННАЯ отправка в Telegram
# -------------------------------------------------

def send_message(text, retries=5):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}

    delay = 2

    for attempt in range(retries):
        try:
            r = requests.post(url, data=data, timeout=10)

            if r.status_code == 200:
                logging.info("Telegram message sent")
                return True

            # Flood control / сервер Telegram
            if r.status_code in (429, 500, 502, 503, 504):
                logging.warning(f"Telegram retry {attempt+1}: {r.status_code}")
                time.sleep(delay)
                delay *= 2
                continue

            logging.error(f"Telegram status: {r.status_code} | {r.text}")
            return False

        except requests.exceptions.RequestException as e:
            logging.error(f"Telegram connection error: {e}")
            time.sleep(delay)
            delay *= 2

    logging.error("Telegram send failed after retries")
    return False


# -------------------------------------------------
# Alerts API
# -------------------------------------------------

def get_alerts_struct():
    try:
        r = requests.get(
            "https://api.alerts.in.ua/v1/alerts/active.json",
            headers={"Authorization": f"Bearer {ALERTS_TOKEN}"},
            timeout=10,
        )

        if r.status_code != 200:
            return None

        data = r.json()
        alerts = data.get("alerts", [])

        result = {"types": [], "cities": set(), "raions": set(), "oblast": False}

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


def get_locations_hash(info):
    combined = list(info["cities"]) + list(info["raions"])
    combined.sort()
    return "|".join(combined)


# -------------------------------------------------
# Сообщения
# -------------------------------------------------

def build_start_message(info):
    alert_type = info["types"][0] if info["types"] else "default"
    emoji, title = ALERT_TYPES.get(alert_type, ALERT_TYPES["default"])
    time_now = datetime.now(KYIV_TZ).strftime("%H:%M")

    if info["oblast"]:
        location_block = "📍 <b>Харківська область</b>"
    elif info["raions"]:
        location_block = "📍 <b>Райони:</b>\n" + "\n".join(f"• {r}" for r in sorted(info["raions"]))
    elif info["cities"]:
        location_block = "📍 <b>Населені пункти:</b>\n" + "\n".join(f"• {c}" for c in sorted(info["cities"]))
    else:
        location_block = "📍 <b>Харківська область</b>"

    body = START_MESSAGES.get(alert_type, START_MESSAGES["default"])

    return (
        f"{emoji} <b>{title}</b>\n\n"
        f"{location_block}\n\n"
        f"🕒 <code>{time_now}</code>\n"
        f"━━━━━━━━━━━━\n"
        f"{body}"
    )


def build_end_message(duration_min):
    global current_alert_type

    time_now = datetime.now(KYIV_TZ).strftime("%H:%M")
    alert_type = current_alert_type or "default"
    extra = END_MESSAGES.get(alert_type, END_MESSAGES["default"])

    msg = (
        "✅ <b>ВІДБІЙ ТРИВОГИ</b>\n\n"
        f"🕒 <code>{time_now}</code>"
    )

    if duration_min:
        msg += f"\n⏱ <b>Тривалість:</b> {duration_min} хв"

    msg += f"\n\n{extra}"
    return msg


# -------------------------------------------------
# Основной цикл
# -------------------------------------------------

def loop():
    global alert_session_active, current_alert_type, current_locations_hash
    global last_alert_start, last_reminder_sent
    global daily_alerts_count, daily_duration_total, daily_types

    while True:
        try:
            info = get_alerts_struct()
            current_status = bool(info and info["types"])
            now = datetime.now(KYIV_TZ)

            locations_hash = get_locations_hash(info) if info else None
            new_type = info["types"][0] if info and info["types"] else None

            if current_status:

                if alert_session_active:

                    if new_type != current_alert_type or locations_hash != current_locations_hash:
                        send_message(
                            f"🔄 <b>ОНОВЛЕННЯ ЗАГРОЗИ</b>\n"
                            f"{ALERT_TYPES.get(new_type, ALERT_TYPES['default'])[0]} "
                            f"<b>{ALERT_TYPES.get(new_type, ALERT_TYPES['default'])[1]}</b>"
                        )
                        current_alert_type = new_type
                        current_locations_hash = locations_hash

                else:
                    alert_session_active = True
                    current_alert_type = new_type
                    current_locations_hash = locations_hash
                    last_alert_start = now
                    last_reminder_sent = now

                    send_message(build_start_message(info))

                    daily_alerts_count += 1
                    for t in info["types"]:
                        daily_types[t] += 1

            else:
                if alert_session_active and last_alert_start:
                    duration_sec = (now - last_alert_start).total_seconds()

                    if duration_sec >= MIN_ALERT_DURATION:
                        duration = int(duration_sec // 60)
                        daily_duration_total += duration
                        send_message(build_end_message(duration))

                        alert_session_active = False
                        current_alert_type = None
                        current_locations_hash = None

            if alert_session_active and last_reminder_sent:
                if (now - last_reminder_sent).total_seconds() >= 900:
                    send_message("⏰ <b>ТРИВОГА ТРИВАЄ</b>\nБудьте в укритті.")
                    last_reminder_sent = now

        except Exception as e:
            logging.error(f"Main loop error: {e}")
            time.sleep(10)

        time.sleep(3)


Thread(target=loop, daemon=True).start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
