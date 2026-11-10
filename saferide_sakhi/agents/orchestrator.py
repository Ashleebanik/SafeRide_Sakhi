"""
Orchestrator – T5.1 / T5.2 / T5.3
Implements the full alert lifecycle state machine (PDF section 3):
  DETECTED → TRIAGED → VERIFYING → AWAITING_OPERATOR → ESCALATED
  → ACKNOWLEDGED → RESPONDING → CLOSED
  Side exits: FALSE_ALARM, TIMEOUT_ESCALATED

Pattern: hierarchical supervisor.
- Owns state, timeouts, retries and the operator gate.
- Explicit SOS shortcut: skips triage, goes straight to Escalation (T5.2).
- Operator gate: confirm/dismiss/edit with audit (T5.3).
- Fail-safe: any agent error escalates to operator, never drops the case.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from saferide_sakhi.logger import AgentLogger, Timer
from saferide_sakhi.tools.mcp_servers import (
    CaseActionRecord, TripRecord,
    case_store_add_action, case_store_open, case_store_transition,
    trip_store_upsert, _audit,
)
from saferide_sakhi.agents import monitor, verifier, escalation, case_followup, driver_safety

_log = AgentLogger("Orchestrator")

# Lifecycle states (matches PDF section 3)
class State:
    DETECTED           = "DETECTED"
    TRIAGED            = "TRIAGED"
    VERIFYING          = "VERIFYING"
    AWAITING_OPERATOR  = "AWAITING_OPERATOR"
    ESCALATED          = "ESCALATED"
    ACKNOWLEDGED       = "ACKNOWLEDGED"
    RESPONDING         = "RESPONDING"
    CLOSED             = "CLOSED"
    FALSE_ALARM        = "FALSE_ALARM"
    TIMEOUT_ESCALATED  = "TIMEOUT_ESCALATED"


# ── Operator gate (T5.3) ──────────────────────────────────────────────────────

def operator_gate(
    case_id: str,
    action: str,           # "confirm" | "dismiss" | "edit"
    operator_id: str = "control_room",
    note: str = "",
) -> dict[str, Any]:
    """
    Human confirms, dismisses or edits a case.
    Every action is written to the audit log.
    Only this function may transition a case past AWAITING_OPERATOR.
    """
    assert action in ("confirm", "dismiss", "edit"), f"Unknown action: {action}"

    if action == "dismiss":
        case_store_transition(case_id, State.FALSE_ALARM)
        new_state = State.FALSE_ALARM
    else:
        case_store_transition(case_id, State.ESCALATED)
        new_state = State.ESCALATED

    _audit(operator_id, f"operator_gate:{action} case={case_id} note={note}", case_id)
    case_store_add_action(CaseActionRecord(
        case_id=case_id, agent=operator_id,
        action=f"operator_{action}", result=f"note={note}",
    ))
    return {"case_id": case_id, "new_state": new_state,
            "operator_id": operator_id, "action": action}


# ── Main trip pipeline ────────────────────────────────────────────────────────

def run_trip_pipeline(
    trip_data: dict[str, Any],
    risk_event: dict[str, Any],
    operator_approved: bool = False,
    mock_passenger_response: str = "I'm fine, just a detour",
    mock_driver_response: str  = "Traffic block, taking alternate route",
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    Run the full alert lifecycle for one risk event on one trip.

    Parameters
    ----------
    trip_data         : dict with trip_id, driver_id, vehicle_id, planned_route…
    risk_event        : dict from the rules engine (type, severity, ts, payload)
    operator_approved : whether the operator has approved high-severity escalation
    dry_run           : suppress real emergency gateway calls

    Returns
    -------
    Summary dict with every agent's output and final lifecycle state.
    """
    trip_id   = trip_data["trip_id"]
    is_sos    = risk_event.get("type") == "sos"
    severity  = risk_event.get("severity", 1)

    summary: dict[str, Any] = {
        "trip_id": trip_id,
        "scenario": trip_data.get("scenario", "unknown"),
        "risk_event_type": risk_event.get("type"),
        "severity": severity,
        "is_sos": is_sos,
    }

    # Ensure trip is in the store
    try:
        trip_store_upsert(TripRecord(
            trip_id=trip_id,
            rider_id=trip_data.get("rider_id", ""),
            driver_id=trip_data.get("driver_id", ""),
            vehicle_id=trip_data.get("vehicle_id", ""),
            route_planned=trip_data.get("planned_route", []),
            status="active",
            started_at=trip_data.get("started_at", ""),
        ))
    except Exception as exc:
        _log.error(trip_id, "trip_store_upsert", str(exc))

    with Timer() as total_t:

        # ── SOS shortcut (T5.2) ────────────────────────────────────────────
        if is_sos:
            case_id = case_store_open(trip_id, severity=4)
            case_store_transition(case_id, State.ESCALATED)
            esc_out = escalation.run(
                case_id=case_id, trip_id=trip_id,
                verifier_output={"verdict": "confirmed", "evidence": ["sos_pressed"]},
                monitor_output={"risk_level": 4, "case_id": case_id,
                                "reasons": ["sos"], "evidence_refs": ["sos"]},
                operator_approved=True, is_sos=True, dry_run=dry_run,
            )
            summary["sos_shortcut"] = True
            summary["case_id"] = case_id
            summary["escalation"] = esc_out
            summary["final_state"] = State.ESCALATED
            _log.step(trip_id=trip_id, stage="orchestrator",
                      input_summary="SOS received",
                      output_summary=f"case={case_id}",
                      latency_ms=total_t.elapsed_ms,
                      decision="sos_direct_escalation")
            return summary

        # ── Normal pipeline ────────────────────────────────────────────────

        # T4.2 Monitor
        try:
            mon_out = monitor.run(risk_event, trip_id)
            case_id = mon_out["case_id"]
            case_store_transition(case_id, State.TRIAGED)
            summary["monitor"] = mon_out
        except Exception as exc:
            _log.error(trip_id, "monitor", str(exc))
            case_id = case_store_open(trip_id, severity)
            mon_out = {"case_id": case_id, "risk_level": severity,
                       "reasons": ["monitor_failed"], "evidence_refs": [],
                       "recommended_checks": ["escalate_operator"], "confidence": 0.0}
            summary["monitor"] = mon_out
            # Fail-safe: escalate to operator
            case_store_transition(case_id, State.AWAITING_OPERATOR)
            summary["final_state"] = State.AWAITING_OPERATOR
            return summary

        # T4.3 Verifier
        case_store_transition(case_id, State.VERIFYING)
        try:
            ver_out = verifier.run(
                mon_out, trip_id,
                mock_passenger_response=mock_passenger_response,
                mock_driver_response=mock_driver_response,
            )
            summary["verifier"] = ver_out
        except Exception as exc:
            _log.error(trip_id, "verifier", str(exc))
            ver_out = {"verdict": "unclear", "evidence": ["verifier_failed"],
                       "passenger_response": "", "driver_response": ""}
            summary["verifier"] = ver_out

        verdict = ver_out.get("verdict", "unclear")

        # False alarm → close
        if verdict == "likely_false" and severity <= 2:
            case_store_transition(case_id, State.FALSE_ALARM)
            summary["final_state"] = State.FALSE_ALARM
            _log.step(trip_id=trip_id, stage="orchestrator",
                      input_summary=f"verdict={verdict}",
                      output_summary="false_alarm",
                      latency_ms=total_t.elapsed_ms, decision="false_alarm")
            return summary

        # Severity 3+ or unclear → operator gate
        if severity >= 3 or verdict == "unclear":
            case_store_transition(case_id, State.AWAITING_OPERATOR)
            summary["awaiting_operator"] = True
            if not operator_approved:
                summary["final_state"] = State.AWAITING_OPERATOR
                summary["message"] = "Case awaiting operator review."
                return summary
            # Operator approved (passed in or simulated)
            operator_gate(case_id, "confirm", note="auto_approved_in_pipeline")

        # T4.4 Escalation
        try:
            esc_out = escalation.run(
                case_id=case_id, trip_id=trip_id,
                verifier_output=ver_out, monitor_output=mon_out,
                operator_approved=operator_approved or severity < 3,
                is_sos=False, dry_run=dry_run,
            )
            summary["escalation"] = esc_out
            case_store_transition(case_id, State.ESCALATED)
        except Exception as exc:
            _log.error(trip_id, "escalation", str(exc))
            summary["escalation"] = {"error": str(exc)}
            case_store_transition(case_id, State.AWAITING_OPERATOR)

        # T4.5 Case Follow-up
        try:
            fu_out = case_followup.run(case_id)
            summary["follow_up"] = fu_out
        except Exception as exc:
            _log.error(trip_id, "case_followup", str(exc))
            summary["follow_up"] = {"error": str(exc)}

    summary["case_id"] = case_id
    summary["final_state"] = State.ESCALATED
    summary["total_latency_ms"] = round(total_t.elapsed_ms, 1)

    _log.step(
        trip_id=trip_id, stage="orchestrator_complete",
        input_summary=f"scenario={trip_data.get('scenario')}, sev={severity}",
        output_summary=f"case={case_id}, final={summary.get('final_state')}",
        latency_ms=total_t.elapsed_ms,
        decision=summary.get("final_state", "unknown"),
    )
    return summary
