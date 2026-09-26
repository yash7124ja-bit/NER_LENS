from fastapi import HTTPException
from fastapi.testclient import TestClient

from ner_lens.app import create_app
from ner_lens.config import Settings


def test_route_errors_expose_only_approved_reasons():
    app = create_app(Settings())

    @app.get("/test-error/{status}/{reason}")
    def fail(status: int, reason: str):
        raise HTTPException(status, reason)

    client = TestClient(app)
    for status, reason in (
        (409, "source_snapshot_expired"),
        (409, "decision_snapshot_changed"),
        (502, "upstream_unavailable"),
    ):
        response = client.get(f"/test-error/{status}/{reason}")
        assert response.status_code == status
        assert response.json()["error"]["details"] == [{"field": "route", "reason": reason}]
        assert response.headers["cache-control"] == "no-store"
    for status, reason in ((409, "private-secret"), (403, "source_snapshot_expired")):
        response = client.get(f"/test-error/{status}/{reason}")
        assert response.json()["error"]["details"] == []
        assert reason not in response.text
