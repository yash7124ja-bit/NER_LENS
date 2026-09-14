"""Implemented v1 wire contracts; unavailable values remain null."""

import re
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(Contract):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024, repr=False)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().casefold()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("A valid email address is required")
        return value


class SessionUser(Contract):
    actor_id: str
    email: str | None
    display_name: str
    roles: list[str]
    jurisdiction_ids: list[str]


class SessionResponse(Contract):
    user: SessionUser
    expires_at: AwareDatetime


class Liveness(Contract):
    status: Literal["live"] = "live"


class ReadyComponents(Contract):
    database: Literal["ready"] = "ready"
    migrations: Literal["compatible"] = "compatible"


class Readiness(Contract):
    status: Literal["ready"] = "ready"
    components: ReadyComponents = Field(default_factory=ReadyComponents)


class Provenance(Contract):
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_at: AwareDatetime | None
    retrieved_at: AwareDatetime
    graph_version: str
    policy_version: Literal["replay_unapproved_v1"] = "replay_unapproved_v1"


class ReplayResponse(Contract):
    data_mode: Literal["replay"] = "replay"
    provenance: Provenance
    limitations: list[str]


class CorridorSummary(Contract):
    corridor_id: UUID
    corridor_version_id: UUID
    name: str
    graph_version: str
    data_mode: Literal["replay"] = "replay"


class CorridorList(ReplayResponse):
    corridors: list[CorridorSummary]


class StateQuery(Contract):
    at: AwareDatetime | None = None
    vehicle_profile: Literal["light_goods", "rigid_truck", "emergency"] | None = None
    include_evidence: bool = False
    cursor: UUID | None = None
    limit: int = Field(default=50, ge=1, le=200)

    @field_validator("at")
    @classmethod
    def normalize_time(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(timezone.utc) if value else None


class LineString(Contract):
    type: Literal["LineString"] = "LineString"
    coordinates: list[tuple[float, float]] = Field(min_length=2)

    @field_validator("coordinates")
    @classmethod
    def valid_coordinates(cls, value: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if any(not (-180 <= lon <= 180 and -90 <= lat <= 90) for lon, lat in value):
            raise ValueError("Coordinates must be longitude/latitude in EPSG:4326")
        return value


class ExternalReference(Contract):
    source: str
    id: str


class UnknownStatus(Contract):
    value: Literal["unknown", "open", "restricted", "closed"] = "unknown"
    vehicle_scope: list[str] = Field(default_factory=lambda: ["all"])
    valid_until: AwareDatetime | None = None


class UnavailableRisk(Contract):
    state: Literal["insufficient_evidence"] = "insufficient_evidence"
    probability: None = None
    horizon_seconds: Literal[21600] = 21600
    abstention_reason: str = (
        "No reviewed operational evidence or approved risk policy is available."
    )


class SegmentState(Contract):
    segment_id: UUID
    external_refs: list[ExternalReference]
    geometry: LineString
    segment_type: Literal["road", "bridge", "tunnel", "approach"]
    direction: Literal["both", "forward", "backward", "forward_only", "backward_only"]
    vehicle_constraints: dict[str, object]
    operational_status: UnknownStatus = Field(default_factory=UnknownStatus)
    risk: UnavailableRisk = Field(default_factory=UnavailableRisk)
    evidence_age_seconds: None = None
    source_health: Literal["failed"] = "failed"
    evidence: list[object] | None = Field(default=None, exclude_if=lambda value: value is None)


class CorridorState(ReplayResponse):
    corridor_id: UUID
    corridor_version_id: UUID
    as_of: AwareDatetime
    segments: list[SegmentState]
    next_cursor: UUID | None


class ErrorDetail(Contract):
    field: str
    reason: str


class ErrorBody(Contract):
    code: Literal[
        "invalid_request",
        "unauthenticated",
        "forbidden",
        "not_found",
        "conflict",
        "idempotency_conflict",
        "payload_too_large",
        "unsupported_media_type",
        "unprocessable_entity",
        "rate_limited",
        "upstream_unavailable",
        "degraded",
        "internal_error",
    ]
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)
    retryable: bool = False
    request_id: UUID


class ErrorResponse(Contract):
    error: ErrorBody
