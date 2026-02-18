import os
import re
import json
import asyncio
import logging
import hashlib
from datetime import datetime

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

from telegram_sender import send_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SMART-PARSER] %(levelname)s: %(message)s"
)

# ================= ENV =================

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME", "parser")
SOURCE_CHANNELS = os.getenv("SOURCE_CHANNELS", "").split(",")

STATE_FILE = "parser_state.json"

# ================= STATE =================

if os.path.exists(STATE_FILE):
    with open(STATE_FILE, "r") as f:
        state = json.load(f)
else:
    state = {"ids": {}, "hashes": []}


def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


# ================= SMART REGION =================

KHARKIV_ROOTS = [
    "харків", "харьков",
    "дергач", "чуг", "ізюм", "изюм",
    "купян", "балакл", "вовчан", "волчан",
    "лозов", "зміїв", "змеев",
    "богодух", "красноград", "мереф",
    "пісочин", "песочин", "солониц"
]


def in_kharkiv(text: str) -> bool:
    t = text.lower()

    if "харківськ" in t or "харьковск" in t:
        return True

    return any(root in t for root in KHARKIV_ROOTS)


# ================= THREAT PRIORITY =================

THREATS = [
    ("🚀 ПРИЛІТ РАКЕТИ", [
        r"прил[её]т", r"влучан", r"ракетн(ий|ый) удар"
    ]),

    ("💥 ВЛУЧАННЯ / УДАР", [
        r"попадан", r"пряме влуч"
    ]),

    ("💣 АРТОБСТРІЛ", [
        r"артилер", r"обстрел", r"обстріл"
    ]),

    ("🛸 ПРИЛІТ БПЛА", [
        r"шахед", r"дрон", r"бпл"
    ]),

    ("🛡 ЗБИТО ЦІЛЬ", [
        r"збит", r"сбит", r"ппо знищ"
    ]),

    ("📍 ПАДІННЯ УЛАМКІВ", [
        r"уламк", r"обломк", r"падін"
    ]),

    ("👁 ЦІЛЬ У НЕБІ / РУХ", [
        r"замечен", r"помічено",
        r"в небі", r"над міст", r"над город",
        r"курс на", r"рухаєт", r"движет",
        r"проліта", r"пролет"
    ]),
]


def detect_threat(text: str) -> str:
    t = text.lower()

    for title, patterns in THREATS:
        for p in patterns:
            if re.search(p, t):
                return title

    return "⚠️ ОПЕРАТИВНЕ ПОВІДОМЛЕННЯ"


# ================= LOCATION =================

def extract_location(text: str) -> str:
    lines = text.split("\n")

    for line in lines:
        if in_kharkiv(line):
            return line.strip()

    return "Харківська область"


# ================= DUPLICATES =================

def text_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def is_duplicate(channel_id: str, msg_id: str, text: str) -> bool:
    if channel_id in state["ids"] and msg_id in state["ids"][channel_id]:
        return True

    h = text_hash(text)
    if h in state["hashes"]:
        return True

    return False


def save_processed(channel_id: str, msg_id: str, text: str):
    state["ids"].setdefault(channel_id, []).append(msg_id)
    state["hashes"].append(text_hash(text))

    state["ids"][channel_id] = state["ids"][channel_id][-200:]
    state["hashes"] = state["hashes"][-200:]

    save_state()


# ================= FORMAT =================

def format_msg(threat: str, location: str, original: str) -> str:
    now = datetime.utcnow().strftime("%H:%M")

    return f"""
━━━━━━━━━━━━━━
{threat}

📍 {location}
🕒 {now}

━━━━━━━━━━━━━━
{original[:400]}
""".strip()


# ================= TELETHON =================

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)


@client.on(events.NewMessage(chats=SOURCE_CHANNELS))
async def handler(event):
    try:
        text = event.raw_text
        if not text:
            return

        if not in_kharkiv(text):
            return

        cid = str(event.chat_id)
        mid = str(event.id)

        if is_duplicate(cid, mid, text):
            return

        threat = detect_threat(text)
        location = extract_location(text)

        send_message(format_msg(threat, location, text))
        save_processed(cid, mid, text)

        logging.info(f"SENT: {threat}")

    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)

    except Exception as e:
        logging.error(f"Handler error: {e}")


# ================= MAIN LOOP =================

async def main():
    while True:
        try:
            logging.info("Connecting to Telegram...")
            await client.start()
            logging.info("SMART parser started")
            await client.run_until_disconnected()

        except Exception as e:
            logging.error(f"Reconnect error: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
