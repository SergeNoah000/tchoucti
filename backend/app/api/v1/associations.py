"""Associations CRUD endpoints."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.association import Association
from app.models.finance import Treasury, TreasuryMovement
from app.models.groupement import Groupement
from app.models.role import Membership, MembershipStatus
from app.models.user import User
from app.schemas.association import AssociationCreate, AssociationOut, AssociationUpdate

router = APIRouter()


def _check_assoc_access(user: User, assoc: Association) -> None:
    """Raise 403 if user has no access to this association's groupement."""
    if user.is_super_admin:
        return
    if user.groupement_id != assoc.groupement_id:
        raise HTTPException(status_code=403, detail="Forbidden")


async def _has_financial_history(db: AsyncSession, association_id: UUID) -> bool:
    """True once the association has at least one treasury movement — the
    currency is then frozen to keep the ledger consistent."""
    row = await db.execute(
        select(TreasuryMovement.id)
        .join(Treasury, TreasuryMovement.treasury_id == Treasury.id)
        .where(Treasury.association_id == association_id)
        .limit(1)
    )
    return row.first() is not None


@router.get("", response_model=List[AssociationOut])
async def list_associations(
    groupement_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List associations.
    - Super admin: all (or filtered by groupement_id).
    - Others: only associations in their groupement.
    """
    stmt = select(Association)

    if current_user.is_super_admin:
        if groupement_id:
            stmt = stmt.where(Association.groupement_id == groupement_id)
    elif current_user.is_groupement_admin:
        # Group admin oversees every association of their groupement.
        if not current_user.groupement_id:
            return []
        stmt = stmt.where(Association.groupement_id == current_user.groupement_id)
    else:
        # Association admin / regular member: only associations they actually
        # belong to (silo at the association grain).
        sub = (
            select(Membership.association_id)
            .where(
                Membership.user_id == current_user.id,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
        stmt = stmt.where(Association.id.in_(sub))

    stmt = stmt.order_by(Association.name)
    result = await db.execute(stmt)
    assocs = result.scalars().all()

    if assocs:
        locked_rows = await db.execute(
            select(Treasury.association_id)
            .join(TreasuryMovement, TreasuryMovement.treasury_id == Treasury.id)
            .where(Treasury.association_id.in_([a.id for a in assocs]))
            .distinct()
        )
        locked_ids = set(locked_rows.scalars().all())
        sub_rows = await db.execute(
            select(Groupement.id, Groupement.subdomain).where(
                Groupement.id.in_([a.groupement_id for a in assocs])
            )
        )
        sub_by_gid = dict(sub_rows.all())
        for a in assocs:
            a.currency_locked = a.id in locked_ids
            a.groupement_subdomain = sub_by_gid.get(a.groupement_id)
    return assocs


@router.get("/{association_id}", response_model=AssociationOut)
async def get_association(
    association_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Association).where(Association.id == association_id))
    assoc = result.scalar_one_or_none()
    if not assoc:
        raise HTTPException(status_code=404, detail="Association not found")
    _check_assoc_access(current_user, assoc)
    assoc.currency_locked = await _has_financial_history(db, assoc.id)
    sub_row = await db.execute(
        select(Groupement.subdomain).where(Groupement.id == assoc.groupement_id)
    )
    assoc.groupement_subdomain = sub_row.scalar_one_or_none()
    return assoc


@router.post("", response_model=AssociationOut, status_code=status.HTTP_201_CREATED)
async def create_association(
    payload: AssociationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Must be super_admin or groupement admin of the target groupement
    if not current_user.is_super_admin:
        if current_user.groupement_id != payload.groupement_id:
            raise HTTPException(status_code=403, detail="Forbidden")

    # Check slug uniqueness within groupement
    existing = await db.execute(
        select(Association).where(
            Association.groupement_id == payload.groupement_id,
            Association.slug == payload.slug,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Slug already taken in this groupement")

    assoc = Association(
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        currency=payload.currency,
        timezone=payload.timezone,
        address=payload.address,
        city=payload.city,
        primary_color=payload.primary_color,
        config=payload.config,
        groupement_id=payload.groupement_id,
    )
    db.add(assoc)
    await db.commit()
    await db.refresh(assoc)
    assoc.currency_locked = False
    sub_row = await db.execute(
        select(Groupement.subdomain).where(Groupement.id == assoc.groupement_id)
    )
    assoc.groupement_subdomain = sub_row.scalar_one_or_none()
    return assoc


@router.patch("/{association_id}", response_model=AssociationOut)
async def update_association(
    association_id: UUID,
    payload: AssociationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Association).where(Association.id == association_id))
    assoc = result.scalar_one_or_none()
    if not assoc:
        raise HTTPException(status_code=404, detail="Association not found")
    _check_assoc_access(current_user, assoc)

    data = payload.model_dump(exclude_unset=True)
    new_currency = data.get("currency")
    locked = await _has_financial_history(db, assoc.id)
    if new_currency and new_currency != assoc.currency and locked:
        raise HTTPException(status_code=409, detail="currency_locked")

    for field, value in data.items():
        setattr(assoc, field, value)

    await db.commit()
    await db.refresh(assoc)
    assoc.currency_locked = locked
    sub_row = await db.execute(
        select(Groupement.subdomain).where(Groupement.id == assoc.groupement_id)
    )
    assoc.groupement_subdomain = sub_row.scalar_one_or_none()
    return assoc
