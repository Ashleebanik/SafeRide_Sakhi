"""
SafeRide Sakhi – Operator Control-Room Dashboard (T8.1 / T8.2)
Tabs:
  1. Live Trips        – active trips on Google Maps, risk badges
  2. Alert Queue       – cases awaiting operator action
  3. Case Detail       – agent reasoning, evidence, operator actions
  4. Metrics           – response times, false alarms, cost (T8.2)
  5. Run Scenarios     – launch evaluation scenarios directly in UI
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from saferide_sakhi.config import GOOGLE_MAPS_API_KEY
from saferide_sakhi.tools.db import init_db, seed_db, get_conn
from saferide_sakhi.tools.mcp_servers import (
    case_store_get, case_store_get_actions, messaging_get_log,
    emergency_gateway_get_log,
)
from saferide_sakhi.agents.orchestrator import operator_gate, run_trip_pipeline
from saferide_sakhi.sim.simulator import build_scenario_library, build_trip, SCENARIO_NAMES
from saferide_sakhi.dashboard.google_maps_component import render_google_map

# ── Bootstrap DB ──────────────────────────────────────────────────────────────
@st.cache_resource
def _init():
    init_db()
    seed_db(5)
    return True

_init()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SafeRide Sakhi – Control Room",
    page_icon="🛡️", layout="wide",
)

RISK_COLORS = {1: "#22c55e", 2: "#f59e0b", 3: "#ef4444", 4: "#7c3aed"}
RISK_LABEL  = {1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "CRITICAL"}
RISK_ICONS  = {1: "✅", 2: "⚠️", 3: "🚨", 4: "🆘"}

STATE_COLORS = {
    "DETECTED":          "#94a3b8",
    "TRIAGED":           "#60a5fa",
    "VERIFYING":         "#f59e0b",
    "AWAITING_OPERATOR": "#ef4444",
    "ESCALATED":         "#7c3aed",
    "ACKNOWLEDGED":      "#22c55e",
    "RESPONDING":        "#3b82f6",
    "CLOSED":            "#64748b",
    "FALSE_ALARM":       "#a3e635",
    "TIMEOUT_ESCALATED": "#f97316",
}

# ── Session state ─────────────────────────────────────────────────────────────
if "pipeline_results" not in st.session_state:
    st.session_state.pipeline_results = []

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🛡️ SafeRide Sakhi")
    st.caption("Operator Control Room")
    st.markdown("---")
    tab_choice = st.radio("Navigate", [
        "Live Trips", "Alert Queue", "Case Detail", "Metrics", "Run Scenarios"
    ])
    st.markdown("---")
    st.caption("Synthetic data only. No real personal data.")

# ── Tab: Run Scenarios ────────────────────────────────────────────────────────
if tab_choice == "Run Scenarios":
    st.title("▶ Run Scenarios")
    st.markdown("Select one or more scripted scenarios and run the full agent pipeline.")

    chosen = st.multiselect("Scenarios to run", SCENARIO_NAMES, default=["deviation", "sos", "normal"])
    op_approve = st.checkbox("Simulate operator approval for severity ≥ 3", value=True)

    if st.button("Run selected scenarios", type="primary"):
        st.session_state.pipeline_results = []
        with st.spinner("Running agent pipeline…"):
            for s in chosen:
                trip = build_trip(s)
                events = [e for e in trip.get("events", []) if e.get("type") != "night_time_flag"]
                risk_event = events[0] if events else {
                    "type": "night_time_flag", "severity": 1,
                    "ts": trip["started_at"], "payload": {}
                }
                result = run_trip_pipeline(
                    trip, risk_event,
                    operator_approved=op_approve,
                    dry_run=True,
                )
                result["scenario"] = s
                result["_trip"] = trip
                st.session_state.pipeline_results.append(result)
        st.success(f"Ran {len(chosen)} scenarios.")

    if st.session_state.pipeline_results:
        for r in st.session_state.pipeline_results:
            sev = r.get("severity", 1)
            icon = RISK_ICONS.get(sev, "")
            with st.expander(f"{icon} {r['scenario']} — {r.get('final_state','?')}", expanded=(sev >= 3)):
                st.json({
                    "final_state": r.get("final_state"),
                    "severity":    r.get("severity"),
                    "case_id":     r.get("case_id","")[:12],
                    "monitor_risk_level": r.get("monitor",{}).get("risk_level"),
                    "verifier_verdict":   r.get("verifier",{}).get("verdict"),
                    "escalation_channels": r.get("escalation",{}).get("channels_used"),
                })


# ── Tab: Live Trips ───────────────────────────────────────────────────────────
elif tab_choice == "Live Trips":
    st.title("🗺️ Live Trips")
    results = st.session_state.pipeline_results

    if not results:
        st.info("Run scenarios from the 'Run Scenarios' tab first.")
    else:
        # KPI row
        sev_counts = {1:0, 2:0, 3:0, 4:0}
        for r in results:
            sev_counts[r.get("severity", 1)] = sev_counts.get(r.get("severity", 1), 0) + 1

        c1, c2, c3, c4 = st.columns(4)
        for col, (sev, cnt) in zip([c1,c2,c3,c4], sev_counts.items()):
            col.metric(f"{RISK_ICONS[sev]} {RISK_LABEL[sev]}", cnt)

        st.markdown("---")

        # Google Maps (uses @googlemaps/js-api-loader pattern via components.html)
        if not GOOGLE_MAPS_API_KEY:
            st.info(
                "🗺️ **Google Maps** – add `GOOGLE_MAPS_API_KEY` to your `.env` file "
                "for the full experience. The map below loads in free/no-key mode "
                "(limited, watermarked).",
                icon="ℹ️",
            )
        render_google_map(results, api_key=GOOGLE_MAPS_API_KEY, height=480)

        # Table
        st.markdown("### Trip summary")
        rows = []
        for r in results:
            sev = r.get("severity", 1)
            rows.append({
                "Trip": str(r.get("trip_id",""))[:8],
                "Scenario": r.get("scenario",""),
                "Severity": f"{RISK_ICONS.get(sev,'')} {RISK_LABEL.get(sev,sev)}",
                "Final State": r.get("final_state",""),
                "Monitor Risk": r.get("monitor",{}).get("risk_level","–"),
                "Verdict": r.get("verifier",{}).get("verdict","–"),
                "Latency ms": r.get("total_latency_ms", "–"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ── Tab: Alert Queue ──────────────────────────────────────────────────────────
elif tab_choice == "Alert Queue":
    st.title("🚨 Alert Queue")
    st.caption("Cases awaiting operator action (state = AWAITING_OPERATOR)")

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM CaseTable WHERE state IN ('AWAITING_OPERATOR','DETECTED','TRIAGED','VERIFYING') "
            "ORDER BY severity DESC, opened_at"
        ).fetchall()

    if not rows:
        st.success("No cases awaiting operator review.")
    else:
        for row in rows:
            case = dict(row)
            sev  = case.get("severity", 1)
            icon = RISK_ICONS.get(sev, "⚠️")
            with st.expander(f"{icon} Case {case['id'][:12]} — Severity {sev} — {case['state']}"):
                st.write(f"**Trip:** `{case['trip_id']}`")
                st.write(f"**Opened:** {case['opened_at']}")
                st.write(f"**Due:** {case.get('due_at','')}")

                col_a, col_b, col_c = st.columns(3)
                if col_a.button("✅ Confirm", key=f"confirm_{case['id']}"):
                    operator_gate(case['id'], "confirm", note="dashboard_confirm")
                    st.rerun()
                note_text = col_c.text_input("Note", key=f"note_{case['id']}")
                if col_b.button("❌ Dismiss", key=f"dismiss_{case['id']}"):
                    operator_gate(case['id'], "dismiss",
                                  note=note_text or "dismissed_from_dashboard")
                    st.rerun()


# ── Tab: Case Detail ──────────────────────────────────────────────────────────
elif tab_choice == "Case Detail":
    st.title("🔍 Case Detail")

    with get_conn() as conn:
        all_cases = conn.execute(
            "SELECT id, severity, state, trip_id, opened_at FROM CaseTable ORDER BY opened_at DESC LIMIT 50"
        ).fetchall()

    if not all_cases:
        st.info("No cases in the database yet. Run scenarios first.")
    else:
        case_options = {f"{dict(r)['id'][:12]} | sev={dict(r)['severity']} | {dict(r)['state']}": dict(r)['id']
                        for r in all_cases}
        chosen_label = st.selectbox("Select case", list(case_options.keys()))
        case_id = case_options[chosen_label]

        case = case_store_get(case_id)
        actions = case_store_get_actions(case_id)
        msgs = [m for m in messaging_get_log() if m.get("case_id") == case_id]

        st.markdown("### Case Record")
        st.json(case)

        st.markdown("### Agent Action Timeline")
        if actions:
            df = pd.DataFrame(actions)
            st.dataframe(df[["ts", "agent", "action", "result"]],
                         use_container_width=True, hide_index=True)
        else:
            st.caption("No actions logged yet.")

        st.markdown("### Messages Sent")
        if msgs:
            for m in msgs:
                st.markdown(
                    f"- `{m['ts'][:19]}` **[{m['channel']}]** → `{m['recipient']}`: "
                    f"{m['body'][:80]}"
                )
        else:
            st.caption("No messages for this case.")

        st.markdown("### Human Override")
        override_note = st.text_input("Override note")
        col1, col2 = st.columns(2)
        if col1.button("✅ Confirm & Escalate"):
            operator_gate(case_id, "confirm", note=override_note)
            st.success("Case confirmed and escalated.")
            st.rerun()
        if col2.button("❌ Dismiss as False Alarm"):
            operator_gate(case_id, "dismiss", note=override_note or "false_alarm")
            st.success("Case dismissed.")
            st.rerun()


# ── Tab: Metrics (T8.2) ───────────────────────────────────────────────────────
elif tab_choice == "Metrics":
    st.title("📊 Metrics")

    eval_file = ROOT / "saferide_sakhi" / "data" / "eval_results.json"

    if st.button("Run evaluation (all 20+ scenarios)"):
        with st.spinner("Running full evaluation..."):
            from saferide_sakhi.eval.runner import run_eval
            metrics = run_eval(dry_run=True)
            st.session_state["eval_metrics"] = metrics

    metrics = st.session_state.get("eval_metrics")
    if not metrics and eval_file.exists():
        metrics = json.loads(eval_file.read_text())
        st.session_state["eval_metrics"] = metrics

    if metrics:
        s = metrics.get("summary", {})
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Precision", f"{s.get('precision',0):.2f}")
        c2.metric("Recall",    f"{s.get('recall',0):.2f}")
        c3.metric("False Alarm Rate", f"{s.get('false_alarm_rate',0):.2f}")
        c4.metric("p50 Latency", f"{s.get('latency_p50_ms',0):.0f} ms")

        c5, c6, c7, _ = st.columns(4)
        c5.metric("True Positives",  s.get("true_positives",0))
        c6.metric("False Positives", s.get("false_positives",0))
        c7.metric("p95 Latency",     f"{s.get('latency_p95_ms',0):.0f} ms")

        st.markdown("---")
        st.markdown("### Per-scenario Results")
        df = pd.DataFrame(metrics.get("per_scenario", []))
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)

        # Message delivery stats
        all_msgs = messaging_get_log()
        emg_log  = emergency_gateway_get_log()
        st.markdown("---")
        st.markdown("### Delivery Statistics")
        col_l, col_r = st.columns(2)
        col_l.metric("Mock SMS/Push sent", len(all_msgs))
        col_r.metric("Emergency packets logged", len(emg_log))

    else:
        st.info("Click 'Run evaluation' to generate metrics.")

st.markdown("---")
st.caption("SafeRide Sakhi · Control Room · Synthetic data · IBM Bob + IBM Granite + Gemini + Groq")
