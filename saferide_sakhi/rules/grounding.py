"""
Grounding checker – T7.3
Rejects agent messages that contain facts not present in the case record.
Uses pattern matching on known fact-patterns (coordinates, names, IDs).
"""
from __future__ import annotations

import re
from typing import Any


# Patterns for facts that must come from the trip/case record
_LAT_LON_PATTERN  = re.compile(r"\b\d{1,2}\.\d{4,}\b")
_VEHICLE_PATTERN  = re.compile(r"\bKA\d{2}-\d{4}\b", re.IGNORECASE)
_PHONE_PATTERN    = re.compile(r"\b[6-9]\d{9}\b")


def _extract_facts_from_text(text: str) -> set[str]:
    facts = set()
    for m in _LAT_LON_PATTERN.findall(text):
        facts.add(f"coord:{m}")
    for m in _VEHICLE_PATTERN.findall(text):
        facts.add(f"vehicle:{m.upper()}")
    for m in _PHONE_PATTERN.findall(text):
        facts.add(f"phone:{m}")
    return facts


def _extract_facts_from_record(record: dict[str, Any]) -> set[str]:
    record_text = str(record)
    return _extract_facts_from_text(record_text)


def check_grounded(
    message: str,
    case_record: dict[str, Any],
    trip_record: dict[str, Any],
) -> tuple[bool, list[str]]:
    """
    Returns (is_grounded, list_of_ungrounded_facts).
    is_grounded=True means the message is safe to send.
    """
    msg_facts = _extract_facts_from_text(message)
    allowed   = _extract_facts_from_record(case_record) | _extract_facts_from_record(trip_record)
    ungrounded = [f for f in msg_facts if f not in allowed]
    return (len(ungrounded) == 0), ungrounded
