"""Meetings CRUD + lifecycle (open/close) + attendances + entries."""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.models.association import Association
from app.models.meeting import (
    Activity,
    EntryStatus,
    Meeting,
    MeetingActivityEntry,
    MeetingAttendance,
    MeetingStatus,
)
from app.models.user import User
from app.schemas.meeting import (
    AttendanceOut,
    AttendanceUpsert,
    EntryCreate,
    EntryOut,
    EntryUpdate,
    MeetingCreate,
    MeetingDetail,
    MeetingOut,
    MeetingUpdate,
)

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────

async def _get_assoc_or_404(db: AsyncSession, association_id: UUID) -> Association:
    result = await db.execute(select(Association).where(Association.id == association_id))
    assoc = result.scalar_one_or_none()
    if not assoc:
        raise HTTPException(status_code=404, detail="Association not found")
    return assoc


def _check_access(user: User, assoc: Association) -> None:
    if user.is_super_admin:
        return
    if user.groupement_id != assoc.groupement_id:
        raise HTTPException(status_code=403, detail="Forbidden")


async def _get_meeting_or_404(db: AsyncSession, meeting_id: UUID) -> Meeting:
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return m


async def _load_meeting_detail(db: AsyncSession, meeting_id: UUID) -> Meeting:
    result = await db.execute(
        select(Meeting)
        .options(
            selectinload(Meeting.attendances),
            selectinload(Meeting.entries),
        )
        .where(Meeting.id == meeting_id)
    )
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return m


def _meeting_to_out(m: Meeting) -> MeetingOut:
    return MeetingOut(
        id=m.id,
        association_id=m.association_id,
        title=m.title,
        description=m.description,
        scheduled_on=m.scheduled_on,
        started_at=m.started_at,
        closed_at=m.closed_at,
        location=m.location,
        status=m.status.value if hasattr(m.status, "value") else m.status,
        facilitator_id=m.facilitator_id,
        created_by_id=m.created_by_id,
        agenda=m.agenda,
        report_url=m.report_url,
        total_in=m.total_in,
        total_out=m.total_out,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _attendance_to_out(a: MeetingAttendance) -> AttendanceOut:
    return AttendanceOut(
        id=a.id,
        meeting_id=a.meeting_id,
        membership_id=a.membership_id,
        status=a.status.value if hasattr(a.status, "value") else a.status,
        notes=a.notes,
        excuse_reason=a.excuse_reason,
    )


def _entry_to_out(e: MeetingActivityEntry) -> EntryOut:
    return EntryOut(
        id=e.id,
        meeting_id=e.meeting_id,
        membership_id=e.membership_id,
        activity_id=e.activity_id,
        amount=e.amount,
        data=e.data,
        status=e.status.value if hasattr(e.status, "value") else e.status,
        movement_id=e.movement_id,
        recorded_by_id=e.recorded_by_id,
        recorded_at=e.recorded_at,
        corrects_entry_id=e.corrects_entry_id,
        correction_reason=e.correction_reason,
        notes=e.notes,
        created_at=e.created_at,
        updated_at=e.updated_at,
    )


# ── Meetings CRUD ──────────────────────────────────────────────────────────

@router.get("", response_model=List[MeetingOut])
async def list_meetings(
    association_id: UUID = Query(...),
    meeting_status: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assoc = await _get_assoc_or_404(db, association_id)
    _check_access(current_user, assoc)

    stmt = select(Meeting).where(Meeting.association_id == association_id)
    if meeting_status:
        stmt = stmt.where(Meeting.status == meeting_status)
    stmt = stmt.order_by(Meeting.scheduled_on.desc())
    result = await db.execute(stmt)
    return [_meeting_to_out(m) for m in result.scalars().all()]


@router.get("/{meeting_id}", response_model=MeetingDetail)
async def get_meeting(
    meeting_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = await _load_meeting_detail(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)

    return MeetingDetail(
        **_meeting_to_out(m).model_dump(),
        attendances=[_attendance_to_out(a) for a in m.attendances],
        entries=[_entry_to_out(e) for e in m.entries],
    )


@router.post("", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    payload: MeetingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assoc = await _get_assoc_or_404(db, payload.association_id)
    _check_access(current_user, assoc)

    meeting = Meeting(
        association_id=payload.association_id,
        title=payload.title,
        description=payload.description,
        scheduled_on=payload.scheduled_on,
        location=payload.location,
        agenda=payload.agenda,
        facilitator_id=payload.facilitator_id,
        created_by_id=current_user.id,
        status=MeetingStatus.PLANNED,
    )
    db.add(meeting)
    await db.commit()
    await db.refresh(meeting)
    return _meeting_to_out(meeting)


@router.patch("/{meeting_id}", response_model=MeetingOut)
async def update_meeting(
    meeting_id: UUID,
    payload: MeetingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = await _get_meeting_or_404(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)

    if m.status == MeetingStatus.CLOSED:
        raise HTTPException(status_code=409, detail="Cannot edit a closed meeting")

    data = payload.model_dump(exclude_unset=True)
    if "status" in data:
        try:
            data["status"] = MeetingStatus(data["status"])
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid status '{data['status']}'")

    for field, value in data.items():
        setattr(m, field, value)

    await db.commit()
    await db.refresh(m)
    return _meeting_to_out(m)


# ── Lifecycle ──────────────────────────────────────────────────────────────

@router.post("/{meeting_id}/open", response_model=MeetingOut)
async def open_meeting(
    meeting_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Transition PLANNED → ONGOING."""
    m = await _get_meeting_or_404(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)

    if m.status != MeetingStatus.PLANNED:
        raise HTTPException(status_code=409, detail=f"Meeting is already {m.status.value}")

    m.status = MeetingStatus.ONGOING
    m.started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(m)
    return _meeting_to_out(m)


@router.post("/{meeting_id}/close", response_model=MeetingOut)
async def close_meeting(
    meeting_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Transition ONGOING → CLOSED. Validates all DRAFT entries → RECORDED."""
    m = await _load_meeting_detail(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)

    if m.status != MeetingStatus.ONGOING:
        raise HTTPException(status_code=409, detail=f"Meeting is not ongoing (status={m.status.value})")

    now = datetime.now(timezone.utc)
    total_in = 0

    # Validate all DRAFT entries
    for entry in m.entries:
        if entry.status == EntryStatus.DRAFT:
            entry.status = EntryStatus.RECORDED
            entry.recorded_by_id = current_user.id
            entry.recorded_at = now
            total_in += entry.amount

    m.status = MeetingStatus.CLOSED
    m.closed_at = now
    m.total_in = total_in

    await db.commit()
    await db.refresh(m)
    return _meeting_to_out(m)


# ── Attendances ────────────────────────────────────────────────────────────

@router.get("/{meeting_id}/attendances", response_model=List[AttendanceOut])
async def list_attendances(
    meeting_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = await _get_meeting_or_404(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)

    result = await db.execute(
        select(MeetingAttendance).where(MeetingAttendance.meeting_id == meeting_id)
    )
    return [_attendance_to_out(a) for a in result.scalars().all()]


@router.put("/{meeting_id}/attendances", response_model=List[AttendanceOut])
async def upsert_attendances(
    meeting_id: UUID,
    payload: List[AttendanceUpsert],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk upsert attendances for a meeting."""
    m = await _get_meeting_or_404(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)

    if m.status == MeetingStatus.CLOSED:
        raise HTTPException(status_code=409, detail="Cannot edit attendances of a closed meeting")

    result = await db.execute(
        select(MeetingAttendance).where(MeetingAttendance.meeting_id == meeting_id)
    )
    existing = {a.membership_id: a for a in result.scalars().all()}

    out = []
    for item in payload:
        if item.membership_id in existing:
            att = existing[item.membership_id]
            att.status = item.status
            att.notes = item.notes
            att.excuse_reason = item.excuse_reason
        else:
            att = MeetingAttendance(
                meeting_id=meeting_id,
                membership_id=item.membership_id,
                status=item.status,
                notes=item.notes,
                excuse_reason=item.excuse_reason,
            )
            db.add(att)
        out.append(att)

    await db.commit()
    for att in out:
        await db.refresh(att)
    return [_attendance_to_out(a) for a in out]


# ── Entries ────────────────────────────────────────────────────────────────

@router.get("/{meeting_id}/entries", response_model=List[EntryOut])
async def list_entries(
    meeting_id: UUID,
    membership_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = await _get_meeting_or_404(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)

    stmt = select(MeetingActivityEntry).where(MeetingActivityEntry.meeting_id == meeting_id)
    if membership_id:
        stmt = stmt.where(MeetingActivityEntry.membership_id == membership_id)
    result = await db.execute(stmt)
    return [_entry_to_out(e) for e in result.scalars().all()]


@router.post("/{meeting_id}/entries", response_model=EntryOut, status_code=status.HTTP_201_CREATED)
async def create_entry(
    meeting_id: UUID,
    payload: EntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a DRAFT entry for a member × activity."""
    m = await _get_meeting_or_404(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)

    if m.status == MeetingStatus.CLOSED:
        raise HTTPException(status_code=409, detail="Cannot add entries to a closed meeting")

    # Validate activity belongs to same association
    res = await db.execute(select(Activity).where(Activity.id == payload.activity_id))
    act = res.scalar_one_or_none()
    if not act or act.association_id != m.association_id:
        raise HTTPException(status_code=422, detail="Activity does not belong to this association")

    entry = MeetingActivityEntry(
        meeting_id=meeting_id,
        membership_id=payload.membership_id,
        activity_id=payload.activity_id,
        amount=payload.amount,
        data=payload.data,
        notes=payload.notes,
        status=EntryStatus.DRAFT,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _entry_to_out(entry)


@router.patch("/{meeting_id}/entries/{entry_id}", response_model=EntryOut)
async def update_entry(
    meeting_id: UUID,
    entry_id: UUID,
    payload: EntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = await _get_meeting_or_404(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)

    res = await db.execute(
        select(MeetingActivityEntry).where(
            MeetingActivityEntry.id == entry_id,
            MeetingActivityEntry.meeting_id == meeting_id,
        )
    )
    entry = res.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    if entry.status == EntryStatus.VOIDED:
        raise HTTPException(status_code=409, detail="Cannot edit a voided entry")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)

    await db.commit()
    await db.refresh(entry)
    return _entry_to_out(entry)


@router.delete("/{meeting_id}/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def void_entry(
    meeting_id: UUID,
    entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Void (soft-delete) a DRAFT entry."""
    m = await _get_meeting_or_404(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)

    res = await db.execute(
        select(MeetingActivityEntry).where(
            MeetingActivityEntry.id == entry_id,
            MeetingActivityEntry.meeting_id == meeting_id,
        )
    )
    entry = res.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    if entry.status == EntryStatus.RECORDED:
        raise HTTPException(
            status_code=409,
            detail="Cannot void a recorded entry. Use correction instead.",
        )

    entry.status = EntryStatus.VOIDED
    await db.commit()
