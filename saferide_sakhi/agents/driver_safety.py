"""
Driver-Safety Agent – T4.6
Goal: protect women drivers (the gap most sources leave open).
Handles: driver SOS, night-shift safe-stop suggestions, harassment reports,
         rating-review flags.
Guardrails:
  - May flag a rating for review but NEVER change ratings or incentives.
  - Reports stored with minimum identifying data.
  - May not lower rule-set severity.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from saferide_sakhi.logger import AgentLogger, Timer
from saferide_sakhi.tools.allowlists import DriverSafetyOutput, validate_output
from saferide_sakhi.tools.mcp_servers import (
    CaseActionRecord, MessagePacket,
    case_store_add_action, case_store_open, case_store_transition,
    messaging_send, route_service_nearest_safe_stop,
    trip_store_get, trip_store_get_pings,
)
from saferide_sakhi.tools.db import get_conn

_log = AgentLogger("DriverSafetyAgent")


def _store_report(driver_id: str, summary: str, rating_review: bool) -> str:
    report_id = str(uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO Report VALUES (?,?,?,?,?)",
            (report_id, driver_id, summary[:500], int(rating_review), now),
        )
        conn.commit()
    return report_id


def run(
    driver_id: str,
    event_type: str,           # "sos" | "safe_stop_request" | "harassment_report"
    trip_id: str = "",
    lat: float | None = None,
    lon: float | None = None,
    report_text: str = "",
    mock_route_escalation: bool = False,
) -> dict[str, Any]:
    """
    Handle a driver safety event.
    Returns DriverSafetyOutput as dict.
    """
    case_id = ""
    safe_stops: list[dict] = []
    rating_review_flag = False
    report_summary = ""

    with Timer() as t:

        # ── SOS ───────────────────────────────────────────────────────────────
        if event_type == "sos":
            # Open a severity-4 case immediately; route to Escalation
            case_id = case_store_open(trip_id or "driver_sos", severity=4)
            case_store_transition(case_id, "ESCALATED")
            messaging_send(MessagePacket(
                trip_id=trip_id, case_id=case_id,
                channel="push", recipient="control_room",
                body=f"DRIVER SOS: driver {driver_id[:8]} needs immediate assistance.",
                priority="critical",
            ))

        # ── Safe-stop request ─────────────────────────────────────────────────
        elif event_type == "safe_stop_request":
            if lat is None or lon is None:
                # Try to get last known position from trip
                if trip_id:
                    pings = trip_store_get_pings(trip_id)
                    if pings:
                        lat = pings[-1]["lat"]
                        lon = pings[-1]["lon"]
            if lat and lon:
                stops = route_service_nearest_safe_stop(lat, lon)
                safe_stops = [s.model_dump() for s in stops]
                # Send suggestions to driver
                stop_text = safe_stops[0]["name"] if safe_stops else "nearest police station"
                messaging_send(MessagePacket(
                    trip_id=trip_id, case_id="",
                    channel="sms", recipient=f"driver:{driver_id[:8]}",
                    body=f"SafeRide Sakhi: Nearest safe stop is {stop_text}. Head there if needed.",
                    priority="high",
                ))

        # ── Harassment report ─────────────────────────────────────────────────
        elif event_type == "harassment_report":
            # Store with minimum data; flag rating for review
            rating_review_flag = True
            report_summary = report_text[:300] if report_text else "Report submitted anonymously."
            _store_report(driver_id, report_summary, rating_review_flag)
            case_id = case_store_open(trip_id or "driver_report", severity=2)
            case_store_add_action(CaseActionRecord(
                case_id=case_id, agent="driver_safety",
                action="harassment_report_received",
                result=f"rating_review_flag=True, summary_len={len(report_summary)}",
            ))
            messaging_send(MessagePacket(
                trip_id=trip_id, case_id=case_id,
                channel="push", recipient="control_room",
                body="Harassment report received from a driver. Rating review flagged.",
                priority="normal",
            ))

    out_raw = {
        "case_id": case_id,
        "safe_stop_options": safe_stops,
        "rating_review_flag": rating_review_flag,
        "report_summary": report_summary,
    }

    validated = validate_output("driver_safety", out_raw, DriverSafetyOutput)
    if validated is None:
        validated = DriverSafetyOutput(**out_raw)

    _log.step(
        trip_id=trip_id, stage="driver_safety",
        input_summary=f"driver={driver_id[:8]}, event={event_type}",
        tool_call="trip_store,route_service,case_store,messaging",
        output_summary=f"case_id={case_id}, stops={len(safe_stops)}, rating_flag={rating_review_flag}",
        latency_ms=t.elapsed_ms,
        decision=event_type,
    )
    return validated.model_dump()
