"""Database engine/session boundary for production and replay repositories."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ner_lens.config import Settings


def build_engine(settings: Settings) -> Engine:
    kwargs: dict[str, object] = {"future": True, "pool_pre_ping": True}
    if settings.database_url.startswith("sqlite") and ":memory:" in settings.database_url:
        kwargs.update({"connect_args": {"check_same_thread": False}, "poolclass": StaticPool})
    return create_engine(settings.database_url, **kwargs)


def build_session_factory(settings: Settings) -> sessionmaker[Session]:
    return sessionmaker(bind=build_engine(settings), autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping_database(engine: Engine) -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
