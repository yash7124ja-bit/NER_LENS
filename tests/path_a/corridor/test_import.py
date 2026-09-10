from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from ner_lens.config import Settings
from ner_lens.corridor.importer import (
    CorridorImportService,
    _stable_id,
    get_active_corridor,
    load_primary_band_specs,
    map_audited_bands_to_segments,
    validate_v3_band_mapping,
)
from ner_lens.corridor.models import Base, CorridorVersion, RoadSegment
from ner_lens.db import build_session_factory
from ner_lens.identity import models as _identity_models  # noqa: F401

FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "corridor"
    / "graphhopper"
    / "fixture_graph.v1.json"
)
FIXTURE_SHA256 = "7206d72246c0d975d7645938f9ac83a65cbcdda901c639ae4f3ff8b3533fbf48"
FIXTURE_SOURCE_URL = "replay://fixture_graph.v1"
MAPPING_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "corridor"
    / "graphhopper"
    / "real_evidence"
    / "v3"
    / "corridor_edge_mapping.json"
)


def test_primary_import_covers_six_bands_and_preserves_structure():
    factory = build_session_factory(Settings(database_url="sqlite+pysqlite:///:memory:"))
    Base.metadata.create_all(factory.kw["bind"])
    specs = load_primary_band_specs(FIXTURE_PATH)

    result = CorridorImportService().import_primary(
        factory,
        graph_version="ner-lens-route-audit-fixture-v1",
        graph_sha256=FIXTURE_SHA256,
        source_url=FIXTURE_SOURCE_URL,
        specs=specs,
    )

    assert result.created is True
    assert result.quarantined == []
    assert len(result.segment_ids) == 6
    with factory() as session:
        version = session.scalar(select(CorridorVersion))
        segments = session.scalars(select(RoadSegment).order_by(RoadSegment.external_ref)).all()
    assert version is not None
    assert version.graph_sha256 == FIXTURE_SHA256
    assert version.provenance_label == "replay"
    assert [segment.external_ref for segment in segments] == [
        "band_1_jalukbari_nagaon",
        "band_2_nagaon_doboka",
        "band_3_doboka_lanka_lumding",
        "band_4_lumding_maibang",
        "band_5_maibang_harangajao_balachera_hill",
        "band_6_balachera_silchar",
    ]
    assert segments[2].segment_type == "bridge"
    assert segments[4].direction == "forward_only"


def test_primary_import_is_idempotent_for_same_graph_version():
    factory = build_session_factory(Settings(database_url="sqlite+pysqlite:///:memory:"))
    Base.metadata.create_all(factory.kw["bind"])
    service = CorridorImportService()
    specs = load_primary_band_specs(FIXTURE_PATH)
    first = service.import_primary(
        factory,
        graph_version="ner-lens-route-audit-fixture-v1",
        graph_sha256=FIXTURE_SHA256,
        source_url=FIXTURE_SOURCE_URL,
        specs=specs,
    )
    second = service.import_primary(
        factory,
        graph_version="ner-lens-route-audit-fixture-v1",
        graph_sha256=FIXTURE_SHA256,
        source_url=FIXTURE_SOURCE_URL,
        specs=specs,
    )

    assert second.created is False
    assert second.segment_ids == first.segment_ids
    with factory() as session:
        assert session.query(CorridorVersion).count() == 1
        assert session.query(RoadSegment).count() == 6


def test_import_rejects_tampered_geometry_without_creating_any_rows():
    factory = build_session_factory(Settings(database_url="sqlite+pysqlite:///:memory:"))
    Base.metadata.create_all(factory.kw["bind"])
    specs = load_primary_band_specs(FIXTURE_PATH)
    specs[0].geometry_endpoints = [[91.0, 26.0], [181.0, 26.1]]

    with pytest.raises(ValueError, match="band specs"):
        CorridorImportService().import_primary(
            factory,
            graph_version="ner-lens-route-audit-fixture-v1",
            graph_sha256=FIXTURE_SHA256,
            source_url=FIXTURE_SOURCE_URL,
            specs=specs,
        )
    with factory() as session:
        assert session.query(CorridorVersion).count() == 0
        assert session.query(RoadSegment).count() == 0


def test_import_rejects_unmanifested_checksum_or_source_url():
    factory = build_session_factory(Settings(database_url="sqlite+pysqlite:///:memory:"))
    Base.metadata.create_all(factory.kw["bind"])
    service = CorridorImportService()
    specs = load_primary_band_specs(FIXTURE_PATH)
    with pytest.raises(ValueError, match="graph checksum"):
        service.import_primary(
            factory,
            graph_version="ner-lens-route-audit-fixture-v1",
            graph_sha256="f" * 64,
            source_url=FIXTURE_SOURCE_URL,
            specs=specs,
        )
    with pytest.raises(ValueError, match="source URL"):
        service.import_primary(
            factory,
            graph_version="ner-lens-route-audit-fixture-v1",
            graph_sha256=FIXTURE_SHA256,
            source_url="https://example.invalid/unverified.pbf",
            specs=specs,
        )


def test_stable_ids_include_graph_checksum_for_same_version_inputs():
    first = _stable_id("corridor", "guwahati_silchar_nh27", "v1", "a" * 64)
    second = _stable_id("corridor", "guwahati_silchar_nh27", "v1", "b" * 64)
    assert first != second


def test_tampered_band_specs_are_rejected_before_any_write():
    factory = build_session_factory(Settings(database_url="sqlite+pysqlite:///:memory:"))
    Base.metadata.create_all(factory.kw["bind"])
    specs = load_primary_band_specs(FIXTURE_PATH)
    specs[0].geometry_endpoints[0][0] += 0.01
    with pytest.raises(ValueError, match="band specs"):
        CorridorImportService().import_primary(
            factory,
            graph_version="ner-lens-route-audit-fixture-v1",
            graph_sha256=FIXTURE_SHA256,
            source_url=FIXTURE_SOURCE_URL,
            specs=specs,
        )
    with factory() as session:
        assert session.query(CorridorVersion).count() == 0
        assert session.query(RoadSegment).count() == 0


def test_active_corridor_and_v3_band_mapping_are_deterministic():
    mapping = validate_v3_band_mapping(MAPPING_PATH)
    assert set(mapping) == {
        "band_1_jalukbari_nagaon",
        "band_2_nagaon_doboka",
        "band_3_doboka_lanka_lumding",
        "band_4_lumding_maibang",
        "band_5_maibang_harangajao_balachera_hill",
        "band_6_balachera_silchar",
    }
    factory = build_session_factory(Settings(database_url="sqlite+pysqlite:///:memory:"))
    Base.metadata.create_all(factory.kw["bind"])
    service = CorridorImportService()
    result = service.import_primary(
        factory,
        graph_version="ner-lens-route-audit-fixture-v1",
        graph_sha256=FIXTURE_SHA256,
        source_url=FIXTURE_SOURCE_URL,
        specs=load_primary_band_specs(FIXTURE_PATH),
    )
    active = get_active_corridor(factory)
    assert active is not None
    assert active.id == result.corridor_version_id
    segment_map = map_audited_bands_to_segments(factory, active.id, mapping)
    assert set(segment_map) == set(mapping)
    assert all(segment_id in result.segment_ids for segment_id in segment_map.values())
