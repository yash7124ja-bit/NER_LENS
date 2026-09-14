"""Local replay sessions, separate from a future OIDC verifier."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ner_lens.config import utc_datetime
from ner_lens.db import session_scope
from ner_lens.identity.models import (
    Actor,
    Jurisdiction,
    RoleAssignment,
    SessionRecord,
    StatusAuthority,
)
from ner_lens.identity.service import AuthContext, AuthorizationService, ResourceScope

JURISDICTION = "replay_guwahati_silchar"
VIEWER = "replay_regional_viewer"


def authorize_corridor(
    factory: sessionmaker[Session],
    actor: AuthContext,
    request_id: str,
    jurisdiction_id: str | None,
) -> bool:
    if jurisdiction_id is None:
        return False

    def audit(event):
        event.jurisdiction_id = jurisdiction_id
        with session_scope(factory) as session:
            session.add(event)

    return (
        AuthorizationService(session_factory=factory, audit_sink=audit)
        .authorize(
            actor,
            "read_corridor_state",
            ResourceScope(jurisdiction_id=jurisdiction_id),
            request_id=request_id,
        )
        .allowed
    )


def session_key(token: str) -> str:
    # 144-bit digest fits the existing opaque session identifier column.
    return hashlib.sha256(token.encode()).hexdigest()[:36]


def issue_viewer_session(factory: sessionmaker[Session]) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    with session_scope(factory) as session:
        if session.get(Jurisdiction, JURISDICTION) is None:
            session.add(
                Jurisdiction(
                    id=JURISDICTION, code=JURISDICTION, name="Synthetic replay jurisdiction"
                )
            )
            session.flush()
        actor = session.get(Actor, VIEWER)
        if actor is None:
            session.add(Actor(id=VIEWER, external_subject=VIEWER, actor_type="synthetic"))
            session.flush()
        elif not actor.active or actor.actor_type != "synthetic":
            raise ValueError("Replay viewer is disabled or has an incompatible identity")
        assignment = session.scalar(
            select(RoleAssignment).where(
                RoleAssignment.actor_id == VIEWER,
                RoleAssignment.role == "regional_viewer",
                RoleAssignment.jurisdiction_id == JURISDICTION,
            )
        )
        if assignment is None:
            session.add(
                RoleAssignment(
                    id=str(uuid4()),
                    actor_id=VIEWER,
                    role="regional_viewer",
                    jurisdiction_id=JURISDICTION,
                )
            )
        session.add(
            SessionRecord(
                id=session_key(token),
                actor_id=VIEWER,
                token_issued_at=now,
                expires_at=now + timedelta(hours=8),
            )
        )
    return token


def authenticate(factory: sessionmaker[Session], token: str) -> AuthContext | None:
    if not 32 <= len(token) <= 128 or not token.isascii():
        return None
    now = datetime.now(timezone.utc)
    with factory() as session:
        record = session.get(SessionRecord, session_key(token))
        if record is None or not record.is_valid(now):
            return None
        actor = session.get(Actor, record.actor_id)
        if actor is None or not actor.active or actor.actor_type not in {"synthetic", "user"}:
            return None
        assignments = session.scalars(
            select(RoleAssignment).where(RoleAssignment.actor_id == actor.id)
        ).all()
        issued = utc_datetime(record.token_issued_at)
        if issued > now:
            return None
        return AuthContext(
            actor_id=actor.id,
            actor_type=actor.actor_type,
            roles=tuple(sorted({row.role for row in assignments})),
            jurisdiction_ids=tuple(
                sorted({row.jurisdiction_id for row in assignments if row.jurisdiction_id})
            ),
            mission_ids=(),
            session_id=record.id,
            token_issued_at=issued,
            expires_at=utc_datetime(record.expires_at),
            status_authority_actor_id=actor.id
            if session.scalar(
                select(StatusAuthority.actor_id)
                .where(StatusAuthority.actor_id == actor.id, StatusAuthority.active.is_(True))
                .limit(1)
            )
            else None,
        )
