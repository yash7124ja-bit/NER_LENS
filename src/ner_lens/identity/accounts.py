"""Local database accounts and bounded, digest-backed sessions."""

import base64
import getpass
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session, sessionmaker

from ner_lens.config import Settings
from ner_lens.db import build_session_factory, session_scope
from ner_lens.identity.models import (
    Actor,
    AuditEvent,
    Jurisdiction,
    LocalAccount,
    LoginThrottle,
    RoleAssignment,
    SessionRecord,
)
from ner_lens.identity.replay import authenticate, session_key
from ner_lens.identity.service import SUPPORTED_ROLES, AuthContext


class InvalidCredentials(ValueError):
    """Credentials do not identify an active account."""


class RateLimited(ValueError):
    """Login attempts have exceeded the configured window."""


def _email(value: str) -> str:
    value = value.strip().casefold()
    if len(value) > 254 or value.count("@") != 1 or any(c.isspace() for c in value):
        raise ValueError("Invalid email address")
    local, domain = value.split("@")
    if not local or not domain or "." not in domain:
        raise ValueError("Invalid email address")
    return value


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**17,
        r=8,
        p=1,
        maxmem=256 * 1024 * 1024,
        dklen=32,
    )


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 1024:
        raise ValueError("Password must contain between 12 and 1024 characters")
    salt = secrets.token_bytes(16)
    digest = _derive(password, salt)
    return "scrypt$131072$8$1$" + "$".join(
        base64.b64encode(item).decode("ascii") for item in (salt, digest)
    )


def verify_password(password: str, encoded: str | None) -> bool:
    valid = False
    salt, expected = bytes(16), bytes(32)
    try:
        algorithm, n, r, p, salt_text, digest_text = (encoded or "").split("$")
        if (algorithm, n, r, p) == ("scrypt", "131072", "8", "1"):
            salt = base64.b64decode(salt_text, validate=True)
            expected = base64.b64decode(digest_text, validate=True)
            valid = len(salt) == 16 and len(expected) == 32
    except (ValueError, TypeError):
        pass
    # Missing/disabled accounts still perform the same password work.
    digest = _derive(password, salt if valid else bytes(16))
    return hmac.compare_digest(digest, expected) and valid


def _audit(
    session: Session, action: str, request_id: str, actor_id: str | None, outcome: str
) -> None:
    session.add(
        AuditEvent(
            id=str(uuid4()),
            actor_id=actor_id,
            action=action,
            target_type="identity",
            target_id=actor_id or "unknown",
            request_id=request_id,
            outcome=outcome,
        )
    )


def provision_account(
    factory: sessionmaker[Session],
    email: str,
    password: str,
    display_name: str,
    roles: tuple[str, ...],
    jurisdiction_ids: tuple[str, ...],
) -> Actor:
    email = _email(email)
    display_name = display_name.strip()
    if not display_name or len(display_name) > 255:
        raise ValueError("Display name is required and must fit 255 characters")
    if not roles or not set(roles) <= SUPPORTED_ROLES or not jurisdiction_ids:
        raise ValueError("Explicit supported roles and jurisdiction IDs are required")
    password_hash = hash_password(password)
    with session_scope(factory) as session:
        if any(session.get(Jurisdiction, scope) is None for scope in jurisdiction_ids):
            raise ValueError("Jurisdiction does not exist")
        account = session.scalar(select(LocalAccount).where(LocalAccount.email == email))
        assignments = {(role, scope) for role in roles for scope in jurisdiction_ids}
        if account is not None:
            actor = session.get(Actor, account.actor_id)
            existing = set(
                session.execute(
                    select(RoleAssignment.role, RoleAssignment.jurisdiction_id).where(
                        RoleAssignment.actor_id == account.actor_id
                    )
                ).all()
            )
            if (
                actor is None
                or not actor.active
                or actor.actor_type != "user"
                or account.display_name != display_name
                or existing != assignments
                or not verify_password(password, account.password_hash)
            ):
                raise ValueError("Account already exists with different settings")
            return actor
        actor = Actor(id=str(uuid4()), external_subject=str(uuid4()), actor_type="user")
        session.add(actor)
        session.flush()
        session.add(
            LocalAccount(
                actor_id=actor.id,
                email=email,
                display_name=display_name,
                password_hash=password_hash,
            )
        )
        for role, scope in sorted(assignments):
            session.add(
                RoleAssignment(id=str(uuid4()), actor_id=actor.id, role=role, jurisdiction_id=scope)
            )
        _audit(session, "account.provision", str(uuid4()), actor.id, "accepted")
        return actor


def profile(factory: sessionmaker[Session], actor: AuthContext) -> dict:
    with factory() as session:
        stored = session.get(Actor, actor.actor_id)
        record = session.get(SessionRecord, actor.session_id)
        if (
            stored is None
            or not stored.active
            or record is None
            or not record.is_valid(datetime.now(timezone.utc))
            or record.actor_id != actor.actor_id
        ):
            raise InvalidCredentials("Invalid credentials")
        account = session.get(LocalAccount, actor.actor_id)
        assignments = session.scalars(
            select(RoleAssignment).where(RoleAssignment.actor_id == actor.actor_id)
        ).all()
        return {
            "actor_id": stored.id,
            "email": account.email if account else None,
            "display_name": account.display_name if account else stored.external_subject,
            "roles": sorted({row.role for row in assignments}),
            "jurisdiction_ids": sorted(
                {row.jurisdiction_id for row in assignments if row.jurisdiction_id}
            ),
        }


def login(
    factory: sessionmaker[Session],
    email: str,
    password: str,
    request_id: str,
    client_key: str,
    session_ttl_seconds: int,
    attempt_limit: int,
    window_seconds: int,
) -> tuple[str, AuthContext, dict]:
    if min(session_ttl_seconds, attempt_limit, window_seconds) <= 0:
        raise ValueError("Login policy values must be positive")
    if len(email) > 254 or len(password) > 1024 or len(client_key) > 512:
        raise InvalidCredentials("Invalid credentials")
    normalized = email.strip().casefold()
    error = None
    token = None
    with session_scope(factory) as session:
        # ponytail: serialize login hashing; partition locks when login throughput requires it.
        if session.get_bind().dialect.name == "sqlite":
            session.execute(text("BEGIN IMMEDIATE"))
        elif session.get_bind().dialect.name == "postgresql":
            session.execute(text("SELECT pg_advisory_xact_lock(hashtext('ner_lens_login'))"))
        else:
            raise RuntimeError("Account login requires SQLite or PostgreSQL")
        now = datetime.now(timezone.utc)
        session.execute(
            delete(LoginThrottle).where(
                LoginThrottle.window_started <= now - timedelta(seconds=window_seconds)
            )
        )
        counters = []
        for kind, value in (("client", client_key), ("account", normalized)):
            key = hashlib.sha256((kind + ":" + value).encode()).hexdigest()
            counter = session.get(LoginThrottle, key)
            if counter is None:
                counter = LoginThrottle(key=key, window_started=now, attempts=0)
                session.add(counter)
            counters.append(counter)
            if counter.attempts >= attempt_limit:
                break
        if any(row.attempts >= attempt_limit for row in counters):
            error = RateLimited("Too many login attempts")
            _audit(session, "login.throttled", request_id, None, "denied")
        else:
            account = session.scalar(select(LocalAccount).where(LocalAccount.email == normalized))
            actor = session.get(Actor, account.actor_id) if account else None
            matched = verify_password(password, account.password_hash if account else None)
            if not matched or actor is None or not actor.active or actor.actor_type != "user":
                for counter in counters:
                    counter.attempts += 1
                error = InvalidCredentials("Invalid credentials")
                _audit(session, "login.failed", request_id, actor.id if actor else None, "denied")
            else:
                # A valid password clears this account's failures, not the client's other failures.
                counters[1].attempts = 0
                token = secrets.token_urlsafe(32)
                session.add(
                    SessionRecord(
                        id=session_key(token),
                        actor_id=actor.id,
                        token_issued_at=now,
                        expires_at=now + timedelta(seconds=session_ttl_seconds),
                        active=True,
                    )
                )
                _audit(session, "login.succeeded", request_id, actor.id, "accepted")
    if error is not None:
        raise error
    assert token is not None
    actor_context = authenticate(factory, token)
    if actor_context is None:
        raise InvalidCredentials("Invalid credentials")
    return token, actor_context, profile(factory, actor_context)


def logout(factory: sessionmaker[Session], token: str, request_id: str) -> None:
    with session_scope(factory) as session:
        record = session.get(SessionRecord, session_key(token))
        if record is not None and record.revoked_at is None:
            record.revoked_at = datetime.now(timezone.utc)
            record.active = False
            _audit(session, "logout", request_id, record.actor_id, "accepted")


def main() -> None:
    settings = Settings.from_env()
    email = os.getenv("NER_LENS_BOOTSTRAP_EMAIL") or input("Email: ")
    password = os.getenv("NER_LENS_BOOTSTRAP_PASSWORD") or getpass.getpass("Password: ")
    display_name = os.getenv("NER_LENS_BOOTSTRAP_DISPLAY_NAME") or input("Display name: ")
    roles = tuple(filter(None, os.getenv("NER_LENS_BOOTSTRAP_ROLES", "").split(",")))
    scopes = tuple(filter(None, os.getenv("NER_LENS_BOOTSTRAP_JURISDICTION_IDS", "").split(",")))
    factory = build_session_factory(settings)
    provision_account(factory, email, password, display_name, roles, scopes)
    print("Account provisioned.")


if __name__ == "__main__":
    main()
