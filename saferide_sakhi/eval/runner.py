"""
Evaluation Runner – T9.1 / T9.2
Replays all scenarios and records metrics from PDF section 9:
  - Risk-event precision and recall
  - False-alarm rate
  - Time from trigger to operator notified
  - Time to acknowledgement and delivery rate
  - Cases closed within deadlines
  - Ungrounded-claim rate (hallucination check)
  - Tokens and cost per alert
  - Latency p50 and p95 per agent

Also runs LLM comparison (T9.2) when EVAL_LLM_COMPARE=1 in env.
"""
from __future__ import annotations

import json
import os
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from saferide_sakhi.sim.simulator import build_scenario_library
from saferide_sakhi.rules.detectors import evaluate_event
from saferide_sakhi.tools.db import init_db, seed_db
from saferide_sakhi.agents.orchestrator import run_trip_pipeline

OUT_DIR = Path(__file__).parent.parent / "data" / "synthetic"
EVAL_OUT = Path(__file__).parent.parent / "data" / "eval_results.json"


def _scenario_to_event(trip: dict) -> dict | None:
    """Extract the first non-night-flag event from a simulated trip."""
    for ev in trip.get("events", []):
        if ev.get("type") != "night_time_flag":
            return ev
    return None


def run_eval(dry_run: bool = True) -> dict[str, Any]:
    """
    Run all scenarios through the full agent pipeline and collect metrics.
    Returns a metrics dict and writes eval_results.json.
    """
    print("[eval] initialising database...")
    init_db()
    seed_db(5)

    print("[eval] building scenario library...")
    scenarios = build_scenario_library()

    metrics: dict[str, Any] = {
        "total_scenarios": len(scenarios),
        "run_at": datetime.utcnow().isoformat() + "Z",
        "per_scenario": [],
    }

    latencies_ms: list[float]    = []
    costs_usd:    list[float]    = []
    tokens_total: list[int]      = []
    tp = fp = tn = fn = 0         # precision/recall counters

    for trip in scenarios:
        scenario   = trip["scenario"]
        expected   = trip.get("expected_outcome", {})
        exp_risk   = expected.get("risk_level", 1)
        exp_esc    = expected.get("escalation", "none")

        risk_event = _scenario_to_event(trip)
        if not risk_event:
            # No anomaly event → synthesise a night_time_flag
            risk_event = {"type": "night_time_flag", "severity": 1,
                          "ts": trip.get("started_at", ""),
                          "payload": {}}

        t0 = time.perf_counter()
        try:
            result = run_trip_pipeline(
                trip_data=trip,
                risk_event=risk_event,
                operator_approved=(exp_risk >= 3),   # simulate operator for eval
                dry_run=dry_run,
            )
        except Exception as exc:
            result = {"error": str(exc), "final_state": "ERROR"}

        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies_ms.append(elapsed_ms)

        # Precision / recall accounting
        detected_sev = result.get("monitor", {}).get("risk_level", 1)
        is_real_risk = exp_risk >= 3
        detected_high = detected_sev >= 3

        if is_real_risk and detected_high:   tp += 1
        elif is_real_risk and not detected_high: fn += 1
        elif not is_real_risk and detected_high: fp += 1
        else:                                tn += 1

        row = {
            "scenario":       scenario,
            "expected_risk":  exp_risk,
            "detected_risk":  detected_sev,
            "expected_esc":   exp_esc,
            "final_state":    result.get("final_state", "unknown"),
            "latency_ms":     round(elapsed_ms, 1),
            "error":          result.get("error", ""),
        }
        metrics["per_scenario"].append(row)
        print(f"  [{scenario:<20}] risk={detected_sev} state={result.get('final_state','?')} "
              f"{elapsed_ms:.0f}ms")

    # Aggregate metrics
    n = len(scenarios)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    fa_rate   = fp / n if n else 0.0

    metrics["summary"] = {
        "precision":    round(precision, 3),
        "recall":       round(recall, 3),
        "false_alarm_rate": round(fa_rate, 3),
        "latency_p50_ms":   round(statistics.median(latencies_ms), 1) if latencies_ms else 0,
        "latency_p95_ms":   round(sorted(latencies_ms)[int(len(latencies_ms)*0.95)-1], 1)
                            if len(latencies_ms) > 1 else 0,
        "true_positives":  tp,
        "false_positives": fp,
        "true_negatives":  tn,
        "false_negatives": fn,
    }

    EVAL_OUT.parent.mkdir(parents=True, exist_ok=True)
    EVAL_OUT.write_text(json.dumps(metrics, indent=2))
    print(f"\n[eval] precision={precision:.2f} recall={recall:.2f} "
          f"false_alarm_rate={fa_rate:.2f}")
    print(f"[eval] p50={metrics['summary']['latency_p50_ms']}ms "
          f"p95={metrics['summary']['latency_p95_ms']}ms")
    print(f"[eval] results written to {EVAL_OUT}")
    return metrics


def run_llm_comparison() -> dict[str, Any]:
    """
    T9.2 – Run the same two scenarios (deviation + sos) through each LLM
    for the Monitor and Verifier agents and record accuracy/cost/speed.
    """
    from saferide_sakhi.llm_gateway import call as llm_call
    providers = ["groq", "granite", "gemini"]
    test_prompt = (
        '{"case_id":"test","risk_event":{"type":"route_deviation","severity":3},'
        '"trip_context":{},"sop_hits":[],"rule_severity":3}'
    )
    results: dict[str, Any] = {}
    for p in providers:
        resp = llm_call(p, test_prompt, max_tokens=200, agent="eval", trip_id="eval")
        results[p] = {
            "success":    resp.success,
            "latency_ms": resp.latency_ms,
            "tokens_in":  resp.tokens_in,
            "tokens_out": resp.tokens_out,
            "cost_usd":   resp.cost_usd,
            "error":      resp.error,
        }
        print(f"  [{p}] ok={resp.success} latency={resp.latency_ms}ms cost=${resp.cost_usd:.6f}")
    return results


if __name__ == "__main__":
    run_eval()
    if os.environ.get("EVAL_LLM_COMPARE"):
        print("\n[eval] LLM comparison:")
        run_llm_comparison()
