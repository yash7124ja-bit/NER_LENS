"""Render entrypoint: migrate replay storage before starting the API."""

import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import uvicorn
from sqlalchemy import select

from ner_lens.config import Settings
from ner_lens.contracts import StateQuery
from ner_lens.corridor.models import CorridorVersion
from ner_lens.corridor.state import list_corridors, read_state
from ner_lens.db import build_session_factory
from ner_lens.identity.accounts import logout, provision_account
from ner_lens.identity.replay import authenticate
from ner_lens.replay import initialize


def main() -> None:
    settings = Settings.from_env()
    token = initialize(settings)
    factory = build_session_factory(settings)
    from ner_lens.administration import ingest_stories
    from ner_lens.identity.models import AuditEvent, LocalAccount, RoleAssignment

    source = Path(__file__).resolve().parents[2] / "data" / "user_stories.json"
    if source.exists():
        ingest_stories(factory, json.loads(source.read_text(encoding="utf-8")))
    admin_email = os.getenv("NER_LENS_SUPERADMIN_EMAIL", "").strip().casefold()
    if admin_email:
        with factory.begin() as session:
            account = session.scalar(select(LocalAccount).where(LocalAccount.email == admin_email))
            if account is None:
                raise ValueError("Super Admin bootstrap requires an existing account")
            scopes = (
                session.scalars(
                    select(RoleAssignment.jurisdiction_id).where(
                        RoleAssignment.actor_id == account.actor_id
                    )
                )
                .unique()
                .all()
            )
            for scope in scopes:
                existing = session.scalar(
                    select(RoleAssignment).where(
                        RoleAssignment.actor_id == account.actor_id,
                        RoleAssignment.role == "system_admin",
                        RoleAssignment.jurisdiction_id == scope,
                    )
                )
                if existing is None:
                    session.add(
                        AuditEvent(
                            id=str(uuid4()),
                            actor_id=account.actor_id,
                            action="admin.bootstrap",
                            target_type="actor",
                            target_id=account.actor_id,
                            jurisdiction_id=scope,
                            request_id=str(uuid4()),
                            outcome="allowed",
                            reason="One-time administrator bootstrap from deployment environment",
                        )
                    )
                    session.add(
                        RoleAssignment(
                            id=str(uuid4()),
                            actor_id=account.actor_id,
                            role="system_admin",
                            jurisdiction_id=scope,
                        )
                    )
    try:
        actor = authenticate(factory, token)
        request_id = str(uuid4())
        catalog = list_corridors(factory, actor, request_id)
        for corridor in catalog.corridors:
            read_state(factory, UUID(str(corridor.corridor_id)), StateQuery(), actor, request_id)
        logout(factory, token, request_id)
        print("Migrations, scoped corridor reads and geometry round-trip verified.", flush=True)
    finally:
        factory.kw["bind"].dispose()
    if os.getenv("NER_LENS_BOOTSTRAP_EMAIL"):
        factory = build_session_factory(settings)
        try:
            with factory() as session:
                scopes = tuple(
                    session.scalars(
                        select(CorridorVersion.jurisdiction_id).where(
                            CorridorVersion.status == "active",
                            CorridorVersion.jurisdiction_id.is_not(None),
                        )
                    ).unique()
                )
            provision_account(
                factory,
                os.environ["NER_LENS_BOOTSTRAP_EMAIL"],
                os.environ["NER_LENS_BOOTSTRAP_PASSWORD"],
                os.environ["NER_LENS_BOOTSTRAP_DISPLAY_NAME"],
                tuple(os.environ["NER_LENS_BOOTSTRAP_ROLES"].split(",")),
                scopes,
            )
        finally:
            factory.kw["bind"].dispose()
    uvicorn.run(
        "ner_lens.app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        access_log=False,
    )


if __name__ == "__main__":
    main()
