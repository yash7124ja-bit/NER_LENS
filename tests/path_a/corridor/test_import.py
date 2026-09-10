from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from ner_lens.config import Settings
from ner_lens.corridor.importer import CorridorImportService, load_primary_band_specs
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


def test_primary_import_covers_six_bands_and_preserves_structure():
    factory = build_session_factory(Settings(database_url="sqlite+pysqlite:///:memory:"))
    Base.metadata.create_all(factory.kw["bind"])
    specs = load_primary_band_specs(FIXTURE_PATH)

    result = CorridorImportService().import_primary(
        factory,
        graph_version="ner-lens-route-audit-fixture-v1",
        graph_sha256="d" * 64,
        source_url="https://download.geofabrik.de/asia/india/north-eastern-zone-260909.osm.pbf",
        specs=specs,
    )

    assert result.created is True
    assert result.quarantined == []
    assert len(result.segment_ids) == 6
    with factory() as session:
        version = session.scalar(select(CorridorVersion))
        segments = session.scalars(select(RoadSegment).order_by(RoadSegment.external_ref)).all()
    assert version is not None
    assert version.graph_sha256 == "d" * 64
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
        graph_sha256="e" * 64,
        source_url="replay://fixture_graph.v1",
        specs=specs,
    )
    second = service.import_primary(
        factory,
        graph_version="ner-lens-route-audit-fixture-v1",
        graph_sha256="e" * 64,
        source_url="replay://fixture_graph.v1",
        specs=specs,
    )

    assert second.created is False
    assert second.segment_ids == first.segment_ids
    with factory() as session:
        assert session.query(CorridorVersion).count() == 1
        assert session.query(RoadSegment).count() == 6


def test_import_quarantines_invalid_geometry_without_creating_a_segment():
    factory = build_session_factory(Settings(database_url="sqlite+pysqlite:///:memory:"))
    Base.metadata.create_all(factory.kw["bind"])
    specs = load_primary_band_specs(FIXTURE_PATH)
    specs[0].geometry_endpoints = [[91.0, 26.0], [181.0, 26.1]]

    result = CorridorImportService().import_primary(
        factory,
        graph_version="ner-lens-route-audit-fixture-v1",
        graph_sha256="f" * 64,
        source_url="replay://fixture_graph.v1",
        specs=specs,
    )

    assert result.created is True
    assert result.quarantined == ["band_1_jalukbari_nagaon"]
    with factory() as session:
        assert session.query(RoadSegment).count() == 5
