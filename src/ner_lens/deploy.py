"""Render entrypoint: migrate replay storage before starting the API."""

import os
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
