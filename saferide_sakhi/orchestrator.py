"""
SafeRide Sakhi – Supervisor / Orchestrator Agent
Passes shared TripState through the seven agents in the correct order,
collects outputs, and returns the final trip summary.

Architecture: hybrid sequential + hierarchical
  - Agents 1–3 run sequentially (pre-trip → live monitoring)
  - Agents 4–5 run in sequence (risk score → context impact)
  - Agent 6 is triggered only when escalation is needed
  - Agent 7 closes the trip

The supervisor holds the single source of truth: TripState.
Agents communicate only through the supervisor, never directly.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from saferide_sakhi.logger import AgentLogger, Timer
from saferide_sakhi.models import (
    ChauffeurProfile,
    GPSPoint,
    PlannedRoute,
    RiderProfile,
    RiskLevel,
    TripState,
    TripStatus,
    VerificationStatus,
)

# Agent imports
from saferide_sakhi.agents import (
    agent1_anticipation,
    agent2_verification,
    agent3_monitoring,
    agent4_risk,
    agent5_impact,
    agent6_escalation,
    agent7_safe_arrival,
)

_log = AgentLogger("SupervisorAgent")


def _build_demo_state(trip_data: dict[str, Any]) -> TripState:
    """
    Construct a TripState from a synthetic trip dict
    (as produced by data/generate.py).
    """
    now = datetime.utcnow()

    # Build GPS points from trace
    trace = [
        GPSPoint(
            lat=pt["lat"], lon=pt["lon"],
            timestamp=datetime.fromisoformat(pt["timestamp"].replace("Z", "")),
            speed_kmh=pt.get("speed_kmh", 20),
            accuracy_metres=pt.get("accuracy_metres", 10),
        )
        for pt in trip_data.get("actual_trace", [])
    ]

    # Planned route from origin/dest
    origin_pt = trip_data.get("origin", {"lat": 12.97, "lon": 77.59})
    dest_pt   = trip_data.get("destination", {"lat": 12.93, "lon": 77.62})

    origin = GPSPoint(lat=origin_pt["lat"], lon=origin_pt["lon"], timestamp=now)
    dest   = GPSPoint(lat=dest_pt["lat"],   lon=dest_pt["lon"],   timestamp=now + timedelta(minutes=30))

    planned_wps = [
        GPSPoint(lat=wp["lat"], lon=wp["lon"], timestamp=now)
        for wp in trip_data.get("planned_route", [])
    ]

    planned_route = PlannedRoute(
        origin=origin,
        destination=dest,
        waypoints=planned_wps,
        estimated_duration_min=30.0,
        distance_km=trip_data.get("distance_km", 5.0),
    )

    rider = RiderProfile(
        name="Priya Sharma",
        phone="9XXXXXXXXX",   # synthetic
        employer_or_campus="Infosys Whitefield",
        trusted_contacts=[],
        consent_location_sharing=True,
        consent_recording=False,
    )

    current_loc = GPSPoint(lat=origin_pt["lat"], lon=origin_pt["lon"], timestamp=now)

    chauffeur = ChauffeurProfile(
        name="Kavitha Reddy",
        phone="9XXXXXXXXX",   # synthetic
        licence_number="KA01-2024-1234",
        police_verification=VerificationStatus.VERIFIED,
        id_status=VerificationStatus.VERIFIED,
        face_match_result=True,
        last_verification_date=now - timedelta(days=30),
        rating=4.8,
        current_location=current_loc,
    )

    return TripState(
        trip_id=UUID(trip_data.get("trip_id", str(uuid4()))),
        rider=rider,
        chauffeur=chauffeur,
        planned_route=planned_route,
        actual_trace=trace,
        status=TripStatus.ACTIVE,
        last_check_in=now - timedelta(minutes=8) if trip_data.get("inject_silence") else now,
        started_at=now,
    )


def run_trip(
    trip_data: dict[str, Any],
    dry_run: bool = True,
    safe_arrival_confirmed: bool = False,
) -> dict[str, Any]:
    """
    Run the full agent pipeline for one trip.

    Parameters
    ----------
    trip_data           : synthetic trip dict from generate.py
    dry_run             : if True all dispatches are simulated (no real calls)
    safe_arrival_confirmed : set True to simulate rider confirming arrival

    Returns
    -------
    Full supervisor summary dict with risk level, escalation step,
    all agent outputs and flags.
    """
    state = _build_demo_state(trip_data)
    summary: dict[str, Any] = {"trip_id": str(state.trip_id)}

    with Timer() as total_t:

        # ── Pre-trip: anticipation ────────────────────────────────────────────
        anticipation = agent1_anticipation.run(
            rider=state.rider,
            current_time=state.started_at,
        )
        summary["anticipation"] = anticipation

        # ── Pre-trip: chauffeur verification ──────────────────────────────────
        verification = agent2_verification.run(
            chauffeur=state.chauffeur,
            rider_location=state.planned_route.origin,
        )
        summary["verification"] = verification

        if not verification["approved"]:
            summary["aborted"] = True
            summary["abort_reason"] = verification["recommendation"]
            state.status = TripStatus.ABORTED
            _log.step(
                trip_id=str(state.trip_id),
                stage="supervisor",
                input_summary="pre-trip checks",
                output_summary="trip aborted – chauffeur verification failed",
                latency_ms=total_t.elapsed_ms,
                decision="abort",
            )
            return {**summary, "trip_state": state.model_dump(mode="json")}

        # ── Live monitoring ───────────────────────────────────────────────────
        monitoring = agent3_monitoring.run(state)
        summary["monitoring"] = monitoring

        # ── Risk scoring (Granite 4) ──────────────────────────────────────────
        risk = agent4_risk.run(state, monitoring)
        summary["risk"] = risk

        # ── Context & impact assessment (Gemini) ─────────────────────────────
        impact = agent5_impact.run(state, risk)
        summary["impact"] = impact

        # ── Escalation ladder (Groq) ─────────────────────────────────────────
        esc_rec = impact.get("escalation_recommendation", "none")
        escalation = agent6_escalation.run(
            state=state,
            escalation_recommendation=esc_rec,
            reasoning=impact.get("reasoning", ""),
            dry_run=dry_run,
        )
        summary["escalation"] = escalation

        # ── Safe arrival / response ───────────────────────────────────────────
        arrival = agent7_safe_arrival.run(
            state=state,
            safe_arrival_confirmed=safe_arrival_confirmed,
            dry_run=dry_run,
        )
        summary["arrival"] = arrival

    summary["final_risk_level"] = state.risk_level.value
    summary["final_escalation_step"] = state.escalation_step.value
    summary["total_latency_ms"] = round(total_t.elapsed_ms, 1)
    summary["flags"] = [f.model_dump(mode="json") for f in state.flags]
    summary["trip_state"] = state.model_dump(mode="json")

    _log.step(
        trip_id=str(state.trip_id),
        stage="supervisor_complete",
        input_summary=f"inject_dev={trip_data.get('inject_deviation')}, inject_sil={trip_data.get('inject_silence')}",
        output_summary=f"risk={state.risk_level.value}, esc={state.escalation_step.value}",
        latency_ms=total_t.elapsed_ms,
        decision=state.risk_level.value,
    )

    return summary
