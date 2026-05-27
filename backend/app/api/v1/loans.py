"""Loan endpoints — request → approve → disburse → repay.

Money flow via FinanceService:
  • disburse → OUT `principal` from the GENERAL fund to the borrower
  • repay    → IN: principal part → GENERAL, interest + late fee → INSURANCE
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.models.association import Association
from app.models.caisse import Caisse
from app.models.finance import Fund, FundKind, MovementDirection
from app.models.loan import (
    Loan,
    LoanInstallment,
    LoanInstallmentStatus,
    LoanRepayment,
    LoanStatus,
    LoanType,
)
from app.models.role import Membership
from app.models.user import User
from app.schemas.loan import (
    InstallmentOut,
    LoanApprove,
    LoanCreate,
    LoanDetail,
    LoanOut,
    LoanReject,
    LoanRepay,
    RepaymentOut,
)
from app.services.finance import Allocation, get_or_create_treasury, post_movement
from app.services.loan_calculator import compute_schedule

router = APIRouter()


# ── Helpers ─────────────────────────────────────────────────────────────────
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


def _require_admin(user: User) -> None:
    if not (user.is_super_admin or user.is_groupement_admin or user.is_association_admin):
        raise HTTPException(403, "Action réservée aux administrateurs")


async def _source_fund_for(db: AsyncSession, loan: Loan, treasury) -> Fund:
    """Resolve the fund that backs `loan` — the caisse snapshotted at request
    time, or the GENERAL fund for legacy loans (no type)."""
    if loan.source_caisse_id is not None:
        res = await db.execute(
            select(Fund)
            .join(Caisse, Caisse.fund_id == Fund.id)
            .where(Caisse.id == loan.source_caisse_id)
        )
        fund = res.scalar_one_or_none()
        if fund is None:
            raise HTTPException(500, "Caisse source du prêt introuvable.")
        return fund
    fund = next((f for f in treasury.funds if f.kind == FundKind.GENERAL), None)
    if fund is None:
        raise HTTPException(500, "Fonds général introuvable")
    return fund


async def _load_loan(db: AsyncSession, loan_id: UUID) -> Loan:
    res = await db.execute(
        select(Loan)
        .options(
            selectinload(Loan.installments),
            selectinload(Loan.repayments),
            selectinload(Loan.borrower).selectinload(Membership.user),
        )
        .where(Loan.id == loan_id)
    )
    loan = res.scalar_one_or_none()
    if not loan:
        raise HTTPException(404, "Prêt introuvable")
    return loan


def _loan_out(loan: Loan) -> LoanOut:
    borrower = getattr(loan, "borrower", None)
    user = getattr(borrower, "user", None) if borrower else None
    return LoanOut(
        id=loan.id,
        association_id=loan.association_id,
        borrower_membership_id=loan.borrower_membership_id,
        borrower_name=getattr(user, "full_name", None),
        loan_type_id=loan.loan_type_id,
        source_caisse_id=loan.source_caisse_id,
        reference=loan.reference,
        principal=loan.principal,
        interest_rate_pct=loan.interest_rate_pct,
        late_fee_pct=loan.late_fee_pct,
        duration_months=loan.duration_months,
        total_interest=loan.total_interest,
        total_due=loan.total_due,
        installment_amount=loan.installment_amount,
        paid_principal=loan.paid_principal,
        paid_interest=loan.paid_interest,
        paid_late_fees=loan.paid_late_fees,
        remaining_balance=loan.remaining_balance,
        requested_on=loan.requested_on,
        approved_on=loan.approved_on,
        disbursed_on=loan.disbursed_on,
        first_due_on=loan.first_due_on,
        last_due_on=loan.last_due_on,
        status=loan.status.value if hasattr(loan.status, "value") else loan.status,
        purpose=loan.purpose,
        created_at=loan.created_at,
    )


def _loan_detail(loan: Loan) -> LoanDetail:
    base = _loan_out(loan).model_dump()
    installments = sorted(loan.installments, key=lambda i: i.number)
    repayments = sorted(loan.repayments, key=lambda r: r.paid_on)
    return LoanDetail(
        **base,
        installments=[InstallmentOut.model_validate(i) for i in installments],
        repayments=[RepaymentOut.model_validate(r) for r in repayments],
    )


# ── Endpoints ───────────────────────────────────────────────────────────────
@router.get("", response_model=List[LoanOut])
async def list_loans(
    association_id: UUID = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assoc = await _get_assoc_or_404(db, association_id)
    _check_access(current_user, assoc)
    stmt = (
        select(Loan)
        .options(selectinload(Loan.borrower).selectinload(Membership.user))
        .where(Loan.association_id == association_id)
        .order_by(Loan.created_at.desc())
    )
    if status_filter:
        stmt = stmt.where(Loan.status == LoanStatus(status_filter))
    res = await db.execute(stmt)
    return [_loan_out(loan) for loan in res.scalars().all()]


@router.get("/{loan_id}", response_model=LoanDetail)
async def get_loan(
    loan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    loan = await _load_loan(db, loan_id)
    assoc = await _get_assoc_or_404(db, loan.association_id)
    _check_access(current_user, assoc)
    return _loan_detail(loan)


@router.post("", response_model=LoanDetail, status_code=status.HTTP_201_CREATED)
async def request_loan(
    payload: LoanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assoc = await _get_assoc_or_404(db, payload.association_id)
    _check_access(current_user, assoc)

    # Loans must be enabled on the association before any request lands.
    cfg_loans = (assoc.config or {}).get("loans") or {}
    if cfg_loans.get("enabled") is False:
        raise HTTPException(409, "Les prêts ne sont pas activés sur cette association.")

    res = await db.execute(
        select(Membership).where(
            Membership.id == payload.borrower_membership_id,
            Membership.association_id == payload.association_id,
        )
    )
    if not res.scalar_one_or_none():
        raise HTTPException(422, "Emprunteur introuvable dans l'association")

    # Phase 2d — résolution du LoanType : snapshot des règles + caisse source.
    loan_type: LoanType | None = None
    source_caisse_id: UUID | None = None
    rate = payload.interest_rate_pct
    late_fee = payload.late_fee_pct
    duration = payload.duration_months

    if payload.loan_type_id is not None:
        lt_res = await db.execute(
            select(LoanType).where(
                LoanType.id == payload.loan_type_id,
                LoanType.association_id == payload.association_id,
            )
        )
        loan_type = lt_res.scalar_one_or_none()
        if not loan_type:
            raise HTTPException(422, "Type de prêt introuvable dans cette association.")
        if not loan_type.is_active:
            raise HTTPException(409, "Ce type de prêt est désactivé.")
        if duration > loan_type.max_duration_months:
            raise HTTPException(
                422,
                f"Durée {duration}m > max autorisée par ce type ({loan_type.max_duration_months}m).",
            )
        # Éligibilité — borne le nombre de prêts vivants + sur 365j.
        if loan_type.max_simultaneous > 0:
            live_res = await db.execute(
                select(func.count(Loan.id)).where(
                    Loan.borrower_membership_id == payload.borrower_membership_id,
                    Loan.loan_type_id == loan_type.id,
                    Loan.status.in_([
                        LoanStatus.REQUESTED,
                        LoanStatus.APPROVED,
                        LoanStatus.DISBURSED,
                        LoanStatus.REPAYING,
                    ]),
                )
            )
            if (live_res.scalar() or 0) >= loan_type.max_simultaneous:
                raise HTTPException(
                    409,
                    f"Limite de prêts simultanés atteinte ({loan_type.max_simultaneous}) pour ce type.",
                )
        if loan_type.max_per_year > 0:
            one_year_ago = date.today() - timedelta(days=365)
            year_res = await db.execute(
                select(func.count(Loan.id)).where(
                    Loan.borrower_membership_id == payload.borrower_membership_id,
                    Loan.loan_type_id == loan_type.id,
                    Loan.requested_on >= one_year_ago,
                )
            )
            if (year_res.scalar() or 0) >= loan_type.max_per_year:
                raise HTTPException(
                    409,
                    f"Limite annuelle atteinte ({loan_type.max_per_year}) pour ce type.",
                )
        if loan_type.eligibility_no_default:
            defaulted = await db.execute(
                select(Loan.id).where(
                    Loan.borrower_membership_id == payload.borrower_membership_id,
                    Loan.status == LoanStatus.DEFAULTED,
                ).limit(1)
            )
            if defaulted.first():
                raise HTTPException(
                    409,
                    "Ce membre a un défaut de paiement antérieur — ce type de prêt l'exclut.",
                )
        # Snapshot des paramètres financiers du type.
        rate = rate if rate is not None else loan_type.interest_rate_pct
        late_fee = late_fee if late_fee is not None else loan_type.late_fee_pct
        source_caisse_id = loan_type.source_caisse_id

    # Fallback minimal pour les prêts sans type (legacy).
    if rate is None:
        raise HTTPException(422, "Le taux d'intérêt est requis (ou choisis un type de prêt).")
    if late_fee is None:
        late_fee = Decimal("0")

    count_res = await db.execute(
        select(func.count(Loan.id)).where(Loan.association_id == payload.association_id)
    )
    seq = (count_res.scalar() or 0) + 1
    reference = f"PRT-{date.today().year}-{seq:04d}"

    loan = Loan(
        association_id=payload.association_id,
        borrower_membership_id=payload.borrower_membership_id,
        loan_type_id=payload.loan_type_id,
        source_caisse_id=source_caisse_id,
        reference=reference,
        principal=payload.principal,
        interest_rate_pct=rate,
        late_fee_pct=late_fee,
        duration_months=duration,
        requested_on=date.today(),
        requested_by_id=current_user.id,
        status=LoanStatus.REQUESTED,
        purpose=payload.purpose,
    )
    db.add(loan)
    await db.commit()
    loan = await _load_loan(db, loan.id)
    return _loan_detail(loan)


@router.post("/{loan_id}/approve", response_model=LoanDetail)
async def approve_loan(
    loan_id: UUID,
    payload: LoanApprove,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve the loan and snapshot its amortisation schedule."""
    loan = await _load_loan(db, loan_id)
    assoc = await _get_assoc_or_404(db, loan.association_id)
    _check_access(current_user, assoc)
    _require_admin(current_user)

    if loan.status != LoanStatus.REQUESTED:
        raise HTTPException(409, "Seule une demande peut être approuvée")

    first_due = payload.first_due_on or (date.today() + timedelta(days=30))
    schedule = compute_schedule(
        principal=loan.principal,
        interest_rate_pct=loan.interest_rate_pct,
        duration_months=loan.duration_months,
        first_due_on=first_due,
    )

    loan.total_interest = schedule.total_interest
    loan.total_due = schedule.total_due
    loan.installment_amount = schedule.installment_amount
    loan.first_due_on = schedule.first_due_on
    loan.last_due_on = schedule.last_due_on
    loan.approved_on = date.today()
    loan.approved_by_id = current_user.id
    loan.status = LoanStatus.APPROVED

    for s in schedule.installments:
        db.add(
            LoanInstallment(
                loan_id=loan.id,
                number=s.number,
                due_on=s.due_on,
                principal_part=s.principal_part,
                interest_part=s.interest_part,
                expected_amount=s.expected_amount,
                status=LoanInstallmentStatus.PENDING,
            )
        )

    await db.commit()
    db.expire_all()  # drop stale collections so the reload sees new installments
    loan = await _load_loan(db, loan_id)
    return _loan_detail(loan)


@router.post("/{loan_id}/reject", response_model=LoanDetail)
async def reject_loan(
    loan_id: UUID,
    payload: LoanReject,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    loan = await _load_loan(db, loan_id)
    assoc = await _get_assoc_or_404(db, loan.association_id)
    _check_access(current_user, assoc)
    _require_admin(current_user)

    if loan.status not in (LoanStatus.REQUESTED, LoanStatus.APPROVED):
        raise HTTPException(409, "Le prêt ne peut plus être rejeté")

    loan.status = LoanStatus.REJECTED
    loan.notes = payload.reason
    await db.commit()
    loan = await _load_loan(db, loan_id)
    return _loan_detail(loan)


@router.post("/{loan_id}/disburse", response_model=LoanDetail)
async def disburse_loan(
    loan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Disburse an approved loan — OUT `principal` from the GENERAL fund."""
    loan = await _load_loan(db, loan_id)
    assoc = await _get_assoc_or_404(db, loan.association_id)
    _check_access(current_user, assoc)
    _require_admin(current_user)

    if loan.status != LoanStatus.APPROVED:
        raise HTTPException(409, "Seul un prêt approuvé peut être décaissé")

    treasury = await get_or_create_treasury(db, assoc)
    fund = await _source_fund_for(db, loan, treasury)

    movement = await post_movement(
        db,
        treasury=treasury,
        direction=MovementDirection.OUT,
        amount=loan.principal,
        allocations=[Allocation(fund=fund, is_credit=False, amount=loan.principal)],
        occurred_on=date.today(),
        source_type="loan_disbursement",
        source_id=loan.id,
        recorded_by_id=current_user.id,
        related_membership_id=loan.borrower_membership_id,
        description=f"Décaissement prêt {loan.reference}",
        commit=False,
    )

    loan.disbursed_on = date.today()
    loan.disbursement_movement_id = movement.id
    loan.status = LoanStatus.REPAYING
    await db.commit()
    loan = await _load_loan(db, loan_id)
    return _loan_detail(loan)


@router.post("/{loan_id}/repay", response_model=LoanDetail)
async def repay_loan(
    loan_id: UUID,
    payload: LoanRepay,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record a repayment — allocated oldest-installment-first, posted IN."""
    loan = await _load_loan(db, loan_id)
    assoc = await _get_assoc_or_404(db, loan.association_id)
    _check_access(current_user, assoc)
    _require_admin(current_user)

    if loan.status not in (LoanStatus.DISBURSED, LoanStatus.REPAYING):
        raise HTTPException(409, "Ce prêt n'est pas en remboursement")

    remaining_balance = loan.remaining_balance
    if payload.amount > remaining_balance:
        raise HTTPException(
            422, f"Le montant dépasse le solde restant ({remaining_balance})"
        )

    # Allocate oldest installment first: interest before principal within each.
    remaining = payload.amount
    paid_principal = 0
    paid_interest = 0
    paid_on = payload.paid_on or date.today()

    for inst in sorted(loan.installments, key=lambda i: i.number):
        if remaining <= 0:
            break
        if inst.status in (LoanInstallmentStatus.PAID, LoanInstallmentStatus.WAIVED):
            continue
        due_i = inst.interest_part - inst.paid_interest
        pay_i = min(remaining, max(0, due_i))
        inst.paid_interest += pay_i
        remaining -= pay_i
        paid_interest += pay_i

        due_p = inst.principal_part - inst.paid_principal
        pay_p = min(remaining, max(0, due_p))
        inst.paid_principal += pay_p
        remaining -= pay_p
        paid_principal += pay_p

        if inst.paid_interest >= inst.interest_part and inst.paid_principal >= inst.principal_part:
            inst.status = LoanInstallmentStatus.PAID
            inst.paid_on = paid_on
        elif inst.paid_interest > 0 or inst.paid_principal > 0:
            inst.status = LoanInstallmentStatus.PARTIALLY_PAID

    # Post the cash-in: principal → loan's source caisse (GENERAL fallback),
    # interest → INSURANCE.
    treasury = await get_or_create_treasury(db, assoc)
    principal_fund = await _source_fund_for(db, loan, treasury)
    insurance = next((f for f in treasury.funds if f.kind == FundKind.INSURANCE), None)
    if insurance is None:
        raise HTTPException(500, "Fonds assurance introuvable")

    allocations = []
    if paid_principal > 0:
        allocations.append(Allocation(fund=principal_fund, is_credit=True, amount=paid_principal))
    if paid_interest > 0:
        allocations.append(Allocation(fund=insurance, is_credit=True, amount=paid_interest))

    movement = await post_movement(
        db,
        treasury=treasury,
        direction=MovementDirection.IN,
        amount=payload.amount,
        allocations=allocations,
        occurred_on=paid_on,
        source_type="loan_repayment",
        source_id=loan.id,
        recorded_by_id=current_user.id,
        related_membership_id=loan.borrower_membership_id,
        description=f"Remboursement prêt {loan.reference}",
        commit=False,
    )

    db.add(
        LoanRepayment(
            loan_id=loan.id,
            paid_on=paid_on,
            total_paid=payload.amount,
            principal=paid_principal,
            interest=paid_interest,
            late_fee=0,
            movement_id=movement.id,
            notes=payload.notes,
        )
    )

    loan.paid_principal += paid_principal
    loan.paid_interest += paid_interest
    if loan.paid_principal + loan.paid_interest >= loan.total_due:
        loan.status = LoanStatus.PAID
        loan.closed_on = paid_on

    await db.commit()
    db.expire_all()  # drop stale collections so the reload sees the new repayment
    loan = await _load_loan(db, loan_id)
    return _loan_detail(loan)
