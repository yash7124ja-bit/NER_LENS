import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from ner_lens.app import create_app
from ner_lens.config import Settings
from ner_lens.db import build_session_factory
from ner_lens.replay import initialize
from ner_lens.sources import SourceSnapshot, health, refresh, retrieve, safe_url


def test_dotenv_loading_preserves_injected_values(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('DATABASE_URL=sqlite:///from-file.sqlite\nNASA_EARTHDATA_TOKEN="test#key"\n')
    monkeypatch.setenv("NER_LENS_ENV_FILE", str(env))
    monkeypatch.setenv("DATABASE_URL", "sqlite:///injected.sqlite")
    monkeypatch.delenv("NASA_EARTHDATA_TOKEN", raising=False)
    settings = Settings.from_env()
    assert settings.database_url == "sqlite:///injected.sqlite"
    assert settings.providers["NASA_EARTHDATA_TOKEN"] == "test#key"
    assert "test#key" not in repr(settings)


def test_blank_example_uses_local_defaults(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("DATABASE_URL=\nNER_LENS_ENV=\nAPI_REQUEST_TIMEOUT_SECONDS=\n")
    monkeypatch.setenv("NER_LENS_ENV_FILE", str(env))
    for key in ("DATABASE_URL", "NER_LENS_ENV", "API_REQUEST_TIMEOUT_SECONDS"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings.from_env()
    assert settings.database_url == "sqlite:///ner_lens_replay.sqlite"
    assert settings.environment == "replay" and settings.api_request_timeout_seconds == 10


@pytest.mark.parametrize("source,variable,response", [
    ("nasa", "NASA_EARTHDATA_TOKEN", {"feed": {"entry": [{"id": "GPM", "title": "IMERG"}]}}),
    ("copernicus", "COPERNICUS_API_KEY", {"id": "reanalysis-era5-land"}),
    ("graphhopper", "GRAPHHOPPER_API_KEY", {"paths": [{"distance": 100, "time": 2000,
        "points": {"type": "LineString", "coordinates": [[91, 26], [92, 25]]}}]}),
    ("mappls", "MAPPLS_API_KEY", {"routes": [{"distance": 100, "duration": 2,
        "geometry": {"type": "LineString", "coordinates": [[91, 26], [92, 25]]}}]}),
])
def test_real_request_auth_and_normalization(source, variable, response):
    def handler(request):
        assert "test-secret" in str(request.url) or any(
            "test-secret" in value for value in request.headers.values())
        if source == "graphhopper":
            assert request.url.params.get_list("point") == ["26,91", "25,92"]
        if source == "mappls":
            assert request.url.path.endswith("91,26;92,25")
        return httpx.Response(200, json=response)

    settings = Settings(providers={variable: "test-secret",
        "COPERNICUS_API_URL": "https://cds.climate.copernicus.eu/api"})
    result = retrieve(source, settings, points=[[91, 26], [92, 25]],
                      transport=httpx.MockTransport(handler))
    assert result.status == "available"
    assert result.records and result.sha256 and result.raw
    assert "test-secret" not in result.url + json.dumps(result.records)
    if source in ("mappls", "graphhopper"):
        assert result.records[0]["duration_seconds"] == 2


@pytest.mark.parametrize("response,reason", [
    (httpx.Response(401), "authentication_failed"),
    (httpx.Response(429), "rate_limited"),
    (httpx.Response(302, headers={"location": "http://127.0.0.1"}), "redirect_rejected"),
    (httpx.Response(200, text="<html>Login</html>"), "schema_invalid"),
    (httpx.Response(200, json={"feed": {"entry": []}, "echo": "test-secret"}),
     "credential_echo_rejected"),
])
def test_fail_closed_and_no_secrets(response, reason):
    result = retrieve("nasa", Settings(providers={"NASA_EARTHDATA_TOKEN": "test-secret"}),
                      transport=httpx.MockTransport(lambda _: response))
    assert result.status == "failed" and result.reason == reason
    assert result.records == []


def test_sachet_rss_and_permission_gate():
    def handler(request):
        assert request.url.path.endswith("rss_india.xml")
        return httpx.Response(200, text='''<rss><channel><item><title>Heavy rain</title>
        <guid>one</guid><pubDate>Mon, 14 Sep 2020 01:00:00 GMT</pubDate>
        </item></channel></rss>''')
    settings = Settings(providers={"SACHET_RSS_URL": "https://sachet.ndma.gov.in/",
                                   "IMD_API_STATUS": "permission_required"})
    transport = httpx.MockTransport(handler)
    result = retrieve("sachet", settings, transport=transport)
    assert result.status == "available"
    assert result.records[0]["observed_at"] is None
    assert "not_road_passability" in result.records[0]["quality_flags"]
    assert retrieve("imd", settings, transport=transport).reason == "permission_required"
    assert retrieve("sachet", settings, transport=httpx.MockTransport(lambda _: httpx.Response(
        200, text='<!DOCTYPE rss [<!ENTITY foo "boom">]><rss/>'))).status == "failed"


@pytest.mark.parametrize("url", ["http://sachet.ndma.gov.in/", "https://127.0.0.1/",
    "https://sachet.ndma.gov.in.evil.test/", "https://user:secret@sachet.ndma.gov.in/",
    "https://sachet.ndma.gov.in/?token=secret"])
def test_egress_allowlist(url):
    with pytest.raises(ValueError):
        safe_url("sachet", url, resolve=False)


def test_migrated_persistence_and_stale_health(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'sources.sqlite'}")
    initialize(settings)
    factory = build_session_factory(settings)
    try:
        configured = replace(settings, providers={"NASA_EARTHDATA_TOKEN": "secret"})
        refresh(factory, configured, sources=("nasa",), transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"feed": {"entry": [{"id": "GPM"}]}})))
        with factory.begin() as session:
            row = session.query(SourceSnapshot).one()
            row.retrieved_at = datetime.now(timezone.utc) - timedelta(days=2)
        assert health(factory, settings)["sources"][1]["status"] == "stale"
        with TestClient(create_app(settings, factory)) as client:
            result = client.get("/health/sources")
            assert result.status_code == 200
            assert "raw" not in result.text and "secret" not in result.text
            assert result.json()["operational_status_effect"] == "none"
    finally:
        factory.kw["bind"].dispose()
