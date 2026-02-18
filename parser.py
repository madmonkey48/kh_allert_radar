import os
import re
import asyncio
import logging
from datetime import datetime

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, RPCError

from telegram_sender import send_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [PARSER] %(levelname)s: %(message)s"
)

# ==============================
# ENV ПЕРЕМЕННЫЕ
# ==============================

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME", "parser")

# Каналы для парсинга (через запятую в Railway)
SOURCE_CHANNELS = os.getenv("SOURCE_CHANNELS", "").split(",")

# ==============================
# ФИЛЬТР РЕГИОНА
# ==============================

TARGET_KEYWORDS = [
    "харків", "харьков",
    "ізюм", "изюм",
    "куп'янськ", "купянск",
    "чуг", "балаклія", "балаклея",
    "вовчанськ", "волчанск",
]

# ==============================
# АНАЛИТИКА УГРОЗ
# ==============================

THREAT_PATTERNS = {
    "🚀 ПРИЛІТ РАКЕТИ": [
        r"прил[её]т",
        r"влучан",
        r"удар ракет",
        r"попадан",
    ],
    "🛸 ПРИЛІТ БПЛА": [
        r"прил[её]т.*бпл",
        r"шахед",
        r"дрон.*влуч",
    ],
    "💥 ВИБУХ": [
        r"вибух",
        r"взрыв",
    ],
    "🛡 ЗБИТО": [
        r"збит",
        r"сбит",
        r"ппо знищ",
    ],
    "📍 ПАДІННЯ УЛАМКІВ": [
        r"падін",
        r"падение обломк",
    ],
    "💣 АРТИЛЕРІЙСЬКИЙ ОБСТРІЛ": [
        r"артилер",
        r"обстр",
    ],
    "✈️ КАБ / АВІАУДАР": [
        r"каб",
        r"авіаудар",
        r"авиаудар",
    ],
}

# ==============================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================

def contains_target_region(text: str) -> bool:
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in TARGET_KEYWORDS)


def detect_threat_type(text: str) -> str:
    text_lower = text.lower()

    for threat, patterns in THREAT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return threat

    return "⚠️ ОПЕРАТИВНЕ ПОВІДОМЛЕННЯ"


def extract_location_line(text: str) -> str:
    lines = text.split("\n")
    for line in lines:
        if any(word in line.lower() for word in TARGET_KEYWORDS):
            return line.strip()
    return ""


def format_alert_message(threat: str, location: str, original_text: str) -> str:
    now = datetime.utcnow().strftime("%H:%M")

    message = f"""
━━━━━━━━━━━━━━
{threat}

📍 {location if location else "Харківська область"}

🕒 {now}

━━━━━━━━━━━━━━
{original_text[:300]}
"""

    return message.strip()


# ==============================
# TELETHON ЛОГИКА
# ==============================

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

processed_ids = set()


@client.on(events.NewMessage(chats=SOURCE_CHANNELS))
async def handler(event):
    try:
        if event.id in processed_ids:
            return

        text = event.raw_text
        if not text:
            return

        if not contains_target_region(text):
            return

        threat = detect_threat_type(text)
        location = extract_location_line(text)

        formatted = format_alert_message(threat, location, text)

        send_message(formatted)

        processed_ids.add(event.id)

        logging.info(f"Sent alert: {threat}")

    except FloodWaitError as e:
        logging.warning(f"Flood wait: {e.seconds}")
        await asyncio.sleep(e.seconds)

    except RPCError as e:
        logging.error(f"Telegram RPC error: {e}")

    except Exception as e:
        logging.error(f"Unexpected error: {e}")


async def main():
    while True:
        try:
            logging.info("Connecting to Telegram...")
            await client.start()
            logging.info("Parser connected")
            await client.run_until_disconnected()

        except Exception as e:
            logging.error(f"Connection error: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
