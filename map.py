# === UPGRADE: Ukraine interactive alert map with animation ===

from flask import Flask, jsonify, render_template_string
import requests, os, threading, time
from datetime import datetime, timezone

app = Flask(__name__)

ALERTS_TOKEN = os.getenv("ALERTS_TOKEN", "")

# ---------- Alerts API ----------

def get_alert_regions():
    try:
        r = requests.get(
            "https://api.alerts.in.ua/v1/alerts/active.json",
            headers={"Authorization": f"Bearer {ALERTS_TOKEN}"},
            timeout=10,
        )
        if r.status_code != 200:
            return []

        data = r.json()
        regions = data.get("regions", []) if isinstance(data, dict) else data

        active = []
        for region in regions:
            if isinstance(region, dict) and region.get("activeAlerts"):
                active.append(region.get("regionName"))

        return active
    except Exception:
        return []


@app.route("/api/alerts")
def api_alerts():
    return jsonify({"active": get_alert_regions(), "time": datetime.now(timezone.utc).isoformat()})


# ---------- Animated map page ----------

MAP_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset='utf-8'/>
<meta name='viewport' content='width=device-width, initial-scale=1.0'>
<title>Ukraine Alerts Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
html, body { margin:0; height:100%; background:#0b0f1a; }
#map { height:100%; }

.pulse {
  background: rgba(255,0,0,0.7);
  border-radius: 50%;
  width: 20px;
  height: 20px;
  position: relative;
}

.pulse::after {
  content: '';
  position: absolute;
  left: -10px; top: -10px;
  width: 40px; height: 40px;
  border-radius: 50%;
  background: rgba(255,0,0,0.4);
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0% { transform: scale(0.5); opacity: 1; }
  100% { transform: scale(1.5); opacity: 0; }
}

.siren {
  position: fixed;
  top: 20px; left: 50%; transform: translateX(-50%);
  color: #ff3b3b;
  font-size: 22px;
  font-weight: bold;
  animation: blink 1s infinite;
}

@keyframes blink {
  0%,100% { opacity:1 }
  50% { opacity:0.2 }
}
</style>
</head>
<body>
<div id="map"></div>
<div id="siren" class="siren" style="display:none">🚨 AIR RAID ALERT 🚨</div>

<script>
const map = L.map('map').setView([48.5, 31], 6);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© OpenStreetMap'
}).addTo(map);

let markers = [];

async function loadAlerts() {
  const r = await fetch('/api/alerts');
  const data = await r.json();

  markers.forEach(m => map.removeLayer(m));
  markers = [];

  if (data.active.length > 0) {
    document.getElementById('siren').style.display = 'block';
  } else {
    document.getElementById('siren').style.display = 'none';
  }

  data.active.forEach(name => {
    const marker = L.marker([48.5 + Math.random(), 31 + Math.random()], {
      icon: L.divIcon({ className: 'pulse' })
    }).addTo(map).bindPopup(name);

    markers.push(marker);
  });
}

setInterval(loadAlerts, 5000);
loadAlerts();
</script>
</body>
</html>
"""


@app.route("/map")
def map_page():
    return render_template_string(MAP_HTML)
