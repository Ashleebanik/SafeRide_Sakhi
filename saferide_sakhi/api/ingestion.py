"""
FastAPI Ingestion API – T2.1
Receives events from rider/driver apps (simulated) and trip simulator.
Validates and sanitises all input before passing to the rules engine.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from saferide_sakhi.rules.detectors import evaluate_event
from saferide_sakhi.tools.mcp_servers import (
    TripRecord, trip_store_upsert, trip_store_add_ping, _audit,
)

app = FastAPI(title="SafeRide Sakhi – Ingestion API", version="1.0.0")

# ── Input schemas ─────────────────────────────────────────────────────────────

_ALLOWED_EVENT_TYPES = {
    "location_ping", "long_stop", "stop",
    "driver_vehicle_mismatch", "missed_checkin",
    "sos", "silent_trigger", "false_alarm",
    "trip_started", "trip_ended",
}

# Basic injection-safe text: allow alphanumeric, spaces, punctuation but not
# HTML/script/command patterns
_UNSAFE = re.compile(r"[<>\"';`\\]|--|\bscript\b|\bexec\b|\bignore\b",
                     re.IGNORECASE)


def _sanitise_text(v: str) -> str:
    if _UNSAFE.search(v):
        raise ValueError(f"Potentially unsafe input detected: {v[:80]}")
    return v[:500]


class LocationPingEvent(BaseModel):
    trip_id: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    speed_kmh: float = Field(ge=0, le=300)
    ts: str = ""

    @field_validator("trip_id")
    @classmethod
    def clean_trip_id(cls, v: str) -> str:
        return _sanitise_text(v)


class GenericTripEvent(BaseModel):
    trip_id: str
    type: str
    ts: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in _ALLOWED_EVENT_TYPES:
            raise ValueError(f"Unknown event type: {v}")
        return v

    @field_validator("trip_id")
    @classmethod
    def clean_trip_id(cls, v: str) -> str:
        return _sanitise_text(v)


class StartTripRequest(BaseModel):
    trip_id: str
    rider_id: str
    driver_id: str
    vehicle_id: str
    planned_route: list[dict] = Field(default_factory=list)
    started_at: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/trip/start")
def start_trip(req: StartTripRequest) -> dict:
    trip_store_upsert(TripRecord(
        trip_id=req.trip_id,
        rider_id=req.rider_id,
        driver_id=req.driver_id,
        vehicle_id=req.vehicle_id,
        route_planned=req.planned_route,
        status="active",
        started_at=req.started_at or datetime.utcnow().isoformat() + "Z",
    ))
    _audit("ingestion_api", f"trip_started {req.trip_id}", req.trip_id)
    return {"status": "ok", "trip_id": req.trip_id}


@app.post("/trip/ping")
def location_ping(event: LocationPingEvent) -> dict:
    ts = event.ts or datetime.utcnow().isoformat() + "Z"
    trip_store_add_ping(event.trip_id, event.lat, event.lon, ts)

    # Evaluate detectors
    raw_event = {
        "type": "location_ping",
        "ts": ts,
        "payload": {"lat": event.lat, "lon": event.lon, "speed_kmh": event.speed_kmh},
        "lat": event.lat,
        "lon": event.lon,
    }
    # trip_context would be fetched from trip_store in production
    risk_events = evaluate_event(raw_event, {"planned_route": []})
    return {"status": "ok", "risk_events": risk_events}


@app.post("/trip/event")
def trip_event(event: GenericTripEvent) -> dict:
    if not event.ts:
        event.ts = datetime.utcnow().isoformat() + "Z"
    raw = {"type": event.type, "ts": event.ts, "payload": event.payload}
    risk_events = evaluate_event(raw, {})
    _audit("ingestion_api", f"event {event.type} on trip {event.trip_id}", event.trip_id)
    return {"status": "ok", "trip_id": event.trip_id, "risk_events": risk_events}


@app.get("/health")
def health() -> dict:
    return {"status": "healthy", "ts": datetime.utcnow().isoformat() + "Z"}
