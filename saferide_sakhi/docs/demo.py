"""
Scripted Demo – T10.2
A complete walkthrough: night trip with deviation, verification,
operator confirmation, escalation and follow-up.
Run:  python -m saferide_sakhi.docs.demo
"""
from __future__ import annotations

import json
from saferide_sakhi.tools.db import init_db, seed_db
from saferide_sakhi.sim.simulator import build_trip
from saferide_sakhi.agents.orchestrator import operator_gate, run_trip_pipeline
from saferide_sakhi.agents.case_followup import run as followup_run
from saferide_sakhi.tools.mcp_servers import messaging_get_log, emergency_gateway_get_log


def _divider(title: str) -> None:
    print(f"\n{'='*60}\n  {title}\n{'='*60}")


def run_demo() -> None:
    _divider("SafeRide Sakhi – Scripted Demo")
    print("All data is SYNTHETIC. No real personal data is used.")

    # ── Setup ─────────────────────────────────────────────────────────────────
    _divider("Phase 0: Initialise")
    init_db()
    seed_db(3)
    print("[OK] database initialised with 3 synthetic drivers")

    # ── Scenario: night trip with route deviation ──────────────────────────────
    _divider("Phase 1: Night Trip Starts – Route Deviation Injected")
    trip = build_trip("deviation")
    print(f"Trip ID:      {trip['trip_id'][:12]}...")
    print(f"Scenario:     {trip['scenario']}")
    print(f"Started at:   {trip['started_at']}")
    print(f"Events:       {[e['type'] for e in trip['events']]}")

    # Pick the deviation event
    risk_event = next(e for e in trip["events"] if e["type"] == "route_deviation")
    print(f"\nRisk event raised: {risk_event['type']} | severity={risk_event['severity']}")
    print(f"Deviation:         {risk_event['payload']['deviation_m']:.0f} m from planned route")

    # ── Run pipeline without operator approval → lands at AWAITING_OPERATOR ────
    _divider("Phase 2: Agent Pipeline Runs (no operator approval yet)")
    result = run_trip_pipeline(
        trip, risk_event,
        operator_approved=False,
        mock_passenger_response="I'm fine, just a different route",
        mock_driver_response="Traffic, taking alternate road",
        dry_run=True,
    )
    print(f"Monitor risk level:    {result.get('monitor', {}).get('risk_level')}")
    print(f"Monitor reasons:       {result.get('monitor', {}).get('reasons')}")
    print(f"Verifier verdict:      {result.get('verifier', {}).get('verdict')}")
    print(f"Pipeline state:        {result.get('final_state')}")
    print(f"Awaiting operator:     {result.get('awaiting_operator', False)}")

    # ── Operator confirms ──────────────────────────────────────────────────────
    _divider("Phase 3: Operator Reviews and Confirms")
    case_id = result.get("case_id", "")
    if case_id:
        gate = operator_gate(case_id, "confirm",
                             operator_id="operator_demo",
                             note="Confirmed – deviation looks suspicious at this hour")
        print(f"Operator action:       {gate['action']}")
        print(f"Case new state:        {gate['new_state']}")
        print(f"Audit entry written:   yes")
    else:
        print("[!] No case_id yet – pipeline returned early")

    # ── Re-run with approval ───────────────────────────────────────────────────
    _divider("Phase 4: Escalation Executes")
    result2 = run_trip_pipeline(
        trip, risk_event,
        operator_approved=True,
        mock_passenger_response="I'm fine, just a different route",
        mock_driver_response="Traffic, taking alternate road",
        dry_run=True,
    )
    esc = result2.get("escalation", {})
    print(f"Channels used:         {esc.get('channels_used')}")
    print(f"Delivered:             {esc.get('delivered')}")
    print(f"Human review required: {esc.get('blocked_pending_operator', False)}")

    # ── Messages sent ──────────────────────────────────────────────────────────
    _divider("Phase 5: Messages Log")
    msgs = messaging_get_log()
    for m in msgs[-4:]:
        print(f"  [{m['channel']}] -> {m['recipient']}: {m['body'][:70]}")

    # ── Follow-up ──────────────────────────────────────────────────────────────
    _divider("Phase 6: Case Follow-up")
    case_id2 = result2.get("case_id", case_id)
    if case_id2:
        fu = followup_run(case_id2)
        print(f"Follow-up status:      {fu['status']}")
        print(f"Next action:           {fu['next_action']}")
        print(f"Summary:               {fu['summary'][:120]}")
    else:
        print("[!] No case to follow up")

    # ── Emergency log ──────────────────────────────────────────────────────────
    emg = emergency_gateway_get_log()
    if emg:
        _divider("Emergency Gateway Log")
        for e in emg:
            print(f"  Packet: case={e['case_id'][:8]} severity={e['severity']}")

    _divider("Demo Complete")
    print("Key outputs:")
    print("  - Agent chain: Monitor -> Verifier -> Operator Gate -> Escalation -> Follow-up")
    print("  - SOS would have skipped Monitor and Verifier entirely")
    print("  - No real emergency services were contacted (dry_run=True)")
    print("  - All actions written to AuditLog in saferide.db")
    print("  - Agent step log at saferide_sakhi/logs/saferide_sakhi.jsonl")


if __name__ == "__main__":
    run_demo()
