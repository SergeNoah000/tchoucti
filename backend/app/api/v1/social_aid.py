"""Social-aid endpoints — cases lifecycle: declare → approve/reject → payout.

A payout debits the INSURANCE fund (« Caisse sociale ») via FinanceService.
The aid amount defaults to the scale configured in
`association.config.social_fund.events[kind]`.
"""
from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.models.association import Association
from app.models.finance import FundKind, MovementDirection
from app.models.role import Membership
from app.models.social_aid import SocialAidCase, SocialAidCaseKind, SocialAidCaseStatus, SocialAidPayout
from app.models.user import User
from app.schemas.social_aid import (
    SocialAidApprove,
    SocialAidCaseCreate,
    SocialAidCaseDetail,
    SocialAidCaseOut,
    SocialAidReject,
)
from app.services.finance import Allocation, get_or_create_treasury, post_movement

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


def _scale_amount(assoc: Association, kind: str) -> Optional[int]:
    """Configured aid amount for a kind, from association.config.social_fund.events."""
    events = ((assoc.config or {}).get("social_fund") or {}).get("events") or {}
    val = events.get(kind)
    return int(val) if isinstance(val, (int, float)) and val else None


async def _load_case(db: AsyncSession, case_id: UUID) -> SocialAidCase:
    res = await db.execute(
        select(SocialAidCase)
        .options(
            selectinload(SocialAidCase.payouts),
            selectinload(SocialAidCase.beneficiary).selectinload(Membership.user),
        )
        .where(SocialAidCase.id == case_id)
    )
    case = res.scalar_one_or_none()
    if not case:
        raise HTTPException(404, "Dossier introuvable")
    return case


def _case_out(case: SocialAidCase) -> SocialAidCaseOut:
    beneficiary = getattr(case, "beneficiary", None)
    user = getattr(beneficiary, "user", None) if beneficiary else None
    return SocialAidCaseOut(
        id=case.id,
        association_id=case.association_id,
        beneficiary_membership_id=case.beneficiary_membership_id,
        beneficiary_name=getattr(user, "full_name", None),
        reference=case.reference,
        kind=case.kind.value if hasattr(case.kind, "value") else case.kind,
        status=case.status.value if hasattr(case.status, "value") else case.status,
        title=case.title,
        description=case.description,
        event_date=case.event_date,
        requested_on=case.requested_on,
        decided_on=case.decided_on,
        requested_amount=case.requested_amount,
        approved_amount=case.approved_amount,
        paid_amount=case.paid_amount,
        rejection_reason=case.rejection_reason,
        created_at=case.created_at,
    )


def _case_detail(case: SocialAidCase) -> SocialAidCaseDetail:
    base = _case_out(case).model_dump()
    return SocialAidCaseDetail(**base, payouts=sorted(case.payouts, key=lambda p: p.paid_on))


# ── Endpoints ───────────────────────────────────────────────────────────────
@router.get("", response_model=List[SocialAidCaseOut])
async def list_cases(
    association_id: UUID = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assoc = await _get_assoc_or_404(db, association_id)
    _check_access(current_user, assoc)

    stmt = (
        select(SocialAidCase)
        .options(selectinload(SocialAidCase.beneficiary).selectinload(Membership.user))
        .where(SocialAidCase.association_id == association_id)
        .order_by(SocialAidCase.created_at.desc())
    )
    if status_filter:
        stmt = stmt.where(SocialAidCase.status == SocialAidCaseStatus(status_filter))
    res = await db.execute(stmt)
    return [_case_out(c) for c in res.scalars().all()]


@router.get("/{case_id}", response_model=SocialAidCaseDetail)
async def get_case(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = await _load_case(db, case_id)
    assoc = await _get_assoc_or_404(db, case.association_id)
    _check_access(current_user, assoc)
    return _case_detail(case)


@router.post("", response_model=SocialAidCaseDetail, status_code=status.HTTP_201_CREATED)
async def declare_case(
    payload: SocialAidCaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Declare a social-aid case. The configured scale seeds `requested_amount`."""
    assoc = await _get_assoc_or_404(db, payload.association_id)
    _check_access(current_user, assoc)

    res = await db.execute(
        select(Membership).where(
            Membership.id == payload.beneficiary_membership_id,
            Membership.association_id == payload.association_id,
        )
    )
    if not res.scalar_one_or_none():
        raise HTTPException(422, "Bénéficiaire introuvable dans l'association")

    count_res = await db.execute(
        select(func.count(SocialAidCase.id)).where(
            SocialAidCase.association_id == payload.association_id
        )
    )
    seq = (count_res.scalar() or 0) + 1
    reference = f"AS-{date.today().year}-{seq:04d}"

    case = SocialAidCase(
        association_id=payload.association_id,
        beneficiary_membership_id=payload.beneficiary_membership_id,
        reference=reference,
        kind=SocialAidCaseKind(payload.kind),
        status=SocialAidCaseStatus.REQUESTED,
        title=payload.title,
        description=payload.description,
        event_date=payload.event_date,
        requested_on=date.today(),
        requested_amount=_scale_amount(assoc, payload.kind),
    )
    case.requested_by_id = current_user.id
    db.add(case)
    await db.commit()
    case = await _load_case(db, case.id)
    return _case_detail(case)


@router.post("/{case_id}/approve", response_model=SocialAidCaseDetail)
async def approve_case(
    case_id: UUID,
    payload: SocialAidApprove,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = await _load_case(db, case_id)
    assoc = await _get_assoc_or_404(db, case.association_id)
    _check_access(current_user, assoc)
    _require_admin(current_user)

    if case.status not in (SocialAidCaseStatus.REQUESTED, SocialAidCaseStatus.REVIEWING):
        raise HTTPException(409, "Le dossier ne peut plus être approuvé")

    amount = payload.approved_amount
    if amount is None:
        amount = _scale_amount(assoc, case.kind.value) or 0
    if amount <= 0:
        raise HTTPException(422, "Montant approuvé requis (aucun barème configuré pour ce type)")

    case.status = SocialAidCaseStatus.APPROVED
    case.approved_amount = amount
    case.decided_on = date.today()
    case.decided_by_id = current_user.id
    await db.commit()
    case = await _load_case(db, case_id)
    return _case_detail(case)


@router.post("/{case_id}/reject", response_model=SocialAidCaseDetail)
async def reject_case(
    case_id: UUID,
    payload: SocialAidReject,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = await _load_case(db, case_id)
    assoc = await _get_assoc_or_404(db, case.association_id)
    _check_access(current_user, assoc)
    _require_admin(current_user)

    if case.status in (SocialAidCaseStatus.PAID, SocialAidCaseStatus.REJECTED):
        raise HTTPException(409, "Le dossier ne peut plus être rejeté")

    case.status = SocialAidCaseStatus.REJECTED
    case.rejection_reason = payload.reason
    case.decided_on = date.today()
    case.decided_by_id = current_user.id
    await db.commit()
    case = await _load_case(db, case_id)
    return _case_detail(case)


@router.post("/{case_id}/payout", response_model=SocialAidCaseDetail)
async def payout_case(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pay out an approved case — OUT movement from the INSURANCE fund."""
    case = await _load_case(db, case_id)
    assoc = await _get_assoc_or_404(db, case.association_id)
    _check_access(current_user, assoc)
    _require_admin(current_user)

    if case.status != SocialAidCaseStatus.APPROVED:
        raise HTTPException(409, "Seul un dossier approuvé peut être décaissé")
    if case.approved_amount <= 0:
        raise HTTPException(422, "Montant approuvé invalide")

    treasury = await get_or_create_treasury(db, assoc)
    fund = next((f for f in treasury.funds if f.kind == FundKind.INSURANCE), None)
    if fund is None:
        raise HTTPException(500, "Fonds caisse sociale introuvable")

    movement = await post_movement(
        db,
        treasury=treasury,
        direction=MovementDirection.OUT,
        amount=case.approved_amount,
        allocations=[Allocation(fund=fund, is_credit=False, amount=case.approved_amount)],
        occurred_on=date.today(),
        source_type="aid_payout",
        source_id=case.id,
        recorded_by_id=current_user.id,
        related_membership_id=case.beneficiary_membership_id,
        description=f"Aide sociale {case.reference} — {case.title}",
        commit=False,
    )

    db.add(
        SocialAidPayout(
            case_id=case.id,
            paid_on=date.today(),
            amount=case.approved_amount,
            movement_id=movement.id,
        )
    )
    case.status = SocialAidCaseStatus.PAID
    case.paid_amount = case.approved_amount
    await db.commit()
    db.expire_all()  # drop stale collections so the reload sees the new payout
    case = await _load_case(db, case_id)
    return _case_detail(case)
