from flask import render_template_string
from main import app

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
const map = L.map('map').setView([49.99, 36.23], 9);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© OpenStreetMap'
}).addTo(map);

let circle = null;

async function loadAlerts() {
  const r = await fetch('/api/alerts');
  const data = await r.json();

  if (data.active) {
    document.getElementById('siren').style.display = 'block';

    if (!circle) {
      circle = L.circle([49.99, 36.23], { radius: 20000, color: 'red' }).addTo(map);
    }
  } else {
    document.getElementById('siren').style.display = 'none';

    if (circle) {
      map.removeLayer(circle);
      circle = null;
    }
  }
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
