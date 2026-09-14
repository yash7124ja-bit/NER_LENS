"""Bounded image quarantine: bytes stay private until a trusted scanner clears them."""

from __future__ import annotations

import hashlib
import io
import re
import warnings
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import JSON, DateTime, ForeignKey, LargeBinary, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column
from starlette.requests import ClientDisconnect

from ner_lens.common.idempotency import canonical_request_hash, validate_idempotency_key
from ner_lens.corridor.models import Base
from ner_lens.identity.models import AuditEvent, IdempotencyRecord
from ner_lens.identity.service import AuthContext, AuthorizationService, ResourceScope
from ner_lens.operations import FieldReport, MutationResponse

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 20_000_000
MAX_SLOTS = 4
FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
# Only deployment code may supply this callback; there is no HTTP scanner override.
Scanner = Callable[[bytes], str]


class MediaObject(Base):
    __tablename__ = "media_object"
    __table_args__ = (UniqueConstraint("field_report_id", "slot", name="uq_report_media_slot"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    field_report_id: Mapped[str] = mapped_column(ForeignKey("field_report.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("actor.id"))
    slot: Mapped[int] = mapped_column()
    sha256: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str] = mapped_column(String(32))
    content_length: Mapped[int] = mapped_column()
    upload_state: Mapped[str] = mapped_column(String(16))
    scan_state: Mapped[str] = mapped_column(String(16))
    scan_reason: Mapped[str] = mapped_column(String(128))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[bytes | None] = mapped_column(LargeBinary)
    derivative: Mapped[bytes | None] = mapped_column(LargeBinary)
    upload_response: Mapped[dict | None] = mapped_column(JSON)


def now_utc():
    return datetime.now(timezone.utc)


def metadata(row):
    return {
        "media_object_id": row.id,
        "field_report_id": row.field_report_id,
        "slot": row.slot,
        "sha256": row.sha256,
        "scan_state": row.scan_state,
        "scan_reason": row.scan_reason,
        "upload_state": row.upload_state,
        "media_state": "complete"
        if row.upload_state == "received" and row.scan_state == "clean"
        else "incomplete",
    }


def report_media_state(session, report_id):
    rows = session.scalars(
        select(MediaObject).where(MediaObject.field_report_id == report_id)
    ).all()
    if not rows:
        return "none"
    return (
        "complete"
        if all(metadata(row)["media_state"] == "complete" for row in rows)
        else "incomplete"
    )


def image_derivative(raw: bytes, content_type: str) -> bytes:
    """Decode and re-encode pixels; decoding is not an antivirus verdict."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as candidate:
                if candidate.format != FORMATS[content_type]:
                    raise ValueError("media_type_mismatch")
                if (
                    candidate.width * candidate.height > MAX_PIXELS
                    or getattr(candidate, "n_frames", 1) != 1
                ):
                    raise ValueError("image_dimensions_or_animation_not_allowed")
                candidate.verify()
            with Image.open(io.BytesIO(raw)) as original:
                decoded = ImageOps.exif_transpose(original).convert("RGB")
                decoded.thumbnail((2048, 2048))
                # New image copies pixels only: no EXIF/GPS/ICC/comment metadata survives.
                clean = Image.new("RGB", decoded.size)
                clean.paste(decoded)
                output = io.BytesIO()
                clean.save(output, format="JPEG", quality=85)
                return output.getvalue()
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("image_decode_failed") from exc


def scan_result(scanner: Scanner | None, raw: bytes):
    if scanner is None:
        return "pending", "scanner_not_configured"
    try:
        result = scanner(raw)
    except Exception:
        return "error", "scanner_failed"
    if result not in {"clean", "rejected"}:
        return "error", "invalid_scanner_verdict"
    return result, "trusted_scanner_verdict"


def audit(session, row, action, *, actor_id=None, reason=None):
    session.add(
        AuditEvent(
            id=str(uuid4()),
            actor_id=actor_id,
            jurisdiction_id=session.get(FieldReport, row.field_report_id).jurisdiction_id,
            action=action,
            target_type="media_object",
            target_id=row.id,
            request_id=str(uuid4()),
            before_hash=None,
            after_hash=canonical_request_hash(metadata(row)),
            reason=reason or row.scan_reason,
            outcome="allowed",
        )
    )


def scan_pending(factory, scanner: Scanner, *, limit=20):
    """Trusted worker hook. Never expose scanner selection or verdicts as request inputs."""
    if scanner is None:
        raise ValueError("trusted_scanner_required")
    count = 0
    with factory() as session:
        rows = session.scalars(
            select(MediaObject)
            .where(
                MediaObject.upload_state == "received",
                MediaObject.scan_state.in_(["pending", "error"]),
            )
            .limit(min(100, max(1, limit)))
        ).all()
        for row in rows:
            row.scan_state, row.scan_reason = scan_result(scanner, row.raw)
            row.scanned_at = now_utc()
            audit(session, row, "media.scanned")
            count += 1
        session.commit()
    return count


def build_router(factory, current_actor, scanner: Scanner | None = None):
    router = APIRouter(tags=["media"])

    def audit_authorization(event):
        with factory.begin() as session:
            session.add(event)

    authorization = AuthorizationService(session_factory=factory, audit_sink=audit_authorization)

    def access(session, report_id, actor, *, upload=False):
        report = session.get(FieldReport, report_id)
        if not report:
            raise HTTPException(404, "field_report_not_found")
        review = not upload and "reviewer" in actor.roles
        decision = authorization.authorize(
            actor,
            "upload_own_media" if upload else "review_evidence" if review else "view_own_report",
            ResourceScope(
                jurisdiction_id=report.jurisdiction_id,
                owner_actor_id=None if review else report.actor_id,
            ),
        )
        if not decision.allowed:
            raise HTTPException(403, decision.code)
        return report

    def set_incomplete(media_id, reason):
        with factory.begin() as session:
            row = session.get(MediaObject, media_id)
            if row and row.upload_state != "received":
                row.upload_state, row.scan_reason = "incomplete", reason
                audit(session, row, "media.upload_incomplete")

    @router.put("/v1/field-reports/{report_id}/media/{slot}", status_code=201)
    async def upload(
        report_id: str,
        slot: int,
        request: Request,
        actor: AuthContext = Depends(current_actor),
        idempotency_key: str = Header(),
        x_media_sha256: str = Header(),
        content_type: str = Header(),
        content_length: int = Header(),
    ):
        if not 0 <= slot < MAX_SLOTS:
            raise HTTPException(422, "media_slot_out_of_range")
        if content_type not in FORMATS:
            raise HTTPException(415, "unsupported_media_type")
        if not 0 < content_length <= MAX_UPLOAD_BYTES:
            raise HTTPException(413, "media_too_large_or_empty")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", x_media_sha256):
            raise HTTPException(422, "invalid_media_digest")
        try:
            validate_idempotency_key(idempotency_key)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        digest = x_media_sha256.lower()
        path = f"/v1/field-reports/{report_id}/media/{slot}"
        fingerprint = canonical_request_hash(
            {"sha256": digest, "content_type": content_type, "content_length": content_length}
        )
        with factory() as session:
            access(session, report_id, actor, upload=True)
            existing_receipt = session.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.actor_id == actor.actor_id,
                    IdempotencyRecord.method == "PUT",
                    IdempotencyRecord.path == path,
                    IdempotencyRecord.idempotency_key == idempotency_key,
                )
            )
            if existing_receipt and existing_receipt.request_hash != fingerprint:
                raise HTTPException(409, "idempotency_conflict")
            row = session.scalar(
                select(MediaObject).where(
                    MediaObject.field_report_id == report_id, MediaObject.slot == slot
                )
            )
            if row and (
                row.sha256 != digest
                or row.content_type != content_type
                or row.content_length != content_length
            ):
                raise HTTPException(409, "media_slot_conflict")
            if not row:
                row = MediaObject(
                    id=str(uuid4()),
                    field_report_id=report_id,
                    actor_id=actor.actor_id,
                    slot=slot,
                    sha256=digest,
                    content_type=content_type,
                    content_length=content_length,
                    upload_state="uploading",
                    scan_state="pending",
                    scan_reason="upload_in_progress",
                    received_at=now_utc(),
                )
                session.add(row)
                try:
                    session.commit()
                except IntegrityError as exc:
                    session.rollback()
                    raise HTTPException(409, "concurrent_upload_retry_same_key") from exc
            media_id = row.id
        chunks, size = [], 0
        try:
            async for chunk in request.stream():
                size += len(chunk)
                if size > content_length or size > MAX_UPLOAD_BYTES:
                    set_incomplete(media_id, "length_limit_exceeded")
                    raise HTTPException(413, "media_length_limit_exceeded")
                chunks.append(chunk)
        except ClientDisconnect as exc:
            set_incomplete(media_id, "upload_disconnected")
            raise HTTPException(400, "upload_disconnected") from exc
        raw = b"".join(chunks)
        if size != content_length:
            set_incomplete(media_id, "content_length_mismatch")
            raise HTTPException(422, "content_length_mismatch")
        if hashlib.sha256(raw).hexdigest() != digest:
            set_incomplete(media_id, "digest_mismatch")
            raise HTTPException(422, "media_digest_mismatch")
        with factory() as session:
            access(session, report_id, actor, upload=True)
            row = session.get(MediaObject, media_id)
            if row.upload_response:
                return row.upload_response
        try:
            derivative = await run_in_threadpool(image_derivative, raw, content_type)
        except ValueError as exc:
            set_incomplete(media_id, str(exc))
            raise HTTPException(422, str(exc)) from exc
        scan_state, scan_reason = await run_in_threadpool(scan_result, scanner, raw)
        with factory() as session:
            access(session, report_id, actor, upload=True)
            row = session.get(MediaObject, media_id)
            if row.upload_response:
                return row.upload_response
            row.raw, row.derivative = raw, derivative
            row.upload_state, row.scan_state, row.scan_reason = "received", scan_state, scan_reason
            row.scanned_at = now_utc() if scanner is not None else None
            response = {**metadata(row), "request_id": str(uuid4())}
            row.upload_response = response
            receipt_id = str(uuid4())
            session.add(
                IdempotencyRecord(
                    id=receipt_id,
                    actor_id=actor.actor_id,
                    method="PUT",
                    path=path,
                    idempotency_key=idempotency_key,
                    request_hash=fingerprint,
                    status_code=201,
                    response_body_hash=canonical_request_hash(response),
                    expires_at=now_utc() + timedelta(days=365),
                )
            )
            audit(session, row, "media.upload_received", actor_id=actor.actor_id)
            try:
                session.flush()
                session.add(MutationResponse(id=receipt_id, body=response))
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                row = session.get(MediaObject, media_id)
                if row.upload_response:
                    return row.upload_response
                raise HTTPException(409, "concurrent_upload_retry_same_key") from exc
            return response

    @router.get("/v1/field-reports/{report_id}/media")
    def list_media(report_id: str, actor: AuthContext = Depends(current_actor)):
        with factory() as session:
            access(session, report_id, actor)
            rows = session.scalars(
                select(MediaObject)
                .where(MediaObject.field_report_id == report_id)
                .order_by(MediaObject.slot)
            ).all()
            return {
                "media": [metadata(row) for row in rows],
                "media_state": report_media_state(session, report_id),
            }

    @router.get("/v1/field-reports/{report_id}/media/{slot}")
    def derivative(report_id: str, slot: int, actor: AuthContext = Depends(current_actor)):
        with factory() as session:
            access(session, report_id, actor)
            row = session.scalar(
                select(MediaObject).where(
                    MediaObject.field_report_id == report_id, MediaObject.slot == slot
                )
            )
            if not row:
                raise HTTPException(404, "media_not_found")
            if row.upload_state != "received" or row.scan_state != "clean" or not row.derivative:
                raise HTTPException(409, "media_not_cleared_by_scanner")
            audit(session, row, "media.derivative_read", actor_id=actor.actor_id)
            session.commit()
            return Response(
                row.derivative,
                media_type="image/jpeg",
                headers={
                    "Cache-Control": "private, no-store",
                    "X-Content-Type-Options": "nosniff",
                    "Content-Disposition": f'inline; filename="{row.id}.jpg"',
                },
            )

    return router
