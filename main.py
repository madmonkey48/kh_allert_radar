import os
import requests
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify, render_template_string
from threading import Thread
import time
import logging

# ---------- Логирование ----------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

logging.info("=== BOT STARTED ===")

# ---------- Flask ----------
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running"

# ---------- HTML карта ----------
MAP_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<title>Air Alerts Map</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css" />
<style>
  body { margin: 0; }
  #map { height: 100vh; }
</style>
</head>
<body>
<div id="map"></div>

<script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
<script>
const map = L.map('map').setView([49.9935, 36.2304], 10);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© OpenStreetMap'
}).addTo(map);

let marker = null;

async function updateAlerts() {
  try {
    const res = await fetch('/api/alerts');
    const data = await res.json();

    if (data.active) {
      if (!marker) {
        marker = L.circle([49.9935, 36.2304], {
          radius: 20000
        }).addTo(map);
      }
    } else {
      if (marker) {
        map.removeLayer(marker);
        marker = null;
      }
    }
  } catch (e) {
    console.error(e);
  }
}

setInterval(updateAlerts, 5000);
updateAlerts();
</script>
</body>
</html>
"""

@app.route('/map')
def map_page():
    return render_template_string(MAP_HTML)

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

# ---------- Telegram ----------

def send_message(text, retries=3):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "MarkdownV2"}

    for _ in range(retries):
        try:
            resp = requests.post(url, data=data, timeout=10)
            if resp.status_code == 200:
                return True
        except Exception as e:
            logging.error(f"Telegram error: {e}")
        time.sleep(5)

    return False

# ---------- Alerts API ----------

def get_alert_status():
    url = "https://api.alerts.in.ua/v1/alerts/active.json"
    headers = {"Authorization": f"Bearer {ALERTS_TOKEN}"}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return []

        data = resp.json()
        regions = data.get("regions", []) if isinstance(data, dict) else data

        alerts = []
        for region in regions:
            if not isinstance(region, dict):
                continue
            if region.get("regionName") != "Харківська область":
                continue

            for a in region.get("activeAlerts", []):
                alerts.append(a)

        return alerts

    except Exception as e:
        logging.error(f"alerts.in.ua error: {e}")
        return []

@app.route('/api/alerts')
def api_alerts():
    alerts = get_alert_status()
    return jsonify({"active": bool(alerts)})

# ---------- Основная логика ----------
last_status = None
last_alert_start = None
last_daily_report = datetime.now(timezone.utc).date()
daily_alerts = []
last_reminder_sent = None


def loop():
    global last_status, last_alert_start, last_daily_report, daily_alerts, last_reminder_sent

    while True:
        try:
            alerts = get_alert_status()
            current_status = bool(alerts)
            now_utc = datetime.now(timezone.utc)

            if last_status is None:
                last_status = current_status

            if current_status != last_status:
                if current_status:
                    send_message("🚨 *Повітряна тривога у Харківській області*")
                    last_alert_start = now_utc
                    daily_alerts.append(now_utc)
                    last_reminder_sent = now_utc
                else:
                    duration = None
                    if last_alert_start:
                        duration = int((now_utc - last_alert_start).total_seconds() // 60)

                    msg = "✅ *Відбій повітряної тривоги*"
                    if duration:
                        msg += f"\n⏱ Тривала: {duration} хв"

                    send_message(msg)

                last_status = current_status

            # Напоминание каждые 15 минут
            if current_status and last_reminder_sent:
                if (now_utc - last_reminder_sent).total_seconds() >= 900:
                    send_message("⏰ *Тривога триває*")
                    last_reminder_sent = now_utc

            # Суточная статистика
            today = (now_utc + timedelta(hours=2)).date()
            if today != last_daily_report:
                send_message(f"📊 *Тривог за день:* {len(daily_alerts)}")
                daily_alerts = []
                last_daily_report = today

        except Exception as e:
            logging.error(f"Main loop error: {e}")
            time.sleep(10)

        time.sleep(60)


Thread(target=loop, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
