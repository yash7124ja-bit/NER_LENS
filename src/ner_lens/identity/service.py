"""Server-side authorization primitive and trusted AuthContext boundary."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ner_lens.identity.models import Actor, AuditEvent, RoleAssignment, SessionRecord

SUPPORTED_ROLES = {
    "field_reporter",
    "reviewer",
    "dispatcher",
    "district_officer",
    "regional_viewer",
    "system_admin",
    "ingestion_service",
}

ROLE_ACTIONS: dict[str, frozenset[str]] = {
    "field_reporter": frozenset(
        {"create_field_report", "view_own_report", "upload_own_media", "submit_gps"}
    ),
    "reviewer": frozenset({"review_evidence", "read_corridor_state"}),
    "dispatcher": frozenset({"create_mission", "compare_routes", "view_mission"}),
    "district_officer": frozenset(
        {"publish_status", "expire_status", "approve_alert", "read_corridor_state"}
    ),
    "regional_viewer": frozenset({"read_corridor_state"}),
    "system_admin": frozenset({"manage_config", "manage_users", "read_health"}),
    "ingestion_service": frozenset({"create_source_snapshot", "create_evidence"}),
}
STATUS_ACTIONS = frozenset({"publish_status", "expire_status"})
REPLAY_STATUS_ACTOR = "replay_district_officer"
REPLAY_STATUS_JURISDICTION = "replay_guwahati_silchar"


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Claims mapped by a trusted identity adapter; clients cannot supply this."""

    actor_id: str
    actor_type: str
    roles: tuple[str, ...]
    jurisdiction_ids: tuple[str, ...]
    mission_ids: tuple[str, ...]
    session_id: str
    token_issued_at: datetime
    expires_at: datetime
    revoked: bool = False
    status_authority_actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class ResourceScope:
    jurisdiction_id: str | None = None
    mission_id: str | None = None
    owner_actor_id: str | None = None
    status_authority_actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    allowed: bool
    code: str
    reason: str


class AuthorizationService:
    def __init__(
        self,
        audit_sink: Callable[[AuditEvent], None] | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self._audit_sink = audit_sink
        self._session_factory = session_factory

    def authorize(
        self,
        actor: AuthContext,
        action: str,
        scope: ResourceScope,
        *,
        now: datetime | None = None,
        request_id: str | None = None,
    ) -> AuthorizationDecision:
        now = now or datetime.now(timezone.utc)
        request_id = request_id or str(uuid.uuid4())
        if self._session_factory:
            persisted = self._check_persisted_context(actor, action, scope, now, request_id)
            if persisted is not None:
                return persisted
        if actor.revoked or now >= actor.expires_at:
            return self._decide(
                actor, action, "session_expired", "session is expired or revoked", request_id
            )

        if not any(role in SUPPORTED_ROLES for role in actor.roles):
            return self._decide(
                actor, action, "role_denied", "actor has no supported role", request_id
            )
        if not any(action in ROLE_ACTIONS.get(role, frozenset()) for role in actor.roles):
            return self._decide(
                actor,
                action,
                "role_denied",
                "role is not allowed to perform this action",
                request_id,
            )
        if action in STATUS_ACTIONS:
            if not scope.jurisdiction_id:
                return self._decide(
                    actor,
                    action,
                    "jurisdiction_scope_required",
                    "status authority jurisdiction must be server-derived",
                    request_id,
                )
            if actor.actor_type == "synthetic" and (
                actor.actor_id != REPLAY_STATUS_ACTOR
                or scope.jurisdiction_id != REPLAY_STATUS_JURISDICTION
            ):
                return self._decide(
                    actor,
                    action,
                    "replay_authority_scope_denied",
                    "synthetic replay authority is bound to its declared jurisdiction",
                    request_id,
                )
            if (
                actor.status_authority_actor_id != actor.actor_id
                or scope.status_authority_actor_id != actor.status_authority_actor_id
            ):
                return self._decide(
                    actor,
                    action,
                    "status_authority_required",
                    "status authority binding is required",
                    request_id,
                )
        if scope.jurisdiction_id and scope.jurisdiction_id not in actor.jurisdiction_ids:
            return self._decide(
                actor,
                action,
                "jurisdiction_scope_denied",
                "object is outside actor jurisdiction",
                request_id,
            )
        if scope.mission_id and scope.mission_id not in actor.mission_ids:
            return self._decide(
                actor,
                action,
                "mission_scope_denied",
                "object is outside actor mission scope",
                request_id,
            )
        if scope.owner_actor_id and scope.owner_actor_id != actor.actor_id:
            return self._decide(
                actor, action, "object_scope_denied", "object is owned by another actor", request_id
            )
        return self._decide(
            actor, action, "allowed", "authorization granted", request_id, allowed=True
        )

    def _check_persisted_context(
        self,
        actor: AuthContext,
        action: str,
        scope: ResourceScope,
        now: datetime,
        request_id: str,
    ) -> AuthorizationDecision | None:
        assert self._session_factory is not None
        with self._session_factory() as session:
            stored_actor = session.get(Actor, actor.actor_id)
            if stored_actor is None or not stored_actor.active:
                return self._decide(
                    actor, action, "actor_inactive", "actor is not active", request_id
                )
            stored_session = session.get(SessionRecord, actor.session_id)
            if (
                stored_session is None
                or stored_session.actor_id != actor.actor_id
                or not stored_session.is_valid(now)
            ):
                return self._decide(
                    actor, action, "session_expired", "session is expired or revoked", request_id
                )
            assignments = session.scalars(
                select(RoleAssignment).where(RoleAssignment.actor_id == actor.actor_id)
            ).all()
        allowed_roles = {
            assignment.role
            for assignment in assignments
            if assignment.jurisdiction_id is None
            or assignment.jurisdiction_id == scope.jurisdiction_id
        }
        if not any(role in allowed_roles for role in actor.roles):
            return self._decide(
                actor,
                action,
                "role_scope_denied",
                "actor role assignment is outside the object scope",
                request_id,
            )
        return None

    def _decide(
        self,
        actor: AuthContext,
        action: str,
        code: str,
        reason: str,
        request_id: str,
        *,
        allowed: bool = False,
    ) -> AuthorizationDecision:
        decision = AuthorizationDecision(allowed=allowed, code=code, reason=reason)
        if self._audit_sink:
            self._audit_sink(
                AuditEvent(
                    id=str(uuid.uuid4()),
                    actor_id=actor.actor_id,
                    action="authorization.decision",
                    target_type="authorization",
                    target_id=action,
                    request_id=request_id,
                    before_hash=None,
                    after_hash=None,
                    reason=reason,
                    outcome="allowed" if allowed else "denied",
                )
            )
        return decision
