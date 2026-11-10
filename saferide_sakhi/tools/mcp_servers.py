"""
MCP Tool Servers – T3.1 / T3.2
trip_store, case_store, driver_registry, route_service,
messaging (mock), emergency_gateway (mock)

Each tool has a strict input/output schema (Pydantic).
In production these would be separate MCP processes;
for the prototype they are plain Python modules.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from saferide_sakhi.tools.db import get_conn

_MSG_LOG: list[dict] = []    # in-process message log
_EMG_LOG: list[dict] = []    # in-process emergency gateway log


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class TripRecord(BaseModel):
    trip_id: str
    rider_id: str
    driver_id: str
    vehicle_id: str
    route_planned: list[dict] = Field(default_factory=list)
    status: str = "active"
    started_at: str = ""


class CaseRecord(BaseModel):
    case_id: str
    trip_id: str
    state: str
    severity: int
    opened_at: str
    due_at: str = ""


class CaseActionRecord(BaseModel):
    case_id: str
    agent: str
    action: str
    result: str = ""
    ts: str = ""


class MessagePacket(BaseModel):
    trip_id: str = ""
    case_id: str = ""
    channel: str          # sms | push | email
    recipient: str
    body: str
    priority: str = "normal"


class EmergencyPacket(BaseModel):
    case_id: str
    trip_id: str
    who: str              # rider name
    where: str            # last known coords
    driver: str
    vehicle: str
    evidence: list[str] = Field(default_factory=list)
    severity: int = 4


class DriverInfo(BaseModel):
    driver_id: str
    name: str
    verified: bool
    vehicle_id: str
    licence: str
    police_check: str


class SafeStop(BaseModel):
    name: str
    lat: float
    lon: float
    type: str
    distance_m: float


# ── trip_store ────────────────────────────────────────────────────────────────

def trip_store_get(trip_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM Trip WHERE id=?", (trip_id,)).fetchone()
    return dict(row) if row else None


def trip_store_upsert(trip: TripRecord) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO Trip VALUES (?,?,?,?,?,?,?)",
            (trip.trip_id, trip.rider_id, trip.driver_id, trip.vehicle_id,
             json.dumps(trip.route_planned), trip.status, trip.started_at),
        )
        conn.commit()


def trip_store_add_ping(trip_id: str, lat: float, lon: float, ts: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO LocationPing (trip_id, lat, lon, ts) VALUES (?,?,?,?)",
            (trip_id, lat, lon, ts),
        )
        conn.commit()


def trip_store_get_pings(trip_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT lat, lon, ts FROM LocationPing WHERE trip_id=? ORDER BY ts",
            (trip_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── case_store ────────────────────────────────────────────────────────────────

def case_store_open(trip_id: str, severity: int, due_hours: int = 4) -> str:
    case_id = str(uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    due = (datetime.utcnow() + __import__("datetime").timedelta(hours=due_hours)).isoformat() + "Z"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO CaseTable VALUES (?,?,?,?,?,?,?)",
            (case_id, trip_id, "DETECTED", severity, now, due, None),
        )
        conn.execute(
            "INSERT INTO AlertState VALUES (?,?,?)",
            (case_id, "DETECTED", now),
        )
        conn.commit()
    _audit("case_store", f"opened case {case_id} severity={severity}", case_id)
    return case_id


def case_store_transition(case_id: str, new_state: str) -> None:
    now = datetime.utcnow().isoformat() + "Z"
    with get_conn() as conn:
        conn.execute("UPDATE CaseTable SET state=? WHERE id=?", (new_state, case_id))
        conn.execute("UPDATE AlertState SET state=?, updated_at=? WHERE case_id=?",
                     (new_state, now, case_id))
        conn.commit()
    _audit("case_store", f"case {case_id} -> {new_state}", case_id)


def case_store_add_action(action: CaseActionRecord) -> None:
    ts = action.ts or datetime.utcnow().isoformat() + "Z"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO CaseAction (case_id, agent, action, result, ts) VALUES (?,?,?,?,?)",
            (action.case_id, action.agent, action.action, action.result, ts),
        )
        conn.commit()


def case_store_get(case_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM CaseTable WHERE id=?", (case_id,)).fetchone()
    return dict(row) if row else None


def case_store_get_actions(case_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM CaseAction WHERE case_id=? ORDER BY ts",
            (case_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── driver_registry ───────────────────────────────────────────────────────────

def driver_registry_get(driver_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM DriverRecord WHERE driver_id=?", (driver_id,)
        ).fetchone()
    return dict(row) if row else None


def driver_registry_check(driver_id: str, vehicle_id: str) -> dict[str, Any]:
    record = driver_registry_get(driver_id)
    if not record:
        return {"found": False, "verified": False, "vehicle_match": False}
    return {
        "found": True,
        "verified": bool(record["verified"]),
        "vehicle_match": record["vehicle_id"] == vehicle_id,
        "police_check": record["police_check"],
        "name": record["name"],
    }


# ── route_service ─────────────────────────────────────────────────────────────

def route_service_get_planned(trip_id: str) -> list[dict]:
    record = trip_store_get(trip_id)
    if not record:
        return []
    raw = record.get("route_planned", "[]")
    return json.loads(raw) if isinstance(raw, str) else raw


def route_service_nearest_safe_stop(lat: float, lon: float) -> list[SafeStop]:
    """Return synthetic lit/staffed stops near a coordinate."""
    from saferide_sakhi.mcp_tools.tools import nearest_help_point
    pt = nearest_help_point(lat, lon)
    if pt.get("found"):
        return [SafeStop(
            name=pt["name"], lat=pt["lat"], lon=pt["lon"],
            type=pt["type"], distance_m=pt["distance_m"],
        )]
    return []


# ── mock messaging ────────────────────────────────────────────────────────────

def messaging_send(packet: MessagePacket) -> dict[str, Any]:
    """Log every packet; no real network calls in prototype."""
    entry = {
        "id": str(uuid4()),
        "ts": datetime.utcnow().isoformat() + "Z",
        **packet.model_dump(),
        "delivered": True,
    }
    _MSG_LOG.append(entry)
    # Persist to DB
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO MessageLog (ts, trip_id, case_id, channel, recipient, body, delivered)"
            " VALUES (?,?,?,?,?,?,?)",
            (entry["ts"], packet.trip_id, packet.case_id,
             packet.channel, packet.recipient, packet.body, 1),
        )
        conn.commit()
    print(f"[msg] [{packet.channel}] -> {packet.recipient}: {packet.body[:60]}")
    return {"delivered": True, "message_id": entry["id"]}


def messaging_get_log(trip_id: str = "") -> list[dict]:
    if trip_id:
        return [m for m in _MSG_LOG if m.get("trip_id") == trip_id]
    return list(_MSG_LOG)


# ── mock emergency_gateway ────────────────────────────────────────────────────

def emergency_gateway_send(packet: EmergencyPacket) -> dict[str, Any]:
    """
    Simulate handoff to police / 112.
    Records the full packet; never makes real calls.
    """
    entry = {
        "id": str(uuid4()),
        "ts": datetime.utcnow().isoformat() + "Z",
        "acknowledged": False,   # set to True by operator confirmation
        **packet.model_dump(),
    }
    _EMG_LOG.append(entry)
    _audit("emergency_gateway",
           f"packet dispatched for case {packet.case_id}", packet.case_id)
    print(f"[EMERGENCY MOCK] case={packet.case_id} who={packet.who} where={packet.where}")
    return {"dispatched": True, "packet_id": entry["id"], "acknowledged": False}


def emergency_gateway_get_log() -> list[dict]:
    return list(_EMG_LOG)


# ── sop_search (stub – vector DB wired up in T6.2) ────────────────────────────

def sop_search(query: str, top_k: int = 3) -> list[dict]:
    """Retrieve relevant SOPs from vector DB. Returns empty list until T6.2."""
    try:
        from saferide_sakhi.memory.vector_store import search_sops
        return search_sops(query, top_k)
    except Exception:
        return []


# ── Audit helper ──────────────────────────────────────────────────────────────

def _audit(actor: str, event: str, payload_ref: str = "") -> None:
    ts = datetime.utcnow().isoformat() + "Z"
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO AuditLog (ts, actor, event, payload_ref) VALUES (?,?,?,?)",
                (ts, actor, event, payload_ref),
            )
            conn.commit()
    except Exception:
        pass
