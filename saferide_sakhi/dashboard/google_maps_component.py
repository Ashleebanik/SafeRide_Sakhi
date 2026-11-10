"""
Google Maps component for Streamlit.
Merges the official Google Maps Geolocation sample
(https://developers.google.com/maps/documentation/javascript/geolocation)
with the SafeRide Sakhi trip overlay.

Features:
  - "Pan to Current Location" button (official geolocation pattern)
  - Polylines per trip, colour-coded by severity (1-4)
  - Circle at trip start, dot marker at trip end
  - InfoWindow on click: trip ID, scenario, state
  - Roadmap / Satellite toggle
  - Risk-level legend
  - No-API-key banner (graceful fallback)
"""
from __future__ import annotations

import json
from typing import Any

import streamlit.components.v1 as components

RISK_HEX = {1: "#22c55e", 2: "#f59e0b", 3: "#ef4444", 4: "#7c3aed"}


def _trip_to_js_obj(result: dict[str, Any]) -> str:
    """Serialise one pipeline result to a JS object literal."""
    trip     = result.get("_trip", {})
    pings    = trip.get("pings", [])
    sev      = int(result.get("severity", 1))
    color    = RISK_HEX.get(sev, "#22c55e")
    tid      = str(result.get("trip_id", ""))[:8]
    state    = result.get("final_state", "unknown")
    scenario = result.get("scenario", "")
    path     = json.dumps([{"lat": p["lat"], "lng": p["lon"]} for p in pings])
    start    = json.dumps({"lat": pings[0]["lat"],  "lng": pings[0]["lon"]}) if pings else "null"
    end      = json.dumps({"lat": pings[-1]["lat"], "lng": pings[-1]["lon"]}) if pings else "null"
    return (
        f'{{"path":{path},"color":"{color}","severity":{sev},'
        f'"tid":"{tid}","state":"{state}","scenario":"{scenario}",'
        f'"start":{start},"end":{end}}}'
    )


def render_google_map(
    results: list[dict[str, Any]],
    api_key: str,
    height: int = 500,
) -> None:
    """
    Render an interactive Google Maps view inside Streamlit.
    Includes the official Geolocation sample button.
    """
    trips_js   = "[" + ",".join(_trip_to_js_obj(r) for r in results
                                if r.get("_trip", {}).get("pings")) + "]"
    center_lat = 12.9716
    center_lng = 77.5946

    no_key_banner = "" if api_key else (
        '<div style="position:absolute;top:8px;left:50%;transform:translateX(-50%);'
        'background:#fef2f2;border:1px solid #fca5a5;border-radius:6px;'
        'padding:8px 16px;font-size:13px;color:#991b1b;z-index:10;">'
        '&#9888;&#65039; Add <code>GOOGLE_MAPS_API_KEY</code> to your '
        '<code>.env</code> file for full Google Maps. '
        'Running in limited no-key mode.</div>'
    )

    # Use weekly channel + solution_channel exactly as the official sample does
    maps_src = (
        f"https://maps.googleapis.com/maps/api/js"
        f"?key={api_key}"
        f"&callback=initMap"
        f"&v=weekly"
        f"&solution_channel=GMP_CCS_geolocation_v2"
    )

    html = f"""<!DOCTYPE html>
<!--
  Based on the official Google Maps Geolocation sample
  Copyright 2019 Google LLC. All Rights Reserved.
  SPDX-License-Identifier: Apache-2.0
-->
<html>
<head>
<meta charset="utf-8"/>
<style>
  /**
   * Always set the map height explicitly to define the size of the div
   * element that contains the map.
   */
  #map {{ height: 100%; }}

  html, body {{
    height: {height}px;
    margin: 0;
    padding: 0;
  }}

  /* "Pan to Current Location" button – exact style from the official sample */
  .custom-map-control-button {{
    background-color: #fff;
    border: 0;
    border-radius: 2px;
    box-shadow: 0 1px 4px -1px rgba(0, 0, 0, 0.3);
    margin: 10px;
    padding: 0 0.5em;
    font: 400 18px Roboto, Arial, sans-serif;
    overflow: hidden;
    height: 40px;
    cursor: pointer;
  }}
  .custom-map-control-button:hover {{
    background: rgb(235, 235, 235);
  }}

  /* Map type toggle (roadmap / satellite) */
  #map-type-control {{
    position: absolute;
    top: 10px;
    right: 10px;
    z-index: 5;
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    padding: 6px 10px;
    font: 400 13px Roboto, Arial, sans-serif;
    box-shadow: 0 1px 4px rgba(0,0,0,.15);
  }}
  #map-type-control label {{
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 4px;
    margin: 2px 0;
  }}

  /* Risk legend */
  #legend {{
    position: absolute;
    bottom: 28px;
    left: 10px;
    z-index: 5;
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    padding: 8px 12px;
    font: 400 11px Roboto, Arial, sans-serif;
    line-height: 1.9;
    box-shadow: 0 1px 4px rgba(0,0,0,.15);
  }}
  .dot {{
    display: inline-block;
    width: 10px; height: 10px;
    border-radius: 50%;
    margin-right: 6px;
    vertical-align: middle;
  }}
</style>
<title>SafeRide Sakhi – Live Trips</title>

<script>
  /**
   * initMap – called by the Maps JS API loader (callback=initMap).
   * Merges the official Geolocation sample with SafeRide trip overlays.
   */
  let map, infoWindow;

  function initMap() {{
    const CENTER = {{ lat: {center_lat}, lng: {center_lng} }};
    const TRIPS  = {trips_js};

    map = new google.maps.Map(document.getElementById("map"), {{
      center: CENTER,
      zoom: 12,
      mapTypeId: "roadmap",
      mapTypeControl: false,
      fullscreenControl: true,
      streetViewControl: false,
    }});

    infoWindow = new google.maps.InfoWindow();

    // ── Official Geolocation sample: "Pan to Current Location" button ──────
    const locationButton = document.createElement("button");
    locationButton.textContent = "Pan to Current Location";
    locationButton.classList.add("custom-map-control-button");
    map.controls[google.maps.ControlPosition.TOP_CENTER].push(locationButton);

    locationButton.addEventListener("click", () => {{
      // Try HTML5 geolocation (exactly as in the official sample)
      if (navigator.geolocation) {{
        navigator.geolocation.getCurrentPosition(
          (position) => {{
            const pos = {{
              lat: position.coords.latitude,
              lng: position.coords.longitude,
            }};
            infoWindow.setPosition(pos);
            infoWindow.setContent("Location found.");
            infoWindow.open(map);
            map.setCenter(pos);
          }},
          () => {{ handleLocationError(true,  infoWindow, map.getCenter()); }}
        );
      }} else {{
        // Browser doesn't support Geolocation
        handleLocationError(false, infoWindow, map.getCenter());
      }}
    }});

    // ── SafeRide trip overlays ──────────────────────────────────────────────
    TRIPS.forEach(function(t) {{
      if (!t.path || t.path.length === 0) return;

      // Colour-coded polyline
      const line = new google.maps.Polyline({{
        path:          t.path,
        geodesic:      true,
        strokeColor:   t.color,
        strokeOpacity: 0.9,
        strokeWeight:  3,
        map:           map,
      }});
      line.addListener("click", function(e) {{
        infoWindow.setContent(
          "<b>Trip " + t.tid + "</b><br>" +
          "Scenario: " + t.scenario + "<br>" +
          "State: "    + t.state    + "<br>" +
          "Severity: " + t.severity
        );
        infoWindow.setPosition(e.latLng);
        infoWindow.open(map);
      }});

      // Start circle
      if (t.start) {{
        new google.maps.Circle({{
          center:      t.start,
          radius:      40,
          fillColor:   t.color,
          fillOpacity: 0.9,
          strokeColor: "#ffffff",
          strokeWeight: 2,
          map:         map,
        }});
      }}

      // End marker
      if (t.end) {{
        const marker = new google.maps.Marker({{
          position: t.end,
          map:      map,
          icon: {{
            path:        google.maps.SymbolPath.CIRCLE,
            fillColor:   t.severity >= 3 ? "#ef4444" : "#22c55e",
            fillOpacity: 1,
            strokeColor: "#ffffff",
            strokeWeight: 2,
            scale:       8,
          }},
          title: "End \u2013 " + t.tid,
        }});
        marker.addListener("click", function() {{
          infoWindow.setContent(
            "<b>Trip " + t.tid + " \u2013 End</b><br>" +
            "Scenario: " + t.scenario + "<br>" +
            "State: "    + t.state
          );
          infoWindow.open(map, marker);
        }});
      }}
    }});

    // Auto-fit to all trip paths when trips are present
    if (TRIPS.length > 0) {{
      const bounds = new google.maps.LatLngBounds();
      TRIPS.forEach(function(t) {{
        t.path.forEach(function(p) {{ bounds.extend(p); }});
      }});
      map.fitBounds(bounds);
    }}
  }}

  // handleLocationError – exact function from the official sample
  function handleLocationError(browserHasGeolocation, infoWindow, pos) {{
    infoWindow.setPosition(pos);
    infoWindow.setContent(
      browserHasGeolocation
        ? "Error: The Geolocation service failed."
        : "Error: Your browser doesn\u2019t support geolocation."
    );
    infoWindow.open(map);
  }}

  // Map type toggle (roadmap / satellite)
  window.setMapType = function(t) {{ map && map.setMapTypeId(t); }};

  window.initMap = initMap;
</script>
</head>
<body>
{no_key_banner}
<div id="map"></div>

<!-- Map type control -->
<div id="map-type-control">
  <label><input type="radio" name="mt" value="roadmap"  checked
         onchange="setMapType(this.value)"> Roadmap</label>
  <label><input type="radio" name="mt" value="satellite"
         onchange="setMapType(this.value)"> Satellite</label>
</div>

<!-- Risk legend -->
<div id="legend">
  <strong>Risk level</strong><br>
  <span class="dot" style="background:#22c55e"></span>LOW (1)<br>
  <span class="dot" style="background:#f59e0b"></span>MEDIUM (2)<br>
  <span class="dot" style="background:#ef4444"></span>HIGH (3)<br>
  <span class="dot" style="background:#7c3aed"></span>CRITICAL (4)
</div>

<!--
  Load the Maps JS API exactly as in the official Geolocation sample.
  solution_channel=GMP_CCS_geolocation_v2 matches the sample exactly.
-->
<script
  src="{maps_src}"
  defer
></script>
</body>
</html>"""

    components.html(html, height=height, scrolling=False)
