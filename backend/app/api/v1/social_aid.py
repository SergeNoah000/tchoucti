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

from slugify import slugify

from app.api.deps import get_current_user, get_db
from app.models.association import Association
from app.models.caisse import Caisse, CaisseCategory
from app.models.finance import Fund, FundKind, MovementDirection
from app.models.role import Membership, MembershipRole, MembershipStatus, Role
from app.models.social_aid import (
    AidType,
    SocialAidCase,
    SocialAidCaseKind,
    SocialAidCaseStatus,
    SocialAidPayout,
)
from app.models.user import User
from app.schemas.social_aid import (
    AidContributionOut,
    SocialAidApprove,
    SocialAidCaseCreate,
    SocialAidCaseDetail,
    SocialAidCaseOut,
    SocialAidReject,
)
from app.models.meeting import (
    Activity,
    EntryStatus,
    Meeting,
    MeetingActivityEntry,
)
from app.services.finance import Allocation, get_or_create_treasury, post_movement
from app.services.meeting_agenda import upsert_caisse_activity

router = APIRouter()


async def _open_beneficiary_caisse(
    db: AsyncSession,
    *,
    assoc: Association,
    case: SocialAidCase,
    aid_type: AidType,
) -> Caisse:
    """Ouvre une caisse temporaire dédiée au bénéficiaire d'une demande d'aide
    (mode `auto_create_caisse`). Elle collecte les cotisations et finance le
    versement de CETTE demande. Reliée au dossier via `case.source_caisse_id`."""
    treasury = await get_or_create_treasury(db, assoc)
    beneficiary_name = (
        getattr(getattr(case.beneficiary, "user", None), "full_name", None) or "bénéficiaire"
    )
    base_slug = slugify(f"aide-{case.reference}")[:90] or f"aide-{case.id.hex[:8]}"

    fund = Fund(
        treasury_id=treasury.id,
        kind=FundKind.CUSTOM,
        ref_key=base_slug,
        name=f"Aide — {beneficiary_name} ({case.reference})",
        description=f"Caisse temporaire pour l'aide {case.reference}.",
        is_system=False,
    )
    db.add(fund)
    await db.flush()

    caisse = Caisse(
        association_id=assoc.id,
        fund_id=fund.id,
        name=f"Aide — {beneficiary_name} ({case.reference})",
        slug=base_slug,
        description="Caisse ouverte automatiquement à l'approbation de la demande d'aide.",
        category=CaisseCategory.COLLECTIVE,
        is_system=False,
        is_recurring=aid_type.is_contribution_recurring,
        recurring_amount=aid_type.member_contribution_amount,
    )
    db.add(caisse)
    await db.flush()

    # Si cotisation récurrente : la caisse apparaît dans les séances pour collecter.
    if aid_type.is_contribution_recurring and aid_type.member_contribution_amount > 0:
        await upsert_caisse_activity(
            db,
            association_id=assoc.id,
            caisse_id=caisse.id,
            name=caisse.name,
            slug=caisse.slug,
            is_recurring=True,
            recurring_amount=aid_type.member_contribution_amount,
            is_member_required=False,
            member_required_amount=0,
        )

    case.source_caisse_id = caisse.id
    return caisse


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


# Phase 5 — placed BEFORE /{case_id} so FastAPI doesn't try to parse
# "contributions" as a UUID. The full implementation lives at the bottom
# of the file ; this is just the route declaration shim that calls it.
@router.get("/contributions", response_model=List[AidContributionOut])
async def list_contributions_route(
    association_id: UUID = Query(...),
    membership_id: UUID | None = Query(None),
    aid_type_id: UUID | None = Query(None),
    since: Optional[date] = Query(None),
    until: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _list_contributions_impl(
        association_id=association_id,
        membership_id=membership_id,
        aid_type_id=aid_type_id,
        since=since,
        until=until,
        db=db,
        current_user=current_user,
    )


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

    # Phase 3b — make the matching Activity visible in séances so members
    # can contribute. Recurring types stay visible until the case is paid ;
    # non-recurring types are one-shot (collected at approval, hidden again
    # immediately to avoid double-charging).
    if case.aid_type_id is not None:
        at_res = await db.execute(select(AidType).where(AidType.id == case.aid_type_id))
        aid_type = at_res.scalar_one_or_none()
        if aid_type:
            # Caisse temporaire : ouvre une caisse dédiée au bénéficiaire à
            # l'approbation (la collecte/versement passe par CETTE caisse).
            if aid_type.auto_create_caisse and case.source_caisse_id is None:
                await _open_beneficiary_caisse(db, assoc=assoc, case=case, aid_type=aid_type)
            else:
                code = f"aid-{aid_type.slug}"
                act_res = await db.execute(
                    select(Activity).where(
                        Activity.association_id == assoc.id, Activity.code == code
                    )
                )
                act = act_res.scalar_one_or_none()
                if act and aid_type.is_contribution_recurring:
                    act.is_visible_in_meeting = True

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

    # Phase 3b — if no other APPROVED case of this type remains, hide the
    # Activity again so it stops appearing on séances.
    if case.aid_type_id is not None:
        other_open = await db.execute(
            select(SocialAidCase.id).where(
                SocialAidCase.aid_type_id == case.aid_type_id,
                SocialAidCase.id != case.id,
                SocialAidCase.status == SocialAidCaseStatus.APPROVED,
            ).limit(1)
        )
        if other_open.first() is None:
            at_res = await db.execute(select(AidType).where(AidType.id == case.aid_type_id))
            aid_type = at_res.scalar_one_or_none()
            if aid_type:
                code = f"aid-{aid_type.slug}"
                act_res = await db.execute(
                    select(Activity).where(
                        Activity.association_id == assoc.id, Activity.code == code
                    )
                )
                act = act_res.scalar_one_or_none()
                if act:
                    act.is_visible_in_meeting = False

    await db.commit()
    db.expire_all()  # drop stale collections so the reload sees the new payout
    case = await _load_case(db, case_id)
    return _case_detail(case)


# ── Phase 5 — historique des cotisations d'aides sociales ──────────────────


async def _resolve_membership_filter(
    db: AsyncSession,
    user: User,
    assoc: Association,
    requested: UUID | None,
) -> UUID | None:
    """Compute the effective membership_id filter for /contributions.

    - Plain members (has_bureau_role=False) : always limited to their own
      membership_id ; any `requested` other than theirs → 403.
    - Bureau / admin : pass `requested` through, or None (= all members).
    """
    if user.is_super_admin or user.is_groupement_admin:
        return requested

    # Find the user's own membership in this asso, if any.
    own_res = await db.execute(
        select(Membership.id)
        .join(MembershipRole, MembershipRole.membership_id == Membership.id)
        .join(Role, Role.id == MembershipRole.role_id)
        .where(
            Membership.user_id == user.id,
            Membership.association_id == assoc.id,
            Membership.status == MembershipStatus.ACTIVE,
        )
        .limit(1)
    )
    own_id = own_res.scalar_one_or_none()
    if own_id is None:
        # Not a member of this asso — let _check_access handle the 403.
        return requested

    # Has bureau (anything other than plain "member") ?
    bureau_res = await db.execute(
        select(Role.code)
        .join(MembershipRole, MembershipRole.role_id == Role.id)
        .where(MembershipRole.membership_id == own_id, Role.code != "member")
        .limit(1)
    )
    is_bureau = bureau_res.first() is not None
    if is_bureau:
        return requested

    # Plain member — force scope to themselves.
    if requested is not None and requested != own_id:
        raise HTTPException(403, "Vous ne pouvez consulter que votre propre historique.")
    return own_id


async def _list_contributions_impl(
    *,
    association_id: UUID,
    membership_id: UUID | None,
    aid_type_id: UUID | None,
    since: Optional[date],
    until: Optional[date],
    db: AsyncSession,
    current_user: User,
):
    """Historique des cotisations d'aides sociales d'un membre ou de tous.

    - Bureau (trésorier, secrétaire, admin) : voit toutes les cotisations,
      filtrable par membre + type + période.
    - Membre simple : limité à `membership_id = sa propre membership`.
    """
    assoc = await _get_assoc_or_404(db, association_id)
    _check_access(current_user, assoc)
    effective_member = await _resolve_membership_filter(db, current_user, assoc, membership_id)

    # Join entries → activities (with aid_type_id in config) → meetings + memberships.
    stmt = (
        select(
            MeetingActivityEntry,
            Meeting,
            Activity,
            Membership,
        )
        .join(Activity, Activity.id == MeetingActivityEntry.activity_id)
        .join(Meeting, Meeting.id == MeetingActivityEntry.meeting_id)
        .join(Membership, Membership.id == MeetingActivityEntry.membership_id)
        .options(selectinload(Membership.user))
        .where(
            Meeting.association_id == assoc.id,
            Activity.code.like("aid-%"),
            MeetingActivityEntry.status != EntryStatus.VOIDED,
        )
        .order_by(Meeting.scheduled_on.desc())
    )
    if effective_member is not None:
        stmt = stmt.where(MeetingActivityEntry.membership_id == effective_member)
    if since is not None:
        stmt = stmt.where(Meeting.scheduled_on >= since)
    if until is not None:
        stmt = stmt.where(Meeting.scheduled_on <= until)

    res = await db.execute(stmt)
    rows = list(res.all())

    if not rows:
        return []

    # Resolve aid type names from activity.config.aid_type_id.
    aid_type_ids: set[UUID] = set()
    for entry, _m, act, _mb in rows:
        cfg = act.config or {}
        aid_id_raw = cfg.get("aid_type_id")
        if aid_id_raw:
            try:
                aid_type_ids.add(UUID(aid_id_raw))
            except (ValueError, TypeError):
                pass
    aid_type_names: dict[UUID, tuple[UUID, str]] = {}
    if aid_type_ids:
        at_res = await db.execute(
            select(AidType.id, AidType.name).where(AidType.id.in_(aid_type_ids))
        )
        aid_type_names = {aid_id: (aid_id, name) for aid_id, name in at_res.all()}

    out: list[AidContributionOut] = []
    for entry, meeting, act, mb in rows:
        cfg = act.config or {}
        atid = None
        atname = None
        aid_id_raw = cfg.get("aid_type_id")
        if aid_id_raw:
            try:
                atid = UUID(aid_id_raw)
                _key, atname = aid_type_names.get(atid, (None, None))
            except (ValueError, TypeError):
                pass
        if aid_type_id is not None and atid != aid_type_id:
            continue  # post-filter by aid type
        u = getattr(mb, "user", None)
        out.append(
            AidContributionOut(
                entry_id=entry.id,
                meeting_id=meeting.id,
                meeting_title=meeting.title,
                meeting_date=meeting.scheduled_on,
                membership_id=mb.id,
                member_name=getattr(u, "full_name", None),
                aid_type_id=atid,
                aid_type_name=atname,
                amount=entry.amount,
                status=entry.status.value if hasattr(entry.status, "value") else entry.status,
            )
        )
    return out
