"""Agent 6 – Alert & Escalation Agent  (Groq / Llama 3)
Runs the Nudge → Alert → Emergency ladder:
  - Nudge: asks the rider
  - Alert: notifies trusted contacts
  - Emergency: hands over to control room and 112.
Uses Groq (Llama3-70B) for very low-latency alert message generation.
POLICY: Never contact emergency services on an LLM output alone.
         A human-in-the-loop review is required from Alert level upward.
"""
from __future__ import annotations

import json
from typing import Any

from saferide_sakhi.config import GROQ_API_KEY, GROQ_MODEL, REACT_MAX_ITERATIONS
from saferide_sakhi.logger import AgentLogger, Timer
from saferide_sakhi.models import EscalationStep, TripState
from saferide_sakhi.mcp_tools.tools import dispatch_alert

_log = AgentLogger("AlertEscalationAgent")

PROMPT_VERSION = "v1"

_SYSTEM_PROMPT = """You are the Alert & Escalation Agent for SafeRide Sakhi, a women's
night-travel safety system in India.  Draft a SHORT, calm, non-alarming message
for the specified escalation step.

Rules:
- Nudge message: addressed to rider, asks if she is safe, max 1 sentence.
- Alert message: addressed to trusted contact, states concern briefly, max 2 sentences.
- Emergency message: addressed to control room, factual, includes trip ID and risk, max 3 sentences.
- Never use alarming caps or exclamation marks.
- Reply ONLY with JSON: {"message": "<text>"}
"""


def _call_groq(step: str, trip_id: str, reasoning: str) -> str | None:
    if not GROQ_API_KEY:
        return None
    try:
        from groq import Groq

        client = Groq(api_key=GROQ_API_KEY)
        payload = json.dumps({"step": step, "trip_id": trip_id, "reasoning": reasoning})
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": payload},
            ],
            max_tokens=120,
            temperature=0.3,
        )
        text = resp.choices[0].message.content.strip()
        parsed = json.loads(text)
        return parsed.get("message")
    except Exception as exc:
        _log.error("llm_call", "groq_call_failed", str(exc))
        return None


_FALLBACK_MESSAGES = {
    "nudge_rider": "Hi, just checking in – are you safe? Tap OK to confirm.",
    "notify_contacts": "This is SafeRide Sakhi. We detected an unusual pattern on a trip and wanted to let you know. Please check in with your contact.",
    "alert_control_room": "Control room alert: unusual trip pattern detected. Human review required.",
    "dispatch_emergency": "Emergency escalation requested. Please review and decide on contacting 112.",
}


def run(
    state: TripState,
    escalation_recommendation: str,
    reasoning: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    Execute the recommended escalation step.

    POLICY: From 'alert_control_room' upward, the action is flagged for
    human review and NOT automatically dispatched (dry_run enforced regardless
    of the dry_run parameter).

    Returns:
        {
            "escalation_step": str,
            "message": str,
            "dispatched": bool,
            "human_review_required": bool,
            "llm_used": bool
        }
    """
    step_map = {
        "none":                EscalationStep.NONE,
        "nudge_rider":         EscalationStep.NUDGE_RIDER,
        "notify_contacts":     EscalationStep.NOTIFY_CONTACTS,
        "alert_control_room":  EscalationStep.ALERT_CONTROL_ROOM,
        "dispatch_emergency":  EscalationStep.DISPATCH_EMERGENCY,
    }
    esc_step = step_map.get(escalation_recommendation, EscalationStep.NONE)

    # POLICY: control room and above always require human review
    human_review_required = esc_step in (
        EscalationStep.ALERT_CONTROL_ROOM,
        EscalationStep.DISPATCH_EMERGENCY,
    )
    effective_dry_run = dry_run or human_review_required

    llm_used = False
    message = ""

    with Timer() as t:
        if esc_step == EscalationStep.NONE:
            return {
                "escalation_step": "none",
                "message": "",
                "dispatched": False,
                "human_review_required": False,
                "llm_used": False,
            }

        # Determine recipient
        recipient = "rider"
        if esc_step == EscalationStep.NOTIFY_CONTACTS:
            contacts = state.rider.trusted_contacts
            recipient = contacts[0].phone if contacts else "trusted_contact"
        elif esc_step in (EscalationStep.ALERT_CONTROL_ROOM, EscalationStep.DISPATCH_EMERGENCY):
            recipient = "control_room"

        # Try Groq for message generation
        for _ in range(min(REACT_MAX_ITERATIONS, 2)):
            msg = _call_groq(escalation_recommendation, str(state.trip_id), reasoning)
            if msg:
                message = msg
                llm_used = True
                break

        if not message:
            message = _FALLBACK_MESSAGES.get(escalation_recommendation, "Safety check triggered.")

        dispatch_result = dispatch_alert(
            trip_id=str(state.trip_id),
            level=escalation_recommendation,
            message=message,
            recipient=recipient,
            dry_run=effective_dry_run,
        )

        state.escalation_step = esc_step

    _log.step(
        trip_id=str(state.trip_id),
        stage="alert_escalation",
        input_summary=f"recommended={escalation_recommendation}",
        tool_call="groq_llama3" if llm_used else "fallback_message",
        output_summary=f"step={esc_step.value}, human_review={human_review_required}",
        latency_ms=t.elapsed_ms,
        decision=esc_step.value,
        prompt_version=PROMPT_VERSION,
    )

    return {
        "escalation_step": esc_step.value,
        "message": message,
        "dispatched": dispatch_result["dispatched"],
        "human_review_required": human_review_required,
        "llm_used": llm_used,
    }
