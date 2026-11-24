from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.email import send_invitation_email
from app.config.settings import Settings
from app.database.engine import get_session_factory
from app.modules.organization.dataproviders.repository import OrganizationRepository
from app.modules.organization.domain.email_outbox import EmailOutbox

logger = logging.getLogger(__name__)


def _next_attempt(attempts: int) -> datetime:
    # Exponential backoff: 1m, 5m, 15m, 1h, 6h (cap)
    delays = [60, 300, 900, 3600, 21600]
    seconds = delays[min(max(attempts - 1, 0), len(delays) - 1)]
    return datetime.now(UTC) + timedelta(seconds=seconds)


def enqueue_email(
    db: Session,
    *,
    event_type: str,
    recipient_email: str,
    subject: str,
    payload: dict,
    dedupe_key: str | None = None,
) -> EmailOutbox:
    payload = dict(payload)
    if dedupe_key:
        payload.setdefault("dedupe_key", dedupe_key)
        existing = db.scalar(select(EmailOutbox).where(EmailOutbox.dedupe_key == dedupe_key))
        if existing is not None:
            return existing

    row = EmailOutbox(
        event_type=event_type,
        recipient_email=recipient_email,
        subject=subject,
        payload=payload,
        dedupe_key=dedupe_key,
        status="pending",
        attempts=0,
        max_attempts=5,
        next_attempt_at=datetime.now(UTC),
    )
    db.add(row)
    try:
        with db.begin_nested():
            db.flush()
    except Exception:
        if dedupe_key:
            existing = db.scalar(select(EmailOutbox).where(EmailOutbox.dedupe_key == dedupe_key))
            if existing is not None:
                return existing
        raise
    return row


def _claim_outbox_row(db: Session, row_id: str, *, now: datetime) -> EmailOutbox | None:
    stmt = select(EmailOutbox).where(
        EmailOutbox.id == row_id,
        EmailOutbox.status.in_(["pending", "failed"]),
        EmailOutbox.next_attempt_at <= now,
        EmailOutbox.attempts < EmailOutbox.max_attempts,
    )
    bind = db.get_bind()
    if getattr(bind.dialect, "supports_for_update", False):
        stmt = stmt.with_for_update(skip_locked=True)
    row = db.scalar(stmt)
    if row is None:
        return None
    row.status = "processing"
    row.attempts += 1
    row.updated_at = now
    db.commit()
    return row


def process_outbox_batch(settings: Settings, *, limit: int = 20, session_factory=None) -> int:
    session_factory = session_factory or get_session_factory()
    processed = 0
    try:
        with session_factory() as db:
            OrganizationRepository(db).expire_invitation_reservations()
            db.commit()
            now = datetime.now(UTC)
            q = (
                select(EmailOutbox.id)
                .where(
                    EmailOutbox.status.in_(["pending", "failed"]),
                    EmailOutbox.next_attempt_at <= now,
                    EmailOutbox.attempts < EmailOutbox.max_attempts,
                )
                .order_by(EmailOutbox.next_attempt_at, EmailOutbox.created_at)
                .limit(limit)
            )
            bind = db.get_bind()
            if getattr(bind.dialect, "supports_for_update", False):
                try:
                    row_ids = list(db.scalars(q.with_for_update(skip_locked=True)))
                except Exception:
                    row_ids = list(db.scalars(q))
            else:
                row_ids = list(db.scalars(q))
    except Exception:
        logger.debug("email outbox batch skipped (db unavailable or schema missing)", exc_info=True)
        return 0

    for row_id in row_ids:
        try:
            with session_factory() as db:
                now = datetime.now(UTC)
                row = _claim_outbox_row(db, row_id, now=now)
                if row is None:
                    continue
                invitation_row = None
                invitation_id = (row.payload or {}).get("invitation_id")
                if invitation_id:
                    from app.modules.organization.domain.models import Invitation

                    invitation_row = db.get(Invitation, str(invitation_id))
                sent = False
                skipped = False
                error: str | None = None
                try:
                    if row.event_type in {"invitation.created", "invitation.resent"}:
                        if not settings.email_enabled or not settings.smtp_host:
                            skipped = True
                            error = "email_disabled"
                        else:
                            sent = send_invitation_email(
                                settings=settings,
                                to_email=row.recipient_email,
                                invite_url=str(row.payload.get("invite_url", "")),
                                workspace_name=row.payload.get("workspace_name"),
                                organization_name=row.payload.get("organization_name"),
                                inviter_name=row.payload.get("inviter_name"),
                                role=row.payload.get("role"),
                                expires_at=row.payload.get("expires_at"),
                                corporate_email=(
                                    invitation_row.corporate_email
                                    if invitation_row is not None
                                    else None
                                ),
                            )
                    else:
                        error = f"unsupported_event_type:{row.event_type}"
                except Exception as exc:  # pragma: no cover - defensive
                    error = str(exc)[:500]
                    sent = False

                row.last_error = error if (not sent) else None
                if sent:
                    row.status = "sent"
                    row.sent_at = datetime.now(UTC)
                    row.next_attempt_at = datetime.now(UTC)
                elif skipped:
                    row.status = "skipped"
                    row.next_attempt_at = datetime.now(UTC)
                else:
                    row.status = "failed"
                    row.next_attempt_at = _next_attempt(row.attempts)
                    if row.last_error is None:
                        row.last_error = "send_failed"
                row.updated_at = datetime.now(UTC)

                if invitation_row is not None:
                    try:
                        from app.modules.workspace_management.domain.models import AuditEvent

                        inv = invitation_row
                        if inv is not None:
                            if sent:
                                inv.send_status = "sent"
                                inv.last_sent_at = row.sent_at
                                action = "invitation.email_sent"
                                result = "success"
                            elif skipped:
                                inv.send_status = "not_configured"
                                action = "invitation.email_skipped"
                                result = "skipped"
                            else:
                                inv.send_status = "failed"
                                action = "invitation.email_failed"
                                result = "failed"
                            db.add(
                                AuditEvent(
                                    organization_id=inv.organization_id,
                                    workspace_id=inv.workspace_id,
                                    scope="organization",
                                    actor_user_id=None,
                                    actor_type="system",
                                    action=action,
                                    entity_type="invitation",
                                    entity_id=inv.id,
                                    result=result,
                                    after={
                                        "send_status": inv.send_status,
                                        "attempts": row.attempts,
                                        "last_error": row.last_error,
                                    },
                                    metadata_={"email": inv.email, "role": inv.role},
                                )
                            )
                    except Exception:
                        logger.exception(
                            "failed to update invitation send status for outbox row_id=%s", row_id
                        )
                db.commit()
                processed += 1
        except Exception:
            logger.exception("email outbox row processing failed row_id=%s", row_id)
    return processed


async def outbox_worker_loop(settings: Settings, *, interval_seconds: float = 15.0) -> None:
    while True:
        try:
            await asyncio.to_thread(process_outbox_batch, settings)
        except Exception:
            logger.exception("email outbox worker loop failed")
        await asyncio.sleep(interval_seconds)
