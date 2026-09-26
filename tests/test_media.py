import hashlib
import io
import struct
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select
from test_operations import api as operations_api  # noqa: F401
from test_operations import post, report_body

from ner_lens.app import create_app
from ner_lens.config import Settings
from ner_lens.media import (
    MAX_UPLOAD_BYTES,
    ClamdScanner,
    MediaObject,
    S3MediaStorage,
    build_router,
    scan_pending,
)


@pytest.fixture
def media_api(operations_api):  # noqa: F811 - imported pytest fixture
    client, factory, selected, actors = operations_api
    client.app.include_router(build_router(factory, lambda: selected[0]))
    result = post(client, "/v1/field-reports", report_body())
    assert result.status_code == 201, result.text
    yield client, factory, selected, actors, result.json()["field_report_id"]


def picture():
    image = Image.new("RGB", (20, 20), "red")
    exif = Image.Exif()
    exif[270] = "private comment"
    exif[34853] = {1: "N", 2: (25.0, 0.0, 0.0), 3: "E", 4: (92.0, 0.0, 0.0)}
    stream = io.BytesIO()
    image.save(stream, "JPEG", exif=exif)
    return stream.getvalue()


def put(client, report_id, raw, *, slot=0, key="upload", content_type="image/jpeg", **extra):
    headers = {
        "Idempotency-Key": key,
        "Content-Type": content_type,
        "Content-Length": str(len(raw)),
        "X-Media-SHA256": hashlib.sha256(raw).hexdigest(),
        **extra,
    }
    return client.put(f"/v1/field-reports/{report_id}/media/{slot}", content=raw, headers=headers)


def test_quarantine_replay_and_protected_stripped_derivative(media_api):
    client, factory, selected, actors, report_id = media_api
    raw = picture()
    first = put(client, report_id, raw)
    assert first.status_code == 201, first.text
    assert first.json()["scan_state"] == "pending"
    assert first.json()["media_state"] == "incomplete"
    assert put(client, report_id, raw).json() == first.json()
    assert put(client, report_id, raw, key="new-key").json() == first.json()
    assert put(client, report_id, raw + b"changed").status_code == 409
    assert client.get(f"/v1/field-reports/{report_id}/media/0").status_code == 409
    # A test-only callback exercises the trusted scanner boundary, never production scanning.
    assert scan_pending(factory, lambda body: "clean" if body == raw else "rejected") == 1
    with factory() as session:
        row = session.scalar(select(MediaObject))
        assert row.raw == raw
        assert row.derivative != raw
        assert session.scalar(select(func.count()).select_from(MediaObject)) == 1
    derivative = client.get(f"/v1/field-reports/{report_id}/media/0")
    assert derivative.status_code == 200
    assert derivative.headers["cache-control"] == "private, no-store"
    with Image.open(io.BytesIO(derivative.content)) as stripped:
        assert dict(stripped.getexif()) == {}
        assert stripped.format == "JPEG"
    assert b"private comment" not in derivative.content
    # Mutation receipts stay stable while GET reports the current scanner outcome.
    assert put(client, report_id, raw).json() == first.json()
    assert client.get(f"/v1/field-reports/{report_id}/media").json()["media_state"] == "complete"
    selected[0] = actors["reviewer-north"]
    assert client.get(f"/v1/field-reports/{report_id}/media/0").status_code == 200
    assert put(client, report_id, raw, slot=1).status_code == 403
    selected[0] = actors["field_reporter-south"]
    assert client.get(f"/v1/field-reports/{report_id}/media/0").status_code == 403
    assert client.get(f"/v1/field-reports/{report_id}/media").status_code == 403
    assert put(client, report_id, raw, slot=1).status_code == 403


def test_invalid_images_lengths_digest_and_partial_retry(media_api):
    client, factory, _, _, report_id = media_api
    raw = picture()
    oversized = put(client, report_id, raw, **{"Content-Length": str(MAX_UPLOAD_BYTES + 1)})
    assert oversized.status_code == 413
    assert (
        put(
            client, report_id, b"<svg><script>bad()</script></svg>", content_type="image/svg+xml"
        ).status_code
        == 415
    )
    assert put(client, report_id, raw, slot=4).status_code == 422
    partial = put(
        client,
        report_id,
        raw[:20],
        **{"Content-Length": str(len(raw)), "X-Media-SHA256": hashlib.sha256(raw).hexdigest()},
    )
    assert partial.status_code == 422
    state = client.get(f"/v1/field-reports/{report_id}/media").json()
    assert state["media"][0]["upload_state"] == "incomplete"
    assert state["media"][0]["scan_reason"] == "content_length_mismatch"
    assert put(client, report_id, raw).status_code == 201
    wrong_digest = put(client, report_id, raw, slot=1, **{"X-Media-SHA256": "0" * 64})
    assert wrong_digest.status_code == 422
    invalid = put(client, report_id, b"not an image", slot=2)
    assert invalid.status_code == 422
    wrong_type = put(client, report_id, raw, slot=3, content_type="image/png")
    assert wrong_type.status_code == 422
    with factory() as session:
        invalid_rows = session.scalars(select(MediaObject).where(MediaObject.slot > 0)).all()
        assert all(
            row.raw is None and row.derivative is None and row.scan_state == "pending"
            for row in invalid_rows
        )


@pytest.mark.parametrize("verdict", ["rejected", "unexpected"])
def test_failed_scanner_never_releases_image(media_api, verdict):
    client, factory, _, _, report_id = media_api
    assert put(client, report_id, picture(), key=str(uuid4())).status_code == 201
    scan_pending(factory, lambda _: verdict)
    state = client.get(f"/v1/field-reports/{report_id}/media").json()["media"][0]
    assert state["scan_state"] == ("rejected" if verdict == "rejected" else "error")
    assert client.get(f"/v1/field-reports/{report_id}/media/0").status_code == 409


def test_hosted_media_requires_scanner_and_private_store(operations_api):  # noqa: F811
    (
        client,
        factory,
        selected,
        _,
    ) = operations_api
    app = FastAPI()
    app.include_router(build_router(factory, lambda: selected[0], require_services=True))
    report_id = post(client, "/v1/field-reports", report_body()).json()["field_report_id"]
    with TestClient(app) as hosted:
        assert put(hosted, report_id, picture()).status_code == 503
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(MediaObject)) == 0


def test_missing_media_services_are_reported_without_database_blame(operations_api):  # noqa: F811
    _, factory, _, _ = operations_api
    app = create_app(Settings(database_url=str(factory.kw["bind"].url)), factory)

    @app.get("/_media-unavailable")
    def unavailable():
        raise HTTPException(503, "media_scanner_or_storage_unavailable")

    with TestClient(app) as client:
        response = client.get("/_media-unavailable")
    assert response.status_code == 503
    assert response.json()["error"]["message"] == (
        "Evidence uploads require private storage and a trusted scanner"
    )


def test_media_upload_uses_media_limit_not_json_limit(operations_api):  # noqa: F811
    _, factory, _, _ = operations_api
    settings = Settings(database_url=str(factory.kw["bind"].url), max_request_bytes=128)
    with TestClient(create_app(settings, factory)) as client:
        response = put(client, "unknown", picture())
        assert response.status_code != 413
        assert client.post("/v1/unknown", content=b"x" * 129).status_code == 413


def test_private_object_storage_and_trusted_scan(operations_api):  # noqa: F811
    (
        client,
        factory,
        selected,
        _,
    ) = operations_api
    report_id = post(client, "/v1/field-reports", report_body()).json()["field_report_id"]

    class InMemoryS3:
        def __init__(self):
            self.objects = {}
            self.fail = "derivative"

        def put_object(self, **kwargs):
            if self.fail and kwargs["Key"].endswith(self.fail):
                raise OSError("store unavailable")
            assert "ACL" not in kwargs and "ServerSideEncryption" not in kwargs
            self.objects[kwargs["Key"]] = kwargs["Body"]

        def get_object(self, **kwargs):
            return {"Body": io.BytesIO(self.objects[kwargs["Key"]])}

        def delete_object(self, **kwargs):
            self.objects.pop(kwargs["Key"], None)

    storage = S3MediaStorage("https://objects.example.test", "private", "auto", "id", "key")
    storage.client = InMemoryS3()
    verdict = ["unexpected"]
    app = FastAPI()
    app.include_router(
        build_router(
            factory, lambda: selected[0], lambda _: verdict[0], storage, require_services=True
        )
    )
    with TestClient(app) as hosted:
        raw = picture()
        assert put(hosted, report_id, raw).status_code == 503
        verdict[0] = "clean"
        assert put(hosted, report_id, raw).status_code == 503
        assert storage.client.objects == {}
        storage.client.fail = ""
        first = put(hosted, report_id, raw)
        assert first.status_code == 201, first.text
        assert first.json()["scan_state"] == "clean"
        assert put(hosted, report_id, raw).json() == first.json()
        with factory() as session:
            row = session.scalar(select(MediaObject))
            assert row.raw is None and row.derivative is None
            assert row.storage_key.startswith(f"media/{row.id}/")
            assert row.derivative_sha256
        derivative = hosted.get(f"/v1/field-reports/{report_id}/media/0")
        assert derivative.status_code == 200
        with Image.open(io.BytesIO(derivative.content)) as stripped:
            assert dict(stripped.getexif()) == {}
        storage.client.objects[f"{row.storage_key}/derivative"] = b"tampered"
        assert hosted.get(f"/v1/field-reports/{report_id}/media/0").status_code == 503
    # The shared fixture downgrades to an older schema after this test.
    with factory.begin() as session:
        session.scalar(select(MediaObject)).storage_key = None


def test_clamd_wire_verdict_is_not_controlled_by_upload():
    raw = b"image"
    sent = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def settimeout(self, value):
            assert value == 10

        def sendall(self, value):
            sent.append(value)

        def recv(self, _):
            return b"stream: OK\0"

    from unittest.mock import patch

    with patch("ner_lens.media.socket.create_connection", return_value=FakeConnection()):
        assert ClamdScanner("private-clamd")(raw) == "clean"
    assert sent == [b"zINSTREAM\0", struct.pack("!I", len(raw)) + raw, b"\0\0\0\0"]
