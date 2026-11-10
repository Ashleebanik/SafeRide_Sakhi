# Agent Policy – SafeRide Sakhi
**Version 1.0 · 10 Nov 2026**

---

## Agent Policy Table

| Agent | May | May NOT |
|-------|-----|---------|
| Orchestrator | Route, retry, time out, escalate on failure | Make safety judgements itself |
| Monitor | Assess and explain risk; cite tool evidence | Lower rule-set severity; invent evidence |
| Verifier | Contact users, cross-check data | Declare a case resolved; ignore unclear results |
| Escalation | Send alerts, retry on fallback channels | Send high-severity alerts without operator gate (except explicit SOS) |
| Case Follow-up | Chase deadlines, draft summaries | Close high-severity cases |
| Driver-Safety | Suggest safe stops, open cases, raise rating flags | Change driver ratings or pay |

---

## Override Procedure

1. Operator logs in to the control-room dashboard.
2. Selects the case and chooses **Confirm**, **Dismiss**, or **Edit**.
3. A note is required for Dismiss or Edit.
4. The `operator_gate()` function in `orchestrator.py` writes the action to `AuditLog`.
5. Only after a Confirm does the Escalation agent proceed to notify emergency services.
6. To fully override agent execution, the operator sets `human_override=True` on the case. All subsequent agent steps for that case are suspended.

---

## Prompt and Model Change Log

| Date | Agent | Change | Approved by |
|------|-------|--------|-------------|
| 2026-11-10 | All | Initial prompts (v1) | @Ashlee |

### How to update a prompt
1. Edit the `_SYSTEM` constant in the agent file.
2. Increment `PROMPT_VERSION` (e.g. `"v1"` → `"v2"`).
3. Add a row to this table with the date, agent, description and approver.
4. Every agent log entry records `prompt_version`, so decisions can be traced.

---

## Kill Switch
Set `human_override = True` on any `CaseTable` row via the operator dashboard.
The orchestrator checks this flag before each agent step and stops if set.

---

## Incident Review Log

| Date | Case ID | What happened | Outcome | Action taken |
|------|---------|---------------|---------|--------------|
| *(populated from AuditLog after each run)* | | | | |

---

## Responsible AI Statement

- All data in the prototype is **synthetic**. No real personal data is stored or processed.
- Location is collected only during an active trip.
- Audio recording is opt-in (`consent_recording` flag); default is off.
- Trip data is deleted after `TRIP_DATA_RETENTION_DAYS` (configurable in `.env`).
- Logs are redacted before retention window expiry.
- The system avoids profiling by area or community: risk scores are based only on route, timing and check-in status.
- Every automated action is explained in plain language on the operator dashboard.
