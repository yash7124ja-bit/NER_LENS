from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from ner_lens.config import Settings
from ner_lens.corridor.models import Base, CorridorVersion, RoadSegment
from ner_lens.db import build_session_factory
from ner_lens.evidence.models import Evidence, SourceSnapshot
from ner_lens.evidence.service import EvidenceService
from ner_lens.identity import models as _identity_models  # noqa: F401

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


def build_factory():
    factory = build_session_factory(Settings(database_url="sqlite+pysqlite:///:memory:"))
    Base.metadata.create_all(factory.kw["bind"])
    return factory


def record_snapshot(service: EvidenceService, factory, **overrides):
    values = {
        "source": "replay_fixture",
        "source_url": "replay://fixture_graph.v1",
        "retrieved_at": NOW - timedelta(hours=12),
        "source_published_at": NOW - timedelta(days=1),
        "content_sha256": "a" * 64,
        "parser_version": "fixture-parser-v1",
        "raw_payload": {"schema_version": "v1", "blocked": True},
        "terms_label": "replay-fixture-no-live-terms",
        "data_mode": "replay",
        "stale_after": timedelta(hours=6),
        "now": NOW,
    }
    values.update(overrides)
    values["content_sha256"] = hashlib.sha256(
        json.dumps(values["raw_payload"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return service.record_snapshot(factory, **values)


def test_snapshot_is_immutable_and_stale_health_is_explicit():
    factory = build_factory()
    service = EvidenceService()
    snapshot = record_snapshot(service, factory)

    assert snapshot.health == "stale"
    assert snapshot.data_mode == "replay"
    assert snapshot.raw_payload["blocked"] is True
    with factory() as session:
        stored = session.get(SourceSnapshot, snapshot.id)
        stored.raw_payload = {"blocked": False}
        with pytest.raises(ValueError, match="immutable"):
            session.flush()

    replacement = record_snapshot(
        service,
        factory,
        retrieved_at=NOW,
        source_published_at=NOW,
        content_sha256="b" * 64,
        raw_payload={"schema_version": "v1", "blocked": False},
        supersedes_snapshot_id=snapshot.id,
    )
    assert replacement.supersedes_snapshot_id == snapshot.id


def test_evidence_retains_raw_value_provenance_and_records_spatial_association():
    factory = build_factory()
    service = EvidenceService()
    snapshot = record_snapshot(service, factory, retrieved_at=NOW, source_published_at=NOW)
    corridor_id = "11111111-1111-4111-8111-111111111111"
    segment_id = "22222222-2222-4222-8222-222222222222"
    with factory() as session:
        session.add(
            CorridorVersion(
                id=corridor_id,
                corridor_key="guwahati_silchar_nh27",
                graph_version="ner-lens-route-audit-fixture-v1",
                graph_sha256="7" * 64,
                status="active",
                effective_from=NOW,
            )
        )
        session.add(
            RoadSegment(
                id=segment_id,
                corridor_version_id=corridor_id,
                external_ref="band_1_jalukbari_nagaon",
                segment_type="road",
                direction="both",
                geometry={"type": "LineString", "coordinates": [[91.7, 26.1], [92.0, 26.0]]},
                vehicle_constraints={},
            )
        )
        session.commit()

    evidence = service.record_evidence(
        factory,
        snapshot_id=snapshot.id,
        evidence_type="field_report",
        source="replay_fixture",
        source_record_id="receipt-1",
        observed_at=NOW - timedelta(minutes=5),
        retrieved_at=NOW,
        geometry={"type": "Point", "coordinates": [91.8, 26.05]},
        raw_value={"condition": "blocked", "depth": 12},
        units={"depth": "cm"},
        now=NOW,
    )
    assert evidence.review_state == "unreviewed"
    assert evidence.snapshot_sha256 == snapshot.content_sha256
    assert evidence.raw_value["condition"] == "blocked"
    associated = service.associate_evidence(
        factory,
        evidence_id=evidence.id,
        segment_id=segment_id,
        method="within_buffer",
        distance_m=5000,
        buffer_m=5000,
    )
    assert associated.segment_id == segment_id
    assert associated.association_method == "within_buffer"
    with factory() as session:
        stored = session.get(Evidence, evidence.id)
        stored.raw_value = {"condition": "mutated"}
        with pytest.raises(ValueError, match="immutable"):
            session.flush()
    with factory() as session:
        with pytest.raises(IntegrityError):
            session.execute(
                update(Evidence)
                .where(Evidence.id == evidence.id)
                .values(raw_value={"condition": "direct-mutation"})
            )


def test_invalid_or_future_evidence_is_quarantined_and_raw_value_preserved():
    factory = build_factory()
    service = EvidenceService()
    snapshot = record_snapshot(service, factory, retrieved_at=NOW, source_published_at=NOW)
    cases = (
        {"observed_at": NOW + timedelta(minutes=1)},
        {"observed_at": datetime(2026, 9, 10, 11, 0)},
        {"geometry": {"type": "Point", "coordinates": [181.0, 26.0]}},
        {"raw_value": {"rainfall": 12}, "units": None},
    )
    for index, overrides in enumerate(cases):
        values = {
            "snapshot_id": snapshot.id,
            "evidence_type": "rainfall",
            "source": "replay_fixture",
            "source_record_id": f"invalid-{index}",
            "observed_at": NOW - timedelta(minutes=5),
            "retrieved_at": NOW,
            "geometry": {"type": "Point", "coordinates": [91.8, 26.05]},
            "raw_value": {"rainfall": 12},
            "units": {"rainfall": "mm"},
            "now": NOW,
        }
        values.update(overrides)
        evidence = service.record_evidence(factory, **values)
        assert evidence.review_state == "quarantined"
        assert evidence.raw_value is not None
        assert evidence.quality_flags

    with factory() as session:
        assert session.scalar(select(Evidence).where(Evidence.review_state == "quarantined"))


def test_live_mode_is_rejected_and_association_boundary_is_enforced():
    factory = build_factory()
    service = EvidenceService()
    with pytest.raises(ValueError, match="data_mode"):
        record_snapshot(service, factory, data_mode="live")
    snapshot = record_snapshot(service, factory, retrieved_at=NOW, source_published_at=NOW)
    with pytest.raises(ValueError, match="buffer"):
        service.associate_evidence(
            factory,
            evidence_id="missing",
            segment_id="missing",
            method="within_buffer",
            distance_m=5001,
            buffer_m=5000,
        )
    assert snapshot.data_mode == "replay"


def test_snapshot_hash_is_derived_and_source_hash_is_unique():
    factory = build_factory()
    service = EvidenceService()
    with pytest.raises(ValueError, match="does not match"):
        service.record_snapshot(
            factory,
            source="replay_fixture",
            source_url="replay://hash",
            retrieved_at=NOW,
            source_published_at=NOW,
            content_sha256="a" * 64,
            parser_version="fixture-parser-v1",
            raw_payload={"value": "different"},
            terms_label="replay",
            stale_after=timedelta(hours=1),
            now=NOW,
        )
    snapshot = record_snapshot(service, factory, source_url="replay://unique")
    with pytest.raises(IntegrityError):
        service.record_snapshot(
            factory,
            source="replay_fixture",
            source_url="replay://other-url",
            retrieved_at=NOW,
            source_published_at=NOW,
            content_sha256=snapshot.content_sha256,
            parser_version="fixture-parser-v1",
            raw_payload={"schema_version": "v1", "blocked": True},
            terms_label="replay-fixture-no-live-terms",
            stale_after=timedelta(hours=1),
            now=NOW,
        )
