"""
Deterministic Rules Engine – T2.2 / T2.3
Evaluates raw trip events and emits RiskEvent objects with severity 1–4.

Detectors:
  1. route_deviation     – deviation > threshold
  2. long_stop           – stationary > threshold at non-destination
  3. driver_vehicle_mismatch – driver ID or vehicle ID changed mid-trip
  4. missed_checkin      – last check-in older than threshold
  5. night_time_flag     – trip is active in late-night window (adds +1 severity bump)

Design principle: Rules for hard triggers; LLMs for judgement.
A safety alert NEVER depends solely on a model output.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any

# Thresholds (tune from evaluation baseline – T9.3)
DEVIATION_THRESHOLD_M: int = 300
LONG_STOP_SECONDS: int = 120
MISSED_CHECKIN_MINUTES: int = 8
LATE_NIGHT_START_HOUR: int = 22
LATE_NIGHT_END_HOUR: int = 5

SEVERITY = {
    "LOW":      1,
    "MEDIUM":   2,
    "HIGH":     3,
    "CRITICAL": 4,
}


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _is_late_night(ts: datetime) -> bool:
    h = ts.hour
    return h >= LATE_NIGHT_START_HOUR or h < LATE_NIGHT_END_HOUR


def _apply_night_bump(severity: int, ts: datetime) -> int:
    """Add 1 severity level (capped at 4) for late-night trips."""
    if _is_late_night(ts):
        return min(severity + 1, 4)
    return severity


# ── Detector 1: Route deviation ───────────────────────────────────────────────

def detect_route_deviation(
    planned_waypoints: list[dict],
    actual_lat: float,
    actual_lon: float,
    ts: datetime,
) -> dict[str, Any] | None:
    """Return a RiskEvent dict or None."""
    if not planned_waypoints:
        return None
    min_dist = min(
        _haversine_m(actual_lat, actual_lon, wp["lat"], wp["lon"])
        for wp in planned_waypoints
    )
    if min_dist > DEVIATION_THRESHOLD_M:
        sev = SEVERITY["HIGH"] if min_dist > 600 else SEVERITY["MEDIUM"]
        sev = _apply_night_bump(sev, ts)
        return {
            "type": "route_deviation",
            "severity": sev,
            "ts": ts.isoformat() + "Z",
            "payload": {"deviation_m": round(min_dist, 1)},
        }
    return None


# ── Detector 2: Long stop ─────────────────────────────────────────────────────

def detect_long_stop(
    stop_start: datetime,
    stop_end: datetime,
    lat: float,
    lon: float,
    dest_lat: float | None,
    dest_lon: float | None,
) -> dict[str, Any] | None:
    duration = (stop_end - stop_start).total_seconds()
    if duration <= LONG_STOP_SECONDS:
        return None
    # Not at destination
    at_dest = False
    if dest_lat is not None and dest_lon is not None:
        at_dest = _haversine_m(lat, lon, dest_lat, dest_lon) < 100
    if at_dest:
        return None
    sev = SEVERITY["HIGH"]
    sev = _apply_night_bump(sev, stop_start)
    return {
        "type": "long_stop",
        "severity": sev,
        "ts": stop_end.isoformat() + "Z",
        "payload": {"duration_s": round(duration, 1),
                    "lat": lat, "lon": lon},
    }


# ── Detector 3: Driver / vehicle mismatch ─────────────────────────────────────

def detect_driver_vehicle_mismatch(
    expected_driver_id: str,
    actual_driver_id: str,
    expected_vehicle_id: str,
    actual_vehicle_id: str,
    ts: datetime,
) -> dict[str, Any] | None:
    if expected_driver_id == actual_driver_id and expected_vehicle_id == actual_vehicle_id:
        return None
    issues = []
    if expected_driver_id != actual_driver_id:
        issues.append("driver_id_mismatch")
    if expected_vehicle_id != actual_vehicle_id:
        issues.append("vehicle_id_mismatch")
    return {
        "type": "driver_vehicle_mismatch",
        "severity": SEVERITY["CRITICAL"],   # always critical, no bump needed
        "ts": ts.isoformat() + "Z",
        "payload": {"issues": issues,
                    "expected_driver": expected_driver_id,
                    "actual_driver": actual_driver_id},
    }


# ── Detector 4: Missed check-in ───────────────────────────────────────────────

def detect_missed_checkin(
    last_checkin: datetime,
    now: datetime,
) -> dict[str, Any] | None:
    overdue_min = (now - last_checkin).total_seconds() / 60
    if overdue_min < MISSED_CHECKIN_MINUTES:
        return None
    sev = SEVERITY["HIGH"] if overdue_min > 15 else SEVERITY["MEDIUM"]
    sev = _apply_night_bump(sev, now)
    return {
        "type": "missed_checkin",
        "severity": sev,
        "ts": now.isoformat() + "Z",
        "payload": {"minutes_overdue": round(overdue_min, 1)},
    }


# ── Detector 5: Night-time flag ───────────────────────────────────────────────

def detect_night_flag(ts: datetime) -> dict[str, Any] | None:
    """Raises a severity-1 informational event when a trip starts at night."""
    if _is_late_night(ts):
        return {
            "type": "night_time_flag",
            "severity": SEVERITY["LOW"],
            "ts": ts.isoformat() + "Z",
            "payload": {"hour": ts.hour},
        }
    return None


# ── Evaluate all detectors on one incoming event ──────────────────────────────

def evaluate_event(event: dict[str, Any], trip_context: dict[str, Any]) -> list[dict]:
    """
    Given a raw app event and trip context, run all applicable detectors.
    Returns a list of RiskEvent dicts (may be empty).
    """
    now_str = event.get("ts", datetime.utcnow().isoformat() + "Z")
    now = datetime.fromisoformat(now_str.replace("Z", ""))
    results = []

    etype = event.get("type", "")

    if etype == "location_ping":
        pl = event.get("payload", event)
        lat = pl.get("lat") or event.get("lat")
        lon = pl.get("lon") or event.get("lon")
        planned = trip_context.get("planned_route", [])
        if lat and lon and planned:
            r = detect_route_deviation(planned, lat, lon, now)
            if r:
                results.append(r)

    elif etype in ("long_stop", "stop"):
        pl = event.get("payload", {})
        stop_start = now - __import__("datetime").timedelta(
            seconds=pl.get("duration_s", 300))
        r = detect_long_stop(
            stop_start, now,
            pl.get("lat", 0), pl.get("lon", 0),
            trip_context.get("dest_lat"), trip_context.get("dest_lon"),
        )
        if r:
            results.append(r)

    elif etype == "driver_vehicle_mismatch":
        pl = event.get("payload", {})
        r = detect_driver_vehicle_mismatch(
            trip_context.get("driver_id", ""), pl.get("seen_driver", ""),
            trip_context.get("vehicle_id", ""), pl.get("seen_vehicle", ""),
            now,
        )
        if r:
            results.append(r)

    elif etype == "missed_checkin":
        pl = event.get("payload", {})
        overdue_min = pl.get("minutes_overdue", 10)
        last_ci = now - __import__("datetime").timedelta(minutes=overdue_min)
        r = detect_missed_checkin(last_ci, now)
        if r:
            results.append(r)

    elif etype == "sos":
        # SOS is always severity 4, no further evaluation
        results.append({
            "type": "sos",
            "severity": SEVERITY["CRITICAL"],
            "ts": now_str,
            "payload": event.get("payload", {}),
        })

    night = detect_night_flag(now)
    if night and not any(r["type"] == "night_time_flag" for r in results):
        results.append(night)

    return results
