# === Ukraine regions GeoJSON alert map with daily chart ===

from flask import render_template_string

# Flask app импортируется из main.py
from main import app


# ---------- Map HTML with GeoJSON + chart ----------

MAP_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset='utf-8'/>
<meta name='viewport' content='width=device-width, initial-scale=1.0'>
<title>Ukraine Alerts Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
html, body { margin:0; height:100%; background:#0b0f1a; color:white; }
#map { height:70%; }
#panel { height:30%; padding:10px; background:#111827; }

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
<div id="panel">
  <canvas id="chart"></canvas>
</div>
<div id="siren" class="siren" style="display:none">🚨 AIR RAID ALERT 🚨</div>

<script>
const map = L.map('map').setView([48.5, 31], 6);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© OpenStreetMap'
}).addTo(map);

let geoLayer = null;
let chart = null;

function updateChart(count) {
  const ctx = document.getElementById('chart');

  if (!chart) {
    chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: ['Today'],
        datasets: [{
          label: 'Air raid alerts',
          data: [count]
        }]
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } }
      }
    });
  } else {
    chart.data.datasets[0].data = [count];
    chart.update();
  }
}

async function loadAlerts() {
  const alertsResp = await fetch('/api/alerts');
  const alertsData = await alertsResp.json();

  const geoResp = await fetch('https://raw.githubusercontent.com/alexkulaga/ukraine-geojson/master/regions.geojson');
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
        fillOpacity: active ? 0.6 : 0.2
      };
    },
    onEachFeature: function(feature, layer) {
      layer.bindPopup(feature.properties.name);
    }
  }).addTo(map);

  document.getElementById('siren').style.display =
    alertsData.active.length > 0 ? 'block' : 'none';

  updateChart(alertsData.count_today);
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
