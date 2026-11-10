"""
SafeRide Sakhi – Core domain models (Pydantic v2).
All personally identifiable fields are synthetic/simulated only.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ── Enumerations ───────────────────────────────────────────────────────────────

class RiskLevel(str, Enum):
    SAFE = "safe"
    NUDGE = "nudge"
    ALERT = "alert"
    EMERGENCY = "emergency"


class TripStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABORTED = "aborted"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    PENDING = "pending"
    FAILED = "failed"
    EXPIRED = "expired"


class EscalationStep(str, Enum):
    NONE = "none"
    NUDGE_RIDER = "nudge_rider"
    NOTIFY_CONTACTS = "notify_contacts"
    ALERT_CONTROL_ROOM = "alert_control_room"
    DISPATCH_EMERGENCY = "dispatch_emergency"


# ── GPS & route models ─────────────────────────────────────────────────────────

class GPSPoint(BaseModel):
    lat: float
    lon: float
    timestamp: datetime
    speed_kmh: float = 0.0
    accuracy_metres: float = 10.0


class PlannedRoute(BaseModel):
    route_id: UUID = Field(default_factory=uuid4)
    origin: GPSPoint
    destination: GPSPoint
    waypoints: list[GPSPoint] = Field(default_factory=list)
    estimated_duration_min: float = 0.0
    distance_km: float = 0.0


# ── Rider & chauffeur models ───────────────────────────────────────────────────

class TrustedContact(BaseModel):
    name: str
    phone: str   # synthetic
    relation: str


class RiderProfile(BaseModel):
    rider_id: UUID = Field(default_factory=uuid4)
    name: str
    phone: str   # synthetic
    employer_or_campus: str = ""
    trusted_contacts: list[TrustedContact] = Field(default_factory=list)
    usual_routes: list[str] = Field(default_factory=list)
    consent_location_sharing: bool = True
    consent_recording: bool = False


class ChauffeurProfile(BaseModel):
    chauffeur_id: UUID = Field(default_factory=uuid4)
    name: str
    phone: str   # synthetic
    licence_number: str
    police_verification: VerificationStatus = VerificationStatus.VERIFIED
    id_status: VerificationStatus = VerificationStatus.VERIFIED
    face_match_result: bool = True
    last_verification_date: datetime
    rating: float = 5.0
    current_location: GPSPoint | None = None


# ── Trip state (shared across agents) ─────────────────────────────────────────

class AgentFlag(BaseModel):
    agent_name: str
    flag_type: str
    score: float        # 0.0 – 1.0
    reasoning: str
    evidence: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    prompt_version: str = "v1"


class TripState(BaseModel):
    trip_id: UUID = Field(default_factory=uuid4)
    rider: RiderProfile
    chauffeur: ChauffeurProfile
    planned_route: PlannedRoute
    actual_trace: list[GPSPoint] = Field(default_factory=list)
    status: TripStatus = TripStatus.PENDING
    risk_level: RiskLevel = RiskLevel.SAFE
    risk_score: float = 0.0
    flags: list[AgentFlag] = Field(default_factory=list)
    last_check_in: datetime | None = None
    escalation_step: EscalationStep = EscalationStep.NONE
    human_override: bool = False
    human_override_by: str = ""
    human_override_reason: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_flag(self, flag: AgentFlag) -> None:
        self.flags.append(flag)

    def latest_position(self) -> GPSPoint | None:
        return self.actual_trace[-1] if self.actual_trace else None
