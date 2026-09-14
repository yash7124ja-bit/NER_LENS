import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from ner_lens.app import create_app
from ner_lens.config import Settings
from ner_lens.contracts import ErrorResponse
from ner_lens.corridor.importer import bind_corridor
from ner_lens.corridor.models import CorridorVersion
from ner_lens.db import build_session_factory
from ner_lens.identity.accounts import provision_account
from ner_lens.identity.models import Actor, Jurisdiction, RoleAssignment, SessionRecord
from ner_lens.identity.replay import session_key
from ner_lens.replay import initialize


@pytest.fixture
def account_api(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'login.sqlite'}", login_attempt_limit=3
    )
    initialize(settings)
    factory = build_session_factory(settings)
    email, password, display = f"{uuid4().hex}@example.test", secrets.token_urlsafe(24), uuid4().hex
    scope, name = str(uuid4()), uuid4().hex
    with factory.begin() as session:
        session.add(Jurisdiction(id=scope, code=scope, name=scope))
        corridor_id = session.scalar(select(CorridorVersion.id))
    bind_corridor(factory, corridor_id, name, scope)
    actor = provision_account(factory, email, password, display, ("regional_viewer",), (scope,))
    with TestClient(create_app(settings, factory)) as client:
        yield (
            client,
            factory,
            settings,
            {
                "email": email,
                "password": password,
                "display_name": display,
                "actor_id": actor.id,
                "scope": scope,
                "corridor_id": corridor_id,
                "name": name,
            },
        )
    factory.kw["bind"].dispose()


def test_cookie_login_restore_scope_and_logout(account_api):
    client, factory, settings, account = account_api
    assert client.get("/v1/auth/session").status_code == 401
    response = client.post(
        "/v1/auth/login",
        json={
            "email": " " + account["email"].upper() + " ",
            "password": account["password"],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["email"] == account["email"]
    assert body["user"]["display_name"] == account["display_name"]
    assert body["user"]["roles"] == ["regional_viewer"]
    assert body["user"]["jurisdiction_ids"] == [account["scope"]]
    cookie = client.cookies.get(settings.session_cookie_name)
    assert cookie and cookie not in response.text
    assert account["password"] not in response.text
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    assert response.headers["cache-control"] == "no-store"
    with TestClient(create_app(settings, factory)) as restored:
        restored.cookies.set(settings.session_cookie_name, cookie)
        assert restored.get("/v1/auth/session").json() == body
    catalog = client.get("/v1/corridors")
    assert catalog.status_code == 200
    assert catalog.json()["corridors"][0]["name"] == account["name"]
    assert client.get(f"/v1/corridors/{account['corridor_id']}/state").status_code == 200
    assert client.post("/v1/auth/logout").status_code == 204
    assert client.cookies.get(settings.session_cookie_name) is None
    assert client.post("/v1/auth/logout").status_code == 204
    client.cookies.set(settings.session_cookie_name, cookie)
    assert client.get("/v1/auth/session").status_code == 401
    assert client.get("/v1/corridors").status_code == 401


def test_wrong_or_unknown_credentials_are_generic_and_throttled(account_api):
    client, _, settings, account = account_api
    errors = []
    for email in (account["email"], f"{uuid4().hex}@example.test", account["email"]):
        response = client.post(
            "/v1/auth/login",
            json={
                "email": email,
                "password": secrets.token_urlsafe(24),
            },
        )
        assert response.status_code == 401
        ErrorResponse.model_validate(response.json())
        errors.append(response.json()["error"]["message"])
        assert email not in response.text
    assert len(set(errors)) == 1
    response = client.post(
        "/v1/auth/login",
        json={
            "email": account["email"],
            "password": account["password"],
        },
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert response.headers["retry-after"] == str(settings.login_window_seconds)
    assert client.cookies.get(settings.session_cookie_name) is None


@pytest.mark.parametrize("change", ["disabled", "expired", "roles", "scope"])
def test_session_rechecks_persisted_account_and_permissions(account_api, change):
    client, factory, settings, account = account_api
    response = client.post(
        "/v1/auth/login",
        json={
            "email": account["email"],
            "password": account["password"],
        },
    )
    assert response.status_code == 200
    token = client.cookies.get(settings.session_cookie_name)
    with factory.begin() as session:
        if change == "disabled":
            session.get(Actor, account["actor_id"]).active = False
        elif change == "expired":
            session.get(SessionRecord, session_key(token)).expires_at = datetime.now(
                timezone.utc
            ) - timedelta(seconds=1)
        elif change == "roles":
            session.execute(
                delete(RoleAssignment).where(RoleAssignment.actor_id == account["actor_id"])
            )
        else:
            scope = str(uuid4())
            session.add(Jurisdiction(id=scope, code=scope, name=scope))
            session.get(CorridorVersion, account["corridor_id"]).jurisdiction_id = scope
    state = client.get(f"/v1/corridors/{account['corridor_id']}/state")
    if change in {"disabled", "expired"}:
        assert client.get("/v1/auth/session").status_code == 401
        assert state.status_code == 401
    else:
        restored = client.get("/v1/auth/session")
        assert restored.status_code == 200
        if change == "roles":
            assert restored.json()["user"]["roles"] == []
        assert state.status_code == 403


def test_cross_origin_login_and_logout_are_rejected(account_api):
    client, _, _, account = account_api
    body = {"email": account["email"], "password": account["password"]}
    for headers in ({"origin": "https://example.invalid"}, {"sec-fetch-site": "cross-site"}):
        assert client.post("/v1/auth/login", json=body, headers=headers).status_code == 403
    assert (
        client.post(
            "/v1/auth/login", json=body, headers={"origin": "http://testserver"}
        ).status_code
        == 200
    )
    assert (
        client.post("/v1/auth/logout", headers={"origin": "https://example.invalid"}).status_code
        == 403
    )
    assert client.get("/v1/auth/session").status_code == 200
    assert (
        client.post("/v1/auth/logout", headers={"origin": "http://testserver"}).status_code == 204
    )
