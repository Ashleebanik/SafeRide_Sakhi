"""Agent 3 – Live Trip Monitoring Agent
Tracks position, speed, stops and route against the expected path in real time.
Rule-based; no LLM required.
"""
from __future__ import annotations

from typing import Any

from saferide_sakhi.logger import AgentLogger, Timer
from saferide_sakhi.models import TripState
from saferide_sakhi.mcp_tools.tools import (
    check_route_deviation,
    check_silence,
    detect_unplanned_stops,
)

_log = AgentLogger("LiveTripMonitoringAgent")


def run(state: TripState) -> dict[str, Any]:
    """
    Run one monitoring cycle for an active trip.

    Returns a dict with deviation, stop and silence findings, plus
    a list of raw signals to pass to Agent 4 for risk scoring.
    """
    planned = [
        {"lat": wp.lat, "lon": wp.lon, "timestamp": wp.timestamp.isoformat()}
        for wp in (state.planned_route.waypoints or [state.planned_route.origin, state.planned_route.destination])
    ]
    actual = [
        {"lat": pt.lat, "lon": pt.lon,
         "timestamp": pt.timestamp.isoformat(),
         "speed_kmh": pt.speed_kmh}
        for pt in state.actual_trace
    ]
    last_ci = state.last_check_in.isoformat() + "Z" if state.last_check_in else None

    with Timer() as t:
        deviation = check_route_deviation(planned, actual)
        stops     = detect_unplanned_stops(actual)
        silence   = check_silence(last_ci)

    signals: list[str] = []
    if deviation["breached"]:
        signals.append(f"route_deviation_{deviation['max_deviation_m']:.0f}m")
    if stops["count"] > 0:
        signals.append(f"unplanned_stops_{stops['count']}")
    if silence["level"] != "none":
        signals.append(f"silence_{silence['level']}_{silence['seconds_silent']:.0f}s")

    _log.step(
        trip_id=str(state.trip_id),
        stage="live_monitoring",
        input_summary=f"trace_pts={len(actual)}, last_ci={last_ci}",
        tool_call="check_route_deviation,detect_unplanned_stops,check_silence",
        output_summary=f"signals={signals}",
        latency_ms=t.elapsed_ms,
        decision=f"signals_raised={len(signals)}",
    )

    return {
        "deviation": deviation,
        "stops": stops,
        "silence": silence,
        "signals": signals,
    }
