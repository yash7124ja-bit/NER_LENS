"""Corridor-scoped administrator actions and persisted SIH user-story register."""

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, DateTime, String, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from ner_lens.corridor.models import Base, CorridorVersion
from ner_lens.identity.accounts import provision_account
from ner_lens.identity.models import (
    Actor,
    AuditEvent,
    LocalAccount,
    RoleAssignment,
    StatusAuthority,
)
from ner_lens.identity.service import AuthorizationService, ResourceScope

Role = Literal[
    "regional_viewer",
    "field_reporter",
    "reviewer",
    "dispatcher",
    "district_officer",
    "system_admin",
]


class Story(Base):
    __tablename__ = "user_story"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    role: Role
    title: str = Field(min_length=1, max_length=200)
    story: str = Field(min_length=1, max_length=4000)
    acceptance: list[str] = Field(min_length=1, max_length=30)
    status: Literal["planned", "implemented", "verified_replay", "external_dependency"]
    evidence: str = Field(max_length=4000)


class RolesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    corridor_id: str
    roles: list[Role] = Field(min_length=1, max_length=6)
    status_authority: bool = False


class AccountInput(RolesInput):
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=12, max_length=1024, repr=False)


def ingest_stories(factory, records, *, overwrite=False):
    validated = [StoryInput.model_validate(record) for record in records]
    with factory.begin() as session:
        for body in validated:
            row = session.get(Story, body.id)
            if row is None:
                session.add(
                    Story(
                        id=body.id, payload=body.model_dump(), updated_at=datetime.now(timezone.utc)
                    )
                )
            elif overwrite:
                row.payload = body.model_dump()
                row.updated_at = datetime.now(timezone.utc)
    return len(validated)


def build_router(factory, current_actor, settings):
    router = APIRouter(tags=["administration"])

    @router.get("/v1/admin/corridors")
    def admin_corridors(actor=Depends(current_actor)):
        with factory() as session:
            rows = session.scalars(
                select(CorridorVersion)
                .where(
                    CorridorVersion.status == "active",
                    CorridorVersion.jurisdiction_id.in_(actor.jurisdiction_ids),
                )
                .order_by(CorridorVersion.name)
            ).all()
            auth = AuthorizationService(session_factory=factory)
            permitted = [
                row for row in rows
                if auth.authorize(
                    actor, "manage_users", ResourceScope(jurisdiction_id=row.jurisdiction_id)
                ).allowed
            ]
            return {
                "corridors": [
                    {
                        "corridor_id": row.id,
                        "corridor_version_id": row.id,
                        "name": row.name or row.corridor_key,
                        "graph_version": row.graph_version,
                        "data_mode": "administration",
                    }
                    for row in permitted
                ],
                "data_mode": "administration",
                "provenance": {},
                "limitations": [],
            }

    def scope(session, actor, corridor_id, action="manage_users"):
        corridor = session.get(CorridorVersion, corridor_id)
        if not corridor:
            raise HTTPException(404)
        result = AuthorizationService(session_factory=factory).authorize(
            actor, action, ResourceScope(jurisdiction_id=corridor.jurisdiction_id)
        )
        if not result.allowed:
            raise HTTPException(403)
        return corridor.jurisdiction_id

    def audit(session, actor, request, target, jurisdiction, roles, authority):
        session.add(
            AuditEvent(
                id=str(uuid4()),
                actor_id=actor.actor_id,
                action="admin.roles_assigned",
                target_type="actor",
                target_id=target,
                jurisdiction_id=jurisdiction,
                request_id=request.state.request_id,
                outcome="allowed",
                reason="roles=" + ",".join(sorted(roles)) + "; status_authority=" + str(authority),
            )
        )

    @router.get("/v1/admin/users")
    def users(corridor_id: str, actor=Depends(current_actor)):
        with factory() as session:
            jurisdiction = scope(session, actor, corridor_id)
            ids = (
                session.scalars(
                    select(RoleAssignment.actor_id).where(
                        RoleAssignment.jurisdiction_id == jurisdiction
                    )
                )
                .unique()
                .all()
            )
            result = []
            for aid in ids:
                account = session.get(LocalAccount, aid)
                if not account:
                    continue
                roles = session.scalars(
                    select(RoleAssignment.role).where(
                        RoleAssignment.actor_id == aid,
                        RoleAssignment.jurisdiction_id == jurisdiction,
                    )
                ).all()
                grant = session.get(StatusAuthority, (aid, jurisdiction))
                result.append(
                    {
                        "actor_id": aid,
                        "email": account.email,
                        "display_name": account.display_name,
                        "roles": sorted(roles),
                        "status_authority": bool(grant and grant.active),
                        "active": session.get(Actor, aid).active,
                    }
                )
            return {"users": result}

    @router.post("/v1/admin/users", status_code=201)
    def create(body: AccountInput, request: Request, actor=Depends(current_actor)):
        with factory() as session:
            jurisdiction = scope(session, actor, body.corridor_id)
        if body.status_authority and "district_officer" not in body.roles:
            raise HTTPException(422)
        try:
            target = provision_account(
                factory,
                body.email,
                body.password,
                body.display_name,
                tuple(body.roles),
                (jurisdiction,),
            )
        except ValueError:
            raise HTTPException(409, "account_settings_conflict") from None
        with factory.begin() as session:
            if body.status_authority:
                grant = session.get(StatusAuthority, (target.id, jurisdiction))
                if grant:
                    grant.active = True
                else:
                    session.add(
                        StatusAuthority(
                            actor_id=target.id, jurisdiction_id=jurisdiction, active=True
                        )
                    )
            audit(
                session, actor, request, target.id, jurisdiction, body.roles, body.status_authority
            )
        return {"actor_id": target.id, "status": "created"}

    @router.post("/v1/admin/users/{actor_id}/roles")
    def assign(actor_id: str, body: RolesInput, request: Request, actor=Depends(current_actor)):
        with factory.begin() as session:
            jurisdiction = scope(session, actor, body.corridor_id)
            target = session.get(Actor, actor_id)
            existing = session.scalars(
                select(RoleAssignment).where(
                    RoleAssignment.actor_id == actor_id,
                    RoleAssignment.jurisdiction_id == jurisdiction,
                )
            ).all()
            if not target or not existing:
                raise HTTPException(404)
            if actor_id == actor.actor_id and "system_admin" not in body.roles:
                raise HTTPException(409, "cannot_remove_own_admin_access")
            if body.status_authority and "district_officer" not in body.roles:
                raise HTTPException(422)
            session.execute(
                delete(RoleAssignment).where(
                    RoleAssignment.actor_id == actor_id,
                    RoleAssignment.jurisdiction_id == jurisdiction,
                )
            )
            for role in set(body.roles):
                session.add(
                    RoleAssignment(
                        id=str(uuid4()), actor_id=actor_id, role=role, jurisdiction_id=jurisdiction
                    )
                )
            grant = session.get(StatusAuthority, (actor_id, jurisdiction))
            if grant:
                grant.active = body.status_authority
            elif body.status_authority:
                session.add(
                    StatusAuthority(actor_id=actor_id, jurisdiction_id=jurisdiction, active=True)
                )
            audit(
                session, actor, request, actor_id, jurisdiction, body.roles, body.status_authority
            )
        return {
            "actor_id": actor_id,
            "status": "updated",
            "note": (
                "New permissions apply on the next request. Sign in again to refresh the interface."
            ),
        }

    @router.get("/v1/user-stories")
    def stories(corridor_id: str, actor=Depends(current_actor)):
        with factory() as session:
            scope(session, actor, corridor_id, "read_corridor_state")
            return {
                "stories": [
                    row.payload for row in session.scalars(select(Story).order_by(Story.id))
                ],
                "storage": "application_database",
                "vector_index": "configured"
                if settings.providers.get("WEAVIATE_API")
                else "not_configured",
            }

    @router.get("/v1/user-stories/search")
    def search(
        corridor_id: str, q: str = Query(min_length=1, max_length=300), actor=Depends(current_actor)
    ):
        import httpx

        from ner_lens.story_search import search_stories

        with factory() as session:
            scope(session, actor, corridor_id, "read_corridor_state")
        try:
            ids = search_stories(settings, q)
        except (ValueError, httpx.HTTPError):
            raise HTTPException(503, "story_search_unavailable") from None
        with factory() as session:
            records = {
                row.id: row.payload
                for row in session.scalars(select(Story).where(Story.id.in_(ids)))
            }
            return {
                "stories": [records[sid] for sid in ids if sid in records],
                "search_mode": "weaviate_bm25",
            }

    @router.post("/v1/admin/user-stories/reindex")
    def reindex(corridor_id: str, actor=Depends(current_actor)):
        import httpx

        from ner_lens.story_search import index_stories

        with factory() as session:
            scope(session, actor, corridor_id)
            records = [row.payload for row in session.scalars(select(Story))]
        try:
            return index_stories(settings, records)
        except (ValueError, httpx.HTTPError):
            raise HTTPException(503, "story_index_unavailable") from None

    @router.post("/v1/admin/user-stories")
    def import_stories(corridor_id: str, body: list[StoryInput], actor=Depends(current_actor)):
        with factory() as session:
            scope(session, actor, corridor_id)
        if len(body) > 100:
            raise HTTPException(413)
        return {
            "ingested": ingest_stories(factory, [row.model_dump() for row in body], overwrite=True)
        }

    return router
