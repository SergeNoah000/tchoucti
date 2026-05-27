"""Social-aid endpoints — cases lifecycle: declare → approve/reject → payout.

A payout debits the INSURANCE fund (« Caisse sociale ») via FinanceService.
The aid amount defaults to the scale configured in
`association.config.social_fund.events[kind]`.
"""
from datetime import date, timedelta
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
from app.models.role import Membership
from app.models.social_aid import (
    AidType,
    SocialAidCase,
    SocialAidCaseKind,
    SocialAidCaseStatus,
    SocialAidPayout,
)
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


async def _source_fund_for(db: AsyncSession, case: SocialAidCase, treasury) -> Fund:
    """Resolve the fund that backs `case`'s payout — the caisse snapshotted at
    declare time, or the INSURANCE fund for legacy cases (no aid_type_id)."""
    if case.source_caisse_id is not None:
        res = await db.execute(
            select(Fund)
            .join(Caisse, Caisse.fund_id == Fund.id)
            .where(Caisse.id == case.source_caisse_id)
        )
        fund = res.scalar_one_or_none()
        if fund is None:
            raise HTTPException(500, "Caisse source du dossier introuvable.")
        return fund
    fund = next((f for f in treasury.funds if f.kind == FundKind.INSURANCE), None)
    if fund is None:
        raise HTTPException(500, "Fonds caisse sociale introuvable")
    return fund


def _case_out(case: SocialAidCase) -> SocialAidCaseOut:
    beneficiary = getattr(case, "beneficiary", None)
    user = getattr(beneficiary, "user", None) if beneficiary else None
    return SocialAidCaseOut(
        id=case.id,
        association_id=case.association_id,
        beneficiary_membership_id=case.beneficiary_membership_id,
        beneficiary_name=getattr(user, "full_name", None),
        aid_type_id=case.aid_type_id,
        source_caisse_id=case.source_caisse_id,
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

    # Block if aids are disabled at the association level.
    cfg_aids = (assoc.config or {}).get("aids") or {}
    if cfg_aids.get("enabled") is False:
        raise HTTPException(409, "Les aides sociales ne sont pas activées sur cette association.")

    res = await db.execute(
        select(Membership).where(
            Membership.id == payload.beneficiary_membership_id,
            Membership.association_id == payload.association_id,
        )
    )
    if not res.scalar_one_or_none():
        raise HTTPException(422, "Bénéficiaire introuvable dans l'association")

    # Phase 2e — résolution du AidType : valide délai + max claims/an,
    # snapshot la caisse source + le plafond.
    aid_type: AidType | None = None
    source_caisse_id: UUID | None = None
    requested_amount = _scale_amount(assoc, payload.kind)

    if payload.aid_type_id is not None:
        at_res = await db.execute(
            select(AidType).where(
                AidType.id == payload.aid_type_id,
                AidType.association_id == payload.association_id,
            )
        )
        aid_type = at_res.scalar_one_or_none()
        if not aid_type:
            raise HTTPException(422, "Type d'aide introuvable dans cette association.")
        if not aid_type.is_active:
            raise HTTPException(409, "Ce type d'aide est désactivé.")

        # Délai de déclaration (si event_date fourni).
        if payload.event_date and aid_type.declaration_delay_days > 0:
            cutoff = date.today() - timedelta(days=aid_type.declaration_delay_days)
            if payload.event_date < cutoff:
                raise HTTPException(
                    409,
                    f"Délai de déclaration dépassé ({aid_type.declaration_delay_days} jours après l'événement).",
                )

        # Max claims par membre par an (12 mois glissants).
        if aid_type.max_claims_per_member_per_year > 0:
            one_year_ago = date.today() - timedelta(days=365)
            year_res = await db.execute(
                select(func.count(SocialAidCase.id)).where(
                    SocialAidCase.beneficiary_membership_id == payload.beneficiary_membership_id,
                    SocialAidCase.aid_type_id == aid_type.id,
                    SocialAidCase.requested_on >= one_year_ago,
                    SocialAidCase.status != SocialAidCaseStatus.REJECTED,
                )
            )
            if (year_res.scalar() or 0) >= aid_type.max_claims_per_member_per_year:
                raise HTTPException(
                    409,
                    f"Limite annuelle atteinte ({aid_type.max_claims_per_member_per_year}) pour ce type d'aide.",
                )

        source_caisse_id = aid_type.source_caisse_id
        # Snapshot the requested amount on the ceiling (admin can adjust at approve time).
        if not requested_amount and aid_type.aid_ceiling_amount > 0:
            requested_amount = aid_type.aid_ceiling_amount

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
        aid_type_id=payload.aid_type_id,
        source_caisse_id=source_caisse_id,
        reference=reference,
        kind=SocialAidCaseKind(payload.kind),
        status=SocialAidCaseStatus.REQUESTED,
        title=payload.title,
        description=payload.description,
        event_date=payload.event_date,
        requested_on=date.today(),
        requested_amount=requested_amount,
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

    # Phase 2e — borne par le plafond du type si applicable.
    if case.aid_type_id is not None:
        at_res = await db.execute(select(AidType).where(AidType.id == case.aid_type_id))
        aid_type = at_res.scalar_one_or_none()
        if aid_type and aid_type.aid_ceiling_amount > 0 and amount > aid_type.aid_ceiling_amount:
            raise HTTPException(
                422,
                f"Montant {amount} > plafond du type ({aid_type.aid_ceiling_amount}).",
            )

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
    fund = await _source_fund_for(db, case, treasury)

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
