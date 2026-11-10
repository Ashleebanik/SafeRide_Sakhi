"""
SafeRide Sakhi – MCP Tools Layer
Each function represents one tool callable by agents via the MCP interface.
In production these would be registered with an MCP server.  For the
challenge build they are plain Python functions that agents call directly.
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from saferide_sakhi.config import (
    MAX_ROUTE_DEVIATION_METRES,
    SILENCE_ALERT_SECONDS,
    SILENCE_NUDGE_SECONDS,
    UNPLANNED_STOP_SECONDS,
)

_DATA_DIR = Path(__file__).parent.parent / "data" / "synthetic"


# ─────────────────────────────────────────────────────────────────────────────
# Tool 1 – Route deviation check
# ─────────────────────────────────────────────────────────────────────────────

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def check_route_deviation(
    planned: list[dict], actual: list[dict]
) -> dict[str, Any]:
    """
    Compare actual GPS trace to planned waypoints.
    Returns max deviation in metres and whether threshold was breached.
    """
    if not planned or not actual:
        return {"max_deviation_m": 0, "breached": False, "details": []}

    deviations = []
    for pt in actual:
        min_dist = min(
            haversine_m(pt["lat"], pt["lon"], wp["lat"], wp["lon"])
            for wp in planned
        )
        deviations.append({"point": pt, "deviation_m": round(min_dist, 1)})

    max_dev = max(d["deviation_m"] for d in deviations)
    return {
        "max_deviation_m": max_dev,
        "breached": max_dev > MAX_ROUTE_DEVIATION_METRES,
        "details": sorted(deviations, key=lambda d: -d["deviation_m"])[:5],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tool 2 – Unplanned stop detector
# ─────────────────────────────────────────────────────────────────────────────

def detect_unplanned_stops(actual_trace: list[dict]) -> dict[str, Any]:
    """
    Find stops (speed < 3 km/h) that last longer than UNPLANNED_STOP_SECONDS.
    """
    stops = []
    i = 0
    while i < len(actual_trace):
        pt = actual_trace[i]
        if pt.get("speed_kmh", 999) < 3.0:
            j = i
            while j < len(actual_trace) and actual_trace[j].get("speed_kmh", 999) < 3.0:
                j += 1
            if j > i:
                try:
                    t_start = datetime.fromisoformat(actual_trace[i]["timestamp"].replace("Z",""))
                    t_end   = datetime.fromisoformat(actual_trace[j - 1]["timestamp"].replace("Z",""))
                    duration = (t_end - t_start).total_seconds()
                except Exception:
                    duration = 0
                if duration > UNPLANNED_STOP_SECONDS:
                    stops.append({
                        "lat": pt["lat"], "lon": pt["lon"],
                        "duration_s": round(duration, 1),
                        "start": actual_trace[i]["timestamp"],
                    })
            i = j
        else:
            i += 1
    return {"stops": stops, "count": len(stops)}


# ─────────────────────────────────────────────────────────────────────────────
# Tool 3 – Silence / check-in monitor
# ─────────────────────────────────────────────────────────────────────────────

def check_silence(last_check_in: str | None, now: str | None = None) -> dict[str, Any]:
    """
    Returns seconds since last check-in and the silence severity level.
    """
    if last_check_in is None:
        return {"seconds_silent": 0, "level": "none"}

    ref = datetime.utcnow() if now is None else datetime.fromisoformat(now.replace("Z", ""))
    lci = datetime.fromisoformat(last_check_in.replace("Z", ""))
    secs = max((ref - lci).total_seconds(), 0)

    if secs >= SILENCE_ALERT_SECONDS:
        level = "alert"
    elif secs >= SILENCE_NUDGE_SECONDS:
        level = "nudge"
    else:
        level = "none"

    return {"seconds_silent": round(secs, 0), "level": level}


# ─────────────────────────────────────────────────────────────────────────────
# Tool 4 – Nearest help point
# ─────────────────────────────────────────────────────────────────────────────

def nearest_help_point(lat: float, lon: float) -> dict[str, Any]:
    """Find the closest public safety help point from local data."""
    help_file = _DATA_DIR / "help_points.json"
    if not help_file.exists():
        return {"found": False}

    points: list[dict] = json.loads(help_file.read_text())
    if not points:
        return {"found": False}

    closest = min(
        points,
        key=lambda p: haversine_m(lat, lon, p["lat"], p["lon"])
    )
    dist = haversine_m(lat, lon, closest["lat"], closest["lon"])
    return {
        "found": True,
        "name": closest["name"],
        "type": closest["type"],
        "lat": closest["lat"],
        "lon": closest["lon"],
        "distance_m": round(dist, 0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tool 5 – Chauffeur verification check
# ─────────────────────────────────────────────────────────────────────────────

def verify_chauffeur(chauffeur_record: dict[str, Any]) -> dict[str, Any]:
    """
    Checks ID, police verification, licence status and face-match result.
    Returns pass/fail and a list of issues found.
    """
    issues = []
    if chauffeur_record.get("police_verification") != "verified":
        issues.append("police_verification_not_cleared")
    if chauffeur_record.get("id_status") in ("pending", "expired", "failed"):
        issues.append(f"id_status_{chauffeur_record.get('id_status')}")
    if not chauffeur_record.get("face_match_result", True):
        issues.append("face_match_failed")

    # Re-verification expiry – flag if > 6 months
    last = chauffeur_record.get("last_verification_date")
    if last:
        try:
            lv = datetime.fromisoformat(last.replace("Z", ""))
            if (datetime.utcnow() - lv).days > 180:
                issues.append("verification_expired_over_6_months")
        except Exception:
            pass

    return {"passed": len(issues) == 0, "issues": issues}


# ─────────────────────────────────────────────────────────────────────────────
# Tool 6 – Context enrichment (time, area lighting, risk zone)
# ─────────────────────────────────────────────────────────────────────────────

def enrich_context(lat: float, lon: float, hour: int) -> dict[str, Any]:
    """
    Returns time-of-night risk context.
    Uses rule-based heuristics on public area categories
    (actual integration would use a geofence layer from OSM).
    """
    late_night = hour >= 22 or hour <= 4
    very_late  = hour >= 0 and hour <= 4

    # Rough area classification using lat/lon bounding boxes
    # These represent publicly known district types in Bangalore
    area_type = "residential"
    if 12.93 < lat < 12.97 and 77.60 < lon < 77.65:
        area_type = "commercial_dense"     # Koramangala / Indiranagar belt
    elif lat < 12.87 or lon > 77.72:
        area_type = "industrial_outskirts"

    lighting = "adequate" if area_type == "commercial_dense" else (
        "dim" if late_night else "adequate"
    )
    help_pt = nearest_help_point(lat, lon)

    return {
        "area_type": area_type,
        "lighting": lighting,
        "late_night": late_night,
        "very_late": very_late,
        "help_point_nearby": help_pt.get("distance_m", 99999) < 1000,
        "nearest_help": help_pt,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tool 7 – Simulated alert dispatcher (no real calls in challenge build)
# ─────────────────────────────────────────────────────────────────────────────

def dispatch_alert(
    trip_id: str,
    level: str,
    message: str,
    recipient: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    Simulate sending an alert.  In production this would call SMS/push/112 APIs.
    dry_run=True (default) prevents any real network calls during the challenge build.
    """
    entry = {
        "trip_id": trip_id,
        "level": level,
        "recipient": recipient,
        "message": message,
        "sent_at": datetime.utcnow().isoformat() + "Z",
        "dry_run": dry_run,
    }
    print(f"[ALERT dispatch] {entry}")
    return {"dispatched": True, "dry_run": dry_run, "entry": entry}
