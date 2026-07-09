"""Celery task — dispatch meeting reminders to active members.

Strategy:
    1. For each upcoming meeting in the next 60 days, look at its association
       reminder offsets (e.g. [7, 1]) and the meeting's existing `MeetingReminder`
       rows.
    2. If today == scheduled_on − offset and no row exists for that offset yet,
       send to every active member of the association and record a
       MeetingReminder for idempotency.

Per-association config lives at `Association.config.notifications.meeting_reminders`:
    enabled:      bool          (default True)
    days_before:  list[int]     (default [7, 1])
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal, engine
from app.models.association import Association
from app.models.meeting import Meeting, MeetingReminder, MeetingStatus
from app.models.role import Membership, MembershipStatus
from app.services import planning
from app.services.mailer import MailError, send_meeting_reminder_email
from app.worker import celery_app

logger = logging.getLogger(__name__)


async def _send_reminders_for_meeting(
    db: AsyncSession, meeting: Meeting, assoc: Association, days_before: int
) -> tuple[int, int]:
    """Send the reminder for one (meeting, offset) pair. Returns (sent, failed)."""
    res = await db.execute(
        select(Membership)
        .options(selectinload(Membership.user))
        .where(
            Membership.association_id == assoc.id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    )
    memberships = list(res.scalars().all())
    lang = (assoc.config or {}).get("language") or "fr"
    pretty_date = meeting.scheduled_on.strftime("%d/%m/%Y")

    sent = 0
    failed = 0
    for m in memberships:
        u = m.user
        if not u or not u.email:
            continue
        try:
            await send_meeting_reminder_email(
                to=u.email,
                member_name=u.full_name,
                association_name=assoc.name,
                meeting_title=meeting.title,
                meeting_date=pretty_date,
                location=meeting.location,
                days_before=days_before,
                lang=lang,
            )
            sent += 1
        except MailError as exc:
            failed += 1
            logger.warning("Reminder failed for %s: %s", u.email, exc)

    db.add(
        MeetingReminder(
            meeting_id=meeting.id,
            days_before=days_before,
            sent_at=datetime.now(timezone.utc),
            recipients_count=sent,
            failed_count=failed,
        )
    )
    return sent, failed


async def _dispatch() -> dict:
    """Scan upcoming meetings and fire any reminder whose day matches today."""
    today = date.today()
    horizon = today + timedelta(days=60)
    stats = {"meetings_checked": 0, "reminders_sent": 0, "emails_sent": 0, "emails_failed": 0}

    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Meeting)
            .options(selectinload(Meeting.attendances))
            .where(
                Meeting.status == MeetingStatus.PLANNED,
                Meeting.scheduled_on >= today,
                Meeting.scheduled_on <= horizon,
            )
        )
        meetings = list(res.scalars().all())
        if not meetings:
            return stats

        assoc_ids = {m.association_id for m in meetings}
        assoc_res = await db.execute(
            select(Association).where(Association.id.in_(assoc_ids))
        )
        assocs = {a.id: a for a in assoc_res.scalars().all()}

        existing_res = await db.execute(
            select(MeetingReminder.meeting_id, MeetingReminder.days_before).where(
                MeetingReminder.meeting_id.in_([m.id for m in meetings])
            )
        )
        already: set[tuple] = {(row[0], row[1]) for row in existing_res.all()}

        for meeting in meetings:
            stats["meetings_checked"] += 1
            assoc = assocs.get(meeting.association_id)
            if not assoc:
                continue
            offsets = planning.reminder_offsets(assoc)
            for offset in offsets:
                target_day = meeting.scheduled_on - timedelta(days=offset)
                if target_day != today:
                    continue
                if (meeting.id, offset) in already:
                    continue
                sent, failed = await _send_reminders_for_meeting(db, meeting, assoc, offset)
                stats["reminders_sent"] += 1
                stats["emails_sent"] += sent
                stats["emails_failed"] += failed

        await db.commit()

    return stats


async def _run_and_dispose() -> dict:
    """Exécute le dispatch puis LIBÈRE le pool du moteur. Indispensable sous
    Celery : chaque tâche tourne dans un NOUVEAU event loop (asyncio.run), or le
    pool de connexions asyncpg reste attaché au loop précédent → « Future
    attached to a different loop » au 2e appel. Disposer le moteur en fin de
    tâche garantit des connexions fraîches, liées au loop courant, à chaque run.
    """
    try:
        return await _dispatch()
    finally:
        await engine.dispose()


@celery_app.task(name="app.tasks.reminders.dispatch_meeting_reminders", ignore_result=False)
def dispatch_meeting_reminders() -> dict:
    """Celery entry — wraps the async dispatcher in a fresh event loop."""
    try:
        result = asyncio.run(_run_and_dispose())
        logger.info("Reminder dispatch finished: %s", result)
        return result
    except Exception:
        logger.exception("Reminder dispatch crashed")
        raise
