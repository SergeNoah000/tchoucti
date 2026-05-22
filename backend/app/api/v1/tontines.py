"""Tontine endpoints — cycles + rounds + beneficiaries (rotating savings).

A cycle is N rounds. Each round, every participant contributes `round_amount`;
the pot leaves the TONTINE fund toward **one or several beneficiaries** who
share it according to `share_parts`.

Total participants = sum of beneficiaries across all rounds (each person is
beneficiary of exactly one round in their cycle).
"""
import random
from datetime import date, timedelta
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.models.association import Association
from app.models.finance import FundKind, MovementDirection
from app.models.role import Membership
from app.models.tontine import (
    TontineCycle,
    TontineCycleStatus,
    TontineRound,
    TontineRoundBeneficiary,
    TontineRoundStatus,
)
from app.models.user import User
from app.services.finance import Allocation, get_or_create_treasury, post_movement
from app.schemas.tontine import (
    TontineBeneficiaryOut,
    TontineCycleCreate,
    TontineCycleDetail,
    TontineCycleOut,
    TontineRoundOut,
)

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


async def _load_cycle(db: AsyncSession, cycle_id: UUID) -> TontineCycle:
    res = await db.execute(
        select(TontineCycle)
        .options(
            selectinload(TontineCycle.rounds)
            .selectinload(TontineRound.beneficiaries)
            .selectinload(TontineRoundBeneficiary.membership)
            .selectinload(Membership.user)
        )
        .where(TontineCycle.id == cycle_id)
    )
    cycle = res.scalar_one_or_none()
    if not cycle:
        raise HTTPException(404, "Tontine cycle not found")
    return cycle


def _round_out(r: TontineRound) -> TontineRoundOut:
    benefs: List[TontineBeneficiaryOut] = []
    for b in r.beneficiaries:
        membership = getattr(b, "membership", None)
        user = getattr(membership, "user", None) if membership else None
        benefs.append(
            TontineBeneficiaryOut(
                membership_id=b.membership_id,
                name=getattr(user, "full_name", None),
                share_amount=b.share_amount,
                share_parts=b.share_parts,
            )
        )
    return TontineRoundOut(
        id=r.id,
        round_number=r.round_number,
        scheduled_date=r.scheduled_date,
        paid_out_date=r.paid_out_date,
        beneficiaries=benefs,
        expected_amount=r.expected_amount,
        collected_amount=r.collected_amount,
        paid_out_amount=r.paid_out_amount,
        status=r.status.value if hasattr(r.status, "value") else r.status,
    )


def _cycle_detail(cycle: TontineCycle) -> TontineCycleDetail:
    rounds = sorted(cycle.rounds, key=lambda r: r.round_number)
    # rounds_count is stored as the number of rounds, not the participants count.
    # Total participants = unique memberships across all beneficiary entries.
    total_participants = sum(len(r.beneficiaries) for r in rounds)
    return TontineCycleDetail(
        id=cycle.id,
        association_id=cycle.association_id,
        name=cycle.name,
        description=cycle.description,
        round_amount=cycle.round_amount,
        rounds_count=cycle.rounds_count,
        current_round_number=cycle.current_round_number,
        start_date=cycle.start_date,
        end_date=cycle.end_date,
        order_strategy=cycle.order_strategy,
        status=cycle.status.value if hasattr(cycle.status, "value") else cycle.status,
        created_at=cycle.created_at,
        rounds=[_round_out(r) for r in rounds],
        pot_amount=cycle.round_amount * total_participants,
    )


def _shares(pot: int, parts: List[int]) -> List[int]:
    """Split `pot` proportionally to `parts`. Residue goes to the last share."""
    total = sum(parts)
    if total <= 0:
        raise HTTPException(422, "Parts invalides")
    out: List[int] = []
    accum = 0
    for i, p in enumerate(parts):
        if i < len(parts) - 1:
            v = (pot * p) // total
            accum += v
            out.append(v)
        else:
            out.append(pot - accum)
    return out


# ── Endpoints ───────────────────────────────────────────────────────────────
@router.get("", response_model=List[TontineCycleOut])
async def list_cycles(
    association_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assoc = await _get_assoc_or_404(db, association_id)
    _check_access(current_user, assoc)
    res = await db.execute(
        select(TontineCycle)
        .where(TontineCycle.association_id == association_id)
        .order_by(TontineCycle.created_at.desc())
    )
    return list(res.scalars().all())


@router.get("/{cycle_id}", response_model=TontineCycleDetail)
async def get_cycle(
    cycle_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cycle = await _load_cycle(db, cycle_id)
    assoc = await _get_assoc_or_404(db, cycle.association_id)
    _check_access(current_user, assoc)
    return _cycle_detail(cycle)


@router.post("", response_model=TontineCycleDetail, status_code=status.HTTP_201_CREATED)
async def create_cycle(
    payload: TontineCycleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assoc = await _get_assoc_or_404(db, payload.association_id)
    _check_access(current_user, assoc)

    # Flatten + validate participants: each member can be beneficiary in only
    # one round across the cycle.
    all_ids: List[UUID] = []
    for r in payload.rounds:
        for b in r.beneficiaries:
            all_ids.append(b.membership_id)
    if len(all_ids) < 2:
        raise HTTPException(422, "Au moins 2 participants requis")
    if len(set(all_ids)) != len(all_ids):
        raise HTTPException(422, "Un participant ne peut être bénéficiaire qu'une seule fois par cycle")

    res = await db.execute(
        select(Membership).where(
            Membership.id.in_(all_ids),
            Membership.association_id == payload.association_id,
        )
    )
    found = {m.id for m in res.scalars().all()}
    missing = [str(i) for i in all_ids if i not in found]
    if missing:
        raise HTTPException(422, f"Membres introuvables dans l'association : {', '.join(missing)}")

    n_participants = len(all_ids)
    pot = payload.round_amount * n_participants  # each round's pot

    # Round cadence comes from the association's tontine config.
    freq = ((assoc.config or {}).get("tontine") or {}).get("frequency") or "monthly"
    interval_days = {"weekly": 7, "biweekly": 14, "monthly": 30, "quarterly": 90}.get(freq, 30)

    rounds_config = list(payload.rounds)
    strategy = "manual"
    if payload.shuffle:
        random.shuffle(rounds_config)
        strategy = "random"

    cycle = TontineCycle(
        association_id=payload.association_id,
        name=payload.name,
        description=payload.description,
        round_amount=payload.round_amount,
        rounds_count=len(rounds_config),
        current_round_number=1,
        start_date=payload.start_date,
        order_strategy=strategy,
        status=TontineCycleStatus.ACTIVE,
    )
    db.add(cycle)
    await db.flush()

    for idx, rcfg in enumerate(rounds_config):
        rnd = TontineRound(
            cycle_id=cycle.id,
            round_number=idx + 1,
            scheduled_date=payload.start_date + timedelta(days=interval_days * idx),
            expected_amount=pot,
            status=TontineRoundStatus.COLLECTING if idx == 0 else TontineRoundStatus.PENDING,
        )
        db.add(rnd)
        await db.flush()
        parts = [b.share_parts for b in rcfg.beneficiaries]
        shares = _shares(pot, parts)
        for b, amt in zip(rcfg.beneficiaries, shares):
            db.add(
                TontineRoundBeneficiary(
                    round_id=rnd.id,
                    membership_id=b.membership_id,
                    share_amount=amt,
                    share_parts=b.share_parts,
                )
            )

    await db.commit()
    cycle = await _load_cycle(db, cycle.id)
    return _cycle_detail(cycle)


@router.post("/{cycle_id}/rounds/{round_id}/payout", response_model=TontineCycleDetail)
async def payout_round(
    cycle_id: UUID,
    round_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a round as paid out — single OUT movement from the TONTINE fund.

    With multi-beneficiary rounds, the pot leaves in ONE movement; per-person
    shares are stored on `TontineRoundBeneficiary.share_amount`.
    """
    cycle = await _load_cycle(db, cycle_id)
    assoc = await _get_assoc_or_404(db, cycle.association_id)
    _check_access(current_user, assoc)

    if cycle.status != TontineCycleStatus.ACTIVE:
        raise HTTPException(409, "Le cycle n'est pas actif")

    rnd = next((r for r in cycle.rounds if r.id == round_id), None)
    if not rnd:
        raise HTTPException(404, "Tour introuvable")
    if rnd.status == TontineRoundStatus.PAID_OUT:
        raise HTTPException(409, "Ce tour a déjà été versé")

    pot = rnd.expected_amount

    treasury = await get_or_create_treasury(db, assoc)
    tontine_fund = next((f for f in treasury.funds if f.kind == FundKind.TONTINE), None)
    if tontine_fund is None:
        raise HTTPException(500, "Fonds tontine introuvable")

    # If there's a single beneficiary, pin them on the movement for traceability.
    related = rnd.beneficiaries[0].membership_id if len(rnd.beneficiaries) == 1 else None

    movement = await post_movement(
        db,
        treasury=treasury,
        direction=MovementDirection.OUT,
        amount=pot,
        allocations=[Allocation(fund=tontine_fund, is_credit=False, amount=pot)],
        occurred_on=date.today(),
        source_type="tontine_payout",
        source_id=rnd.id,
        recorded_by_id=current_user.id,
        related_membership_id=related,
        description=f"Tontine {cycle.name} — tour {rnd.round_number}",
        commit=False,
    )

    rnd.status = TontineRoundStatus.PAID_OUT
    rnd.paid_out_date = date.today()
    rnd.paid_out_amount = pot
    rnd.collected_amount = pot
    rnd.payout_movement_id = movement.id

    # Advance to the next pending round, or complete the cycle.
    nxt = next(
        (r for r in sorted(cycle.rounds, key=lambda x: x.round_number)
         if r.status == TontineRoundStatus.PENDING),
        None,
    )
    if nxt:
        nxt.status = TontineRoundStatus.COLLECTING
        cycle.current_round_number = nxt.round_number
    else:
        cycle.status = TontineCycleStatus.COMPLETED
        cycle.end_date = date.today()

    await db.commit()
    cycle = await _load_cycle(db, cycle_id)
    return _cycle_detail(cycle)


@router.post("/{cycle_id}/cancel", response_model=TontineCycleDetail)
async def cancel_cycle(
    cycle_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cycle = await _load_cycle(db, cycle_id)
    assoc = await _get_assoc_or_404(db, cycle.association_id)
    _check_access(current_user, assoc)
    if cycle.status == TontineCycleStatus.COMPLETED:
        raise HTTPException(409, "Cycle déjà terminé")
    cycle.status = TontineCycleStatus.CANCELLED
    await db.commit()
    cycle = await _load_cycle(db, cycle_id)
    return _cycle_detail(cycle)
