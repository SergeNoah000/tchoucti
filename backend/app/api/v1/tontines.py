"""Tontine endpoints — cycles + rounds + beneficiaries (rotating savings).

A cycle is N rounds. Each round, every participant contributes `round_amount`;
the pot leaves the TONTINE fund toward **one or several beneficiaries** who
share it according to `share_parts`.

Total participants = sum of beneficiaries across all rounds (each person is
beneficiary of exactly one round in their cycle).
"""
import random
import re
from datetime import date
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.models.association import Association
from app.models.caisse import Caisse, CaisseCategory
from app.models.finance import Fund, FundKind, MovementDirection
from app.models.meeting import Meeting, MeetingStatus
from app.models.role import Membership, MembershipStatus
from app.models.tontine import (
    TontineCycle,
    TontineCycleStatus,
    TontineMeetingLink,
    TontineParticipation,
    TontineRound,
    TontineRoundBeneficiary,
    TontineRoundStatus,
)
from app.models.user import User
from app.services import planning
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


async def _meeting_map_for_cycle(
    db: AsyncSession, cycle_id: UUID
) -> dict[UUID, tuple[UUID, str]]:
    """Return {round_id: (meeting_id, meeting_title)} for all linked rounds."""
    res = await db.execute(
        select(TontineMeetingLink, Meeting)
        .join(Meeting, Meeting.id == TontineMeetingLink.meeting_id)
        .join(TontineRound, TontineRound.id == TontineMeetingLink.round_id)
        .where(TontineRound.cycle_id == cycle_id)
    )
    return {link.round_id: (m.id, m.title) for link, m in res.all()}


def _round_out(r: TontineRound, meeting_info: tuple[UUID, str] | None = None) -> TontineRoundOut:
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
    meeting_id = meeting_info[0] if meeting_info else None
    meeting_title = meeting_info[1] if meeting_info else None
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
        meeting_id=meeting_id,
        meeting_title=meeting_title,
    )


def _cycle_detail(
    cycle: TontineCycle, meeting_map: dict[UUID, tuple[UUID, str]] | None = None
) -> TontineCycleDetail:
    rounds = sorted(cycle.rounds, key=lambda r: r.round_number)
    # rounds_count is stored as the number of rounds, not the participants count.
    # Total participants = unique memberships across all beneficiary entries.
    total_participants = sum(len(r.beneficiaries) for r in rounds)
    mm = meeting_map or {}
    return TontineCycleDetail(
        id=cycle.id,
        association_id=cycle.association_id,
        name=cycle.name,
        slug=cycle.slug,
        description=cycle.description,
        round_amount=cycle.round_amount,
        rounds_count=cycle.rounds_count,
        current_round_number=cycle.current_round_number,
        start_date=cycle.start_date,
        end_date=cycle.end_date,
        order_strategy=cycle.order_strategy,
        status=cycle.status.value if hasattr(cycle.status, "value") else cycle.status,
        is_mandatory=cycle.is_mandatory,
        created_at=cycle.created_at,
        rounds=[_round_out(r, mm.get(r.id)) for r in rounds],
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
    meeting_map = await _meeting_map_for_cycle(db, cycle.id)
    return _cycle_detail(cycle, meeting_map)


async def _unique_slug(db: AsyncSession, association_id: UUID, name: str) -> str:
    """Generate a slug unique within the association — handles collisions
    with -2, -3… suffix."""
    base = slugify(name)[:80] or "tontine"
    base = re.sub(r"-+", "-", base).strip("-") or "tontine"
    candidate = base
    i = 2
    while True:
        existing = await db.execute(
            select(TontineCycle.id).where(
                TontineCycle.association_id == association_id,
                TontineCycle.slug == candidate,
            )
        )
        if existing.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base}-{i}"
        i += 1


async def _pick_or_make_meetings(
    db: AsyncSession,
    assoc: Association,
    rounds_count: int,
    start_date: date,
    explicit_ids: list[UUID] | None,
) -> list[Meeting]:
    """Resolve `rounds_count` meetings to host the rounds.

    - If `explicit_ids` is provided, validate length + ownership.
    - Otherwise pick the next N PLANNED meetings (asso, scheduled_on >= start_date).
    - If the pool is short, auto-generate missing ones via the cadence helper.
    """
    if explicit_ids is not None:
        if len(explicit_ids) != rounds_count:
            raise HTTPException(
                422,
                f"meeting_ids doit avoir {rounds_count} entrées (autant que de tours).",
            )
        res = await db.execute(
            select(Meeting)
            .where(Meeting.id.in_(explicit_ids), Meeting.association_id == assoc.id)
            .order_by(Meeting.scheduled_on)
        )
        meetings = list(res.scalars().all())
        if len(meetings) != rounds_count:
            raise HTTPException(422, "Une ou plusieurs séances explicites n'appartiennent pas à l'association.")
        # Preserve the order the admin supplied.
        by_id = {m.id: m for m in meetings}
        return [by_id[i] for i in explicit_ids]

    # Auto-pick the next N planned meetings.
    res = await db.execute(
        select(Meeting)
        .where(
            Meeting.association_id == assoc.id,
            Meeting.status == MeetingStatus.PLANNED,
            Meeting.scheduled_on >= start_date,
        )
        .order_by(Meeting.scheduled_on)
    )
    pool = list(res.scalars().all())
    if len(pool) >= rounds_count:
        return pool[:rounds_count]

    # Top up the pool — generate missing slots from the cadence.
    last_date = pool[-1].scheduled_on if pool else None
    anchor = last_date if last_date and last_date >= start_date else start_date
    # First missing date is one cadence step after the anchor; but if the
    # pool is empty, anchor IS start_date — use it directly.
    if not pool:
        d = start_date
    else:
        d = planning.next_date_after(assoc, anchor)
    to_create = rounds_count - len(pool)
    for _ in range(to_create):
        m = Meeting(
            association_id=assoc.id,
            title=planning.default_title(assoc, d),
            scheduled_on=d,
            location=planning.default_location(assoc),
            status=MeetingStatus.PLANNED,
        )
        db.add(m)
        await db.flush()
        pool.append(m)
        d = planning.next_date_after(assoc, d)
    return pool[:rounds_count]


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

    # Validate opt-outs (only meaningful when is_mandatory=False).
    if payload.is_mandatory and payload.excluded_membership_ids:
        raise HTTPException(
            422, "Impossible d'exclure des membres quand la tontine est obligatoire."
        )
    if payload.excluded_membership_ids:
        # All excluded must be active members of the association.
        exc_res = await db.execute(
            select(Membership.id).where(
                Membership.id.in_(payload.excluded_membership_ids),
                Membership.association_id == payload.association_id,
            )
        )
        exc_found = {m for m in exc_res.scalars().all()}
        bad = [str(i) for i in payload.excluded_membership_ids if i not in exc_found]
        if bad:
            raise HTTPException(422, f"Membres exclus introuvables : {', '.join(bad)}")

    n_participants = len(all_ids)
    pot = payload.round_amount * n_participants  # each round's pot

    rounds_config = list(payload.rounds)
    strategy = "manual"
    if payload.shuffle:
        random.shuffle(rounds_config)
        strategy = "random"

    # 1. Slug unique pour l'asso (sert de ref_key sur le Fund dédié).
    cycle_slug = await _unique_slug(db, payload.association_id, payload.name)

    # 2. Caisse système + Fund dédiés à cette tontine (préserve l'invariant
    #    trésorerie tout en isolant les flux entre cycles concurrents).
    treasury = await get_or_create_treasury(db, assoc)
    tontine_fund = Fund(
        treasury_id=treasury.id,
        kind=FundKind.TONTINE,
        ref_key=cycle_slug,
        name=f"Tontine — {payload.name}",
        description="Fonds dédié à la rotation de cette tontine.",
        is_system=True,
    )
    db.add(tontine_fund)
    await db.flush()
    db.add(
        Caisse(
            association_id=payload.association_id,
            fund_id=tontine_fund.id,
            name=f"Tontine — {payload.name}",
            slug=cycle_slug,
            description="Caisse système liée à cette tontine (auto-créée).",
            category=CaisseCategory.SYSTEM,
            is_system=True,
        )
    )

    # 3. Cycle.
    cycle = TontineCycle(
        association_id=payload.association_id,
        name=payload.name,
        slug=cycle_slug,
        description=payload.description,
        round_amount=payload.round_amount,
        rounds_count=len(rounds_config),
        current_round_number=1,
        start_date=payload.start_date,
        order_strategy=strategy,
        status=TontineCycleStatus.ACTIVE,
        is_mandatory=payload.is_mandatory,
    )
    db.add(cycle)
    await db.flush()

    # 4. Résolution séances ↔ tours (explicite ou auto).
    meetings = await _pick_or_make_meetings(
        db, assoc, len(rounds_config), payload.start_date, payload.meeting_ids
    )

    # 5. Création des tours + liens séances + bénéficiaires.
    for idx, (rcfg, meeting) in enumerate(zip(rounds_config, meetings)):
        rnd = TontineRound(
            cycle_id=cycle.id,
            round_number=idx + 1,
            scheduled_date=meeting.scheduled_on,
            expected_amount=pot,
            status=TontineRoundStatus.COLLECTING if idx == 0 else TontineRoundStatus.PENDING,
        )
        db.add(rnd)
        await db.flush()

        db.add(TontineMeetingLink(round_id=rnd.id, meeting_id=meeting.id))

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

    # 6. Opt-outs explicites.
    for mid in payload.excluded_membership_ids:
        db.add(
            TontineParticipation(
                cycle_id=cycle.id,
                membership_id=mid,
                is_participating=False,
            )
        )

    await db.commit()
    cycle = await _load_cycle(db, cycle.id)
    meeting_map = await _meeting_map_for_cycle(db, cycle.id)
    return _cycle_detail(cycle, meeting_map)


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
    # Phase 2c — each cycle has its own dedicated TONTINE fund identified by
    # ref_key=cycle.slug, so concurrent tontines never share a balance.
    tontine_fund = next(
        (f for f in treasury.funds
         if f.kind == FundKind.TONTINE and f.ref_key == cycle.slug),
        None,
    )
    if tontine_fund is None:
        # Backward compatibility — cycles created before Phase 2c had a single
        # shared TONTINE fund with empty ref_key. Fall back to it if needed.
        tontine_fund = next(
            (f for f in treasury.funds if f.kind == FundKind.TONTINE and not f.ref_key),
            None,
        )
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
    meeting_map = await _meeting_map_for_cycle(db, cycle.id)
    return _cycle_detail(cycle, meeting_map)


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
    meeting_map = await _meeting_map_for_cycle(db, cycle.id)
    return _cycle_detail(cycle, meeting_map)


# ── Phase 2c — relinking a round to a different meeting ───────────────────


@router.patch("/{cycle_id}/rounds/{round_id}/meeting", response_model=TontineCycleDetail)
async def relink_round_to_meeting(
    cycle_id: UUID,
    round_id: UUID,
    meeting_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Déplace un tour vers une autre séance hôte (sauf si le lien est verrouillé).

    Use cases :
      - L'admin a généré le mapping auto puis veut substituer une séance ;
      - Une séance est annulée/déplacée et il faut rattacher le tour à une autre.

    Le tour doit être PENDING ou COLLECTING (jamais déjà payé).
    """
    cycle = await _load_cycle(db, cycle_id)
    assoc = await _get_assoc_or_404(db, cycle.association_id)
    _check_access(current_user, assoc)

    rnd = next((r for r in cycle.rounds if r.id == round_id), None)
    if not rnd:
        raise HTTPException(404, "Tour introuvable")
    if rnd.status == TontineRoundStatus.PAID_OUT:
        raise HTTPException(409, "Tour déjà versé — il ne peut plus être déplacé.")

    res = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id, Meeting.association_id == assoc.id)
    )
    new_meeting = res.scalar_one_or_none()
    if not new_meeting:
        raise HTTPException(422, "Séance cible introuvable dans cette association.")

    link_res = await db.execute(
        select(TontineMeetingLink).where(TontineMeetingLink.round_id == round_id)
    )
    link = link_res.scalar_one_or_none()
    if link and link.is_locked:
        raise HTTPException(
            409, "Lien tour ↔ séance verrouillé — décale le cycle entier à la place."
        )
    if link:
        link.meeting_id = new_meeting.id
    else:
        db.add(TontineMeetingLink(round_id=round_id, meeting_id=new_meeting.id))
    rnd.scheduled_date = new_meeting.scheduled_on

    await db.commit()
    cycle = await _load_cycle(db, cycle_id)
    meeting_map = await _meeting_map_for_cycle(db, cycle.id)
    return _cycle_detail(cycle, meeting_map)
