"""Server-side authorization primitive and trusted AuthContext boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from ner_lens.identity.models import AuditEvent

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
    def __init__(self, audit_sink: Callable[[AuditEvent], None] | None = None) -> None:
        self._audit_sink = audit_sink

    def authorize(
        self,
        actor: AuthContext,
        action: str,
        scope: ResourceScope,
        *,
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        now = now or datetime.now(timezone.utc)
        if actor.revoked or now >= actor.expires_at:
            return self._decide(actor, action, "session_expired", "session is expired or revoked")

        if not any(role in SUPPORTED_ROLES for role in actor.roles):
            return self._decide(actor, action, "role_denied", "actor has no supported role")
        if not any(action in ROLE_ACTIONS.get(role, frozenset()) for role in actor.roles):
            return self._decide(
                actor, action, "role_denied", "role is not allowed to perform this action"
            )
        if scope.jurisdiction_id and scope.jurisdiction_id not in actor.jurisdiction_ids:
            return self._decide(
                actor,
                action,
                "jurisdiction_scope_denied",
                "object is outside actor jurisdiction",
            )
        if scope.mission_id and scope.mission_id not in actor.mission_ids:
            return self._decide(
                actor, action, "mission_scope_denied", "object is outside actor mission scope"
            )
        if scope.owner_actor_id and scope.owner_actor_id != actor.actor_id:
            return self._decide(
                actor, action, "object_scope_denied", "object is owned by another actor"
            )
        if action in STATUS_ACTIONS and scope.status_authority_actor_id != actor.actor_id:
            return self._decide(
                actor,
                action,
                "status_authority_required",
                "status authority binding is required",
            )
        return self._decide(actor, action, "allowed", "authorization granted", allowed=True)

    def _decide(
        self,
        actor: AuthContext,
        action: str,
        code: str,
        reason: str,
        *,
        allowed: bool = False,
    ) -> AuthorizationDecision:
        decision = AuthorizationDecision(allowed=allowed, code=code, reason=reason)
        if self._audit_sink:
            self._audit_sink(
                AuditEvent(
                    id=_deterministic_event_id(actor, action, code),
                    actor_id=actor.actor_id,
                    action="authorization.decision",
                    target_type="authorization",
                    target_id=action,
                    request_id=actor.session_id,
                    before_hash=None,
                    after_hash=None,
                    reason=reason,
                    outcome="allowed" if allowed else "denied",
                )
            )
        return decision


def _deterministic_event_id(actor: AuthContext, action: str, code: str) -> str:
    import hashlib

    digest = hashlib.sha256(
        f"{actor.actor_id}:{actor.session_id}:{action}:{code}".encode()
    ).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-4{digest[13:16]}-8{digest[17:20]}-{digest[20:32]}"
