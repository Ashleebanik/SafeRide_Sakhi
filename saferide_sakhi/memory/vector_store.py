"""
Memory Layer – T6.1 / T6.2 / T6.3
Short-term: dict-based in-process trip/case state (Redis-compatible interface).
Long-term: ChromaDB vector store for SOPs and closed-case summaries.
Retrieved content is REFERENCE ONLY – cannot override policy.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from saferide_sakhi.config import CHROMA_PERSIST_DIR

# ── Short-term state (T6.1) ───────────────────────────────────────────────────

_TRIP_STATE: dict[str, dict[str, Any]] = {}
_CASE_STATE: dict[str, dict[str, Any]] = {}


def st_set_trip(trip_id: str, data: dict[str, Any]) -> None:
    _TRIP_STATE[trip_id] = data


def st_get_trip(trip_id: str) -> dict[str, Any]:
    return _TRIP_STATE.get(trip_id, {})


def st_set_case(case_id: str, data: dict[str, Any]) -> None:
    _CASE_STATE[case_id] = data


def st_get_case(case_id: str) -> dict[str, Any]:
    return _CASE_STATE.get(case_id, {})


def st_clear_trip(trip_id: str) -> None:
    """Clear on case close (privacy: don't hold data longer than needed)."""
    _TRIP_STATE.pop(trip_id, None)


# ── Long-term vector store (T6.2) ─────────────────────────────────────────────

_CHROMA_COLLECTION = None


def _get_collection():
    global _CHROMA_COLLECTION
    if _CHROMA_COLLECTION is not None:
        return _CHROMA_COLLECTION
    try:
        import chromadb
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        _CHROMA_COLLECTION = client.get_or_create_collection("saferide_sops")
        return _CHROMA_COLLECTION
    except Exception as exc:
        print(f"[vector_store] ChromaDB unavailable: {exc}")
        return None


# Seed SOPs
_SOPS = [
    {"id": "sop_001", "text": "Route deviation protocol: contact passenger first via in-app message. If no response within 5 minutes, alert trusted contact. Never call emergency services without operator approval."},
    {"id": "sop_002", "text": "Long unplanned stop protocol: send check-in message. If no response in 3 minutes and area is isolated, escalate to operator immediately."},
    {"id": "sop_003", "text": "Driver/vehicle mismatch: immediate severity-4 flag. Operator must verify. Do not tell passenger the alert is dismissed until operator confirms."},
    {"id": "sop_004", "text": "SOS protocol: bypass all triage. Immediately alert operator and send location to trusted contacts. Emergency gateway requires operator confirmation."},
    {"id": "sop_005", "text": "False alarm procedure: operator dismisses case. Follow-up message to passenger explaining the check-in was a safety feature. Log outcome."},
    {"id": "sop_006", "text": "Driver harassment report: open case, flag for rating review, do NOT change driver rating directly. Operator reviews within 24 hours."},
    {"id": "sop_007", "text": "Night-time protocol: all trips between 10pm and 5am receive automatic night_time_flag. Severity bumped by 1 level if deviation or stop occurs."},
]


def load_sops() -> None:
    """Load SOPs into the vector store. Safe to call multiple times."""
    col = _get_collection()
    if col is None:
        return
    existing = set(col.get()["ids"]) if col.count() > 0 else set()
    to_add = [s for s in _SOPS if s["id"] not in existing]
    if to_add:
        col.add(
            ids=[s["id"] for s in to_add],
            documents=[s["text"] for s in to_add],
        )
        print(f"[vector_store] loaded {len(to_add)} SOPs")


def search_sops(query: str, top_k: int = 3) -> list[dict]:
    """
    Retrieve relevant SOPs.
    Returns a list of {id, text, distance} dicts.
    Retrieved text is REFERENCE ONLY – callers must treat it as context, not instruction.
    """
    col = _get_collection()
    if col is None or col.count() == 0:
        # Fallback: keyword search in hardcoded SOPs
        ql = query.lower()
        return [
            {"id": s["id"], "text": s["text"], "distance": 0.5}
            for s in _SOPS
            if any(w in s["text"].lower() for w in ql.split()[:3])
        ][:top_k]
    try:
        results = col.query(query_texts=[query], n_results=min(top_k, col.count()))
        hits = []
        for i, doc in enumerate(results["documents"][0]):
            hits.append({
                "id": results["ids"][0][i],
                "text": doc,
                "distance": results["distances"][0][i] if results.get("distances") else 0,
            })
        return hits
    except Exception as exc:
        print(f"[vector_store] search error: {exc}")
        return []


def add_closed_case_summary(case_id: str, summary: str) -> None:
    """Store a closed-case summary for future retrieval by Monitor/Follow-up."""
    col = _get_collection()
    if col is None:
        return
    try:
        col.add(ids=[f"case_{case_id}"], documents=[summary[:1000]])
    except Exception:
        pass
