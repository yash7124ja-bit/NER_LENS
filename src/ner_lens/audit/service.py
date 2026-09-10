"""Small append-only audit sink shared by deterministic domain services."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from ner_lens.identity.models import AuditEvent


@dataclass(frozen=True, slots=True)
class AuditRecord:
    id: str
    actor_id: str
    action: str
    target_type: str
    target_id: str
    request_id: str
    occurred_at: datetime
    before_hash: str | None
    after_hash: str | None
    outcome: str


class AuditLog:
    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self.events: list[AuditRecord] = []
        self.session_factory = session_factory

    def append(
        self,
        *,
        actor_id: str,
        action: str,
        target_type: str,
        target_id: str,
        request_id: str,
        before_hash: str | None,
        after_hash: str | None,
        outcome: str = "accepted",
        occurred_at: datetime | None = None,
        session: Session | None = None,
        event_id: str | None = None,
    ) -> AuditRecord:
        record = AuditRecord(
            id=event_id or str(uuid.uuid4()),
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            request_id=request_id,
            occurred_at=occurred_at or datetime.now(timezone.utc),
            before_hash=before_hash,
            after_hash=after_hash,
            outcome=outcome,
        )
        self.events.append(record)
        if session is not None:
            session.add(
                AuditEvent(
                    id=record.id,
                    actor_id=record.actor_id,
                    action=record.action,
                    target_type=record.target_type,
                    target_id=record.target_id,
                    request_id=record.request_id,
                    occurred_at=record.occurred_at,
                    before_hash=record.before_hash,
                    after_hash=record.after_hash,
                    reason=None,
                    outcome=record.outcome,
                )
            )
        return record
