"""Agent 5 – Context & Impact Assessment Agent  (Google Gemini)
Considers time of night, area type, lighting, nearby help points and
who is affected to judge how serious a flag is.
Uses Gemini 1.5 Flash for multi-context reasoning.
"""
from __future__ import annotations

import json
from typing import Any

from saferide_sakhi.config import GEMINI_API_KEY, GEMINI_MODEL, REACT_MAX_ITERATIONS
from saferide_sakhi.logger import AgentLogger, Timer
from saferide_sakhi.models import AgentFlag, TripState
from saferide_sakhi.mcp_tools.tools import enrich_context, nearest_help_point

_log = AgentLogger("ContextImpactAgent")

PROMPT_VERSION = "v1"

_SYSTEM_PROMPT = """You are the Context & Impact Assessment Agent for SafeRide Sakhi.
Given a risk score and contextual data about a night-time ride in an Indian city,
assess the real-world severity and recommend an escalation level.

Input JSON fields:
- risk_score: float 0-1
- risk_level: "safe"|"nudge"|"alert"|"emergency"
- area_type: "residential"|"commercial_dense"|"industrial_outskirts"
- lighting: "adequate"|"dim"
- late_night: bool
- very_late: bool
- help_point_nearby: bool
- nearest_help: dict with name and distance_m
- signals: list of anomaly strings

Respond ONLY with valid JSON (no markdown):
{
  "severity": "low"|"medium"|"high"|"critical",
  "adjusted_risk_score": <float 0.0-1.0>,
  "escalation_recommendation": "none"|"nudge_rider"|"notify_contacts"|"alert_control_room"|"dispatch_emergency",
  "reasoning": "<two sentences max, grounded in data>",
  "mitigating_factors": ["<factor>"],
  "aggravating_factors": ["<factor>"]
}
"""


def _call_gemini(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        prompt = _SYSTEM_PROMPT + "\n\nData:\n" + json.dumps(payload)
        response = model.generate_content(prompt)
        text = response.text.strip()
        # Strip any accidental markdown fences
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception as exc:
        _log.error("llm_call", "gemini_call_failed", str(exc))
        return None


def _rule_based_assess(
    risk_score: float, context: dict[str, Any]
) -> dict[str, Any]:
    """Deterministic fallback."""
    agg = []
    mit = []

    if context.get("very_late"):
        agg.append("very_late_night")
        risk_score = min(risk_score + 0.1, 1.0)
    if context.get("lighting") == "dim":
        agg.append("dim_lighting")
        risk_score = min(risk_score + 0.05, 1.0)
    if context.get("area_type") == "industrial_outskirts":
        agg.append("industrial_outskirts")
        risk_score = min(risk_score + 0.1, 1.0)
    if context.get("help_point_nearby"):
        mit.append("help_point_within_1km")
        risk_score = max(risk_score - 0.05, 0.0)

    if risk_score >= 0.80:
        severity, esc = "critical", "dispatch_emergency"
    elif risk_score >= 0.60:
        severity, esc = "high", "alert_control_room"
    elif risk_score >= 0.35:
        severity, esc = "medium", "nudge_rider"
    else:
        severity, esc = "low", "none"

    return {
        "severity": severity,
        "adjusted_risk_score": round(risk_score, 3),
        "escalation_recommendation": esc,
        "reasoning": "Rule-based context assessment.",
        "mitigating_factors": mit,
        "aggravating_factors": agg,
    }


def run(state: TripState, risk_result: dict[str, Any]) -> dict[str, Any]:
    """
    Assess contextual severity and recommend escalation step.

    Returns:
        {
            "severity": str,
            "adjusted_risk_score": float,
            "escalation_recommendation": str,
            "reasoning": str,
            "mitigating_factors": list,
            "aggravating_factors": list,
            "llm_used": bool
        }
    """
    pos = state.latest_position()
    hour = pos.timestamp.hour if pos else 23
    ctx = enrich_context(
        pos.lat if pos else 12.97,
        pos.lon if pos else 77.59,
        hour,
    )

    payload = {
        **risk_result,
        **ctx,
        "signals": risk_result.get("evidence", []),
    }

    llm_used = False
    result = None

    with Timer() as t:
        for _ in range(min(REACT_MAX_ITERATIONS, 2)):
            result = _call_gemini(payload)
            if result and "severity" in result:
                llm_used = True
                break

        if not result:
            result = _rule_based_assess(risk_result.get("risk_score", 0.0), ctx)

    flag = AgentFlag(
        agent_name="ContextImpactAgent",
        flag_type="context_assessment",
        score=float(result.get("adjusted_risk_score", 0.0)),
        reasoning=result.get("reasoning", ""),
        evidence=result.get("aggravating_factors", []),
        prompt_version=PROMPT_VERSION,
    )
    state.add_flag(flag)

    _log.step(
        trip_id=str(state.trip_id),
        stage="context_impact",
        input_summary=f"risk_score={risk_result.get('risk_score')}, area={ctx.get('area_type')}",
        tool_call="gemini_flash" if llm_used else "rule_based_fallback",
        output_summary=f"severity={result['severity']}, esc={result['escalation_recommendation']}",
        latency_ms=t.elapsed_ms,
        decision=result["escalation_recommendation"],
        prompt_version=PROMPT_VERSION,
    )

    return {**result, "llm_used": llm_used}
