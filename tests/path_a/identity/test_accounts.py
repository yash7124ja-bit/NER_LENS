import hashlib
import importlib
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import delete, inspect, select

from ner_lens.config import Settings
from ner_lens.corridor.importer import bind_corridor
from ner_lens.corridor.models import Base, CorridorVersion
from ner_lens.db import build_session_factory
from ner_lens.identity.accounts import (
    InvalidCredentials,
    RateLimited,
    login,
    logout,
    profile,
    provision_account,
    verify_password,
)
from ner_lens.identity.models import (
    Actor,
    AuditEvent,
    Jurisdiction,
    LocalAccount,
    LoginThrottle,
    RoleAssignment,
    SessionRecord,
)
from ner_lens.identity.replay import authenticate, authorize_corridor, session_key


def test_account_lifecycle_permissions_throttling_and_no_plaintext():
    factory = build_session_factory(Settings())
    Base.metadata.create_all(factory.kw["bind"])
    scope = str(uuid4())
    email = f"{uuid4().hex}@example.test"
    password = secrets.token_urlsafe(24)
    wrong = secrets.token_urlsafe(24)
    display = uuid4().hex
    with factory.begin() as session:
        session.add(Jurisdiction(id=scope, code=scope, name=scope))
    actor = provision_account(factory, email, password, display, ("regional_viewer",), (scope,))
    assert (
        provision_account(
            factory, email.upper(), password, display, ("regional_viewer",), (scope,)
        ).id
        == actor.id
    )
    with pytest.raises(ValueError, match="different settings"):
        provision_account(factory, email, wrong, display, ("regional_viewer",), (scope,))
    with factory() as session:
        account = session.get(LocalAccount, actor.id)
        assert account.password_hash.startswith("scrypt$131072$8$1$")
        assert password not in account.password_hash
        assert verify_password(password, account.password_hash)
        assert not verify_password(wrong, account.password_hash)
    args = dict(
        request_id=str(uuid4()),
        client_key=uuid4().hex,
        session_ttl_seconds=3600,
        attempt_limit=3,
        window_seconds=60,
    )
    with pytest.raises(InvalidCredentials):
        login(factory, email, wrong, **args)
    for _ in range(args["attempt_limit"] + 1):
        token, context, user = login(factory, email.upper(), password, **args)
    with factory() as session:
        account_key = hashlib.sha256(("account:" + email).encode()).hexdigest()
        client_key = hashlib.sha256(("client:" + args["client_key"]).encode()).hexdigest()
        assert session.get(LoginThrottle, account_key).attempts == 0
        assert session.get(LoginThrottle, client_key).attempts == 1
    assert user["email"] == email
    assert user["display_name"] == display
    assert user["roles"] == ["regional_viewer"]
    assert authorize_corridor(factory, context, str(uuid4()), scope)
    with factory() as session:
        assert session.get(SessionRecord, token) is None
        assert session.get(SessionRecord, session_key(token)) is not None
    with factory.begin() as session:
        session.execute(delete(RoleAssignment).where(RoleAssignment.actor_id == actor.id))
    assert profile(factory, context)["roles"] == []
    assert not authorize_corridor(factory, context, str(uuid4()), scope)
    logout(factory, token, str(uuid4()))
    logout(factory, token, str(uuid4()))
    assert authenticate(factory, token) is None
    with pytest.raises(InvalidCredentials):
        profile(factory, context)
    for _ in range(2):
        with pytest.raises(InvalidCredentials):
            login(factory, email, wrong, **args)
    with pytest.raises(RateLimited):
        login(factory, email, password, **args)
    unknown = f"{uuid4().hex}@example.test"
    with pytest.raises(RateLimited):
        login(factory, unknown, wrong, **args)
    with factory.begin() as session:
        for counter in session.scalars(select(LoginThrottle)):
            counter.window_started = datetime.now(timezone.utc) - timedelta(minutes=2)
    with pytest.raises(InvalidCredentials):
        login(factory, unknown, wrong, **args)
    with factory.begin() as session:
        session.get(Actor, actor.id).active = False
    with pytest.raises(InvalidCredentials):
        login(factory, email, password, **args)
    with factory() as session:
        audit = " ".join(repr(event.__dict__) for event in session.scalars(select(AuditEvent)))
        assert password not in audit and wrong not in audit and email not in audit
        assert token not in audit


def test_local_account_migration_roundtrip_and_explicit_corridor_binding():
    factory = build_session_factory(Settings())
    engine = factory.kw["bind"]
    revisions = [
        importlib.import_module("migrations.versions." + name)
        for name in (
            "0001_foundation",
            "0002_session_record",
            "0003_corridor_import",
            "0004_local_accounts",
        )
    ]
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            for revision in revisions:
                revision.upgrade()
            assert "local_account" in inspect(connection).get_table_names()
            revisions[-1].downgrade()
            assert "local_account" not in inspect(connection).get_table_names()
            revisions[-1].upgrade()
    scope, corridor = str(uuid4()), str(uuid4())
    with factory.begin() as session:
        session.add(Jurisdiction(id=scope, code=scope, name=scope))
        session.add(
            CorridorVersion(
                id=corridor,
                corridor_key=uuid4().hex,
                graph_version=uuid4().hex,
                graph_sha256=secrets.token_hex(32),
                status="active",
                effective_from=datetime.now(timezone.utc),
            )
        )
    bind_corridor(factory, corridor, corridor, scope)
    with factory() as session:
        version = session.get(CorridorVersion, corridor)
        assert version.jurisdiction_id == scope and version.name == corridor


def test_parallel_unknown_account_attempts_share_database_throttle(tmp_path):
    factory = build_session_factory(Settings(database_url=f"sqlite:///{tmp_path / 'auth.sqlite'}"))
    Base.metadata.create_all(factory.kw["bind"])
    client = uuid4().hex

    def attempt(_):
        try:
            login(
                factory,
                f"{uuid4().hex}@example.test",
                secrets.token_urlsafe(24),
                request_id=str(uuid4()),
                client_key=client,
                session_ttl_seconds=60,
                attempt_limit=1,
                window_seconds=60,
            )
        except (InvalidCredentials, RateLimited) as error:
            return type(error)

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(attempt, range(2)))
    assert results.count(InvalidCredentials) == 1
    assert results.count(RateLimited) == 1
    with factory() as session:
        assert len(session.scalars(select(LoginThrottle)).all()) == 2
    factory.kw["bind"].dispose()
