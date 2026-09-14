from dataclasses import replace

from fastapi.testclient import TestClient
from sqlalchemy import insert, select
from sqlalchemy.dialects import postgresql

from ner_lens.app import create_app
from ner_lens.config import Settings, normalize_database_url
from ner_lens.corridor.models import RoadSegment
from ner_lens.db import build_session_factory
from ner_lens.replay import initialize


def test_postgis_expressions_and_driver():
    dialect = postgresql.dialect()
    assert "ST_AsGeoJSON" in str(select(RoadSegment.geometry).compile(dialect=dialect))
    assert "ST_GeomFromGeoJSON" in str(
        insert(RoadSegment).values(geometry={}).compile(dialect=dialect)
    )
    assert normalize_database_url("postgres://host/db") == "postgresql+psycopg://host/db"


def test_hosted_proxy_boundary(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'hosted.sqlite'}")
    initialize(settings)
    settings = replace(settings, proxy_secret="test-only-proxy", session_cookie_secure=True)
    factory = build_session_factory(settings)
    with TestClient(create_app(settings, factory)) as client:
        assert client.get("/health/ready").status_code == 200
        assert client.get("/v1/auth/session").status_code == 403
        assert (
            client.get(
                "/v1/auth/session", headers={"x-ner-lens-proxy": "test-only-proxy"}
            ).status_code
            == 401
        )
    factory.kw["bind"].dispose()
