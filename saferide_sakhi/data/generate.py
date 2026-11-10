"""
SafeRide Sakhi – Synthetic data generator.
Produces realistic-looking but entirely fictional trip traces, rider profiles
and chauffeur records.  NO real personal data is ever used.

Run directly:  python -m saferide_sakhi.data.generate
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from faker import Faker

fake = Faker("en_IN")
random.seed(42)

OUT_DIR = Path(__file__).parent / "synthetic"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Bangalore bounding box (safe for public use – OSM data) ───────────────────
LAT_MIN, LAT_MAX = 12.85, 13.10
LON_MIN, LON_MAX = 77.45, 77.75

SAFETY_HELP_POINTS = [
    {"name": "KR Puram Police Station", "lat": 13.0067, "lon": 77.6946, "type": "police"},
    {"name": "Manipal Hospital Whitefield", "lat": 12.9698, "lon": 77.7499, "type": "hospital"},
    {"name": "Indiranagar Police Station", "lat": 12.9784, "lon": 77.6408, "type": "police"},
    {"name": "24x7 Pharmacy – Koramangala", "lat": 12.9352, "lon": 77.6245, "type": "pharmacy"},
    {"name": "St John's Hospital", "lat": 12.9403, "lon": 77.6227, "type": "hospital"},
    {"name": "Marathahalli Police Post", "lat": 12.9591, "lon": 77.7010, "type": "police"},
]


def _rand_point(
    lat: float | None = None, lon: float | None = None, jitter: float = 0.01
) -> dict:
    """Random GPS point, optionally near a seed coordinate."""
    base_lat = lat if lat is not None else random.uniform(LAT_MIN, LAT_MAX)
    base_lon = lon if lon is not None else random.uniform(LON_MIN, LON_MAX)
    return {
        "lat": round(base_lat + random.uniform(-jitter, jitter), 6),
        "lon": round(base_lon + random.uniform(-jitter, jitter), 6),
    }


def _interpolate_route(
    origin: dict, dest: dict, n_points: int = 20
) -> list[dict]:
    """Linear interpolation between two GPS points."""
    points = []
    for i in range(n_points):
        t = i / max(n_points - 1, 1)
        points.append({
            "lat": round(origin["lat"] + t * (dest["lat"] - origin["lat"]), 6),
            "lon": round(origin["lon"] + t * (dest["lon"] - origin["lon"]), 6),
        })
    return points


def _inject_deviation(trace: list[dict], deviation_metres: int = 600) -> list[dict]:
    """Divert the route mid-trip by ~deviation_metres worth of GPS delta."""
    idx = len(trace) // 2
    delta_deg = deviation_metres / 111_000
    deviated = list(trace)
    for i in range(idx, min(idx + 5, len(trace))):
        deviated[i] = {
            "lat": round(trace[i]["lat"] + delta_deg, 6),
            "lon": round(trace[i]["lon"] + delta_deg * 1.5, 6),
        }
    return deviated


def generate_trip_trace(
    inject_deviation: bool = False,
    inject_silence: bool = False,
    inject_unplanned_stop: bool = False,
) -> dict:
    origin = _rand_point()
    dest = _rand_point(origin["lat"], origin["lon"], jitter=0.05)
    base_trace = _interpolate_route(origin, dest, n_points=30)

    if inject_deviation:
        base_trace = _inject_deviation(base_trace)

    start_time = datetime.utcnow().replace(
        hour=random.choice([22, 23, 0, 1, 2]), minute=random.randint(0, 59)
    )

    gps_trace = []
    for i, pt in enumerate(base_trace):
        ts = start_time + timedelta(seconds=i * 40)
        speed = round(random.uniform(15, 45), 1)
        if inject_unplanned_stop and i == 15:
            speed = 0.0
        if inject_silence and i >= 18:
            pass  # silence = no check-in events (modelled separately)
        gps_trace.append({
            **pt,
            "timestamp": ts.isoformat() + "Z",
            "speed_kmh": speed,
            "accuracy_metres": round(random.uniform(5, 20), 1),
        })

    dist_km = round(
        math.hypot(dest["lat"] - origin["lat"], dest["lon"] - origin["lon"]) * 111, 2
    )

    return {
        "trip_id": str(uuid4()),
        "origin": origin,
        "destination": dest,
        "planned_route": base_trace,
        "actual_trace": gps_trace,
        "inject_deviation": inject_deviation,
        "inject_silence": inject_silence,
        "inject_unplanned_stop": inject_unplanned_stop,
        "distance_km": dist_km,
        "started_at": gps_trace[0]["timestamp"],
    }


def generate_rider_profile() -> dict:
    return {
        "rider_id": str(uuid4()),
        "name": fake.name_female(),
        "phone": fake.phone_number(),
        "employer_or_campus": random.choice([
            "Infosys Whitefield", "Manyata Tech Park", "RV College of Engineering",
            "Manipal Hospital", "Myntra HQ", "ISRO Outer Ring Road"
        ]),
        "trusted_contacts": [
            {"name": fake.name(), "phone": fake.phone_number(), "relation": rel}
            for rel in random.sample(["Mother", "Father", "Sister", "Friend", "Husband"], k=2)
        ],
        "usual_routes": [],
        "consent_location_sharing": True,
        "consent_recording": False,
    }


def generate_chauffeur_profile() -> dict:
    verified = random.random() > 0.1   # 10% chance of verification issue
    return {
        "chauffeur_id": str(uuid4()),
        "name": fake.name_female(),
        "phone": fake.phone_number(),
        "licence_number": f"KA{random.randint(10,99)}-{random.randint(1000,9999)}-{random.randint(1000,9999)}",
        "police_verification": "verified" if verified else "pending",
        "id_status": "verified" if verified else "expired",
        "face_match_result": verified,
        "last_verification_date": (
            datetime.utcnow() - timedelta(days=random.randint(1, 90))
        ).isoformat() + "Z",
        "rating": round(random.uniform(3.8, 5.0), 1),
    }


def generate_dataset(n_trips: int = 50) -> None:
    trips, riders, chauffeurs = [], [], []

    for i in range(n_trips):
        # Inject anomalies in ~30 % of trips
        dev  = i % 5 == 0
        sil  = i % 7 == 0
        stop = i % 6 == 0
        trips.append(generate_trip_trace(dev, sil, stop))
        riders.append(generate_rider_profile())
        chauffeurs.append(generate_chauffeur_profile())

    (OUT_DIR / "trips.json").write_text(json.dumps(trips, indent=2))
    (OUT_DIR / "riders.json").write_text(json.dumps(riders, indent=2))
    (OUT_DIR / "chauffeurs.json").write_text(json.dumps(chauffeurs, indent=2))
    (OUT_DIR / "help_points.json").write_text(json.dumps(SAFETY_HELP_POINTS, indent=2))
    print(f"[generate] wrote {n_trips} trips, riders, chauffeurs -> {OUT_DIR}")


if __name__ == "__main__":
    generate_dataset()
