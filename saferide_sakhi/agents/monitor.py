"""
Monitor Agent – T4.2
Goal: turn a raw risk event into a triaged, explained risk assessment.
LLM: Groq (low-latency fast triage).
Guardrails:
  - May NOT lower a severity the rules engine set.
  - May only cite evidence returned by tools.
  - Output validated against MonitorOutput schema.
"""
from __future__ import annotations

import json
from typing import Any

from saferide_sakhi.llm_gateway import call as llm_call
from saferide_sakhi.logger import AgentLogger, Timer
from saferide_sakhi.tools.allowlists import MonitorOutput, validate_output
from saferide_sakhi.tools.mcp_servers import (
    case_store_add_action, case_store_open,
    route_service_get_planned, sop_search, trip_store_get, trip_store_get_pings,
    CaseActionRecord,
)

_log = AgentLogger("MonitorAgent")
PROMPT_VERSION = "v1"

_SYSTEM = """You are the Monitor Agent for a women's night-ride safety system.
Triage a risk event and return ONLY valid JSON matching this exact schema:
{
  "case_id": "<string>",
  "risk_level": <integer 1-4>,
  "reasons": ["<string>"],
  "evidence_refs": ["<tool:field:value>"],
  "recommended_checks": ["<string>"],
  "confidence": <float 0.0-1.0>
}

Rules:
- risk_level MUST be >= the rule_severity in the input (never lower it).
- Only cite facts from trip_context or sop_hits fields in evidence_refs.
- recommended_checks must be from: [check_passenger, check_driver, cross_check_route,
  verify_vehicle, check_contacts, escalate_operator]
"""


def run(
    risk_event: dict[str, Any],
    trip_id: str,
    case_id: str = "",
) -> dict[str, Any]:
    """
    Triage one risk event.
    Opens a Case if none exists yet.
    Returns MonitorOutput as dict, or raises on unrecoverable failure.
    """
    # ── Tool calls (allow-listed) ─────────────────────────────────────────────
    trip = trip_store_get(trip_id) or {}
    pings = trip_store_get_pings(trip_id)[-5:]    # last 5 pings
    planned = route_service_get_planned(trip_id)
    sop_hits = sop_search(
        f"{risk_event.get('type')} severity {risk_event.get('severity')}", top_k=2
    )

    rule_severity: int = risk_event.get("severity", 1)

    if not case_id:
        case_id = case_store_open(trip_id, rule_severity)

    payload = {
        "case_id": case_id,
        "risk_event": risk_event,
        "trip_context": {
            "driver_id": trip.get("driver_id"),
            "status": trip.get("status"),
            "recent_pings": pings,
            "planned_waypoints": planned[:3],
        },
        "sop_hits": sop_hits,
        "rule_severity": rule_severity,
    }

    prompt = _SYSTEM + "\n\nInput:\n" + json.dumps(payload)

    with Timer() as t:
        resp = llm_call("groq", prompt, max_tokens=400,
                        agent="monitor", trip_id=trip_id)

    raw: dict[str, Any] = {}
    if resp.success:
        try:
            text = resp.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1].lstrip("json").strip()
            raw = json.loads(text)
        except Exception:
            pass

    # Enforce guardrail: never lower rule severity
    if raw.get("risk_level", 0) < rule_severity:
        raw["risk_level"] = rule_severity

    # Ensure case_id is propagated
    raw.setdefault("case_id", case_id)
    raw.setdefault("reasons", [risk_event.get("type", "unknown")])
    raw.setdefault("confidence", 0.7)

    # Validate with retry
    def _retry() -> dict[str, Any]:
        raw2 = dict(raw)
        raw2["risk_level"] = max(raw2.get("risk_level", rule_severity), rule_severity)
        raw2.setdefault("reasons", ["triage_retry"])
        raw2.setdefault("evidence_refs", [])
        raw2.setdefault("recommended_checks", ["check_passenger"])
        raw2.setdefault("confidence", 0.5)
        return raw2

    validated = validate_output("monitor", raw, MonitorOutput, _retry)
    if validated is None:
        # Fail-safe: escalate to operator with minimum viable output
        validated = MonitorOutput(
            case_id=case_id,
            risk_level=rule_severity,
            reasons=["monitor_agent_failed_fallback"],
            evidence_refs=[],
            recommended_checks=["escalate_operator"],
            confidence=0.0,
        )

    # Log action to case store
    case_store_add_action(CaseActionRecord(
        case_id=case_id,
        agent="monitor",
        action="triage",
        result=json.dumps(validated.model_dump()),
        ts="",
    ))

    _log.step(
        trip_id=trip_id,
        stage="monitor_triage",
        input_summary=f"event={risk_event.get('type')}, rule_sev={rule_severity}",
        tool_call="groq,trip_store,route_service,sop_search",
        output_summary=f"risk_level={validated.risk_level}, confidence={validated.confidence}",
        latency_ms=t.elapsed_ms,
        decision=f"checks={validated.recommended_checks}",
        prompt_version=PROMPT_VERSION,
    )

    return validated.model_dump()
