import hashlib
import io
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import func, select
from test_operations import api as operations_api  # noqa: F401
from test_operations import post, report_body

from ner_lens.media import MAX_UPLOAD_BYTES, MediaObject, build_router, scan_pending


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
