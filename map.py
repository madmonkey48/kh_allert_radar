# === FINAL: Ukraine animated alert map ===

from flask import render_template_string, jsonify
import requests, os
from datetime import datetime, timezone

# импорт Flask-приложения из main.py
from main import app

ALERTS_TOKEN = os.getenv("ALERTS_TOKEN", "")


# ---------- Получение активных областей ----------
def get_active_regions():
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


# ---------- API для карты (ОТДЕЛЬНЫЙ путь!) ----------
@app.route("/api/map/alerts")
def api_map_alerts():
    return jsonify({
        "active": get_active_regions(),
        "time": datetime.now(timezone.utc).isoformat()
    })


# ---------- HTML карты ----------
MAP_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset='utf-8'/>
<meta name='viewport' content='width=device-width, initial-scale=1.0'>
<title>Ukraine Air Alerts</title>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<style>
html, body {
  margin:0;
  height:100%;
  background:#0b0f1a;
  color:white;
}

#map { height:100%; }

/* Сирена */
.siren {
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  color: #ff3b3b;
  font-size: 24px;
  font-weight: bold;
  animation: blink 1s infinite;
}

@keyframes blink {
  0%,100% { opacity:1 }
  50% { opacity:0.2 }
}

/* Пульсация области */
.leaflet-interactive.alert-active {
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%   { fill-opacity: 0.7; }
  50%  { fill-opacity: 1; }
  100% { fill-opacity: 0.7; }
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

let geoLayer = null;


// ---------- Загрузка тревог ----------
async function loadAlerts() {
  const alertsResp = await fetch('/api/map/alerts');
  const alertsData = await alertsResp.json();

  const geoResp = await fetch(
    'https://raw.githubusercontent.com/alexkulaga/ukraine-geojson/master/regions.geojson'
  );
  const geo = await geoResp.json();

  if (geoLayer) map.removeLayer(geoLayer);

  geoLayer = L.geoJSON(geo, {
    style: function(feature) {
      const name = feature.properties.name;
      const active = alertsData.active.includes(name);

      return {
        color: active ? '#ff3b3b' : '#3a4a6a',
        weight: active ? 2 : 1,
        fillColor: active ? '#ff0000' : '#1b2538',
        fillOpacity: active ? 0.8 : 0.2,
        className: active ? 'alert-active' : ''
      };
    },
    onEachFeature: function(feature, layer) {
      layer.bindPopup(feature.properties.name);
    }
  }).addTo(map);

  // сирена сверху
  document.getElementById('siren').style.display =
    alertsData.active.length > 0 ? 'block' : 'none';
}


// обновление каждые 5 секунд
setInterval(loadAlerts, 5000);
loadAlerts();
</script>

</body>
</html>
"""


# ---------- Страница карты ----------
@app.route("/map")
def map_page():
    return render_template_string(MAP_HTML)
