"""Caisses CRUD — user-defined funds layered over the Fund accounting unit.

Phase 1 ships the basic CRUD. Phase 2 will enrich the read endpoints with
member balances + progress against ceiling/objective.

Auth model:
- list/get : any role with access to the association
- create/patch/delete : association_admin only (config)
- SYSTEM caisses are read-only (name/description editable, no deletion)
"""
from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_db,
    require_association_admin_for,
)
from app.models.association import Association
from app.models.caisse import Caisse, CaisseCategory
from app.models.finance import Fund, FundKind, Treasury
from app.models.user import User
from app.schemas.caisse import CaisseCreate, CaisseOut, CaisseUpdate
from app.services.meeting_agenda import upsert_caisse_activity

router = APIRouter()


async def _check_access(db: AsyncSession, user: User, association_id: UUID) -> Association:
    res = await db.execute(select(Association).where(Association.id == association_id))
    assoc = res.scalar_one_or_none()
    if not assoc:
        raise HTTPException(404, "Association introuvable")
    if not user.is_super_admin and user.groupement_id != assoc.groupement_id:
        raise HTTPException(403, "Forbidden")
    return assoc


@router.get("", response_model=List[CaisseOut])
async def list_caisses(
    association_id: UUID = Query(...),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _check_access(db, current_user, association_id)
    stmt = select(Caisse).where(Caisse.association_id == association_id)
    if not include_inactive:
        stmt = stmt.where(Caisse.is_active.is_(True))
    stmt = stmt.order_by(Caisse.is_system.desc(), Caisse.created_at)
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.get("/{caisse_id}", response_model=CaisseOut)
async def get_caisse(
    caisse_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    res = await db.execute(select(Caisse).where(Caisse.id == caisse_id))
    caisse = res.scalar_one_or_none()
    if not caisse:
        raise HTTPException(404, "Caisse introuvable")
    await _check_access(db, current_user, caisse.association_id)
    return caisse


# ── Admin-only writes ──────────────────────────────────────────────────────


def _caisse_admin(
    association_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reuse the existing per-association admin guard. The association_id
    must be in scope (query, body or path) for FastAPI to resolve it."""
    return require_association_admin_for(association_id=association_id, user=user, db=db)


@router.post("", response_model=CaisseOut, status_code=status.HTTP_201_CREATED)
async def create_caisse(
    payload: CaisseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a custom caisse. The association admin chooses category +
    rules; a backing Fund is auto-created so the treasury invariant holds."""
    # Inline admin check (body carries the association_id — can't be a path dep).
    assoc = await _check_access(db, current_user, payload.association_id)
    if not (current_user.is_super_admin or current_user.is_groupement_admin):
        # Strict check: must be association_admin on THIS association.
        from app.api.deps import _user_is_association_admin
        if not await _user_is_association_admin(db, current_user, payload.association_id):
            raise HTTPException(403, "Réservé à l'admin de cette association")

    # Unique slug per association.
    dupe = await db.execute(
        select(Caisse).where(
            Caisse.association_id == payload.association_id,
            Caisse.slug == payload.slug,
        )
    )
    if dupe.scalar_one_or_none():
        raise HTTPException(409, "Une caisse avec ce slug existe déjà")

    # Get or attach the association's treasury.
    treas_res = await db.execute(
        select(Treasury).where(Treasury.association_id == payload.association_id)
    )
    treasury = treas_res.scalar_one_or_none()
    if not treasury:
        treasury = Treasury(association_id=payload.association_id, currency=assoc.currency)
        db.add(treasury)
        await db.flush()

    fund = Fund(
        treasury_id=treasury.id,
        kind=FundKind.CUSTOM,
        ref_key=payload.slug,
        name=payload.name,
        description=payload.description,
        is_system=False,
    )
    db.add(fund)
    await db.flush()

    caisse = Caisse(
        association_id=payload.association_id,
        fund_id=fund.id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        category=payload.category,
        is_system=False,
        is_recurring=payload.is_recurring,
        recurring_amount=payload.recurring_amount,
        is_member_required=payload.is_member_required,
        member_required_amount=payload.member_required_amount,
        has_ceiling=payload.has_ceiling,
        ceiling_amount=payload.ceiling_amount,
        has_objective=payload.has_objective,
        objective_amount=payload.objective_amount,
        objective_deadline=payload.objective_deadline,
    )
    db.add(caisse)
    await db.flush()

    # Phase 3 — auto-create the Activity row so the séance page picks up
    # this caisse as a row to enter at every meeting (when recurring/required).
    await upsert_caisse_activity(
        db,
        association_id=payload.association_id,
        caisse_id=caisse.id,
        name=payload.name,
        slug=payload.slug,
        is_recurring=payload.is_recurring,
        recurring_amount=payload.recurring_amount,
        is_member_required=payload.is_member_required,
        member_required_amount=payload.member_required_amount,
    )

    await db.commit()
    await db.refresh(caisse)
    return caisse


@router.patch("/{caisse_id}", response_model=CaisseOut)
async def update_caisse(
    caisse_id: UUID,
    payload: CaisseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    res = await db.execute(select(Caisse).where(Caisse.id == caisse_id))
    caisse = res.scalar_one_or_none()
    if not caisse:
        raise HTTPException(404, "Caisse introuvable")
    await _check_access(db, current_user, caisse.association_id)
    if not (current_user.is_super_admin or current_user.is_groupement_admin):
        from app.api.deps import _user_is_association_admin
        if not await _user_is_association_admin(db, current_user, caisse.association_id):
            raise HTTPException(403, "Réservé à l'admin de cette association")

    data = payload.model_dump(exclude_unset=True)
    # System caisses: only name/description/is_active mutable; behavior config locked.
    if caisse.is_system:
        for k in (
            "is_recurring",
            "recurring_amount",
            "is_member_required",
            "member_required_amount",
            "has_ceiling",
            "ceiling_amount",
            "has_objective",
            "objective_amount",
            "objective_deadline",
        ):
            data.pop(k, None)

    for field, value in data.items():
        setattr(caisse, field, value)
    # Mirror name/description onto the backing fund so the finance UI stays in sync.
    if "name" in data or "description" in data:
        fund_res = await db.execute(select(Fund).where(Fund.id == caisse.fund_id))
        fund = fund_res.scalar_one_or_none()
        if fund:
            if "name" in data:
                fund.name = caisse.name
            if "description" in data:
                fund.description = caisse.description

    # Phase 3 — re-sync the matching Activity (custom caisses only).
    if not caisse.is_system:
        await upsert_caisse_activity(
            db,
            association_id=caisse.association_id,
            caisse_id=caisse.id,
            name=caisse.name,
            slug=caisse.slug,
            is_recurring=caisse.is_recurring,
            recurring_amount=caisse.recurring_amount,
            is_member_required=caisse.is_member_required,
            member_required_amount=caisse.member_required_amount,
        )

    await db.commit()
    await db.refresh(caisse)
    return caisse


@router.delete("/{caisse_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_caisse(
    caisse_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    res = await db.execute(select(Caisse).where(Caisse.id == caisse_id))
    caisse = res.scalar_one_or_none()
    if not caisse:
        raise HTTPException(404, "Caisse introuvable")
    if caisse.is_system:
        raise HTTPException(409, "Les caisses système ne sont pas supprimables")
    await _check_access(db, current_user, caisse.association_id)
    if not (current_user.is_super_admin or current_user.is_groupement_admin):
        from app.api.deps import _user_is_association_admin
        if not await _user_is_association_admin(db, current_user, caisse.association_id):
            raise HTTPException(403, "Réservé à l'admin de cette association")

    # Refuse delete if the fund has a non-zero balance — protects the invariant.
    fund_res = await db.execute(select(Fund).where(Fund.id == caisse.fund_id))
    fund = fund_res.scalar_one_or_none()
    if fund and fund.balance != 0:
        raise HTTPException(
            409, "Solde non nul — videz la caisse (transfert) avant de la supprimer."
        )

    await db.delete(caisse)
    if fund:
        await db.delete(fund)
    await db.commit()
