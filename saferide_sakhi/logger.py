"""
SafeRide Sakhi – Structured logger.
Every agent step emits a JSON log line: input, tool call, output, latency, decision.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from saferide_sakhi.config import LOG_LEVEL, ROOT_DIR

_LOG_DIR = ROOT_DIR / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / "saferide_sakhi.jsonl"


def _add_timestamp(
    logger: Any, method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    event_dict["timestamp"] = datetime.utcnow().isoformat() + "Z"
    return event_dict


structlog.configure(
    processors=[
        _add_timestamp,
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

_base_logger = structlog.get_logger()


class AgentLogger:
    """Wrapper that writes structured JSONL entries for one agent."""

    def __init__(self, agent_name: str) -> None:
        self._log = _base_logger.bind(agent=agent_name)
        self._file = open(_LOG_FILE, "a", encoding="utf-8")

    def _write(self, level: str, **kwargs: Any) -> None:
        entry = {"level": level, **kwargs, "ts": datetime.utcnow().isoformat() + "Z"}
        self._file.write(json.dumps(entry) + "\n")
        self._file.flush()

    def step(
        self,
        *,
        trip_id: str,
        stage: str,
        input_summary: str,
        tool_call: str = "",
        output_summary: str,
        latency_ms: float,
        decision: str,
        prompt_version: str = "v1",
    ) -> None:
        self._write(
            "INFO",
            trip_id=trip_id,
            stage=stage,
            input=input_summary,
            tool=tool_call,
            output=output_summary,
            latency_ms=round(latency_ms, 1),
            decision=decision,
            prompt_version=prompt_version,
        )

    def error(self, trip_id: str, stage: str, error: str) -> None:
        self._write("ERROR", trip_id=trip_id, stage=stage, error=error)

    def close(self) -> None:
        self._file.close()


class Timer:
    """Context manager for measuring wall-clock latency in milliseconds."""

    def __init__(self) -> None:
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_: Any) -> None:
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000.0
