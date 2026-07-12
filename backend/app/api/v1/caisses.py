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
from app.models.finance import LedgerEntry, MovementDirection, TreasuryMovement
from app.services.finance import Allocation, get_or_create_treasury, post_movement
from app.models.finance import Fund, FundKind, Treasury
from app.models.loan import (
    Loan,
    LoanInstallment,
    LoanInstallmentStatus,
    LoanRepayment,
    LoanStatus,
    LoanType,
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
    LoanContributorShare,
    LoanDetailProjection,
    LoanScheduleEntry,
    MemberBalanceOut,
    MyFinanceCard,
    MyFinanceNotification,
    MyFinances,
    MyVersement,
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


@router.get("/my-finances", response_model=MyFinances)
async def my_finances(
    association_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """« Mes Finances » du membre courant : apport + rendement par caisse,
    historique de mes versements avec le RENDEMENT attribué à chacun (modèle de
    Fred : rentabilité par unité d'argent disponible × mon montant présent lors
    de chaque prêt), et notifications (ex. assurance en dessous du minimum).

    NOTE : déclaré AVANT GET /{caisse_id} (sinon « my-finances » lu comme UUID)."""
    assoc = await _check_access(db, current_user, association_id)
    membership = (
        await db.execute(
            select(Membership).where(
                Membership.user_id == current_user.id,
                Membership.association_id == association_id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        return MyFinances(currency=assoc.currency)
    my_mid = membership.id

    # Caisses non-système de l'association (fonds → caisse).
    caisses = (
        await db.execute(
            select(Caisse).where(
                Caisse.association_id == association_id,
                Caisse.is_system.is_(False),
            )
        )
    ).scalars().all()
    if not caisses:
        return MyFinances(currency=assoc.currency)
    fund_to_caisse = {c.fund_id: c for c in caisses if c.fund_id}
    caisse_ids = [c.id for c in caisses]

    # Versements (crédits) de TOUS les membres vers les fonds de caisse, datés.
    contrib_rows = (
        await db.execute(
            select(
                LedgerEntry.fund_id,
                TreasuryMovement.related_membership_id,
                LedgerEntry.amount,
                TreasuryMovement.occurred_on,
            )
            .join(TreasuryMovement, TreasuryMovement.id == LedgerEntry.movement_id)
            .join(Treasury, Treasury.id == TreasuryMovement.treasury_id)
            .where(
                Treasury.association_id == association_id,
                LedgerEntry.fund_id.in_(list(fund_to_caisse.keys())),
                LedgerEntry.is_credit.is_(True),
                TreasuryMovement.direction == MovementDirection.IN,
                TreasuryMovement.is_voided.is_(False),
            )
        )
    ).all()

    # Regroupe les contributions par caisse (toutes) et prépare l'apport cumulé
    # dans le temps (pour connaître « l'argent disponible » à chaque date).
    from collections import defaultdict

    per_caisse_contribs: dict = defaultdict(list)  # caisse_id → [(date, amount, membership_id)]
    for fund_id, mid, amount, occ in contrib_rows:
        c = fund_to_caisse.get(fund_id)
        if c is None or occ is None or not amount:
            continue
        per_caisse_contribs[c.id].append((occ, int(amount), mid))

    # Prêts financés par chaque caisse (décaissés), avec date + intérêt total.
    loans = (
        await db.execute(
            select(Loan).where(
                Loan.source_caisse_id.in_(caisse_ids),
                Loan.status.in_(
                    [LoanStatus.DISBURSED, LoanStatus.REPAYING, LoanStatus.PAID]
                ),
                Loan.disbursed_on.isnot(None),
            )
        )
    ).scalars().all()
    per_caisse_loans: dict = defaultdict(list)  # caisse_id → [(disbursed_on, total_interest)]
    for l in loans:
        per_caisse_loans[l.source_caisse_id].append((l.disbursed_on, l.total_interest))

    # Pour chaque caisse : taux de chaque prêt = intérêt ÷ apport disponible à sa date.
    # apport_at(D) = Σ des contributions (tous membres) de date ≤ D.
    per_caisse_loan_rates: dict = {}  # caisse_id → [(disbursed_on, rate)]
    for cid in caisse_ids:
        contribs = sorted(per_caisse_contribs.get(cid, []), key=lambda x: x[0])
        rates = []
        for d_on, interest in sorted(per_caisse_loans.get(cid, []), key=lambda x: x[0]):
            avail = sum(a for (dt, a, _m) in contribs if dt <= d_on)
            if avail > 0 and interest:
                rates.append((d_on, interest / avail))
        per_caisse_loan_rates[cid] = rates

    # Mes versements + leur rendement (Fred) ; cartes par caisse.
    caisse_by_id = {c.id: c for c in caisses}
    versements: list[MyVersement] = []
    rendement_by_caisse: dict = defaultdict(int)
    for cid in caisse_ids:
        rates = per_caisse_loan_rates.get(cid, [])
        for (dt, amount, mid) in sorted(per_caisse_contribs.get(cid, []), key=lambda x: x[0]):
            if mid != my_mid:
                continue
            # Rendement = montant × Σ(taux des prêts décaissés APRÈS ce versement).
            rperunit = sum(rate for (d_on, rate) in rates if d_on >= dt)
            rendement = int(round(amount * rperunit))
            rendement_by_caisse[cid] += rendement
            versements.append(
                MyVersement(
                    caisse_id=cid,
                    caisse_name=caisse_by_id[cid].name,
                    date=dt,
                    amount=amount,
                    rendement=rendement,
                )
            )
    versements.sort(key=lambda v: v.date)

    # Cartes : mon apport par caisse (CaisseContributorBalance) + rendement.
    my_balances = {
        b.caisse_id: b
        for b in (
            await db.execute(
                select(CaisseContributorBalance).where(
                    CaisseContributorBalance.caisse_id.in_(caisse_ids),
                    CaisseContributorBalance.membership_id == my_mid,
                )
            )
        ).scalars().all()
    }
    # Caisses « prêtables » : source d'un type de prêt OU ayant au moins un prêt.
    loanable: set = set()
    for cid in (
        await db.execute(
            select(LoanType.source_caisse_id).where(
                LoanType.association_id == association_id,
                LoanType.source_caisse_id.isnot(None),
            )
        )
    ).scalars().all():
        loanable.add(cid)
    for cid in (
        await db.execute(
            select(Loan.source_caisse_id)
            .where(Loan.source_caisse_id.in_(caisse_ids))
            .distinct()
        )
    ).scalars().all():
        loanable.add(cid)

    cards: list[MyFinanceCard] = []
    total_invested = 0
    total_rendement = 0
    for c in caisses:
        bal = my_balances.get(c.id)
        apport = bal.apport_cum if bal else 0
        rendement = rendement_by_caisse.get(c.id, 0)
        is_loanable = c.id in loanable
        # Affiche les caisses où j'ai un apport/rendement OU qui sont prêtables.
        if apport <= 0 and rendement <= 0 and not is_loanable:
            continue
        total_invested += apport
        total_rendement += rendement
        cards.append(
            MyFinanceCard(
                caisse_id=c.id,
                caisse_name=c.name,
                category=c.category.value if hasattr(c.category, "value") else str(c.category),
                my_apport=apport,
                my_rendement=rendement,
                expected_at_cassation=apport + rendement,
                is_loanable=is_loanable,
            )
        )

    # Notifications : caisse à cotisation minimale où mon apport est insuffisant.
    notifications: list[MyFinanceNotification] = []
    for c in caisses:
        minimum = getattr(c, "member_required_amount", 0) or 0
        if getattr(c, "is_member_required", False) and minimum > 0:
            bal = my_balances.get(c.id)
            apport = bal.apport_cum if bal else 0
            if apport < minimum:
                notifications.append(
                    MyFinanceNotification(
                        kind="warning",
                        message=(
                            f"Votre cotisation « {c.name} » n'est pas au complet "
                            f"({apport}/{minimum} {assoc.currency}). Pensez à la régulariser."
                        ),
                    )
                )

    return MyFinances(
        currency=assoc.currency,
        cards=cards,
        total_invested=total_invested,
        total_rendement=total_rendement,
        versements=versements,
        notifications=notifications,
    )


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

    from collections import defaultdict

    def _lr_split(total: int, weights: list[int]) -> list[int]:
        """Répartit `total` au prorata de `weights` — méthode du plus grand
        reste (Σ des parts == total, pas de perte d'arrondi)."""
        S = sum(weights)
        if S <= 0 or total <= 0:
            return [0] * len(weights)
        raw = [total * w / S for w in weights]
        floors = [int(x) for x in raw]
        rem = total - sum(floors)
        order = sorted(range(len(weights)), key=lambda i: raw[i] - floors[i], reverse=True)
        for k in range(rem):
            floors[order[k % len(order)]] += 1
        return floors

    # ── Contributions DATÉES (tous membres) vers le fonds de la caisse ──
    contrib_rows = (
        await db.execute(
            select(
                TreasuryMovement.related_membership_id,
                LedgerEntry.amount,
                TreasuryMovement.occurred_on,
            )
            .join(TreasuryMovement, TreasuryMovement.id == LedgerEntry.movement_id)
            .join(Treasury, Treasury.id == TreasuryMovement.treasury_id)
            .where(
                Treasury.association_id == caisse.association_id,
                LedgerEntry.fund_id == caisse.fund_id,
                LedgerEntry.is_credit.is_(True),
                TreasuryMovement.direction == MovementDirection.IN,
                TreasuryMovement.is_voided.is_(False),
            )
        )
    ).all()
    contribs = [(occ, int(amt), mid) for (mid, amt, occ) in contrib_rows if occ and amt and mid]

    # Apports cumulés + noms (pour l'apport global du membre et les libellés).
    balances = (
        await db.execute(
            select(CaisseContributorBalance)
            .options(
                selectinload(CaisseContributorBalance.membership).selectinload(Membership.user)
            )
            .where(CaisseContributorBalance.caisse_id == caisse_id)
        )
    ).scalars().all()
    total_apport = sum(b.apport_cum for b in balances)
    apport_by_mid = {b.membership_id: b.apport_cum for b in balances}
    name_by_mid = {
        b.membership_id: getattr(getattr(b, "membership", None), "user", None)
        and b.membership.user.full_name
        for b in balances
    }

    my_membership = (
        await db.execute(
            select(Membership).where(
                Membership.user_id == current_user.id,
                Membership.association_id == caisse.association_id,
            )
        )
    ).scalar_one_or_none()
    my_mid = my_membership.id if my_membership else None

    # ── Prêts financés par cette caisse, DÉCAISSÉS (en activité + soldés) ──
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
                Loan.disbursed_on.isnot(None),
            )
            .order_by(Loan.disbursed_on)
        )
    ).scalars().all()

    loan_projs: list[LoanDetailProjection] = []
    total_collected = 0
    total_upcoming = 0
    total_principal = 0
    my_collected_tot = 0
    my_upcoming_tot = 0

    for loan in loans:
        d_on = loan.disbursed_on
        # Argent disponible + apport de chaque membre AU DÉCAISSEMENT (Fred).
        total_at_loan = sum(a for (dt, a, _m) in contribs if dt <= d_on)
        amt_at_loan: dict = defaultdict(int)
        for (dt, a, mid) in contribs:
            if dt <= d_on:
                amt_at_loan[mid] += a
        # Repli si aucune contribution datée : prorata sur l'apport cumulé.
        if total_at_loan <= 0 and total_apport > 0:
            total_at_loan = total_apport
            amt_at_loan = dict(apport_by_mid)

        collected_full = loan.paid_interest
        upcoming_full = max(0, loan.total_interest - loan.paid_interest)
        total_collected += collected_full
        total_upcoming += upcoming_full
        if loan.status != LoanStatus.PAID:
            total_principal += loan.principal

        # Échéancier (intérêt total par date) : encaissé (remboursements) + à venir.
        entries: list[tuple] = []  # (due_on, interest_total, collected_bool)
        for rp in sorted(loan.repayments, key=lambda r: r.paid_on):
            it = getattr(rp, "interest", 0) or 0
            if it > 0:
                entries.append((rp.paid_on, it, True))
        remaining = upcoming_full
        for inst in sorted(loan.installments, key=lambda i: i.number):
            if remaining <= 0:
                break
            if inst.status in (LoanInstallmentStatus.PAID, LoanInstallmentStatus.WAIVED):
                continue
            part = inst.interest_part - inst.paid_interest
            part = max(0, min(part, remaining))
            if part <= 0:
                continue
            remaining -= part
            entries.append((inst.due_on, part, False))

        remaining_installments = sum(
            1
            for inst in loan.installments
            if inst.status not in (LoanInstallmentStatus.PAID, LoanInstallmentStatus.WAIVED)
        )
        rentability = (loan.total_interest / loan.principal * 100.0) if loan.principal else 0.0
        rev_per_unit = (loan.total_interest / total_at_loan) if total_at_loan else 0.0

        # Parts figées au décaissement : contributeurs présents à la date.
        present = [(mid, amt_at_loan.get(mid, 0)) for mid in amt_at_loan if amt_at_loan.get(mid, 0) > 0]
        weights = [a for (_m, a) in present]
        coll_split = _lr_split(collected_full, weights)
        up_split = _lr_split(upcoming_full, weights)

        my_amount_at_loan = 0
        my_share_pct = 0.0
        my_collected = 0
        my_upcoming = 0
        contributors: list[LoanContributorShare] = []
        for idx, (mid, amount) in enumerate(present):
            share = (amount / total_at_loan) if total_at_loan else 0.0
            c_coll = coll_split[idx]
            c_up = up_split[idx]
            contributors.append(
                LoanContributorShare(
                    membership_id=mid,
                    member_name=name_by_mid.get(mid),
                    amount_at_loan=amount,
                    share_pct=round(share * 100.0, 2),
                    expected_return=c_coll + c_up,
                    collected=c_coll,
                    upcoming=c_up,
                )
            )
            if mid == my_mid:
                my_amount_at_loan = amount
                my_share_pct = round(share * 100.0, 2)
                my_collected = c_coll
                my_upcoming = c_up

        my_collected_tot += my_collected
        my_upcoming_tot += my_upcoming
        # Répartit MA part (encaissée / à venir) sur les échéances correspondantes,
        # au prorata de l'intérêt de chaque échéance (Σ == ma part → visible).
        coll_entries = [(d, it) for (d, it, c) in entries if c]
        up_entries = [(d, it) for (d, it, c) in entries if not c]
        my_coll_per = _lr_split(my_collected, [it for (_d, it) in coll_entries])
        my_up_per = _lr_split(my_upcoming, [it for (_d, it) in up_entries])
        my_schedule = [
            LoanScheduleEntry(due_on=d, interest_total=it, my_share=my_coll_per[i], collected=True)
            for i, (d, it) in enumerate(coll_entries)
        ] + [
            LoanScheduleEntry(due_on=d, interest_total=it, my_share=my_up_per[i], collected=False)
            for i, (d, it) in enumerate(up_entries)
        ]
        my_schedule.sort(key=lambda e: (e.due_on, e.collected))

        borrower = getattr(loan, "borrower", None)
        buser = getattr(borrower, "user", None) if borrower else None
        loan_projs.append(
            LoanDetailProjection(
                loan_id=loan.id,
                reference=loan.reference,
                borrower_name=getattr(buser, "full_name", None),
                principal=loan.principal,
                total_interest=loan.total_interest,
                rentability_pct=round(rentability, 2),
                revenue_per_unit_invested=round(rev_per_unit, 4),
                disbursed_on=d_on,
                remaining_installments=remaining_installments,
                total_at_loan=total_at_loan,
                my_amount_at_loan=my_amount_at_loan,
                my_share_pct=my_share_pct,
                my_expected_return=my_collected + my_upcoming,
                my_collected=my_collected,
                my_upcoming=my_upcoming,
                my_schedule=my_schedule,
                contributors=sorted(contributors, key=lambda c: c.amount_at_loan, reverse=True),
            )
        )

    my_apport = apport_by_mid.get(my_mid, 0) if my_mid else 0
    my_expected_return = my_collected_tot + my_upcoming_tot
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
        my_membership_id=my_mid,
        my_apport=my_apport,
        my_collected=my_collected_tot,
        my_upcoming=my_upcoming_tot,
        my_expected_return=my_expected_return,
        my_expected_at_cassation=my_apport + my_expected_return,
        loans=loan_projs,
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


