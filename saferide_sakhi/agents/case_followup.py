"""
Case Follow-up Agent – T4.5
Goal: make sure no case is dropped – deadlines met, user hears back, record complete.
LLM: Gemini (summaries and tone).
Guardrails:
  - Only humans can close high-severity cases.
  - Summaries must reference logged events only.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from saferide_sakhi.llm_gateway import call as llm_call
from saferide_sakhi.logger import AgentLogger, Timer
from saferide_sakhi.tools.allowlists import FollowUpOutput, validate_output
from saferide_sakhi.tools.mcp_servers import (
    CaseActionRecord, MessagePacket,
    case_store_add_action, case_store_get, case_store_get_actions,
    case_store_transition, messaging_send, sop_search,
)

_log = AgentLogger("CaseFollowUpAgent")
PROMPT_VERSION = "v1"

_SUMMARY_PROMPT = """You are the Case Follow-up Agent. Draft a professional case summary
from the logged actions below. Return ONLY JSON:
{{
  "status": "<open|pending_closure|closed>",
  "next_action": "<string>",
  "due_at": "<ISO timestamp or empty>",
  "summary": "<3 sentences max, only facts from actions>"
}}

Case: {case_id}
Logged actions:
{actions}

Rules:
- Do not invent facts not present in the actions list.
- High-severity cases (severity >= 3) cannot be marked closed by this agent.
"""


def run(
    case_id: str,
    high_severity_close_approved: bool = False,
) -> dict[str, Any]:
    """
    Check deadlines, chase pending actions, draft summary.
    Returns FollowUpOutput as dict.
    """
    case = case_store_get(case_id)
    if not case:
        return {"status": "not_found", "next_action": "", "due_at": "", "summary": ""}

    actions = case_store_get_actions(case_id)
    sop_hits = sop_search("case closure follow-up procedure", top_k=2)

    severity = case.get("severity", 1)
    state = case.get("state", "DETECTED")
    due_at = case.get("due_at", "")
    now = datetime.utcnow()

    # Deadline check
    overdue = False
    if due_at:
        try:
            due_dt = datetime.fromisoformat(due_at.replace("Z", ""))
            overdue = now > due_dt
        except Exception:
            pass

    if overdue:
        # Chase pending – send reminder to operator
        messaging_send(MessagePacket(
            case_id=case_id, channel="push",
            recipient="control_room",
            body=f"Case {case_id[:8]} is overdue. Please review.",
            priority="high",
        ))
        case_store_transition(case_id, "TIMEOUT_ESCALATED")

    # Contact user after incident
    if state in ("ESCALATED", "RESPONDING", "ACKNOWLEDGED"):
        messaging_send(MessagePacket(
            case_id=case_id, channel="sms",
            recipient="passenger",
            body="SafeRide Sakhi: Following up – are you safe and home? "
                 "Please reply to confirm.",
            priority="normal",
        ))

    prompt = _SUMMARY_PROMPT.format(
        case_id=case_id,
        actions=json.dumps(actions, indent=2)[:2000],
    )

    with Timer() as t:
        resp = llm_call("gemini", prompt, max_tokens=350,
                        agent="case_followup", trip_id="")

    raw: dict[str, Any] = {}
    if resp.success:
        try:
            text = resp.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1].lstrip("json").strip()
            raw = json.loads(text)
        except Exception:
            pass

    # Guardrail: high-severity cannot be closed without human approval
    if severity >= 3 and not high_severity_close_approved:
        if raw.get("status") == "closed":
            raw["status"] = "pending_closure"
            raw["next_action"] = "awaiting_human_approval_to_close"

    raw.setdefault("status", "open")
    raw.setdefault("next_action", "monitor")
    raw.setdefault("due_at", due_at)
    raw.setdefault("summary", "Case in progress.")

    def _retry() -> dict[str, Any]:
        return {"status": "open", "next_action": "retry_failed",
                "due_at": due_at, "summary": "Follow-up summary unavailable."}

    validated = validate_output("case_followup", raw, FollowUpOutput, _retry)
    if validated is None:
        validated = FollowUpOutput(status="open", next_action="escalate_operator",
                                   due_at=due_at, summary="Agent failed; human review required.")

    case_store_add_action(CaseActionRecord(
        case_id=case_id, agent="case_followup",
        action="follow_up", result=json.dumps(validated.model_dump()),
    ))

    _log.step(
        trip_id=case.get("trip_id", ""), stage="case_followup",
        input_summary=f"case={case_id}, severity={severity}, overdue={overdue}",
        tool_call="gemini,case_store,messaging,sop_search",
        output_summary=f"status={validated.status}, next={validated.next_action}",
        latency_ms=t.elapsed_ms,
        decision=validated.status,
        prompt_version=PROMPT_VERSION,
    )
    return validated.model_dump()
