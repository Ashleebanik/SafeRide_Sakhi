"""
Google Maps component for Streamlit – replaces Folium.
Uses @googlemaps/js-api-loader (the official Google Maps JS API loader)
and the same API that @vis.gl/react-google-maps wraps, rendered via
streamlit.components.v1.html so no npm build step is needed.

Features:
  - Polylines per trip, colour-coded by severity
  - Start circle marker + home marker at end
  - InfoWindow on click: trip ID, scenario, state
  - Satellite / roadmap toggle
  - Falls back to a clear "add your API key" message when key is absent
"""
from __future__ import annotations

import json
from typing import Any

import streamlit.components.v1 as components

RISK_HEX = {1: "#22c55e", 2: "#f59e0b", 3: "#ef4444", 4: "#7c3aed"}


def _trip_to_js_obj(result: dict[str, Any]) -> str:
    """Serialise one pipeline result to a JS object literal."""
    trip  = result.get("_trip", {})
    pings = trip.get("pings", [])
    sev   = int(result.get("severity", 1))
    color = RISK_HEX.get(sev, "#22c55e")
    tid   = str(result.get("trip_id", ""))[:8]
    state = result.get("final_state", "unknown")
    scenario = result.get("scenario", "")

    path = json.dumps([{"lat": p["lat"], "lng": p["lon"]} for p in pings])

    start = json.dumps({"lat": pings[0]["lat"],  "lng": pings[0]["lon"]}) if pings else "null"
    end   = json.dumps({"lat": pings[-1]["lat"], "lng": pings[-1]["lon"]}) if pings else "null"

    return (
        f'{{"path":{path},"color":"{color}","severity":{sev},'
        f'"tid":"{tid}","state":"{state}","scenario":"{scenario}",'
        f'"start":{start},"end":{end}}}'
    )


def render_google_map(
    results: list[dict[str, Any]],
    api_key: str,
    height: int = 480,
) -> None:
    """
    Render an interactive Google Maps view inside the Streamlit app.
    `results` is the list of pipeline result dicts held in session_state.
    `api_key` is GOOGLE_MAPS_API_KEY from config / .env.
    """
    trips_js = "[" + ",".join(_trip_to_js_obj(r) for r in results if r.get("_trip", {}).get("pings")) + "]"

    # Centre on Bangalore
    center_lat, center_lng = 12.9716, 77.5946

    no_key_banner = "" if api_key else """
      <div style="position:absolute;top:8px;left:50%;transform:translateX(-50%);
           background:#fef2f2;border:1px solid #fca5a5;border-radius:6px;
           padding:8px 16px;font-size:13px;color:#991b1b;z-index:10;">
        ⚠️ Add <code>GOOGLE_MAPS_API_KEY</code> to your <code>.env</code> file to enable Google Maps.
        The map below is using the free no-key mode (limited, watermarked).
      </div>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  * {{ margin:0;padding:0;box-sizing:border-box; }}
  html,body,#map {{ width:100%;height:{height}px; }}
  #controls {{
    position:absolute;top:10px;right:10px;z-index:5;
    background:#fff;border:1px solid #e5e7eb;border-radius:6px;
    padding:6px 10px;font-family:system-ui,sans-serif;font-size:12px;
    box-shadow:0 1px 4px rgba(0,0,0,.15);
  }}
  #controls label {{ cursor:pointer;display:flex;align-items:center;gap:4px; }}
  #legend {{
    position:absolute;bottom:28px;left:10px;z-index:5;
    background:#fff;border:1px solid #e5e7eb;border-radius:6px;
    padding:8px 12px;font-family:system-ui,sans-serif;font-size:11px;
    line-height:1.8;box-shadow:0 1px 4px rgba(0,0,0,.15);
  }}
  .dot {{
    display:inline-block;width:10px;height:10px;
    border-radius:50%;margin-right:6px;vertical-align:middle;
  }}
</style>
</head>
<body>
{no_key_banner}
<div id="map"></div>
<div id="controls">
  <label><input type="radio" name="maptype" value="roadmap" checked onchange="setType(this.value)"> Roadmap</label>
  <label><input type="radio" name="maptype" value="satellite" onchange="setType(this.value)"> Satellite</label>
</div>
<div id="legend">
  <strong>Risk level</strong><br>
  <span class="dot" style="background:#22c55e"></span>LOW (1)<br>
  <span class="dot" style="background:#f59e0b"></span>MEDIUM (2)<br>
  <span class="dot" style="background:#ef4444"></span>HIGH (3)<br>
  <span class="dot" style="background:#7c3aed"></span>CRITICAL (4)
</div>

<script>
(function() {{
  const TRIPS  = {trips_js};
  const CENTER = {{ lat: {center_lat}, lng: {center_lng} }};
  let map, infoWindow;

  function initMap() {{
    map = new google.maps.Map(document.getElementById("map"), {{
      center: CENTER,
      zoom: 12,
      mapTypeId: "roadmap",
      mapTypeControl: false,
      fullscreenControl: true,
      streetViewControl: false,
    }});
    infoWindow = new google.maps.InfoWindow();

    TRIPS.forEach(function(t) {{
      if (!t.path || t.path.length === 0) return;

      // Polyline
      const line = new google.maps.Polyline({{
        path: t.path,
        geodesic: true,
        strokeColor: t.color,
        strokeOpacity: 0.9,
        strokeWeight: 3,
        map: map,
      }});
      line.addListener("click", function(e) {{
        infoWindow.setContent(
          "<b>Trip " + t.tid + "</b><br>" +
          "Scenario: " + t.scenario + "<br>" +
          "State: " + t.state + "<br>" +
          "Severity: " + t.severity
        );
        infoWindow.setPosition(e.latLng);
        infoWindow.open(map);
      }});

      // Start circle
      if (t.start) {{
        new google.maps.Circle({{
          center: t.start,
          radius: 40,
          fillColor: t.color,
          fillOpacity: 0.9,
          strokeColor: "#ffffff",
          strokeWeight: 2,
          map: map,
        }});
      }}

      // End marker (home icon)
      if (t.end) {{
        const marker = new google.maps.Marker({{
          position: t.end,
          map: map,
          icon: {{
            path: google.maps.SymbolPath.CIRCLE,
            fillColor: t.severity >= 3 ? "#ef4444" : "#22c55e",
            fillOpacity: 1,
            strokeColor: "#ffffff",
            strokeWeight: 2,
            scale: 8,
          }},
          title: "End – " + t.tid,
        }});
        marker.addListener("click", function() {{
          infoWindow.setContent(
            "<b>Trip " + t.tid + " – End</b><br>" +
            "Scenario: " + t.scenario + "<br>" +
            "State: " + t.state
          );
          infoWindow.open(map, marker);
        }});
      }}
    }});

    // Auto-fit bounds to all trip paths
    if (TRIPS.length > 0) {{
      const bounds = new google.maps.LatLngBounds();
      TRIPS.forEach(function(t) {{
        t.path.forEach(function(p) {{ bounds.extend(p); }});
      }});
      map.fitBounds(bounds);
    }}
  }}

  window.setType = function(t) {{ map && map.setMapTypeId(t); }};

  // Load Google Maps JS API using the official loader pattern
  // (mirrors @googlemaps/js-api-loader behaviour)
  const script = document.createElement("script");
  script.src = "https://maps.googleapis.com/maps/api/js?key={api_key}&callback=initMap&loading=async";
  script.async = true;
  script.defer = true;
  document.head.appendChild(script);
}})();
</script>
</body>
</html>"""

    components.html(html, height=height, scrolling=False)
