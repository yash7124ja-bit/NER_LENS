"""Replay-safe source snapshot and evidence recording boundary."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ner_lens.corridor.models import RoadSegment
from ner_lens.db import session_scope
from ner_lens.evidence.models import Evidence, SourceSnapshot

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
ASSOCIATION_METHODS = frozenset({"segment_intersects", "within_buffer", "manual_review"})
REPLAY_DATA_MODES = frozenset({"replay", "synthetic"})


class EvidenceService:
    def record_snapshot(
        self,
        factory: sessionmaker[Session],
        *,
        source: str,
        source_url: str,
        retrieved_at: datetime,
        source_published_at: datetime | None,
        content_sha256: str,
        parser_version: str,
        raw_payload: dict[str, Any],
        terms_label: str,
        data_mode: str = "replay",
        stale_after: timedelta | None = None,
        now: datetime | None = None,
        supersedes_snapshot_id: str | None = None,
        snapshot_id: str | None = None,
    ) -> SourceSnapshot:
        now = now or datetime.now(timezone.utc)
        _require_aware(retrieved_at, "retrieved_at")
        if source_published_at is not None:
            _require_aware(source_published_at, "source_published_at")
        _require_aware(now, "now")
        if data_mode not in REPLAY_DATA_MODES:
            raise ValueError("data_mode must be replay or synthetic")
        if not SHA256_RE.fullmatch(content_sha256):
            raise ValueError("content_sha256 must be a 64-character hexadecimal hash")
        if not source or not source_url or not parser_version or not terms_label:
            raise ValueError("source provenance fields are required")
        if not isinstance(raw_payload, dict):
            raise ValueError("raw_payload must be a JSON object")
        if source_published_at is not None and source_published_at > now:
            raise ValueError("source_published_at cannot be in the future")
        age = now - retrieved_at
        health = "stale" if stale_after is not None and age > stale_after else "healthy"
        with session_scope(factory) as session:
            if supersedes_snapshot_id is not None and session.get(
                SourceSnapshot, supersedes_snapshot_id
            ) is None:
                raise ValueError("superseded snapshot does not exist")
            snapshot = SourceSnapshot(
                id=snapshot_id or str(uuid.uuid4()),
                source=source,
                source_url=source_url,
                retrieved_at=retrieved_at,
                source_published_at=source_published_at,
                content_sha256=content_sha256.lower(),
                parser_version=parser_version,
                raw_payload=raw_payload,
                terms_label=terms_label,
                data_mode=data_mode,
                health=health,
                supersedes_snapshot_id=supersedes_snapshot_id,
            )
            session.add(snapshot)
            session.flush()
            return snapshot

    def record_evidence(
        self,
        factory: sessionmaker[Session],
        *,
        snapshot_id: str,
        evidence_type: str,
        source: str,
        source_record_id: str,
        observed_at: datetime,
        retrieved_at: datetime,
        geometry: dict[str, Any],
        raw_value: dict[str, Any],
        units: dict[str, Any] | None,
        source_published_at: datetime | None = None,
        valid_until: datetime | None = None,
        confidence: float | None = None,
        now: datetime | None = None,
        evidence_id: str | None = None,
    ) -> Evidence:
        now = now or datetime.now(timezone.utc)
        _require_aware(now, "now")
        flags: list[str] = []
        for value, name in (
            (observed_at, "observed_at"),
            (retrieved_at, "retrieved_at"),
        ):
            if not _is_aware(value):
                flags.append(f"{name}_timezone_missing")
        if source_published_at is not None and not _is_aware(source_published_at):
            flags.append("source_published_at_timezone_missing")
        if valid_until is not None and not _is_aware(valid_until):
            flags.append("valid_until_timezone_missing")
        if _is_aware(observed_at) and observed_at > now:
            flags.append("observed_at_in_future")
        try:
            _validate_geometry(geometry)
        except ValueError as exc:
            flags.append(str(exc))
        if not isinstance(raw_value, dict):
            flags.append("raw_value_not_object")
        if _contains_numeric(raw_value) and not units:
            flags.append("units_missing")
        if confidence is not None and not 0 <= confidence <= 1:
            flags.append("confidence_out_of_range")
        with session_scope(factory) as session:
            snapshot = session.get(SourceSnapshot, snapshot_id)
            if snapshot is None:
                raise ValueError("snapshot does not exist")
            if source != snapshot.source:
                flags.append("source_snapshot_mismatch")
            if snapshot.health == "stale":
                flags.append("snapshot_stale")
            evidence = Evidence(
                id=evidence_id or str(uuid.uuid4()),
                snapshot_id=snapshot.id,
                snapshot_sha256=snapshot.content_sha256,
                evidence_type=evidence_type,
                source=source,
                source_record_id=source_record_id,
                observed_at=observed_at,
                source_published_at=source_published_at,
                retrieved_at=retrieved_at,
                valid_until=valid_until,
                geometry=geometry,
                raw_value=raw_value,
                units=units,
                quality_flags=sorted(set(flags)),
                review_state="quarantined" if flags else "unreviewed",
                confidence=confidence,
            )
            session.add(evidence)
            session.flush()
            return evidence

    def associate_evidence(
        self,
        factory: sessionmaker[Session],
        *,
        evidence_id: str,
        segment_id: str,
        method: str,
        distance_m: float | None = None,
        buffer_m: float | None = None,
    ) -> Evidence:
        if method not in ASSOCIATION_METHODS:
            raise ValueError("unsupported spatial association method")
        if method == "within_buffer":
            if distance_m is None or buffer_m is None or buffer_m < 0 or distance_m < 0:
                raise ValueError("within_buffer requires non-negative distance and buffer")
            if distance_m > buffer_m:
                raise ValueError("evidence is outside the association buffer")
        with session_scope(factory) as session:
            evidence = session.get(Evidence, evidence_id)
            if evidence is None:
                raise ValueError("evidence does not exist")
            if session.get(RoadSegment, segment_id) is None:
                raise ValueError("segment does not exist")
            evidence.segment_id = segment_id
            evidence.association_method = method
            evidence.association_distance_m = distance_m
            session.flush()
            return evidence

    associate_segment = associate_evidence


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _require_aware(value: datetime, name: str) -> None:
    if not _is_aware(value):
        raise ValueError(f"{name} must include a timezone")


def _validate_geometry(geometry: dict[str, Any]) -> None:
    if not isinstance(geometry, dict):
        raise ValueError("geometry_invalid")
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Point":
        valid = (
            isinstance(coordinates, list)
            and len(coordinates) == 2
            and all(isinstance(value, (int, float)) for value in coordinates)
            and -180 <= coordinates[0] <= 180
            and -90 <= coordinates[1] <= 90
        )
    elif geometry_type == "LineString":
        valid = (
            isinstance(coordinates, list)
            and len(coordinates) >= 2
            and all(
                isinstance(point, list)
                and len(point) == 2
                and all(isinstance(value, (int, float)) for value in point)
                and -180 <= point[0] <= 180
                and -90 <= point[1] <= 90
                for point in coordinates
            )
        )
    else:
        valid = False
    if not valid:
        raise ValueError("geometry_invalid")


def _contains_numeric(value: Any) -> bool:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    if isinstance(value, dict):
        return any(_contains_numeric(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_numeric(item) for item in value)
    return False
