from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from ner_lens.config import Settings
from ner_lens.corridor.models import Base, CorridorVersion, RoadSegment
from ner_lens.db import build_session_factory


def test_database_constraints_reject_invalid_corridor_status_segment_type_and_direction():
    factory = build_session_factory(Settings(database_url="sqlite+pysqlite:///:memory:"))
    Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        with pytest.raises((IntegrityError, ValueError)):
            session.execute(
                text(
                    "INSERT INTO corridor_version "
                    "(id, corridor_key, graph_version, graph_sha256, status, effective_from) "
                    "VALUES ('1', 'test', 'v1', :sha, 'not_a_status', :effective)"
                ),
                {"sha": "a" * 64, "effective": datetime.now(timezone.utc)},
            )

    factory = build_session_factory(Settings(database_url="sqlite+pysqlite:///:memory:"))
    Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        session.add(
            CorridorVersion(
                id="11111111-1111-4111-8111-111111111111",
                corridor_key="test",
                graph_version="v1",
                graph_sha256="a" * 64,
                status="active",
                effective_from=datetime.now(timezone.utc),
            )
        )
        session.flush()
        session.add(
            RoadSegment(
                id="22222222-2222-4222-8222-222222222222",
                corridor_version_id="11111111-1111-4111-8111-111111111111",
                external_ref="way/1",
                segment_type="unknown",
                direction="sideways",
                geometry={"type": "LineString", "coordinates": [[91, 26], [92, 25]]},
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
