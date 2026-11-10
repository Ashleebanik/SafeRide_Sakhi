"""
Database schema and seed helpers – T1.1
Entities from PDF section 8. Uses SQLite for the prototype
(swap connection string for PostgreSQL/PostGIS in production).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from uuid import uuid4
import random

DB_PATH = Path(__file__).parent.parent / "data" / "saferide.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DDL = """
CREATE TABLE IF NOT EXISTS Trip (
    id          TEXT PRIMARY KEY,
    rider_id    TEXT NOT NULL,
    driver_id   TEXT NOT NULL,
    vehicle_id  TEXT NOT NULL,
    route_planned TEXT,
    status      TEXT DEFAULT 'active',
    started_at  TEXT
);

CREATE TABLE IF NOT EXISTS LocationPing (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id     TEXT NOT NULL,
    lat         REAL NOT NULL,
    lon         REAL NOT NULL,
    ts          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS RiskEvent (
    id          TEXT PRIMARY KEY,
    trip_id     TEXT NOT NULL,
    type        TEXT NOT NULL,
    severity    INTEGER NOT NULL,  -- 1..4
    ts          TEXT NOT NULL,
    payload     TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS AlertState (
    case_id     TEXT PRIMARY KEY,
    state       TEXT NOT NULL,    -- DETECTED|TRIAGED|VERIFYING|AWAITING_OPERATOR|...
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS CaseTable (
    id          TEXT PRIMARY KEY,
    trip_id     TEXT NOT NULL,
    state       TEXT DEFAULT 'DETECTED',
    severity    INTEGER NOT NULL,
    opened_at   TEXT NOT NULL,
    due_at      TEXT,
    closed_at   TEXT
);

CREATE TABLE IF NOT EXISTS CaseAction (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id     TEXT NOT NULL,
    agent       TEXT NOT NULL,
    action      TEXT NOT NULL,
    result      TEXT,
    ts          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS Contact (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    channel     TEXT NOT NULL,  -- sms|push|email
    address     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS DriverRecord (
    driver_id   TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    verified    INTEGER DEFAULT 0,
    vehicle_id  TEXT,
    licence     TEXT,
    police_check TEXT DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS Report (
    id          TEXT PRIMARY KEY,
    driver_id   TEXT NOT NULL,
    summary     TEXT NOT NULL,
    rating_review_flag INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS AuditLog (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    actor       TEXT NOT NULL,
    event       TEXT NOT NULL,
    payload_ref TEXT
);

CREATE TABLE IF NOT EXISTS MessageLog (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    trip_id     TEXT,
    case_id     TEXT,
    channel     TEXT NOT NULL,
    recipient   TEXT NOT NULL,
    body        TEXT NOT NULL,
    delivered   INTEGER DEFAULT 0
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(DDL)
    print(f"[db] schema initialised at {DB_PATH}")


def seed_db(n: int = 10) -> None:
    """Seed synthetic drivers, riders (contacts) and vehicle records."""
    from faker import Faker
    fake = Faker("en_IN")
    random.seed(42)

    with get_conn() as conn:
        # Seed drivers
        for _ in range(n):
            did = str(uuid4())
            vid = f"KA{random.randint(10,99)}-{random.randint(1000,9999)}"
            conn.execute(
                "INSERT OR IGNORE INTO DriverRecord VALUES (?,?,?,?,?,?)",
                (did, fake.name_female(), 1, vid,
                 f"KA{random.randint(10,99)}-{random.randint(1000,9999)}",
                 "verified"),
            )
            uid = str(uuid4())
            conn.execute(
                "INSERT OR IGNORE INTO Contact VALUES (NULL,?,?,?)",
                (uid, "sms", fake.phone_number()),
            )
        conn.commit()
    print(f"[db] seeded {n} drivers and contacts")


if __name__ == "__main__":
    init_db()
    seed_db()
