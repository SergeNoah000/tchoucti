"""Finance endpoints — treasury, funds, movements."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.association import Association
from app.models.finance import Fund, MovementDirection, Treasury, TreasuryMovement
from app.models.user import User
from app.schemas.finance import MovementCreate, MovementOut, TreasuryOut, VoidRequest
from app.services.finance import Allocation, get_or_create_treasury, post_movement, void_movement

router = APIRouter()


async def _get_assoc_or_404(db: AsyncSession, association_id: UUID) -> Association:
    res = await db.execute(select(Association).where(Association.id == association_id))
    assoc = res.scalar_one_or_none()
    if not assoc:
        raise HTTPException(404, "Association not found")
    return assoc


def _check_access(user: User, assoc: Association) -> None:
    if user.is_super_admin:
        return
    if user.groupement_id != assoc.groupement_id:
        raise HTTPException(403, "Forbidden")


@router.get("/treasury", response_model=TreasuryOut)
async def get_treasury(
    association_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the treasury + funds, provisioning them on first access."""
    assoc = await _get_assoc_or_404(db, association_id)
    _check_access(current_user, assoc)
    treasury = await get_or_create_treasury(db, assoc)
    return treasury


@router.get("/movements", response_model=List[MovementOut])
async def list_movements(
    association_id: UUID = Query(...),
    fund_id: Optional[UUID] = Query(None),
    direction: Optional[str] = Query(None, pattern=r"^(in|out|xfer)$"),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assoc = await _get_assoc_or_404(db, association_id)
    _check_access(current_user, assoc)
    treasury = await get_or_create_treasury(db, assoc)

    stmt = select(TreasuryMovement).where(TreasuryMovement.treasury_id == treasury.id)
    if direction:
        stmt = stmt.where(TreasuryMovement.direction == MovementDirection(direction))
    if fund_id:
        # movements that touched this fund
        from app.models.finance import LedgerEntry

        sub = select(LedgerEntry.movement_id).where(LedgerEntry.fund_id == fund_id)
        stmt = stmt.where(TreasuryMovement.id.in_(sub))
    stmt = stmt.order_by(
        TreasuryMovement.occurred_on.desc(), TreasuryMovement.created_at.desc()
    ).limit(limit)

    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.post("/movements", response_model=MovementOut, status_code=status.HTTP_201_CREATED)
async def create_movement(
    payload: MovementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Post a manual movement (admin adjustment / external cash / inter-fund transfer)."""
    assoc = await _get_assoc_or_404(db, payload.association_id)
    _check_access(current_user, assoc)
    treasury = await get_or_create_treasury(db, assoc)

    funds_by_id = {f.id: f for f in treasury.funds}
    fund = funds_by_id.get(payload.fund_id)
    if not fund:
        raise HTTPException(422, "Fonds introuvable dans cette caisse")

    direction = MovementDirection(payload.direction)

    if direction == MovementDirection.IN:
        allocations = [Allocation(fund=fund, is_credit=True, amount=payload.amount)]
    elif direction == MovementDirection.OUT:
        allocations = [Allocation(fund=fund, is_credit=False, amount=payload.amount)]
    else:  # XFER
        if not payload.to_fund_id:
            raise HTTPException(422, "Le fonds de destination est requis pour un transfert")
        to_fund = funds_by_id.get(payload.to_fund_id)
        if not to_fund:
            raise HTTPException(422, "Fonds de destination introuvable")
        allocations = [
            Allocation(fund=fund, is_credit=False, amount=payload.amount),
            Allocation(fund=to_fund, is_credit=True, amount=payload.amount),
        ]

    movement = await post_movement(
        db,
        treasury=treasury,
        direction=direction,
        amount=payload.amount,
        allocations=allocations,
        occurred_on=payload.occurred_on,
        source_type="manual",
        recorded_by_id=current_user.id,
        related_membership_id=payload.related_membership_id,
        description=payload.description,
    )
    return movement


@router.post("/movements/{movement_id}/void", response_model=MovementOut)
async def void_treasury_movement(
    movement_id: UUID,
    payload: VoidRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    res = await db.execute(select(TreasuryMovement).where(TreasuryMovement.id == movement_id))
    movement = res.scalar_one_or_none()
    if not movement:
        raise HTTPException(404, "Mouvement introuvable")

    tres = await db.execute(
        select(Treasury).where(Treasury.id == movement.treasury_id)
    )
    treasury = tres.scalar_one()
    assoc = await _get_assoc_or_404(db, treasury.association_id)
    _check_access(current_user, assoc)

    # need funds loaded for the reversal
    fres = await db.execute(select(Fund).where(Fund.treasury_id == treasury.id))
    treasury.funds = list(fres.scalars().all())  # type: ignore[attr-defined]

    movement = await void_movement(db, treasury=treasury, movement=movement, reason=payload.reason)
    return movement
