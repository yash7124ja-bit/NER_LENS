import pytest
from sqlalchemy import select

from ner_lens.config import Settings
from ner_lens.corridor.models import CorridorVersion, RoadSegment
from ner_lens.db import build_session_factory
from ner_lens.replay import initialize
from ner_lens.spatial import assert_corridor_point


def test_projected_corridor_accepts_segment_and_rejects_far_point(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'spatial.sqlite'}")
    initialize(settings)
    factory = build_session_factory(settings)
    with factory() as session:
        corridor = session.scalar(select(CorridorVersion))
        segment = session.scalar(select(RoadSegment))
        assert_corridor_point(session, corridor.id, segment.geometry["coordinates"][0])
        with pytest.raises(ValueError, match="outside_corridor_bounds"):
            assert_corridor_point(session, corridor.id, [0, 0])
        with pytest.raises(ValueError, match="invalid_coordinates"):
            assert_corridor_point(session, corridor.id, [91, float("nan")])
    factory.kw["bind"].dispose()
