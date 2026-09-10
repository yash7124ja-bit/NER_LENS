"""Small append-only audit sink shared by deterministic domain services."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone


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
    def __init__(self) -> None:
        self.events: list[AuditRecord] = []

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
    ) -> AuditRecord:
        record = AuditRecord(
            id=str(uuid.uuid4()),
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
        return record
