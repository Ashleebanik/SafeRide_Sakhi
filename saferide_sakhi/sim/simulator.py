"""
Trip Simulator – T1.2
Generates planned routes and GPS ping streams with scripted events:
  deviation, long_stop, driver_change, missed_checkin, sos
Each scenario produces a list of (event_type, payload) tuples.
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

OUT_DIR = Path(__file__).parent.parent / "data" / "synthetic"
OUT_DIR.mkdir(parents=True, exist_ok=True)

random.seed(42)

# Bangalore bounding box
LAT_ORIGIN, LON_ORIGIN = 12.9716, 77.5946
STEP = 0.0008    # ~90 m per ping


def _straight_route(origin_lat: float, origin_lon: float,
                    n_pings: int = 30) -> list[dict]:
    """Simple straight-line route heading NE."""
    pings = []
    for i in range(n_pings):
        pings.append({
            "lat": round(origin_lat + i * STEP, 6),
            "lon": round(origin_lon + i * STEP * 0.7, 6),
        })
    return pings


def build_trip(
    scenario: str,
    origin_lat: float | None = None,
    origin_lon: float | None = None,
    inject_at: int = 15,       # ping index where event is injected
) -> dict:
    """
    Build one simulated trip with a scripted anomaly.
    Returns a dict compatible with the ingestion API.
    """
    lat = origin_lat or LAT_ORIGIN + random.uniform(-0.02, 0.02)
    lon = origin_lon or LON_ORIGIN + random.uniform(-0.02, 0.02)
    planned = _straight_route(lat, lon)
    trip_id = str(uuid4())
    driver_id = str(uuid4())
    vehicle_id = f"KA{random.randint(10,99)}-{random.randint(1000,9999)}"
    started_at = datetime.utcnow().replace(hour=22, minute=random.randint(0, 59))

    pings: list[dict] = []
    events: list[dict] = []

    for i, wp in enumerate(planned):
        ts = started_at + timedelta(seconds=i * 45)
        ping_lat, ping_lon = wp["lat"], wp["lon"]
        speed = round(random.uniform(18, 40), 1)

        # ── Inject scenario ──────────────────────────────────────────────────
        if i == inject_at:
            if scenario == "deviation":
                # Route deviates ~700 m
                ping_lat += 0.007
                ping_lon -= 0.005
                events.append({"type": "route_deviation", "severity": 3,
                                "ts": ts.isoformat() + "Z",
                                "payload": {"deviation_m": 720}})

            elif scenario == "long_stop":
                speed = 0.0
                # Extend stop for 8 pings
                for j in range(8):
                    stop_ts = ts + timedelta(seconds=j * 60)
                    pings.append({"lat": ping_lat, "lon": ping_lon,
                                  "speed_kmh": 0.0,
                                  "ts": stop_ts.isoformat() + "Z"})
                events.append({"type": "long_stop", "severity": 3,
                                "ts": ts.isoformat() + "Z",
                                "payload": {"duration_s": 480,
                                            "lat": ping_lat, "lon": ping_lon}})
                continue

            elif scenario == "driver_change":
                new_driver = str(uuid4())
                events.append({"type": "driver_vehicle_mismatch", "severity": 4,
                                "ts": ts.isoformat() + "Z",
                                "payload": {"expected_driver": driver_id,
                                            "seen_driver": new_driver}})

            elif scenario == "missed_checkin":
                events.append({"type": "missed_checkin", "severity": 2,
                                "ts": ts.isoformat() + "Z",
                                "payload": {"minutes_overdue": 10}})

            elif scenario == "sos":
                events.append({"type": "sos", "severity": 4,
                                "ts": ts.isoformat() + "Z",
                                "payload": {"triggered_by": "rider"}})

            elif scenario == "silent_trigger":
                events.append({"type": "missed_checkin", "severity": 2,
                                "ts": ts.isoformat() + "Z",
                                "payload": {"minutes_overdue": 20,
                                            "no_response": True}})

            elif scenario == "false_alarm":
                # Detour due to traffic, speed still normal
                ping_lat += 0.003
                events.append({"type": "route_deviation", "severity": 2,
                                "ts": ts.isoformat() + "Z",
                                "payload": {"deviation_m": 310,
                                            "traffic_note": "known_diversion"}})

            elif scenario == "normal":
                pass

        pings.append({"lat": ping_lat, "lon": ping_lon,
                      "speed_kmh": speed, "ts": ts.isoformat() + "Z"})

    return {
        "trip_id": trip_id,
        "driver_id": driver_id,
        "vehicle_id": vehicle_id,
        "rider_id": str(uuid4()),
        "planned_route": planned,
        "pings": pings,
        "events": events,
        "scenario": scenario,
        "started_at": started_at.isoformat() + "Z",
        "expected_outcome": _expected_outcome(scenario),
    }


def _expected_outcome(scenario: str) -> dict:
    outcomes = {
        "normal":         {"risk_level": 1, "escalation": "none"},
        "false_alarm":    {"risk_level": 2, "escalation": "none"},
        "deviation":      {"risk_level": 3, "escalation": "notify_contacts"},
        "long_stop":      {"risk_level": 3, "escalation": "notify_contacts"},
        "missed_checkin": {"risk_level": 2, "escalation": "nudge_rider"},
        "silent_trigger": {"risk_level": 3, "escalation": "alert_control_room"},
        "driver_change":  {"risk_level": 4, "escalation": "alert_control_room"},
        "sos":            {"risk_level": 4, "escalation": "dispatch_emergency"},
    }
    return outcomes.get(scenario, {"risk_level": 1, "escalation": "none"})


# ── 20+ scenario library (T1.3) ───────────────────────────────────────────────

SCENARIO_NAMES = [
    "normal", "normal", "normal",                  # 3 normals for baseline
    "false_alarm", "false_alarm",                  # traffic diversions
    "deviation", "deviation", "deviation",         # 3 route deviations
    "long_stop", "long_stop",                      # isolated stops
    "driver_change",                               # mismatch
    "missed_checkin", "missed_checkin",
    "silent_trigger", "silent_trigger",
    "sos", "sos",
    "false_alarm",                                 # offline passenger
    "missed_checkin",                              # passenger not responding
    "deviation",                                   # prompt-injection attempt trip
    "long_stop",                                   # driver SOS at night
]


def build_scenario_library() -> list[dict]:
    random.seed(42)
    library = [build_trip(s) for s in SCENARIO_NAMES]
    out = OUT_DIR / "scenarios.json"
    out.write_text(json.dumps(library, indent=2))
    print(f"[sim] wrote {len(library)} scenarios -> {out}")
    return library


if __name__ == "__main__":
    build_scenario_library()
