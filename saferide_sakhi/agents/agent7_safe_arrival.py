"""Agent 7 – Response & Safe-Arrival Agent
Recommends the nearest safe stop, dispatches support, confirms safe
arrival to family and records the outcome.
Rule-based with final LLM-free closure logic.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from saferide_sakhi.logger import AgentLogger, Timer
from saferide_sakhi.models import RiskLevel, TripState, TripStatus
from saferide_sakhi.mcp_tools.tools import dispatch_alert, nearest_help_point

_log = AgentLogger("ResponseSafeArrivalAgent")


def run(
    state: TripState,
    safe_arrival_confirmed: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    Close out the trip safely or recommend a safe stop.

    Returns:
        {
            "action": str,
            "nearest_safe_stop": dict,
            "arrival_notified": bool,
            "outcome": "safe_arrival"|"support_dispatched"|"emergency_handed_off"
        }
    """
    pos = state.latest_position()

    with Timer() as t:
        nearest = nearest_help_point(
            pos.lat if pos else 12.97,
            pos.lon if pos else 77.59,
        )

        if safe_arrival_confirmed or state.risk_level == RiskLevel.SAFE:
            # Confirm arrival to trusted contacts
            contacts = state.rider.trusted_contacts
            for contact in contacts[:1]:   # notify primary contact only
                dispatch_alert(
                    trip_id=str(state.trip_id),
                    level="safe_arrival",
                    message=f"{state.rider.name} has arrived safely.",
                    recipient=contact.phone,
                    dry_run=dry_run,
                )
            state.status = TripStatus.COMPLETED
            state.ended_at = datetime.utcnow()
            action = "confirmed_safe_arrival"
            outcome = "safe_arrival"

        elif state.risk_level in (RiskLevel.ALERT, RiskLevel.EMERGENCY):
            # Recommend diverting to nearest help point
            action = f"divert_to_{nearest.get('name', 'nearest_safe_point')}"
            dispatch_alert(
                trip_id=str(state.trip_id),
                level="support_dispatch",
                message=(
                    f"Redirecting rider to {nearest.get('name')} "
                    f"({nearest.get('distance_m', '?')}m away)."
                ),
                recipient="control_room",
                dry_run=dry_run,
            )
            outcome = "support_dispatched"

        else:
            action = "monitor_continue"
            outcome = "safe_arrival"

    _log.step(
        trip_id=str(state.trip_id),
        stage="safe_arrival",
        input_summary=f"risk={state.risk_level.value}, safe_confirmed={safe_arrival_confirmed}",
        tool_call="nearest_help_point,dispatch_alert",
        output_summary=f"action={action}, outcome={outcome}",
        latency_ms=t.elapsed_ms,
        decision=outcome,
    )

    return {
        "action": action,
        "nearest_safe_stop": nearest,
        "arrival_notified": outcome == "safe_arrival",
        "outcome": outcome,
    }
