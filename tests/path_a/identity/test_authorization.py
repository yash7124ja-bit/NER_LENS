from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ner_lens.config import Settings
from ner_lens.corridor.models import Base
from ner_lens.db import build_session_factory
from ner_lens.identity.models import Actor, Jurisdiction, RoleAssignment, SessionRecord
from ner_lens.identity.service import AuthContext, AuthorizationService, ResourceScope


def actor_context(
    *,
    roles: tuple[str, ...],
    jurisdictions: tuple[str, ...] = ("kamrup",),
    missions: tuple[str, ...] = ("mission-1",),
    expires_in_seconds: int = 3600,
) -> AuthContext:
    now = datetime.now(timezone.utc)
    return AuthContext(
        actor_id="11111111-1111-4111-8111-111111111111",
        actor_type="user",
        roles=roles,
        jurisdiction_ids=jurisdictions,
        mission_ids=missions,
        session_id="22222222-2222-4222-8222-222222222222",
        token_issued_at=now,
        expires_at=now + timedelta(seconds=expires_in_seconds),
        status_authority_actor_id=(
            "11111111-1111-4111-8111-111111111111" if "district_officer" in roles else None
        ),
    )


def test_authorize_enforces_role_matrix_and_status_authority():
    service = AuthorizationService()
    scope = ResourceScope(jurisdiction_id="kamrup", mission_id="mission-1")

    assert service.authorize(actor_context(roles=("dispatcher",)), "compare_routes", scope).allowed
    assert not service.authorize(
        actor_context(roles=("regional_viewer",)), "compare_routes", scope
    ).allowed
    assert not service.authorize(
        actor_context(roles=("system_admin",)), "publish_status", scope
    ).allowed

    officer = actor_context(roles=("district_officer",))
    assert service.authorize(
        officer,
        "publish_status",
        ResourceScope(
            jurisdiction_id="kamrup",
            status_authority_actor_id=officer.actor_id,
        ),
    ).allowed


def test_authorize_denies_cross_jurisdiction_and_cross_mission_objects():
    service = AuthorizationService()
    actor = actor_context(roles=("dispatcher",), jurisdictions=("kamrup",), missions=("mission-1",))

    wrong_jurisdiction = service.authorize(
        actor,
        "compare_routes",
        ResourceScope(jurisdiction_id="cachar", mission_id="mission-1"),
    )
    wrong_mission = service.authorize(
        actor,
        "compare_routes",
        ResourceScope(jurisdiction_id="kamrup", mission_id="mission-2"),
    )
    assert not wrong_jurisdiction.allowed
    assert wrong_jurisdiction.code == "jurisdiction_scope_denied"
    assert not wrong_mission.allowed
    assert wrong_mission.code == "mission_scope_denied"


def test_authorize_denies_expired_or_revoked_sessions():
    service = AuthorizationService()
    expired = actor_context(roles=("reviewer",), expires_in_seconds=-1)
    decision = service.authorize(
        expired,
        "review_evidence",
        ResourceScope(jurisdiction_id="kamrup"),
    )
    assert not decision.allowed
    assert decision.code == "session_expired"

    record = SessionRecord(
        id=expired.session_id,
        actor_id=expired.actor_id,
        token_issued_at=expired.token_issued_at,
        expires_at=expired.expires_at,
        revoked_at=datetime.now(timezone.utc),
    )
    assert not record.is_valid(datetime.now(timezone.utc))


def test_authorization_decisions_emit_minimal_append_only_audit_events():
    events = []
    service = AuthorizationService(audit_sink=events.append)
    actor = actor_context(roles=("reviewer",))
    scope = ResourceScope(jurisdiction_id="kamrup")

    allowed = service.authorize(actor, "review_evidence", scope, request_id="req-allowed")
    denied = service.authorize(actor, "publish_status", scope, request_id="req-denied")

    assert allowed.allowed is True
    assert denied.allowed is False
    assert [event.outcome for event in events] == ["allowed", "denied"]
    assert all(event.action == "authorization.decision" for event in events)
    assert all("token" not in (event.reason or "").lower() for event in events)
    assert [event.request_id for event in events] == ["req-allowed", "req-denied"]
    assert len({event.id for event in events}) == 2


def test_status_authority_requires_server_bound_scope_and_replay_jurisdiction():
    service = AuthorizationService()
    replay_officer = AuthContext(
        actor_id="replay_district_officer",
        actor_type="synthetic",
        roles=("district_officer",),
        jurisdiction_ids=("replay_guwahati_silchar",),
        mission_ids=(),
        session_id="replay-session",
        token_issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        status_authority_actor_id="replay_district_officer",
    )
    assert not service.authorize(
        replay_officer,
        "publish_status",
        ResourceScope(status_authority_actor_id="replay_district_officer"),
        request_id="missing-jurisdiction",
    ).allowed
    assert not service.authorize(
        replay_officer,
        "publish_status",
        ResourceScope(
            jurisdiction_id="replay_other_corridor",
            status_authority_actor_id="replay_district_officer",
        ),
        request_id="foreign-jurisdiction",
    ).allowed
    assert not service.authorize(
        replay_officer,
        "publish_status",
        ResourceScope(
            jurisdiction_id="replay_guwahati_silchar",
            status_authority_actor_id="arbitrary_officer",
        ),
        request_id="arbitrary-officer",
    ).allowed
    assert service.authorize(
        replay_officer,
        "publish_status",
        ResourceScope(
            jurisdiction_id="replay_guwahati_silchar",
            status_authority_actor_id="replay_district_officer",
        ),
        request_id="bound-officer",
    ).allowed


def test_persisted_identity_and_assignment_state_is_checked():
    actor_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    session_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    now = datetime.now(timezone.utc)
    factory = build_session_factory(Settings(database_url="sqlite+pysqlite:///:memory:"))
    Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        session.add(Jurisdiction(id="j-1", code="replay", name="Replay"))
        session.add(Actor(id=actor_id, external_subject="subject", actor_type="user"))
        session.add(
            SessionRecord(
                id=session_id,
                actor_id=actor_id,
                token_issued_at=now,
                expires_at=now + timedelta(hours=1),
                active=True,
            )
        )
        session.add(
            RoleAssignment(
                id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
                actor_id=actor_id,
                role="reviewer",
                jurisdiction_id="j-1",
            )
        )
        session.commit()
    actor = AuthContext(
        actor_id=actor_id,
        actor_type="user",
        roles=("reviewer",),
        jurisdiction_ids=("j-1",),
        mission_ids=(),
        session_id=session_id,
        token_issued_at=now,
        expires_at=now + timedelta(hours=1),
    )
    service = AuthorizationService(session_factory=factory)
    scope = ResourceScope(jurisdiction_id="j-1")
    assert service.authorize(actor, "review_evidence", scope, now=now).allowed
    with factory() as session:
        session.get(SessionRecord, session_id).revoked_at = now
        session.commit()
    assert not service.authorize(actor, "review_evidence", scope, now=now).allowed
