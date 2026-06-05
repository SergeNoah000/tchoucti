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
from app.models.caisse import (
    Caisse,
    CaisseCategory,
    CaisseContributorBalance,
    CaisseDistribution,
    CaisseDistributionShare,
    InterestDistribution,
)
from app.models.finance import Fund, FundKind, Treasury
from app.models.role import Membership
from app.models.user import User
from app.schemas.caisse import (
    CaisseContributorBalanceOut,
    CaisseCreate,
    CaisseDistributionOut,
    CaisseDistributionShareOut,
    CaisseOut,
    CaisseUpdate,
)
from app.services.caisse_distribution import close_distribution_period
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
