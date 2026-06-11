"""Finance endpoints — treasury, funds, movements."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.association import Association
from app.models.caisse import Caisse, CaisseContributorBalance, MemberCaisseBalance
from app.models.finance import (
    Fund,
    LedgerEntry,
    MovementDirection,
    Treasury,
    TreasuryMovement,
)
from app.models.loan import Loan
from app.models.role import Membership
from app.models.social_aid import SocialAidCase
from app.models.user import User
from app.schemas.finance import (
    MovementCreate,
    MovementOut,
    MyAidLine,
    MyCaisseLine,
    MyFinanceSummary,
    MyLoanLine,
    MyMovement,
    TreasuryOut,
    VoidRequest,
)
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


@router.get("/my-summary", response_model=MyFinanceSummary)
async def my_finance_summary(
    association_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Vue « Mes cotisations » : historique financier propre au membre courant
    (cotisations versées, prêts reçus + remboursements, aides reçues, soldes de
    caisses). Jamais les totaux de l'association."""
    assoc = await _get_assoc_or_404(db, association_id)
    _check_access(current_user, assoc)

    mres = await db.execute(
        select(Membership.id).where(
            Membership.user_id == current_user.id,
            Membership.association_id == association_id,
        )
    )
    my_mem_ids = list(mres.scalars().all())
    if not my_mem_ids:
        return MyFinanceSummary(
            total_contributed=0, total_loans_outstanding=0, total_aids_received=0,
            movements=[], loans=[], aids=[], caisses=[],
        )

    treasury = await get_or_create_treasury(db, assoc)
    mv_res = await db.execute(
        select(TreasuryMovement)
        .where(
            TreasuryMovement.treasury_id == treasury.id,
            TreasuryMovement.related_membership_id.in_(my_mem_ids),
        )
        .order_by(TreasuryMovement.occurred_on.desc(), TreasuryMovement.created_at.desc())
        .limit(100)
    )
    movements_rows = list(mv_res.scalars().all())
    fund_by_movement: dict = {}
    if movements_rows:
        le_res = await db.execute(
            select(LedgerEntry.movement_id, Fund.name)
            .join(Fund, Fund.id == LedgerEntry.fund_id)
            .where(LedgerEntry.movement_id.in_([m.id for m in movements_rows]))
        )
        for mid, fname in le_res.all():
            fund_by_movement.setdefault(mid, fname)

    movements = [
        MyMovement(
            occurred_on=m.occurred_on,
            direction=m.direction.value if hasattr(m.direction, "value") else str(m.direction),
            amount=m.amount,
            label=m.description or m.source_type,
            fund_name=fund_by_movement.get(m.id),
            source_type=m.source_type,
        )
        for m in movements_rows
        if not getattr(m, "is_voided", False)
    ]
    total_contributed = sum(
        m.amount for m in movements_rows
        if (m.direction == MovementDirection.IN) and not getattr(m, "is_voided", False)
    )

    loan_res = await db.execute(
        select(Loan).where(Loan.borrower_membership_id.in_(my_mem_ids))
        .order_by(Loan.created_at.desc())
    )
    loans_rows = list(loan_res.scalars().all())
    loans = [
        MyLoanLine(
            id=ln.id, reference=ln.reference, principal=ln.principal,
            status=ln.status.value if hasattr(ln.status, "value") else str(ln.status),
            remaining=ln.remaining_balance, requested_on=ln.requested_on,
        )
        for ln in loans_rows
    ]
    total_loans_outstanding = sum(ln.remaining_balance for ln in loans_rows)

    aid_res = await db.execute(
        select(SocialAidCase).where(SocialAidCase.beneficiary_membership_id.in_(my_mem_ids))
        .order_by(SocialAidCase.created_at.desc())
    )
    aids_rows = list(aid_res.scalars().all())
    aids = [
        MyAidLine(
            id=a.id, reference=a.reference, title=a.title,
            status=a.status.value if hasattr(a.status, "value") else str(a.status),
            approved_amount=a.approved_amount, paid_amount=a.paid_amount,
        )
        for a in aids_rows
    ]
    total_aids_received = sum(a.paid_amount for a in aids_rows)

    caisses: list[MyCaisseLine] = []
    ccb_res = await db.execute(
        select(CaisseContributorBalance, Caisse)
        .join(Caisse, Caisse.id == CaisseContributorBalance.caisse_id)
        .where(CaisseContributorBalance.membership_id.in_(my_mem_ids))
    )
    for bal, caisse in ccb_res.all():
        caisses.append(
            MyCaisseLine(
                caisse_id=caisse.id, caisse_name=caisse.name,
                category=caisse.category.value if hasattr(caisse.category, "value") else str(caisse.category),
                kind="shared" if caisse.interest_distribution == "shared_pro_rata" else "contribution",
                my_contributed=bal.apport_cum,
                my_interest=bal.interest_cum or None,
            )
        )
    seen = {c.caisse_id for c in caisses}
    mcb_res = await db.execute(
        select(MemberCaisseBalance, Caisse)
        .join(Caisse, Caisse.id == MemberCaisseBalance.caisse_id)
        .where(MemberCaisseBalance.membership_id.in_(my_mem_ids))
    )
    for bal, caisse in mcb_res.all():
        existing = next((c for c in caisses if c.caisse_id == caisse.id), None)
        if existing:
            existing.my_personal_balance = bal.balance
            existing.kind = "personal"
        else:
            caisses.append(
                MyCaisseLine(
                    caisse_id=caisse.id, caisse_name=caisse.name,
                    category=caisse.category.value if hasattr(caisse.category, "value") else str(caisse.category),
                    kind="personal", my_contributed=bal.balance,
                    my_personal_balance=bal.balance,
                )
            )

    return MyFinanceSummary(
        total_contributed=total_contributed,
        total_loans_outstanding=total_loans_outstanding,
        total_aids_received=total_aids_received,
        movements=movements,
        loans=loans,
        aids=aids,
        caisses=caisses,
    )


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
