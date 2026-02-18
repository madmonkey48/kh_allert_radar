import asyncio
import re
import time
import logging
from datetime import datetime, timedelta

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from main import send_message  # используем твою функцию отправки

# ================== НАСТРОЙКИ ==================

API_ID = 123456          # <-- вставь
API_HASH = "YOUR_HASH"   # <-- вставь
SESSION = "radar_session"

CHANNELS = [
    "cxidua",
    "tlknewsua",
    "radar_kharkov",
]

# антиспам
DUPLICATE_TIMEOUT = 300        # 5 минут
PRIORITY_RESET_TIME = 20 * 60  # сброс приоритета через 20 минут

# ================== ЛОГИ ==================

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ================== ПРИОРИТЕТЫ УГРОЗ ==================

THREAT_PRIORITY = {
    "rocket": 5,
    "missile": 5,
    "iskander": 5,
    "kalibr": 5,

    "aviation": 4,
    "mig": 4,
    "tu": 4,

    "drone": 3,
    "shahed": 3,
    "uav": 3,

    "explosion": 2,
    "arrival": 2,

    "other": 1,
}

last_priority_sent = 0
last_priority_time = 0

# ================== КЛЮЧЕВЫЕ СЛОВА ==================

THREAT_KEYWORDS = {
    "rocket": ["ракета", "missile", "калібр", "искандер"],
    "drone": ["бпла", "дрон", "shahed", "шахед"],
    "aviation": ["авіація", "авиация", "миг", "ту-"],
    "explosion": ["вибух", "взрыв", "приліт", "прилет"],
}

DISTRICTS = [
    "центр",
    "салтівка",
    "павлове поле",
    "олексіївка",
    "хтз",
    "нові будинки",
]

DIRECTIONS = [
    "з півночі",
    "з півдня",
    "зі сходу",
    "з заходу",
]

# ================== АНТИДУБЛИКАТ ==================

recent_messages = {}


def is_duplicate(text: str) -> bool:
    now = time.time()

    for msg, t in list(recent_messages.items()):
        if now - t > DUPLICATE_TIMEOUT:
            del recent_messages[msg]

    if text in recent_messages:
        return True

    recent_messages[text] = now
    return False


# ================== ОПРЕДЕЛЕНИЕ УГРОЗЫ ==================

def detect_threat(text: str) -> str:
    t = text.lower()

    for threat, words in THREAT_KEYWORDS.items():
        for w in words:
            if w in t:
                return threat

    return "other"


def detect_district(text: str) -> str | None:
    t = text.lower()
    for d in DISTRICTS:
        if d in t:
            return d.title()
    return None


def detect_direction(text: str) -> str | None:
    t = text.lower()
    for d in DIRECTIONS:
        if d in t:
            return d
    return None


# ================== ПРИОРИТЕТ ==================

def get_priority(threat: str) -> int:
    return THREAT_PRIORITY.get(threat, 1)


def should_send(priority: int) -> bool:
    global last_priority_sent, last_priority_time

    now = time.time()

    # сброс приоритета через время
    if now - last_priority_time > PRIORITY_RESET_TIME:
        last_priority_sent = 0

    if priority >= last_priority_sent:
        last_priority_sent = priority
        last_priority_time = now
        return True

    return False


# ================== ФОРМИРОВАНИЕ СООБЩЕНИЯ ==================

EMOJI = {
    "rocket": "🚀",
    "drone": "🛸",
    "aviation": "✈️",
    "explosion": "💥",
    "other": "⚠️",
}


def build_message(threat: str, district: str | None, direction: str | None) -> str:
    emoji = EMOJI.get(threat, "⚠️")
    time_now = datetime.now().strftime("%H:%M")

    msg = f"{emoji} *ЗАГРОЗА*\n"
    msg += f"📍 Харків\n"
    msg += f"🕒 {time_now}\n\n"

    if district:
        msg += f"🏙 Район: *{district}*\n"

    if direction:
        msg += f"🧭 Напрямок: *{direction}*\n"

    msg += "\n➡️ *Перебувайте в укриттях*"

    return msg


# ================== TELEGRAM CLIENT ==================

client = TelegramClient(SESSION, API_ID, API_HASH)


@client.on(events.NewMessage(chats=CHANNELS))
async def handler(event):
    text = event.raw_text

    if not text:
        return

    if is_duplicate(text):
        return

    threat = detect_threat(text)
    priority = get_priority(threat)

    if not should_send(priority):
        return

    district = detect_district(text)
    direction = detect_direction(text)

    message = build_message(threat, district, direction)

    logging.info(f"SEND → {message.replace(chr(10), ' ')}")

    send_message(message)


# ================== ЗАПУСК ==================

async def main():
    await client.start()
    logging.info("Parser started")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
