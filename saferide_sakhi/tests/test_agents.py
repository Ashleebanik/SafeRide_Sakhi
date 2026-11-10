"""
Tests – SafeRide Sakhi
Run: pytest saferide_sakhi/tests/
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from saferide_sakhi.models import (
    ChauffeurProfile,
    GPSPoint,
    PlannedRoute,
    RiderProfile,
    TripState,
    TripStatus,
    VerificationStatus,
)
from saferide_sakhi.mcp_tools.tools import (
    check_route_deviation,
    check_silence,
    detect_unplanned_stops,
    haversine_m,
    verify_chauffeur,
)
from saferide_sakhi.agents import (
    agent1_anticipation,
    agent2_verification,
    agent3_monitoring,
    agent4_risk,
)
from saferide_sakhi.data.generate import generate_trip_trace, generate_rider_profile


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def base_rider() -> RiderProfile:
    return RiderProfile(
        name="Test Rider",
        phone="9000000001",
        employer_or_campus="Test Corp",
        trusted_contacts=[],
    )


@pytest.fixture
def verified_chauffeur() -> ChauffeurProfile:
    return ChauffeurProfile(
        name="Test Chauffeur",
        phone="9000000002",
        licence_number="KA01-2024-9999",
        police_verification=VerificationStatus.VERIFIED,
        id_status=VerificationStatus.VERIFIED,
        face_match_result=True,
        last_verification_date=datetime.utcnow() - timedelta(days=10),
        current_location=GPSPoint(lat=12.97, lon=77.59, timestamp=datetime.utcnow()),
    )


@pytest.fixture
def unverified_chauffeur() -> ChauffeurProfile:
    return ChauffeurProfile(
        name="Bad Chauffeur",
        phone="9000000003",
        licence_number="KA01-2024-0001",
        police_verification=VerificationStatus.PENDING,
        id_status=VerificationStatus.EXPIRED,
        face_match_result=False,
        last_verification_date=datetime.utcnow() - timedelta(days=200),
    )


@pytest.fixture
def clean_trip_state(base_rider, verified_chauffeur) -> TripState:
    now = datetime.utcnow()
    origin = GPSPoint(lat=12.97, lon=77.59, timestamp=now)
    dest   = GPSPoint(lat=12.93, lon=77.62, timestamp=now + timedelta(minutes=20))
    trace  = [
        GPSPoint(lat=12.97 + i * 0.001, lon=77.59 + i * 0.001,
                 timestamp=now + timedelta(seconds=i * 40), speed_kmh=30.0)
        for i in range(15)
    ]
    return TripState(
        rider=base_rider,
        chauffeur=verified_chauffeur,
        # Use the full actual trace as the planned waypoints so no deviation fires
        planned_route=PlannedRoute(origin=origin, destination=dest, waypoints=trace),
        actual_trace=trace,
        status=TripStatus.ACTIVE,
        last_check_in=now - timedelta(minutes=2),
    )


# ── Haversine ─────────────────────────────────────────────────────────────────

def test_haversine_same_point():
    assert haversine_m(12.97, 77.59, 12.97, 77.59) == pytest.approx(0, abs=1)


def test_haversine_known_distance():
    # Roughly 111 km per degree latitude
    dist = haversine_m(12.0, 77.0, 13.0, 77.0)
    assert 110_000 < dist < 112_000


# ── Route deviation tool ──────────────────────────────────────────────────────

def test_no_deviation_on_identical_routes():
    pts = [{"lat": 12.97 + i * 0.001, "lon": 77.59} for i in range(10)]
    result = check_route_deviation(pts, pts)
    assert result["breached"] is False


def test_deviation_detected():
    planned = [{"lat": 12.97, "lon": 77.59}]
    # 1 km off route
    actual  = [{"lat": 12.97 + 0.01, "lon": 77.59, "speed_kmh": 30, "timestamp": datetime.utcnow().isoformat()}]
    result = check_route_deviation(planned, actual)
    assert result["max_deviation_m"] > 300


# ── Silence monitor ───────────────────────────────────────────────────────────

def test_no_silence_recent_checkin():
    lci = (datetime.utcnow() - timedelta(minutes=1)).isoformat() + "Z"
    result = check_silence(lci)
    assert result["level"] == "none"


def test_nudge_silence():
    lci = (datetime.utcnow() - timedelta(minutes=7)).isoformat() + "Z"
    result = check_silence(lci)
    assert result["level"] == "nudge"


def test_alert_silence():
    lci = (datetime.utcnow() - timedelta(minutes=12)).isoformat() + "Z"
    result = check_silence(lci)
    assert result["level"] == "alert"


def test_no_checkin_at_all():
    result = check_silence(None)
    assert result["seconds_silent"] == 0


# ── Unplanned stop detector ───────────────────────────────────────────────────

def test_no_stops_moving_trace():
    now = datetime.utcnow()
    trace = [
        {"lat": 12.97, "lon": 77.59,
         "timestamp": (now + timedelta(seconds=i * 30)).isoformat() + "Z",
         "speed_kmh": 35.0}
        for i in range(20)
    ]
    result = detect_unplanned_stops(trace)
    assert result["count"] == 0


def test_stop_detected():
    now = datetime.utcnow()
    trace = [
        {"lat": 12.97, "lon": 77.59,
         "timestamp": (now + timedelta(seconds=i * 60)).isoformat() + "Z",
         "speed_kmh": 0.0 if 5 <= i <= 12 else 30.0}
        for i in range(20)
    ]
    result = detect_unplanned_stops(trace)
    assert result["count"] >= 1


# ── Chauffeur verification ────────────────────────────────────────────────────

def test_verified_chauffeur_passes(verified_chauffeur):
    record = verified_chauffeur.model_dump(mode="json")
    result = verify_chauffeur(record)
    assert result["passed"] is True
    assert result["issues"] == []


def test_unverified_chauffeur_fails(unverified_chauffeur):
    record = unverified_chauffeur.model_dump(mode="json")
    result = verify_chauffeur(record)
    assert result["passed"] is False
    assert len(result["issues"]) >= 2


# ── Agent 1: Anticipation ─────────────────────────────────────────────────────

def test_anticipation_late_night_suggests_ride(base_rider):
    late = datetime.utcnow().replace(hour=23, minute=30)
    result = agent1_anticipation.run(base_rider, current_time=late)
    assert result["suggest_ride"] is True


def test_anticipation_midday_no_ride(base_rider):
    midday = datetime.utcnow().replace(hour=14, minute=0)
    result = agent1_anticipation.run(base_rider, current_time=midday)
    assert result["suggest_ride"] is False


# ── Agent 2: Verification ─────────────────────────────────────────────────────

def test_agent2_approves_verified(verified_chauffeur):
    origin = GPSPoint(lat=12.97, lon=77.59, timestamp=datetime.utcnow())
    result = agent2_verification.run(verified_chauffeur, origin)
    assert result["approved"] is True


def test_agent2_rejects_unverified(unverified_chauffeur):
    origin = GPSPoint(lat=12.97, lon=77.59, timestamp=datetime.utcnow())
    result = agent2_verification.run(unverified_chauffeur, origin)
    assert result["approved"] is False


# ── Agent 3: Monitoring ───────────────────────────────────────────────────────

def test_agent3_clean_trip_no_signals(clean_trip_state):
    result = agent3_monitoring.run(clean_trip_state)
    assert result["signals"] == []


def test_agent3_detects_silence():
    """Build a state with a stale check-in."""
    now = datetime.utcnow()
    rider = RiderProfile(name="R", phone="9", trusted_contacts=[])
    chauffeur = ChauffeurProfile(
        name="C", phone="9", licence_number="KA01",
        police_verification=VerificationStatus.VERIFIED,
        id_status=VerificationStatus.VERIFIED,
        face_match_result=True,
        last_verification_date=now - timedelta(days=1),
    )
    origin = GPSPoint(lat=12.97, lon=77.59, timestamp=now)
    dest   = GPSPoint(lat=12.93, lon=77.62, timestamp=now + timedelta(minutes=20))
    state = TripState(
        rider=rider, chauffeur=chauffeur,
        planned_route=PlannedRoute(origin=origin, destination=dest),
        actual_trace=[origin],
        last_check_in=now - timedelta(minutes=12),
        status=TripStatus.ACTIVE,
    )
    result = agent3_monitoring.run(state)
    assert any("silence" in s for s in result["signals"])


# ── Agent 4: Risk scoring (rule-based fallback only in tests) ─────────────────

def test_agent4_safe_on_clean_trip(clean_trip_state):
    monitoring = agent3_monitoring.run(clean_trip_state)
    risk = agent4_risk.run(clean_trip_state, monitoring)
    assert risk["risk_level"] in ("safe", "nudge")   # clean trip should be low risk


# ── Data generator ────────────────────────────────────────────────────────────

def test_generate_trip_trace_has_required_fields():
    trip = generate_trip_trace()
    assert "trip_id" in trip
    assert "actual_trace" in trip
    assert len(trip["actual_trace"]) > 0


def test_generate_deviation_flag():
    trip = generate_trip_trace(inject_deviation=True)
    assert trip["inject_deviation"] is True


def test_generate_rider_profile_has_contacts():
    rider = generate_rider_profile()
    assert "trusted_contacts" in rider
    assert len(rider["trusted_contacts"]) >= 1
