"""Activities CRUD endpoints (catalogue d'activités d'une association)."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.association import Association
from app.models.meeting import Activity, ActivityType
from app.models.user import User
from app.schemas.meeting import ActivityCreate, ActivityOut, ActivityUpdate

router = APIRouter()


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


@router.get("", response_model=List[ActivityOut])
async def list_activities(
    association_id: UUID = Query(...),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assoc = await _get_assoc_or_404(db, association_id)
    _check_access(current_user, assoc)

    stmt = select(Activity).where(Activity.association_id == association_id)
    if active_only:
        stmt = stmt.where(Activity.is_active == True)  # noqa: E712
    stmt = stmt.order_by(Activity.sort_order, Activity.name)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{activity_id}", response_model=ActivityOut)
async def get_activity(
    activity_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Activity).where(Activity.id == activity_id))
    act = result.scalar_one_or_none()
    if not act:
        raise HTTPException(status_code=404, detail="Activity not found")
    assoc = await _get_assoc_or_404(db, act.association_id)
    _check_access(current_user, assoc)
    return act


@router.post("", response_model=ActivityOut, status_code=status.HTTP_201_CREATED)
async def create_activity(
    payload: ActivityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assoc = await _get_assoc_or_404(db, payload.association_id)
    _check_access(current_user, assoc)

    # Validate type
    try:
        act_type = ActivityType(payload.type)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid activity type '{payload.type}'")

    # Check code uniqueness within association
    existing = await db.execute(
        select(Activity).where(
            Activity.association_id == payload.association_id,
            Activity.code == payload.code,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Activity code already exists in this association")

    act = Activity(
        association_id=payload.association_id,
        type=act_type,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        color=payload.color,
        icon=payload.icon,
        config=payload.config,
        is_visible_in_meeting=payload.is_visible_in_meeting,
        is_required=payload.is_required,
        sort_order=payload.sort_order,
    )
    db.add(act)
    await db.commit()
    await db.refresh(act)
    return act


@router.patch("/{activity_id}", response_model=ActivityOut)
async def update_activity(
    activity_id: UUID,
    payload: ActivityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Activity).where(Activity.id == activity_id))
    act = result.scalar_one_or_none()
    if not act:
        raise HTTPException(status_code=404, detail="Activity not found")
    assoc = await _get_assoc_or_404(db, act.association_id)
    _check_access(current_user, assoc)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(act, field, value)

    await db.commit()
    await db.refresh(act)
    return act
