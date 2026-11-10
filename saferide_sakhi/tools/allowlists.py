"""
Per-agent tool allow-lists and output schema validation – T3.3
Each agent may only call the tools on its allow-list.
All agent outputs are validated against their Pydantic schema.
Invalid output → one retry → escalate to operator.
"""
from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError

# ── Allow-lists ───────────────────────────────────────────────────────────────

AGENT_TOOL_ALLOWLIST: dict[str, set[str]] = {
    "orchestrator":   {"case_store", "all_agents"},
    "monitor":        {"trip_store", "route_service", "driver_registry", "sop_search"},
    "verifier":       {"messaging", "trip_store", "route_service", "driver_registry"},
    "escalation":     {"messaging", "emergency_gateway", "case_store"},
    "case_followup":  {"case_store", "messaging", "sop_search"},
    "driver_safety":  {"trip_store", "route_service", "case_store", "messaging"},
}


def check_tool_allowed(agent: str, tool: str) -> None:
    allowed = AGENT_TOOL_ALLOWLIST.get(agent, set())
    if "all_agents" not in allowed and tool not in allowed:
        raise PermissionError(
            f"Agent '{agent}' is not allowed to call tool '{tool}'. "
            f"Allowed: {sorted(allowed)}"
        )


# ── Agent output schemas ──────────────────────────────────────────────────────

class MonitorOutput(BaseModel):
    case_id: str
    risk_level: int = Field(ge=1, le=4)
    reasons: list[str]
    evidence_refs: list[str] = Field(default_factory=list)
    recommended_checks: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class VerifierOutput(BaseModel):
    verdict: str   # confirmed | likely_false | unclear
    evidence: list[str] = Field(default_factory=list)
    passenger_response: str = ""
    driver_response: str = ""

    def model_post_init(self, __context: Any) -> None:
        if self.verdict not in ("confirmed", "likely_false", "unclear"):
            raise ValueError(f"Invalid verdict: {self.verdict}")


class EscalationOutput(BaseModel):
    channels_used: list[str]
    delivered: bool
    acknowledged_by: str = ""
    time_to_ack: float = 0.0   # seconds


class FollowUpOutput(BaseModel):
    status: str
    next_action: str
    due_at: str
    summary: str


class DriverSafetyOutput(BaseModel):
    case_id: str = ""
    safe_stop_options: list[dict] = Field(default_factory=list)
    rating_review_flag: bool = False
    report_summary: str = ""


# ── Validation wrapper with retry-then-escalate ───────────────────────────────

def validate_output(
    agent: str,
    raw: dict[str, Any],
    schema: type[BaseModel],
    retry_fn: Callable[[], dict[str, Any]] | None = None,
) -> BaseModel | None:
    """
    Validate agent output against schema.
    If invalid: retry once (if retry_fn provided), then return None
    (caller must escalate to operator).
    """
    try:
        return schema(**raw)
    except (ValidationError, Exception) as first_err:
        if retry_fn is not None:
            try:
                raw2 = retry_fn()
                return schema(**raw2)
            except Exception:
                pass
        # Escalate to operator by returning None
        from saferide_sakhi.tools.mcp_servers import _audit
        _audit(agent, f"invalid_output_escalated: {str(first_err)[:120]}", "")
        return None
