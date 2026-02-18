from flask import Blueprint, render_template_string, jsonify

.leaflet-interactive.alert-active {
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0% { fill-opacity:0.7; }
  50% { fill-opacity:1; }
  100% { fill-opacity:0.7; }
}
</style>
</head>

<body>

<div id="map"></div>
<div id="siren" class="siren" style="display:none">🚨 AIR RAID ALERT 🚨</div>

<script>
const map = L.map('map').setView([48.5, 31], 6);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

let geoLayer = null;

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

      const active = alertsData.active.some(r =>
        name.toLowerCase().includes(r.toLowerCase()) ||
        r.toLowerCase().includes(name.toLowerCase())
      );

      return {
        color: active ? '#ff3b3b' : '#3a4a6a',
        weight: active ? 2 : 1,
        fillColor: active ? '#ff0000' : '#1b2538',
        fillOpacity: active ? 0.8 : 0.2,
        className: active ? 'alert-active' : ''
      };
    }
  }).addTo(map);

  document.getElementById('siren').style.display =
    alertsData.active.length > 0 ? 'block' : 'none';
}

setInterval(loadAlerts, 5000);
loadAlerts();
</script>

</body>
</html>
"""


@map_bp.route("/map")
def map_page():
    return render_template_string(MAP_HTML)
