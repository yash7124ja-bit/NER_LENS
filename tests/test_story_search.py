import json
from types import SimpleNamespace

import httpx
import pytest
import weaviate

from ner_lens.config import Settings
from ner_lens.story_search import connection, index_stories, search_stories


def test_index_retry_ids_and_partial_failure():
    settings = Settings(
        providers={
            "WEAVIATE_REST_ENDPOINT": "test.weaviate.cloud",
            "WEAVIATE_API": "private-test-key",
        }
    )
    objects = []

    def handle(req):
        assert req.headers["Authorization"] == "Bearer private-test-key"
        body = json.loads(req.content) if req.content else {}
        if req.url.path.startswith("/v1/schema"):
            return httpx.Response(200, json={})
        if req.url.path == "/v1/batch/objects":
            objects.append(body["objects"])
            return httpx.Response(200, json=[{"result": {"status": "SUCCESS"}}])
        raise AssertionError(f"unexpected Weaviate REST path: {req.url.path}")

    transport = httpx.MockTransport(handle)
    rows = [
        {
            "id": "SIH-01",
            "title": "Medicine",
            "role": "dispatcher",
            "story": "Deliver medicine",
            "acceptance": ["Stored"],
            "status": "implemented",
            "evidence": "test",
        }
    ]
    assert index_stories(settings, rows, transport)["indexed"] == 1
    index_stories(settings, rows, transport)
    assert objects[0][0]["id"] == objects[1][0]["id"]

    def failed(req):
        return httpx.Response(
            200,
            json={}
            if req.url.path.startswith("/v1/schema")
            else [{"result": {"status": "FAILED", "errors": {"error": [{"message": "private"}]}}}],
        )

    with pytest.raises(ValueError, match="partial_index_failure"):
        index_stories(settings, rows, httpx.MockTransport(failed))
    assert "private-test-key" not in repr(settings)


def test_search_uses_cloud_grpc_bm25(monkeypatch):
    settings = Settings(
        providers={
            "WEAVIATE_REST_ENDPOINT": "test.weaviate.cloud",
            "WEAVIATE_API": "private-test-key",
        }
    )
    calls = {}

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        @property
        def collections(self):
            return self

        @property
        def query(self):
            return self

        def use(self, name):
            calls["collection"] = name
            return self

        def bm25(self, **kwargs):
            calls.update(kwargs)
            return SimpleNamespace(objects=[SimpleNamespace(properties={"storyId": "SIH-01"})])

    def connect(**kwargs):
        calls["url"] = kwargs["cluster_url"]
        return FakeClient()

    monkeypatch.setattr(weaviate, "connect_to_weaviate_cloud", connect)
    assert search_stories(settings, 'medicine " } injected') == ["SIH-01"]
    assert calls["url"] == "https://test.weaviate.cloud"
    assert calls["collection"] == "NERLensUserStory"
    assert calls["query"] == 'medicine " } injected'


def test_endpoint_and_collection_reject_credentials_and_injection():
    for url in [
        "http://test.weaviate.cloud",
        "https://user:secret@test.weaviate.cloud",
        "https://test.weaviate.cloud/?key=secret",
    ]:
        with pytest.raises(ValueError):
            connection(Settings(providers={"WEAVIATE_REST_ENDPOINT": url, "WEAVIATE_API": "test"}))
    with pytest.raises(ValueError):
        connection(
            Settings(
                providers={
                    "WEAVIATE_REST_ENDPOINT": "test.weaviate.cloud",
                    "WEAVIATE_API": "test",
                    "WEAVIATE_STORY_COLLECTION": "Class{injection}",
                }
            )
        )
