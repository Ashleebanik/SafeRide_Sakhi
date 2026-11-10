"""Agent 4 – Risk & Anomaly Detection Agent  (IBM Granite 4)
Scores deviations, unusual stops, long silence and missed check-ins,
and flags rising risk.  Uses IBM Granite 4 for governed risk reasoning
via the ReAct pattern.
"""
from __future__ import annotations

import json
import os
from typing import Any

from saferide_sakhi.config import (
    GRANITE_MODEL_ID,
    REACT_MAX_ITERATIONS,
    RISK_ALERT_THRESHOLD,
    RISK_EMERGENCY_THRESHOLD,
    RISK_NUDGE_THRESHOLD,
    WATSONX_API_KEY,
    WATSONX_PROJECT_ID,
    WATSONX_URL,
)
from saferide_sakhi.logger import AgentLogger, Timer
from saferide_sakhi.models import AgentFlag, RiskLevel, TripState

_log = AgentLogger("RiskAnomalyAgent")

PROMPT_VERSION = "v1"

_SYSTEM_PROMPT = """You are the Risk & Anomaly Detection Agent for SafeRide Sakhi, a women's
night-travel safety system. Your job is to score the risk of an active trip
based on signals from the monitoring layer.

You receive a JSON object with these fields:
- signals: list of detected anomaly strings
- context: time of night, area type, lighting
- trip_id: trip identifier

Respond ONLY with a JSON object matching this schema (no extra text):
{
  "risk_score": <float 0.0-1.0>,
  "risk_level": <"safe"|"nudge"|"alert"|"emergency">,
  "reasoning": "<one sentence grounded in the signals>",
  "evidence": ["<signal1>", ...]
}

Rules:
- Cite only the signals provided; never invent new facts.
- risk_score >= 0.80 → emergency
- risk_score >= 0.60 → alert
- risk_score >= 0.35 → nudge
- risk_score < 0.35  → safe
"""


def _rule_based_score(signals: list[str]) -> float:
    """Fallback deterministic scorer when LLM is unavailable."""
    score = 0.0
    for sig in signals:
        if "route_deviation" in sig:
            try:
                metres = float(sig.split("_")[-1].replace("m", ""))
                score += min(metres / 1000, 0.4)
            except ValueError:
                score += 0.2
        if "unplanned_stops" in sig:
            score += 0.2
        if "silence_alert" in sig:
            score += 0.35
        if "silence_nudge" in sig:
            score += 0.15
    return min(score, 1.0)


def _score_to_level(score: float) -> RiskLevel:
    if score >= RISK_EMERGENCY_THRESHOLD:
        return RiskLevel.EMERGENCY
    if score >= RISK_ALERT_THRESHOLD:
        return RiskLevel.ALERT
    if score >= RISK_NUDGE_THRESHOLD:
        return RiskLevel.NUDGE
    return RiskLevel.SAFE


def _call_granite(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Call IBM Granite 4 via watsonx.ai REST.  Returns parsed JSON or None."""
    if not WATSONX_API_KEY or not WATSONX_PROJECT_ID:
        return None
    try:
        import httpx  # local import to avoid hard dependency in tests

        url = f"{WATSONX_URL}/ml/v1/text/generation?version=2024-05-01"
        headers = {
            "Authorization": f"Bearer {WATSONX_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "model_id": GRANITE_MODEL_ID,
            "project_id": WATSONX_PROJECT_ID,
            "input": _SYSTEM_PROMPT + "\n\nTrip data:\n" + json.dumps(payload),
            "parameters": {
                "decoding_method": "greedy",
                "max_new_tokens": 256,
                "stop_sequences": ["\n\n"],
            },
        }
        resp = httpx.post(url, headers=headers, json=body, timeout=15.0)
        resp.raise_for_status()
        text = resp.json()["results"][0]["generated_text"].strip()
        return json.loads(text)
    except Exception as exc:
        _log.error("llm_call", "granite_call_failed", str(exc))
        return None


def run(state: TripState, monitoring_result: dict[str, Any]) -> dict[str, Any]:
    """
    Score risk for the current trip state.

    Returns:
        {
            "risk_score": float,
            "risk_level": str,
            "reasoning": str,
            "evidence": list[str],
            "llm_used": bool
        }
    """
    signals: list[str] = monitoring_result.get("signals", [])
    pos = state.latest_position()
    hour = pos.timestamp.hour if pos else 23
    context = {
        "hour": hour,
        "late_night": hour >= 22 or hour <= 4,
    }
    payload = {
        "trip_id": str(state.trip_id),
        "signals": signals,
        "context": context,
    }

    llm_used = False
    llm_result = None

    with Timer() as t:
        # Try Granite 4 first (ReAct loop capped at REACT_MAX_ITERATIONS)
        for _ in range(min(REACT_MAX_ITERATIONS, 2)):
            llm_result = _call_granite(payload)
            if llm_result and "risk_score" in llm_result:
                llm_used = True
                break

        if not llm_result:
            # Fallback: deterministic rule-based scorer
            score = _rule_based_score(signals)
            llm_result = {
                "risk_score": round(score, 3),
                "risk_level": _score_to_level(score).value,
                "reasoning": f"Rule-based score from {len(signals)} signals.",
                "evidence": signals,
            }

    # Validate output schema
    risk_score: float = float(llm_result.get("risk_score", 0.0))
    risk_level: str   = _score_to_level(risk_score).value
    reasoning: str    = str(llm_result.get("reasoning", ""))
    evidence: list    = list(llm_result.get("evidence", signals))

    flag = AgentFlag(
        agent_name="RiskAnomalyAgent",
        flag_type="risk_score",
        score=risk_score,
        reasoning=reasoning,
        evidence=evidence,
        prompt_version=PROMPT_VERSION,
    )
    state.add_flag(flag)
    state.risk_score = risk_score
    state.risk_level = RiskLevel(risk_level)

    _log.step(
        trip_id=str(state.trip_id),
        stage="risk_scoring",
        input_summary=f"signals={signals}",
        tool_call="ibm_granite_4" if llm_used else "rule_based_fallback",
        output_summary=f"score={risk_score:.3f}, level={risk_level}",
        latency_ms=t.elapsed_ms,
        decision=f"risk_level={risk_level}",
        prompt_version=PROMPT_VERSION,
    )

    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "reasoning": reasoning,
        "evidence": evidence,
        "llm_used": llm_used,
    }
