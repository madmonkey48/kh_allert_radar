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
</style>
</head>
<body>
<div id="map"></div>

<script>
const map = L.map('map').setView([48.5, 31], 6);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© OpenStreetMap'
}).addTo(map);
</script>
</body>
</html>
"""


@app.route("/map")
def map_page():
    return render_template_string(MAP_HTML)
