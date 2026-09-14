import json

import httpx
import pytest

from ner_lens.config import Settings
from ner_lens.story_search import connection, index_stories, search_stories


def test_index_retry_ids_search_escaping_and_partial_failure():
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
        assert json.dumps('medicine " } injected') in body["query"]
        return httpx.Response(
            200, json={"data": {"Get": {"NERLensUserStory": [{"storyId": "SIH-01"}]}}}
        )

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
    assert search_stories(settings, 'medicine " } injected', transport) == ["SIH-01"]

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
