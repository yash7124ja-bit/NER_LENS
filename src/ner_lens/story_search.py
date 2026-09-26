"""Weaviate keyword index for non-sensitive SIH stories; PostgreSQL stays authoritative."""

import json
import re
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

import httpx
import weaviate
from weaviate.classes.init import Auth
from weaviate.exceptions import WeaviateBaseError

from ner_lens.config import Settings


def connection(settings):
    values = settings.providers
    raw = values.get("WEAVIATE_REST_ENDPOINT", "").strip()
    key = values.get("WEAVIATE_API", "")
    if not raw or not key:
        raise ValueError("weaviate_not_configured")
    url = raw if "://" in raw else "https://" + raw
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("invalid_weaviate_endpoint")
    collection = values.get("WEAVIATE_STORY_COLLECTION") or "NERLensUserStory"
    if not re.fullmatch(r"[A-Z][A-Za-z0-9_]{0,99}", collection):
        raise ValueError("invalid_weaviate_collection")
    return url.rstrip("/"), key, collection


def client(settings, transport=None):
    url, key, _ = connection(settings)
    return httpx.Client(
        base_url=url,
        headers={"Authorization": "Bearer " + key},
        timeout=20,
        follow_redirects=False,
        transport=transport,
    )


def index_stories(settings, stories, transport=None):
    _, _, collection = connection(settings)
    fields = ["storyId", "title", "role", "story", "acceptance", "status", "evidence"]
    with client(settings, transport) as c:
        schema = c.get("/v1/schema/" + collection)
        if schema.status_code == 404:
            schema = c.post(
                "/v1/schema",
                json={
                    "class": collection,
                    "vectorizer": "none",
                    "description": (
                        "NER LENS SIH user stories; BM25 keyword index; "
                        "no operational personal data."
                    ),
                    "vectorIndexConfig": {"skip": True},
                    "properties": [{"name": field, "dataType": ["text"]} for field in fields],
                },
            )
        schema.raise_for_status()
        objects = [
            {
                "class": collection,
                "id": str(uuid5(NAMESPACE_URL, collection + "/" + row["id"])),
                "properties": {
                    "storyId": row["id"],
                    "title": row["title"],
                    "role": row["role"],
                    "story": row["story"],
                    "acceptance": "\n".join(row["acceptance"]),
                    "status": row["status"],
                    "evidence": row["evidence"],
                },
            }
            for row in stories
        ]
        if not objects:
            return {"indexed": 0, "search_mode": "weaviate_bm25"}
        response = c.post("/v1/batch/objects", json={"objects": objects})
        response.raise_for_status()
        results = response.json()
        if (
            not isinstance(results, list)
            or len(results) != len(objects)
            or any(row.get("result", {}).get("status") != "SUCCESS" for row in results)
        ):
            raise ValueError("weaviate_partial_index_failure")
        return {"indexed": len(results), "search_mode": "weaviate_bm25"}


def search_stories(settings, query):
    url, key, collection = connection(settings)
    if not query.strip() or len(query) > 300:
        raise ValueError("invalid_search_query")
    try:
        with weaviate.connect_to_weaviate_cloud(
            cluster_url=url, auth_credentials=Auth.api_key(key), skip_init_checks=True
        ) as c:
            results = c.collections.use(collection).query.bm25(
                query=query,
                query_properties=["title^2", "story", "acceptance", "evidence"],
                limit=20,
            )
            return [row.properties["storyId"] for row in results.objects]
    except (WeaviateBaseError, KeyError, AttributeError):
        raise ValueError("weaviate_query_failed") from None


if __name__ == "__main__":
    from sqlalchemy import select

    from ner_lens.administration import Story
    from ner_lens.db import build_session_factory

    settings = Settings.from_env()
    factory = build_session_factory(settings)
    with factory() as session:
        rows = [row.payload for row in session.scalars(select(Story))]
    try:
        print(json.dumps(index_stories(settings, rows)))
    except (ValueError, httpx.HTTPError):
        raise SystemExit(
            "Weaviate indexing failed; check server configuration and collection access."
        ) from None
