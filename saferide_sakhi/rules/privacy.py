"""
Privacy controls – T7.5
Consent flag enforcement, retention window checks, and log redaction.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from saferide_sakhi.config import TRIP_DATA_RETENTION_DAYS, ROOT_DIR


# ── Consent flags ─────────────────────────────────────────────────────────────

def check_consent(rider_profile: dict[str, Any], purpose: str) -> bool:
    """
    Return True if rider has consented to the given data use purpose.
    Purposes: "location_sharing" | "recording"
    """
    if purpose == "location_sharing":
        return rider_profile.get("consent_location_sharing", True)
    if purpose == "recording":
        return rider_profile.get("consent_recording", False)
    return False


def enforce_location_consent(
    rider_profile: dict[str, Any], lat: float, lon: float
) -> tuple[float | None, float | None]:
    """Return coords if consented, else None."""
    if check_consent(rider_profile, "location_sharing"):
        return lat, lon
    return None, None


# ── Log redaction ─────────────────────────────────────────────────────────────

_PHONE_RE   = re.compile(r"\b[6-9]\d{9}\b")
_EMAIL_RE   = re.compile(r"\b[\w.+-]+@[\w-]+\.\w+\b")
_NAME_RE    = re.compile(r'"name"\s*:\s*"([^"]{3,})"')


def redact_log_entry(entry: str) -> str:
    """Replace PII patterns with [REDACTED]."""
    entry = _PHONE_RE.sub("[PHONE]", entry)
    entry = _EMAIL_RE.sub("[EMAIL]", entry)
    return entry


# ── Retention window ──────────────────────────────────────────────────────────

def purge_expired_logs() -> int:
    """
    Remove log entries older than TRIP_DATA_RETENTION_DAYS.
    Returns count of purged lines.
    """
    log_file = ROOT_DIR / "logs" / "saferide_sakhi.jsonl"
    if not log_file.exists():
        return 0

    cutoff = datetime.utcnow() - timedelta(days=TRIP_DATA_RETENTION_DAYS)
    kept: list[str] = []
    purged = 0

    for line in log_file.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
            ts_str = entry.get("ts", "")
            if ts_str:
                ts = datetime.fromisoformat(ts_str.replace("Z", ""))
                if ts < cutoff:
                    purged += 1
                    continue
        except Exception:
            pass
        kept.append(redact_log_entry(line))

    log_file.write_text("\n".join(kept), encoding="utf-8")
    return purged
