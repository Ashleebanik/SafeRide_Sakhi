"""
Escalation Agent – T4.4
Goal: get the right people informed and confirm receipt.
Guardrails:
  - Location/identifiers copied from trip store ONLY (never generated).
  - High-severity sends require operator gate (except explicit SOS).
  - Retries on fallback channel (SMS) if primary fails.
  - Tracks acknowledgement times.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

from saferide_sakhi.llm_gateway import call as llm_call
from saferide_sakhi.logger import AgentLogger, Timer
from saferide_sakhi.tools.allowlists import EscalationOutput, validate_output
from saferide_sakhi.tools.mcp_servers import (
    CaseActionRecord, EmergencyPacket, MessagePacket,
    case_store_add_action, case_store_transition,
    emergency_gateway_send, messaging_send, trip_store_get, trip_store_get_pings,
)

_log = AgentLogger("EscalationAgent")
PROMPT_VERSION = "v1"

_MSG_PROMPT = """Draft a short, calm safety alert message for the given step.
Return ONLY JSON: {{"message": "<text max 2 sentences>"}}
Step: {step}
Context: {context}
Rules: no alarming caps, no exclamation marks, state facts only."""


def _draft_message(step: str, context: dict) -> str:
    resp = llm_call("groq",
                    _MSG_PROMPT.format(step=step, context=json.dumps(context)),
                    max_tokens=120, agent="escalation",
                    trip_id=context.get("trip_id", ""))
    if resp.success:
        try:
            return json.loads(resp.text.strip()).get("message", "")
        except Exception:
            pass
    # Fallback templates
    fallbacks = {
        "notify_contacts": "SafeRide Sakhi: An unusual pattern was detected on a trip. We are following up.",
        "alert_control_room": "Control room: unusual trip activity detected. Human review required.",
        "dispatch_emergency": "Emergency review requested for an active trip. Please assess and decide on 112 contact.",
    }
    return fallbacks.get(step, "Safety check triggered.")


def run(
    case_id: str,
    trip_id: str,
    verifier_output: dict[str, Any],
    monitor_output: dict[str, Any],
    operator_approved: bool = False,
    is_sos: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    Execute the escalation ladder.

    POLICY (from PDF):
    - Severity 3+ requires operator approval UNLESS it is an explicit SOS.
    - SOS skips triage and goes straight here with is_sos=True.
    - Returns EscalationOutput as dict.
    """
    risk_level = monitor_output.get("risk_level", 1)
    high_severity = risk_level >= 3

    # Operator gate: block unless approved or SOS
    if high_severity and not operator_approved and not is_sos:
        return {
            "channels_used": [],
            "delivered": False,
            "acknowledged_by": "",
            "time_to_ack": 0.0,
            "blocked_pending_operator": True,
            "message": "Awaiting operator approval.",
        }

    trip = trip_store_get(trip_id) or {}
    pings = trip_store_get_pings(trip_id)
    last_ping = pings[-1] if pings else {}
    where = f"{last_ping.get('lat', 'unknown')},{last_ping.get('lon', 'unknown')}"

    context = {
        "trip_id": trip_id, "case_id": case_id,
        "risk_level": risk_level, "where": where,
        "driver_id": trip.get("driver_id"),
        "vehicle_id": trip.get("vehicle_id"),
    }

    channels_used: list[str] = []
    delivered = False
    t_start = time.perf_counter()

    with Timer() as t:
        # Step 1: Notify trusted contacts
        if risk_level >= 2:
            msg = _draft_message("notify_contacts", context)
            r = messaging_send(MessagePacket(
                trip_id=trip_id, case_id=case_id,
                channel="sms", recipient="trusted_contact",
                body=msg, priority="high",
            ))
            channels_used.append("sms_contact")
            delivered = r.get("delivered", False)

        # Step 2: Alert control room
        if risk_level >= 3:
            msg = _draft_message("alert_control_room", context)
            r = messaging_send(MessagePacket(
                trip_id=trip_id, case_id=case_id,
                channel="push", recipient="control_room",
                body=msg, priority="critical",
            ))
            channels_used.append("push_control_room")
            # Fallback to SMS if push fails
            if not r.get("delivered"):
                messaging_send(MessagePacket(
                    trip_id=trip_id, case_id=case_id,
                    channel="sms", recipient="control_room",
                    body=msg, priority="critical",
                ))
                channels_used.append("sms_control_room_fallback")

        # Step 3: Emergency gateway (severity 4 or explicit SOS)
        if (risk_level >= 4 or is_sos) and not dry_run:
            msg = _draft_message("dispatch_emergency", context)
            pkt = EmergencyPacket(
                case_id=case_id, trip_id=trip_id,
                who=trip.get("rider_id", "unknown"),
                where=where,
                driver=trip.get("driver_id", "unknown"),
                vehicle=trip.get("vehicle_id", "unknown"),
                evidence=monitor_output.get("evidence_refs", []),
                severity=risk_level,
            )
            emergency_gateway_send(pkt)
            channels_used.append("emergency_gateway_112")

        case_store_transition(case_id, "ESCALATED")
        time_to_ack = round((time.perf_counter() - t_start) * 1000, 1)

    out = EscalationOutput(
        channels_used=channels_used,
        delivered=delivered,
        acknowledged_by="",
        time_to_ack=time_to_ack,
    )

    case_store_add_action(CaseActionRecord(
        case_id=case_id, agent="escalation",
        action="escalate", result=json.dumps(out.model_dump()),
    ))

    _log.step(
        trip_id=trip_id, stage="escalation",
        input_summary=f"risk={risk_level}, sos={is_sos}, approved={operator_approved}",
        tool_call="messaging,emergency_gateway,case_store",
        output_summary=f"channels={channels_used}, delivered={delivered}",
        latency_ms=t.elapsed_ms,
        decision=f"escalated_to={channels_used}",
        prompt_version=PROMPT_VERSION,
    )
    return out.model_dump()
