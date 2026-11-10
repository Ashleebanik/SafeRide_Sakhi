"""Agent 1 – Context & Anticipation Agent
Reads shift rosters, calendars and past trips to suggest a ride when a shift
ends or a rider is out late.  Rule-based; no LLM required.
"""
from __future__ import annotations

from datetime import datetime, time
from typing import Any

from saferide_sakhi.logger import AgentLogger, Timer
from saferide_sakhi.models import RiderProfile, TripState

_log = AgentLogger("ContextAnticipationAgent")

# Late-night window: 10 pm – 5 am
_LATE_START = time(22, 0)
_LATE_END   = time(5, 0)


def is_late_night(dt: datetime) -> bool:
    t = dt.time()
    return t >= _LATE_START or t <= _LATE_END


def run(
    rider: RiderProfile,
    current_time: datetime | None = None,
    shift_end: datetime | None = None,
) -> dict[str, Any]:
    """
    Decide whether a ride should be proactively suggested.

    Returns:
        {
            "suggest_ride": bool,
            "reason": str,
            "priority": "high" | "medium" | "low"
        }
    """
    now = current_time or datetime.utcnow()

    with Timer() as t:
        late = is_late_night(now)
        shift_ending_soon = False
        reason = ""
        priority = "low"

        if shift_end:
            mins_to_end = (shift_end - now).total_seconds() / 60
            shift_ending_soon = 0 <= mins_to_end <= 30

        if shift_ending_soon and late:
            reason = f"Shift ends in {mins_to_end:.0f} min during late-night hours"
            priority = "high"
        elif late:
            reason = "Rider is active during late-night hours"
            priority = "medium"
        elif shift_ending_soon:
            reason = "Shift ending soon"
            priority = "low"
        else:
            reason = "No immediate need detected"

        suggest = priority in ("high", "medium")

    _log.step(
        trip_id="pre-trip",
        stage="anticipation",
        input_summary=f"rider={rider.name}, late={late}, shift_end={shift_end}",
        tool_call="is_late_night",
        output_summary=f"suggest={suggest}, priority={priority}",
        latency_ms=t.elapsed_ms,
        decision=f"suggest_ride={suggest}",
    )

    return {"suggest_ride": suggest, "reason": reason, "priority": priority}
