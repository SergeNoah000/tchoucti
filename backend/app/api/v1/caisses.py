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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import (
    _user_has_bureau_role,
    _user_is_association_admin,
    get_current_user,
    get_db,
    require_association_admin_for,
)
from app.models.notification import NotificationKind
from app.models.payout_request import PayoutKind, PayoutRequest
from app.models.association import Association
from app.models.caisse import (
    Caisse,
    CaisseCategory,
    CaisseContributorBalance,
    CaisseDistribution,
    CaisseDistributionShare,
    InterestDistribution,
    MemberCaisseBalance,
    WithdrawalMode,
)
from app.models.finance import MovementDirection
from app.services.finance import Allocation, get_or_create_treasury, post_movement
from app.models.finance import Fund, FundKind, Treasury
from app.models.loan import (
    Loan,
    LoanInstallment,
    LoanInstallmentStatus,
    LoanRepayment,
    LoanStatus,
)
from app.models.role import Membership, MembershipStatus
from app.models.user import User
from app.schemas.caisse import (
    CaisseContributorBalanceOut,
    CaisseCreate,
    CaisseDistributionOut,
    CaisseDistributionShareOut,
    CaisseOut,
    CaisseProjection,
    ContributorProjection,
    LoanProjection,
    MemberBalanceOut,
    ProjectionTimelineEntry,
    CaisseUpdate,
    CaisseWithdrawRequest,
    CaisseWithdrawResponse,
    MyShareItem,
)
from app.services.caisse_distribution import close_distribution_period
from app.services.meeting_agenda import upsert_caisse_activity
from app.services.notify import notify_users, treasurer_users_of
from app.services import payouts

router = APIRouter()


async def _check_access(db: AsyncSession, user: User, association_id: UUID) -> Association:
    res = await db.execute(select(Association).where(Association.id == association_id))
    assoc = res.scalar_one_or_none()
    if not assoc:
        raise HTTPException(404, "Association introuvable")
    if not user.is_super_admin and user.groupement_id != assoc.groupement_id:
        raise HTTPException(403, "Forbidden")
    return assoc


def _to_out(caisse: Caisse, fund_kind: str | None) -> CaisseOut:
    base = CaisseOut.model_validate(caisse)
    base.fund_kind = fund_kind
    return base


@router.get("", response_model=List[CaisseOut])
async def list_caisses(
    association_id: UUID = Query(...),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _check_access(db, current_user, association_id)
    stmt = (
        select(Caisse, Fund.kind)
        .join(Fund, Fund.id == Caisse.fund_id)
        .where(Caisse.association_id == association_id)
    )
    if not include_inactive:
        stmt = stmt.where(Caisse.is_active.is_(True))
    stmt = stmt.order_by(Caisse.is_system.desc(), Caisse.created_at)
    res = await db.execute(stmt)
    return [
        _to_out(c, k.value if hasattr(k, "value") else k) for c, k in res.all()
    ]


@router.get("/my-shares", response_model=List[MyShareItem])
async def my_shares(
    association_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Vue « mes parts » pour le membre courant : pour chaque caisse de
    l'association où il a un apport, son apport_cum + interest_cum + le total
    des apports pour calculer son % côté UI.

    NOTE : déclaré AVANT GET /{caisse_id} pour éviter que FastAPI interprète
    « my-shares » comme un UUID (sinon → 422)."""
    await _check_access(db, current_user, association_id)
    mem_res = await db.execute(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.association_id == association_id,
        )
    )
    membership = mem_res.scalar_one_or_none()
    if not membership:
        return []

    res = await db.execute(
        select(CaisseContributorBalance, Caisse).join(
            Caisse, Caisse.id == CaisseContributorBalance.caisse_id
        ).where(
            CaisseContributorBalance.membership_id == membership.id,
            Caisse.association_id == association_id,
        )
    )
    rows = res.all()
    if not rows:
        return []

    caisse_ids = [c.id for _b, c in rows]
    totals_res = await db.execute(
        select(
            CaisseContributorBalance.caisse_id,
            func.coalesce(func.sum(CaisseContributorBalance.apport_cum), 0),
        )
        .where(CaisseContributorBalance.caisse_id.in_(caisse_ids))
        .group_by(CaisseContributorBalance.caisse_id)
    )
    totals = {cid: int(s) for cid, s in totals_res.all()}

    return [
        MyShareItem(
            caisse_id=caisse.id,
            caisse_name=caisse.name,
            caisse_slug=caisse.slug,
            category=(caisse.category.value if hasattr(caisse.category, "value") else str(caisse.category)),
            interest_distribution=caisse.interest_distribution,
            apport_cum=bal.apport_cum,
            interest_cum=bal.interest_cum,
            total_apport=totals.get(caisse.id, 0),
            last_distribution_at=caisse.last_distribution_at,
        )
        for bal, caisse in rows
    ]


@router.get("/{caisse_id}", response_model=CaisseOut)
async def get_caisse(
    caisse_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    res = await db.execute(
        select(Caisse, Fund.kind)
        .join(Fund, Fund.id == Caisse.fund_id)
        .where(Caisse.id == caisse_id)
    )
    row = res.first()
    if not row:
        raise HTTPException(404, "Caisse introuvable")
    caisse, kind = row
    await _check_access(db, current_user, caisse.association_id)
    return _to_out(caisse, kind.value if hasattr(kind, "value") else kind)


@router.get("/{caisse_id}/projections", response_model=CaisseProjection)
async def caisse_projections(
    caisse_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pronostics de la caisse : pour chaque prêt financé par la caisse,
    intérêts DÉJÀ ENCAISSÉS et intérêts À VENIR (échéancier par date, jusqu'à la
    fin des remboursements), et la QUOTE-PART de chaque contributeur au prorata
    de son apport. Visible par TOUS les membres (répartition comprise)."""
    cres = await db.execute(select(Caisse).where(Caisse.id == caisse_id))
    caisse = cres.scalar_one_or_none()
    if not caisse:
        raise HTTPException(404, "Caisse introuvable")
    assoc = await _check_access(db, current_user, caisse.association_id)
    is_admin = (
        current_user.is_super_admin
        or current_user.is_groupement_admin
        or await _user_is_association_admin(db, current_user, caisse.association_id)
    )

    # ── Prêts financés par cette caisse, DÉCAISSÉS (en activité) ──
    loans = (
        await db.execute(
            select(Loan)
            .options(
                selectinload(Loan.installments),
                selectinload(Loan.repayments),
                selectinload(Loan.borrower).selectinload(Membership.user),
            )
            .where(
                Loan.source_caisse_id == caisse_id,
                Loan.status.in_([LoanStatus.DISBURSED, LoanStatus.REPAYING, LoanStatus.PAID]),
            )
            .order_by(Loan.created_at.desc())
        )
    ).scalars().all()

    loan_projs: list[LoanProjection] = []
    total_collected = 0
    total_upcoming = 0
    total_principal = 0
    # Échéancier consolidé de la caisse : (date, collected) → intérêt cumulé.
    timeline_agg: dict[tuple, int] = {}

    for loan in loans:
        sched: list[ProjectionTimelineEntry] = []
        # 1) Intérêts DÉJÀ ENCAISSÉS — par date de remboursement.
        collected = 0
        for rp in sorted(loan.repayments, key=lambda r: r.paid_on):
            interest = getattr(rp, "interest", 0) or 0
            if interest > 0:
                collected += interest
                sched.append(ProjectionTimelineEntry(due_on=rp.paid_on, interest=interest, collected=True))
                timeline_agg[(rp.paid_on, True)] = timeline_agg.get((rp.paid_on, True), 0) + interest
        # 2) Intérêts À VENIR — échéances non payées, bornés au reste théorique
        #    (évite les artefacts d'arrondi : Σ = total_interest − déjà payé).
        remaining = max(0, loan.total_interest - loan.paid_interest)
        upcoming = 0
        for inst in sorted(loan.installments, key=lambda i: i.number):
            if remaining <= 0:
                break
            if inst.status in (LoanInstallmentStatus.PAID, LoanInstallmentStatus.WAIVED):
                continue
            part = inst.interest_part - inst.paid_interest
            part = max(0, min(part, remaining))
            if part <= 0:
                continue
            upcoming += part
            remaining -= part
            sched.append(ProjectionTimelineEntry(due_on=inst.due_on, interest=part, collected=False))
            timeline_agg[(inst.due_on, False)] = timeline_agg.get((inst.due_on, False), 0) + part

        rentability = (loan.total_interest / loan.principal * 100.0) if loan.principal else 0.0
        borrower = getattr(loan, "borrower", None)
        buser = getattr(borrower, "user", None) if borrower else None
        loan_projs.append(
            LoanProjection(
                loan_id=loan.id,
                reference=loan.reference,
                borrower_name=getattr(buser, "full_name", None),
                principal=loan.principal,
                total_interest=loan.total_interest,
                rentability_pct=round(rentability, 2),
                interest_collected=collected,
                interest_upcoming=upcoming,
                schedule=sched,
            )
        )
        total_collected += collected
        total_upcoming += upcoming
        if loan.status != LoanStatus.PAID:
            total_principal += loan.principal

    timeline = [
        ProjectionTimelineEntry(due_on=d, interest=amt, collected=coll)
        for (d, coll), amt in sorted(timeline_agg.items(), key=lambda kv: (kv[0][0], kv[0][1]))
    ]

    # ── Contributeurs : quote-part au prorata de l'apport (TOUJOURS calculée,
    #    quel que soit le mode ; visible par tous). ──
    balances = (
        await db.execute(
            select(CaisseContributorBalance)
            .options(
                selectinload(CaisseContributorBalance.membership).selectinload(
                    Membership.user
                )
            )
            .where(CaisseContributorBalance.caisse_id == caisse_id)
            .order_by(CaisseContributorBalance.created_at)
        )
    ).scalars().all()
    total_apport = sum(b.apport_cum for b in balances)
    apports = [b.apport_cum for b in balances]

    def _split(total: int) -> list[int]:
        """Répartit `total` au prorata des apports, méthode du plus grand reste
        (les parts somment EXACTEMENT au total, pas de perte d'arrondi)."""
        S = sum(apports)
        if S <= 0 or total <= 0:
            return [0] * len(apports)
        raw = [total * a / S for a in apports]
        floors = [int(x) for x in raw]
        rem = total - sum(floors)
        order = sorted(range(len(apports)), key=lambda i: raw[i] - floors[i], reverse=True)
        for k in range(rem):
            floors[order[k]] += 1
        return floors

    coll_shares = _split(total_collected)
    up_shares = _split(total_upcoming)

    contributors: list[ContributorProjection] = []
    for i, bal in enumerate(balances):
        weight = (bal.apport_cum / total_apport) if total_apport else 0.0
        mem = getattr(bal, "membership", None)
        muser = getattr(mem, "user", None) if mem else None
        contributors.append(
            ContributorProjection(
                membership_id=bal.membership_id,
                member_name=getattr(muser, "full_name", None),
                apport_cum=bal.apport_cum,
                weight_pct=round(weight * 100.0, 2),
                interest_collected_share=coll_shares[i],
                interest_upcoming_share=up_shares[i],
            )
        )

    my_membership = (
        await db.execute(
            select(Membership).where(
                Membership.user_id == current_user.id,
                Membership.association_id == caisse.association_id,
            )
        )
    ).scalar_one_or_none()
    my_proj = None
    if my_membership is not None:
        my_proj = next(
            (c for c in contributors if c.membership_id == my_membership.id), None
        )

    idist = (
        caisse.interest_distribution.value
        if hasattr(caisse.interest_distribution, "value")
        else str(caisse.interest_distribution)
    )
    return CaisseProjection(
        caisse_id=caisse.id,
        caisse_name=caisse.name,
        currency=assoc.currency,
        interest_distribution=idist,
        total_principal_active=total_principal,
        total_interest_collected=total_collected,
        total_interest_upcoming=total_upcoming,
        total_apport=total_apport,
        loans=loan_projs,
        timeline=timeline,
        contributors=contributors,
        my=my_proj,
        is_admin_view=is_admin,
    )


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
        member_min_balance=payload.member_min_balance,
        has_ceiling=payload.has_ceiling,
        ceiling_amount=payload.ceiling_amount,
        has_objective=payload.has_objective,
        objective_amount=payload.objective_amount,
        objective_deadline=payload.objective_deadline,
        interest_distribution=payload.interest_distribution.value,
        distribution_period=payload.distribution_period.value,
        withdrawal_mode=payload.withdrawal_mode.value,
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


# ── Phase 7 (Fred) ──────────────────────────────────────────────────────────

from datetime import date as _date  # local pour ne pas polluer le haut
from sqlalchemy.orm import selectinload  # local pour le chargement des shares


@router.get("/{caisse_id}/contributors", response_model=List[CaisseContributorBalanceOut])
async def list_contributors(
    caisse_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sous-soldes (apport_cum, interest_cum) par cotisant d'une caisse.
    Accessible à toute personne ayant accès à l'association."""
    cres = await db.execute(select(Caisse).where(Caisse.id == caisse_id))
    caisse = cres.scalar_one_or_none()
    if not caisse:
        raise HTTPException(404, "Caisse introuvable")
    await _check_access(db, current_user, caisse.association_id)

    res = await db.execute(
        select(CaisseContributorBalance, Membership)
        .join(Membership, Membership.id == CaisseContributorBalance.membership_id)
        .options(selectinload(Membership.user))
        .where(CaisseContributorBalance.caisse_id == caisse_id)
        .order_by(CaisseContributorBalance.created_at.asc())
    )
    out: List[CaisseContributorBalanceOut] = []
    for bal, mem in res.all():
        out.append(
            CaisseContributorBalanceOut(
                membership_id=bal.membership_id,
                member_name=mem.user.full_name if mem and mem.user else None,
                apport_cum=bal.apport_cum,
                apport_cum_at_period_start=bal.apport_cum_at_period_start,
                interest_cum=bal.interest_cum,
            )
        )
    return out


@router.get("/{caisse_id}/member-balances", response_model=List[MemberBalanceOut])
async def list_member_balances(
    caisse_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Solde de CHAQUE membre actif dans une caisse + drapeau « zone rouge »
    (solde < objectif minimum par membre). Vaut pour TOUS les types de caisses :
    - PERSONAL : solde individuel (MemberCaisseBalance) ;
    - autres   : cotisation cumulée du membre (CaisseContributorBalance.apport_cum).
    Tous les membres actifs sont listés, même sans solde."""
    cres = await db.execute(select(Caisse).where(Caisse.id == caisse_id))
    caisse = cres.scalar_one_or_none()
    if not caisse:
        raise HTTPException(404, "Caisse introuvable")
    await _check_access(db, current_user, caisse.association_id)

    if caisse.category == CaisseCategory.PERSONAL:
        bal_res = await db.execute(
            select(MemberCaisseBalance.membership_id, MemberCaisseBalance.balance).where(
                MemberCaisseBalance.caisse_id == caisse_id
            )
        )
    else:
        bal_res = await db.execute(
            select(
                CaisseContributorBalance.membership_id,
                CaisseContributorBalance.apport_cum,
            ).where(CaisseContributorBalance.caisse_id == caisse_id)
        )
    balances = {mid: bal for mid, bal in bal_res.all()}

    mem_res = await db.execute(
        select(Membership)
        .options(selectinload(Membership.user))
        .where(
            Membership.association_id == caisse.association_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    )
    mn = caisse.member_min_balance or 0
    out: List[MemberBalanceOut] = []
    for mem in mem_res.scalars().all():
        bal = int(balances.get(mem.id, 0))
        out.append(
            MemberBalanceOut(
                membership_id=mem.id,
                member_name=mem.user.full_name if mem.user else None,
                balance=bal,
                min_balance=mn,
                below_min=mn > 0 and bal < mn,
            )
        )
    out.sort(key=lambda x: (not x.below_min, x.member_name or ""))
    return out


@router.get("/{caisse_id}/distributions", response_model=List[CaisseDistributionOut])
async def list_distributions(
    caisse_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Historique des distributions d'intérêts sur une caisse (mode partagé)."""
    cres = await db.execute(select(Caisse).where(Caisse.id == caisse_id))
    caisse = cres.scalar_one_or_none()
    if not caisse:
        raise HTTPException(404, "Caisse introuvable")
    await _check_access(db, current_user, caisse.association_id)

    res = await db.execute(
        select(CaisseDistribution)
        .options(
            selectinload(CaisseDistribution.shares)
            .selectinload(CaisseDistributionShare.membership)
            .selectinload(Membership.user)
        )
        .where(CaisseDistribution.caisse_id == caisse_id)
        .order_by(CaisseDistribution.closed_at.desc())
    )
    out: List[CaisseDistributionOut] = []
    for dist in res.scalars().all():
        shares = []
        for s in dist.shares:
            name = None
            if s.membership and s.membership.user:
                name = s.membership.user.full_name
            shares.append(
                CaisseDistributionShareOut(
                    membership_id=s.membership_id,
                    member_name=name,
                    base=s.base,
                    share_amount=s.share_amount,
                )
            )
        out.append(
            CaisseDistributionOut(
                id=dist.id,
                caisse_id=dist.caisse_id,
                period_start=dist.period_start,
                period_end=dist.period_end,
                period_label=dist.period_label,
                interest_pool=dist.interest_pool,
                total_base=dist.total_base,
                closed_at=dist.closed_at,
                closed_by_id=dist.closed_by_id,
                shares=shares,
            )
        )
    return out


@router.post("/{caisse_id}/close-distribution", response_model=CaisseDistributionOut)
async def close_distribution(
    caisse_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clôture manuelle de la période courante d'une caisse en mode SHARED_PRO_RATA :
    calcule l'intérêt encaissé sur la période et redistribue au prorata."""
    cres = await db.execute(select(Caisse).where(Caisse.id == caisse_id))
    caisse = cres.scalar_one_or_none()
    if not caisse:
        raise HTTPException(404, "Caisse introuvable")
    await _check_access(db, current_user, caisse.association_id)
    if not (current_user.is_super_admin or current_user.is_groupement_admin):
        from app.api.deps import _user_is_association_admin
        if not await _user_is_association_admin(db, current_user, caisse.association_id):
            raise HTTPException(403, "Réservé à l'admin de cette association")

    if caisse.interest_distribution != InterestDistribution.SHARED_PRO_RATA.value:
        raise HTTPException(409, "La caisse n'est pas en mode rendement partagé.")

    dist = await close_distribution_period(
        db,
        caisse=caisse,
        period_end=_date.today(),
        closed_by=current_user,
    )
    await db.commit()

    # Recharger pour les shares avec nom
    res = await db.execute(
        select(CaisseDistribution)
        .options(
            selectinload(CaisseDistribution.shares)
            .selectinload(CaisseDistributionShare.membership)
            .selectinload(Membership.user)
        )
        .where(CaisseDistribution.id == dist.id)
    )
    dist = res.scalar_one()
    shares = []
    for s in dist.shares:
        name = None
        if s.membership and s.membership.user:
            name = s.membership.user.full_name
        shares.append(
            CaisseDistributionShareOut(
                membership_id=s.membership_id,
                member_name=name,
                base=s.base,
                share_amount=s.share_amount,
            )
        )
    return CaisseDistributionOut(
        id=dist.id,
        caisse_id=dist.caisse_id,
        period_start=dist.period_start,
        period_end=dist.period_end,
        period_label=dist.period_label,
        interest_pool=dist.interest_pool,
        total_base=dist.total_base,
        closed_at=dist.closed_at,
        closed_by_id=dist.closed_by_id,
        shares=shares,
    )


@router.post("/{caisse_id}/withdraw", response_model=CaisseWithdrawResponse)
async def withdraw(
    caisse_id: UUID,
    payload: CaisseWithdrawRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrait d'apport d'un cotisant selon le `withdrawal_mode` de la caisse :
    - `never`              : refusé.
    - `anytime_if_liquid`  : autorisé tant que fund.balance ≥ montant ET
                             apport_cum ≥ montant.
    - `end_of_period_only` : autorisé uniquement si aucun nouvel apport
                             depuis la dernière distribution
                             (apport_cum_at_period_start == apport_cum) ET
                             last_distribution_at non null.

    Les `interest_cum` ne sont jamais retirables (rendement « papier »)."""
    cres = await db.execute(select(Caisse).where(Caisse.id == caisse_id))
    caisse = cres.scalar_one_or_none()
    if not caisse:
        raise HTTPException(404, "Caisse introuvable")
    assoc = await _check_access(db, current_user, caisse.association_id)

    # Auth : un membre retire pour lui-même ; un admin peut retirer pour un autre.
    mem_res = await db.execute(
        select(Membership).where(
            Membership.id == payload.membership_id,
            Membership.association_id == caisse.association_id,
        )
    )
    membership = mem_res.scalar_one_or_none()
    if not membership:
        raise HTTPException(422, "Membre introuvable dans cette association")
    is_admin = current_user.is_super_admin or current_user.is_groupement_admin
    if not is_admin:
        from app.api.deps import _user_is_association_admin
        is_admin = await _user_is_association_admin(db, current_user, caisse.association_id)
    if not is_admin and membership.user_id != current_user.id:
        raise HTTPException(403, "Vous ne pouvez retirer que vos propres apports.")

    # Mode
    if caisse.withdrawal_mode == WithdrawalMode.NEVER.value:
        raise HTTPException(409, "Cette caisse n'autorise pas les retraits.")

    # Solde cotisant
    bal_res = await db.execute(
        select(CaisseContributorBalance).where(
            CaisseContributorBalance.caisse_id == caisse.id,
            CaisseContributorBalance.membership_id == payload.membership_id,
        )
    )
    bal = bal_res.scalar_one_or_none()
    if bal is None or bal.apport_cum < payload.amount:
        raise HTTPException(409, "Apport cumulé insuffisant pour ce retrait.")

    # Mode end_of_period_only
    if caisse.withdrawal_mode == WithdrawalMode.END_OF_PERIOD_ONLY.value:
        if caisse.last_distribution_at is None:
            raise HTTPException(409, "Aucune période clôturée — retrait non disponible.")
        if bal.apport_cum_at_period_start != bal.apport_cum:
            raise HTTPException(
                409,
                "Retrait possible uniquement en fin de période, avant tout nouvel apport.",
            )

    # Liquidité (pour les deux modes autorisés)
    fund_res = await db.execute(select(Fund).where(Fund.id == caisse.fund_id))
    fund = fund_res.scalar_one_or_none()
    if not fund or fund.balance < payload.amount:
        raise HTTPException(409, "Solde de la caisse insuffisant pour ce retrait.")

    # PRÉPARE la sortie : aucun argent ne bouge tant que le trésorier n'a pas
    # validé. On enregistre le contexte nécessaire à la finalisation.
    await payouts.create_request(
        db,
        association_id=assoc.id,
        kind=PayoutKind.CAISSE_WITHDRAWAL,
        source_type="caisse_withdrawal",
        source_id=caisse.id,
        amount=payload.amount,
        fund_id=fund.id,
        related_membership_id=membership.id,
        description=payload.note or f"Retrait apport — {caisse.name}",
        prepared_by_id=current_user.id,
        enforce_unique=False,  # plusieurs retraits d'une même caisse coexistent
        commit=False,
    )
    validators = await treasurer_users_of(db, assoc.id)
    await notify_users(
        db,
        users=validators,
        kind=NotificationKind.WARNING,
        title="Retrait de caisse à valider",
        body=f"Un retrait de {payload.amount} {assoc.currency} "
        f"(caisse {caisse.name}) attend votre validation.",
        action_url="/dashboard/finance/validations",
        association_id=assoc.id,
    )
    await db.commit()
    return CaisseWithdrawResponse(
        movement_id=None,
        amount=payload.amount,
        apport_cum_after=bal.apport_cum,
        fund_balance_after=fund.balance,
        pending=True,
    )


async def complete_caisse_withdrawal(
    db: AsyncSession, request: PayoutRequest, current_user: User
):
    """Finalise un retrait de caisse validé : sort l'argent + décrémente l'apport
    cumulé du cotisant. Appelé par le routeur de validation (payouts)."""
    cres = await db.execute(select(Caisse).where(Caisse.id == request.source_id))
    caisse = cres.scalar_one_or_none()
    if not caisse:
        raise HTTPException(404, "Caisse introuvable")
    assoc = await _check_access(db, current_user, caisse.association_id)

    amount = request.amount
    bal_res = await db.execute(
        select(CaisseContributorBalance).where(
            CaisseContributorBalance.caisse_id == caisse.id,
            CaisseContributorBalance.membership_id == request.related_membership_id,
        )
    )
    bal = bal_res.scalar_one_or_none()
    if bal is None or bal.apport_cum < amount:
        raise HTTPException(409, "Apport cumulé insuffisant pour ce retrait.")

    fund_res = await db.execute(select(Fund).where(Fund.id == caisse.fund_id))
    fund = fund_res.scalar_one_or_none()
    if not fund or fund.balance < amount:
        raise HTTPException(409, "Solde de la caisse insuffisant pour ce retrait.")

    treasury = await get_or_create_treasury(db, assoc)
    movement = await post_movement(
        db,
        treasury=treasury,
        direction=MovementDirection.OUT,
        amount=amount,
        allocations=[Allocation(fund=fund, is_credit=False, amount=amount)],
        occurred_on=_date.today(),
        source_type="caisse_withdrawal",
        source_id=caisse.id,
        recorded_by_id=current_user.id,
        related_membership_id=request.related_membership_id,
        description=request.description or f"Retrait apport — {caisse.name}",
        commit=False,
    )
    bal.apport_cum -= amount
    bal.apport_cum_at_period_start = max(0, bal.apport_cum_at_period_start - amount)
    return movement


