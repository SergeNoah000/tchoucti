"""Tontine endpoints (Phase 6A) — Tontine (durable) → Cycles → tours = séances.

- Une **tontine** est durable et possède UNE caisse système dédiée.
- Chaque **cycle** est une rotation complète ; ses **séances** sont créées
  d'office à la création du cycle (1 séance = 1 tour).
- Le **cycle suivant** hérite de toute la config + participants du précédent.
- Distribution : plusieurs gagnants/tour, chacun gagne une fois →
  nb_tours = ceil(participants / bénéficiaires_par_tour).
"""
import random
import re
from datetime import date, timedelta
from typing import List, Optional
from uuid import UUID

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Query, status
from slugify import slugify
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import _user_has_bureau_role, get_current_user, get_db
from app.models.association import Association
from app.models.caisse import Caisse, CaisseCategory
from app.models.finance import Fund, FundKind, MovementDirection
from app.models.meeting import Meeting, MeetingStatus
from app.models.role import Membership, MembershipStatus
from app.models.tontine import (
    Tontine,
    TontineCycle,
    TontineCycleStatus,
    TontineMeetingLink,
    TontineParticipation,
    TontineRound,
    TontineRoundBeneficiary,
    TontineRoundStatus,
)
from app.models.user import User
from app.services.finance import Allocation, get_or_create_treasury, post_movement
from app.services.meeting_agenda import upsert_tontine_activity
from app.schemas.tontine import (
    BeneficiaryRename,
    CycleParticipantsUpdate,
    NextCycleCreate,
    TontineBeneficiaryOut,
    TontineCreate,
    TontineCycleDetail,
    TontineCycleOut,
    TontineDetail,
    TontineOut,
    TontineRoundOut,
)

router = APIRouter()


# ── Helpers ─────────────────────────────────────────────────────────────────
async def _get_assoc_or_404(db: AsyncSession, association_id: UUID) -> Association:
    res = await db.execute(select(Association).where(Association.id == association_id))
    assoc = res.scalar_one_or_none()
    if not assoc:
        raise HTTPException(404, "Association introuvable")
    return assoc


def _check_access(user: User, assoc: Association) -> None:
    if user.is_super_admin:
        return
    if user.groupement_id != assoc.groupement_id:
        raise HTTPException(403, "Forbidden")


def _shares(pot: int, parts: List[int]) -> List[int]:
    """Répartit `pot` au prorata de `parts`. Le reste va au dernier."""
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


def _next_date(d: date, frequency: str, custom_days: int | None) -> date:
    if frequency == "weekly":
        return d + timedelta(days=7)
    if frequency == "biweekly":
        return d + timedelta(days=14)
    if frequency == "monthly":
        return d + relativedelta(months=1)
    if frequency == "bimonthly":
        return d + relativedelta(months=2)
    return d + timedelta(days=custom_days or 30)


def _cycle_dates(tontine: Tontine, start: date, count: int) -> list[date]:
    dates = [start]
    for _ in range(count - 1):
        dates.append(_next_date(dates[-1], tontine.frequency, tontine.custom_interval_days))
    return dates


async def _unique_slug(db: AsyncSession, association_id: UUID, name: str) -> str:
    base = re.sub(r"-+", "-", slugify(name)[:80]).strip("-") or "tontine"
    candidate, i = base, 2
    while True:
        exists = await db.execute(
            select(Tontine.id).where(
                Tontine.association_id == association_id, Tontine.slug == candidate
            )
        )
        if exists.scalar_one_or_none() is None:
            return candidate
        candidate, i = f"{base}-{i}", i + 1


async def _get_tontine_fund(db: AsyncSession, treasury, tontine: Tontine) -> Fund | None:
    return next(
        (f for f in treasury.funds if f.kind == FundKind.TONTINE and f.ref_key == tontine.slug),
        None,
    )


def _resolve_order_and_labels(
    ids: list[UUID],
    names: Optional[list[Optional[str]]],
    shuffle: bool,
) -> tuple[list[UUID], list[Optional[str]]]:
    """Construit l'ordre de passage + les libellés (un par slot). Les doublons
    de membre sont autorisés (plusieurs noms). `shuffle` mélange les paires."""
    labels = names if names is not None else [None] * len(ids)
    if len(labels) != len(ids):
        raise HTTPException(
            422, "participant_names doit avoir la même longueur que participant_ids."
        )
    pairs = list(zip(ids, labels))
    if shuffle:
        random.shuffle(pairs)
    order = [p[0] for p in pairs]
    out_labels = [(p[1].strip() if p[1] and str(p[1]).strip() else None) for p in pairs]
    return order, out_labels


async def _populate_cycle(
    db: AsyncSession,
    *,
    cycle: TontineCycle,
    tontine: Tontine,
    participant_order: list[UUID],
    excluded_ids: list[UUID],
    activate: bool,
    name_labels: list[Optional[str]] | None = None,
) -> None:
    """(Re)génère tours + séances d'office + bénéficiaires + opt-outs sur un cycle
    EXISTANT (déjà flushé).

    nb_tours = ceil(n_participants / bénéficiaires_par_tour). À chaque tour,
    `beneficiaries_per_round` participants consécutifs se partagent la cagnotte à
    parts égales. La cagnotte = round_amount × nb de payeurs. Si `activate`, le
    cycle passe ACTIVE et le 1er tour COLLECTING ; sinon il reste BROUILLON
    (tous les tours PENDING) — sans participant, aucun tour n'est créé.
    """
    k = max(1, tontine.beneficiaries_per_round)
    n = len(participant_order)
    n_rounds = (n + k - 1) // k  # ceil

    cycle.rounds_count = n_rounds
    cycle.current_round_number = 1
    cycle.status = TontineCycleStatus.ACTIVE if activate else TontineCycleStatus.DRAFT

    dates = _cycle_dates(tontine, cycle.start_date, n_rounds) if n_rounds else []

    for idx in range(n_rounds):
        beneficiaries = participant_order[idx * k : (idx + 1) * k]
        n_payers = n - (0 if tontine.beneficiary_pays else len(beneficiaries))
        pot = tontine.round_amount * max(0, n_payers)
        round_date = dates[idx]

        rnd = TontineRound(
            cycle_id=cycle.id,
            round_number=idx + 1,
            scheduled_date=round_date,
            expected_amount=pot,
            status=(
                TontineRoundStatus.COLLECTING
                if (idx == 0 and activate)
                else TontineRoundStatus.PENDING
            ),
        )
        db.add(rnd)
        await db.flush()

        # Séance d'office pour ce tour.
        meeting = Meeting(
            association_id=tontine.association_id,
            title=f"{tontine.name} — Tour {idx + 1}",
            scheduled_on=round_date,
            status=MeetingStatus.PLANNED,
        )
        db.add(meeting)
        await db.flush()
        db.add(TontineMeetingLink(round_id=rnd.id, meeting_id=meeting.id))

        labels = (name_labels[idx * k : (idx + 1) * k] if name_labels else [None] * len(beneficiaries))
        shares = _shares(pot, [1] * len(beneficiaries))
        for mid, amt, label in zip(beneficiaries, shares, labels):
            db.add(
                TontineRoundBeneficiary(
                    round_id=rnd.id,
                    membership_id=mid,
                    name_label=label,
                    share_amount=amt,
                    share_parts=1,
                )
            )

    cycle.end_date = dates[-1] if n_rounds else None

    for mid in excluded_ids:
        db.add(TontineParticipation(cycle_id=cycle.id, membership_id=mid, is_participating=False))


async def _build_cycle(
    db: AsyncSession,
    *,
    tontine: Tontine,
    cycle_number: int,
    start_date: date,
    participant_order: list[UUID],
    is_mandatory: bool,
    excluded_ids: list[UUID],
    activate: bool = True,
    name_labels: list[Optional[str]] | None = None,
) -> TontineCycle:
    """Crée un cycle puis le peuple. Sans participant (`activate=False`), le cycle
    est créé vide en BROUILLON — les membres sont ajoutés ensuite via la config."""
    cycle = TontineCycle(
        tontine_id=tontine.id,
        cycle_number=cycle_number,
        round_amount=tontine.round_amount,
        rounds_count=0,
        current_round_number=1,
        start_date=start_date,
        order_strategy=tontine.selection_method,
        status=TontineCycleStatus.DRAFT,
        is_mandatory=is_mandatory,
    )
    db.add(cycle)
    await db.flush()
    await _populate_cycle(
        db,
        cycle=cycle,
        tontine=tontine,
        participant_order=participant_order,
        excluded_ids=excluded_ids,
        activate=activate,
        name_labels=name_labels,
    )
    return cycle


async def _clear_cycle_content(db: AsyncSession, cycle: TontineCycle) -> None:
    """Supprime tours + séances + opt-outs d'un cycle BROUILLON pour le régénérer."""
    round_ids = (
        await db.execute(select(TontineRound.id).where(TontineRound.cycle_id == cycle.id))
    ).scalars().all()
    if round_ids:
        meeting_ids = (
            await db.execute(
                select(TontineMeetingLink.meeting_id).where(
                    TontineMeetingLink.round_id.in_(round_ids)
                )
            )
        ).scalars().all()
        # Supprimer les tours (cascade : bénéficiaires, contributions, liens séance).
        await db.execute(delete(TontineRound).where(TontineRound.cycle_id == cycle.id))
        if meeting_ids:
            await db.execute(delete(Meeting).where(Meeting.id.in_(meeting_ids)))
    await db.execute(
        delete(TontineParticipation).where(TontineParticipation.cycle_id == cycle.id)
    )
    await db.flush()


async def _meeting_map_for_cycle(db: AsyncSession, cycle_id: UUID) -> dict[UUID, tuple[UUID, str]]:
    res = await db.execute(
        select(TontineMeetingLink, Meeting)
        .join(Meeting, Meeting.id == TontineMeetingLink.meeting_id)
        .join(TontineRound, TontineRound.id == TontineMeetingLink.round_id)
        .where(TontineRound.cycle_id == cycle_id)
    )
    return {link.round_id: (m.id, m.title) for link, m in res.all()}


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
        raise HTTPException(404, "Cycle de tontine introuvable")
    return cycle


async def _load_tontine(db: AsyncSession, tontine_id: UUID) -> Tontine:
    res = await db.execute(
        select(Tontine)
        .options(
            selectinload(Tontine.cycles)
            .selectinload(TontineCycle.rounds)
            .selectinload(TontineRound.beneficiaries)
            .selectinload(TontineRoundBeneficiary.membership)
            .selectinload(Membership.user)
        )
        .where(Tontine.id == tontine_id)
    )
    tontine = res.scalar_one_or_none()
    if not tontine:
        raise HTTPException(404, "Tontine introuvable")
    return tontine


def _round_out(r: TontineRound, meeting_info: tuple[UUID, str] | None = None) -> TontineRoundOut:
    benefs = []
    for b in r.beneficiaries:
        member_name = getattr(
            getattr(b, "membership", None) and b.membership.user, "full_name", None
        )
        benefs.append(
            TontineBeneficiaryOut(
                id=b.id,
                membership_id=b.membership_id,
                name=b.name_label or member_name,
                member_name=member_name,
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
        meeting_id=meeting_info[0] if meeting_info else None,
        meeting_title=meeting_info[1] if meeting_info else None,
    )


def _cycle_detail(cycle: TontineCycle, meeting_map: dict[UUID, tuple[UUID, str]] | None = None) -> TontineCycleDetail:
    rounds = sorted(cycle.rounds, key=lambda r: r.round_number)
    total_beneficiaries = sum(len(r.beneficiaries) for r in rounds)
    mm = meeting_map or {}
    return TontineCycleDetail(
        id=cycle.id,
        tontine_id=cycle.tontine_id,
        cycle_number=cycle.cycle_number,
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
        pot_amount=cycle.round_amount * total_beneficiaries,
    )


def _cycle_out(cycle: TontineCycle) -> TontineCycleOut:
    return TontineCycleOut(
        id=cycle.id,
        tontine_id=cycle.tontine_id,
        cycle_number=cycle.cycle_number,
        round_amount=cycle.round_amount,
        rounds_count=cycle.rounds_count,
        current_round_number=cycle.current_round_number,
        start_date=cycle.start_date,
        end_date=cycle.end_date,
        order_strategy=cycle.order_strategy,
        status=cycle.status.value if hasattr(cycle.status, "value") else cycle.status,
        is_mandatory=cycle.is_mandatory,
        created_at=cycle.created_at,
    )


def _tontine_out(tontine: Tontine) -> TontineOut:
    cycles = sorted(tontine.cycles, key=lambda c: c.cycle_number)
    # Cycle courant = le plus récent actif, sinon le dernier.
    current = next((c for c in reversed(cycles) if c.status == TontineCycleStatus.ACTIVE), None)
    current = current or (cycles[-1] if cycles else None)
    return TontineOut(
        id=tontine.id,
        association_id=tontine.association_id,
        name=tontine.name,
        slug=tontine.slug,
        description=tontine.description,
        is_active=tontine.is_active,
        round_amount=tontine.round_amount,
        frequency=tontine.frequency,
        custom_interval_days=tontine.custom_interval_days,
        beneficiaries_per_round=tontine.beneficiaries_per_round,
        beneficiary_pays=tontine.beneficiary_pays,
        selection_method=tontine.selection_method,
        created_at=tontine.created_at,
        cycles_count=len(cycles),
        current_cycle=_cycle_out(current) if current else None,
    )


async def _tontine_detail(db: AsyncSession, tontine: Tontine) -> TontineDetail:
    base = _tontine_out(tontine).model_dump()
    base.pop("current_cycle", None)
    cycles_detail = []
    for c in sorted(tontine.cycles, key=lambda c: c.cycle_number):
        mm = await _meeting_map_for_cycle(db, c.id)
        cycles_detail.append(_cycle_detail(c, mm))
    current = next(
        (c for c in reversed(cycles_detail) if c.status == "active"),
        cycles_detail[-1] if cycles_detail else None,
    )
    return TontineDetail(**base, current_cycle=current, cycles=cycles_detail)


# ── Endpoints ───────────────────────────────────────────────────────────────
@router.get("", response_model=List[TontineOut])
async def list_tontines(
    association_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assoc = await _get_assoc_or_404(db, association_id)
    _check_access(current_user, assoc)
    res = await db.execute(
        select(Tontine)
        .options(selectinload(Tontine.cycles))
        .where(Tontine.association_id == association_id)
        .order_by(Tontine.created_at.desc())
    )
    return [_tontine_out(t) for t in res.scalars().all()]


@router.get("/{tontine_id}", response_model=TontineDetail)
async def get_tontine(
    tontine_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tontine = await _load_tontine(db, tontine_id)
    assoc = await _get_assoc_or_404(db, tontine.association_id)
    _check_access(current_user, assoc)
    return await _tontine_detail(db, tontine)


@router.post("", response_model=TontineDetail, status_code=status.HTTP_201_CREATED)
async def create_tontine(
    payload: TontineCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assoc = await _get_assoc_or_404(db, payload.association_id)
    _check_access(current_user, assoc)

    ids = list(payload.participant_ids)
    # Doublons autorisés : un membre peut tenir plusieurs noms/parts.
    order, labels = _resolve_order_and_labels(
        ids, payload.participant_names, payload.shuffle
    )
    if ids:
        res = await db.execute(
            select(Membership.id).where(
                Membership.id.in_(set(ids)),
                Membership.association_id == payload.association_id,
            )
        )
        found = {m for m in res.scalars().all()}
        missing = [str(i) for i in set(ids) if i not in found]
        if missing:
            raise HTTPException(422, f"Membres introuvables : {', '.join(missing)}")
    if payload.is_mandatory and payload.excluded_membership_ids:
        raise HTTPException(422, "Exclusions impossibles quand la tontine est obligatoire.")

    slug = await _unique_slug(db, payload.association_id, payload.name)

    tontine = Tontine(
        association_id=payload.association_id,
        name=payload.name,
        slug=slug,
        description=payload.description,
        round_amount=payload.round_amount,
        frequency=payload.frequency,
        custom_interval_days=payload.custom_interval_days,
        beneficiaries_per_round=payload.beneficiaries_per_round,
        beneficiary_pays=payload.beneficiary_pays,
        selection_method=payload.selection_method,
    )
    db.add(tontine)
    await db.flush()

    # Caisse système + fonds dédiés à la tontine (réutilisés par tous ses cycles).
    treasury = await get_or_create_treasury(db, assoc)
    fund = Fund(
        treasury_id=treasury.id,
        kind=FundKind.TONTINE,
        ref_key=slug,
        name=f"Tontine — {payload.name}",
        description="Fonds dédié à cette tontine.",
        is_system=True,
    )
    db.add(fund)
    await db.flush()
    db.add(
        Caisse(
            association_id=payload.association_id,
            fund_id=fund.id,
            name=f"Tontine — {payload.name}",
            slug=slug,
            description="Caisse système liée à cette tontine (auto-créée).",
            category=CaisseCategory.SYSTEM,
            is_system=True,
        )
    )

    await upsert_tontine_activity(
        db,
        association_id=payload.association_id,
        cycle_id=tontine.id,  # l'activité pointe sur la tontine (durable)
        name=payload.name,
        slug=slug,
        round_amount=payload.round_amount,
    )

    # Sans participant → 1er cycle créé en brouillon (membres ajoutés ensuite via
    # la config de la tontine). Avec participants → cycle actif + séances d'office.
    await _build_cycle(
        db,
        tontine=tontine,
        cycle_number=1,
        start_date=payload.start_date,
        participant_order=order,
        is_mandatory=payload.is_mandatory,
        excluded_ids=payload.excluded_membership_ids,
        activate=bool(order),
        name_labels=labels,
    )

    await db.commit()
    tontine = await _load_tontine(db, tontine.id)
    return await _tontine_detail(db, tontine)


@router.post("/{tontine_id}/cycles", response_model=TontineDetail, status_code=status.HTTP_201_CREATED)
async def create_next_cycle(
    tontine_id: UUID,
    payload: NextCycleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Génère le cycle suivant — hérite config + participants + activités."""
    tontine = await _load_tontine(db, tontine_id)
    assoc = await _get_assoc_or_404(db, tontine.association_id)
    _check_access(current_user, assoc)

    cycles = sorted(tontine.cycles, key=lambda c: c.cycle_number)
    if cycles and cycles[-1].status == TontineCycleStatus.ACTIVE:
        raise HTTPException(409, "Le cycle courant est encore actif — terminez-le d'abord.")
    last = cycles[-1] if cycles else None
    next_number = (last.cycle_number + 1) if last else 1

    # Participants hérités du cycle précédent (ordre des tours), sinon erreur.
    if last:
        order: list[UUID] = []
        for rnd in sorted(last.rounds, key=lambda r: r.round_number):
            order.extend(b.membership_id for b in rnd.beneficiaries)
        # opt-outs hérités
        op_res = await db.execute(
            select(TontineParticipation.membership_id).where(
                TontineParticipation.cycle_id == last.id,
                TontineParticipation.is_participating.is_(False),
            )
        )
        excluded = [m for m in op_res.scalars().all()]
        is_mandatory = last.is_mandatory
    else:
        raise HTTPException(422, "Aucun cycle précédent à hériter.")

    start = payload.start_date or _next_date(
        last.end_date or last.start_date, tontine.frequency, tontine.custom_interval_days
    )

    await _build_cycle(
        db,
        tontine=tontine,
        cycle_number=next_number,
        start_date=start,
        participant_order=order,
        is_mandatory=is_mandatory,
        excluded_ids=excluded,
    )
    await db.commit()
    tontine = await _load_tontine(db, tontine_id)
    return await _tontine_detail(db, tontine)


@router.put("/cycles/{cycle_id}/participants", response_model=TontineDetail)
async def set_cycle_participants(
    cycle_id: UUID,
    payload: CycleParticipantsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Définit/édite les participants d'un cycle BROUILLON et (re)génère ses tours
    + séances. Permet de créer une tontine sans membre puis d'ajouter les membres
    depuis sa config. Interdit une fois le cycle démarré (actif)."""
    cycle = await _load_cycle(db, cycle_id)
    tontine = await _load_tontine(db, cycle.tontine_id)
    assoc = await _get_assoc_or_404(db, tontine.association_id)
    _check_access(current_user, assoc)

    if cycle.status != TontineCycleStatus.DRAFT:
        raise HTTPException(409, "Seul un cycle brouillon peut être modifié.")

    ids = list(payload.participant_ids)
    # Doublons autorisés : un membre peut tenir plusieurs noms/parts.
    order, labels = _resolve_order_and_labels(
        ids, payload.participant_names, payload.shuffle
    )
    if ids:
        res = await db.execute(
            select(Membership.id).where(
                Membership.id.in_(set(ids)), Membership.association_id == assoc.id
            )
        )
        found = set(res.scalars().all())
        missing = [str(i) for i in set(ids) if i not in found]
        if missing:
            raise HTTPException(422, f"Membres introuvables : {', '.join(missing)}")
    if payload.is_mandatory and payload.excluded_membership_ids:
        raise HTTPException(422, "Exclusions impossibles quand la tontine est obligatoire.")

    if payload.start_date:
        cycle.start_date = payload.start_date
    cycle.is_mandatory = payload.is_mandatory

    await _clear_cycle_content(db, cycle)
    await _populate_cycle(
        db,
        cycle=cycle,
        tontine=tontine,
        participant_order=order,
        excluded_ids=payload.excluded_membership_ids,
        activate=False,
        name_labels=labels,
    )
    await db.commit()
    # Le cycle a été pré-chargé puis vidé/régénéré via bulk delete : on détache
    # tout pour que le rechargement reflète bien les nouveaux tours.
    tid = cycle.tontine_id
    db.expunge_all()
    tontine = await _load_tontine(db, tid)
    return await _tontine_detail(db, tontine)


@router.patch("/beneficiaries/{beneficiary_id}/rename", response_model=TontineDetail)
async def rename_beneficiary(
    beneficiary_id: UUID,
    payload: BeneficiaryRename,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Renomme un nom/part d'un bénéficiaire. Admin + bureau, à tout moment
    (même cycle démarré) : ce n'est qu'un libellé."""
    b = (
        await db.execute(
            select(TontineRoundBeneficiary).where(TontineRoundBeneficiary.id == beneficiary_id)
        )
    ).scalar_one_or_none()
    if not b:
        raise HTTPException(404, "Bénéficiaire introuvable")
    rnd = (
        await db.execute(select(TontineRound).where(TontineRound.id == b.round_id))
    ).scalar_one()
    cycle = await _load_cycle(db, rnd.cycle_id)
    tontine = await _load_tontine(db, cycle.tontine_id)
    assoc = await _get_assoc_or_404(db, tontine.association_id)
    _check_access(current_user, assoc)
    if not await _user_has_bureau_role(db, current_user, assoc.id):
        raise HTTPException(403, "Réservé aux admins et membres du bureau.")

    b.name_label = payload.name.strip()
    await db.commit()
    tid = tontine.id
    db.expunge_all()
    tontine = await _load_tontine(db, tid)
    return await _tontine_detail(db, tontine)


@router.post("/cycles/{cycle_id}/activate", response_model=TontineDetail)
async def activate_cycle(
    cycle_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Démarre un cycle BROUILLON : le 1er tour passe en collecte. Nécessite au
    moins un participant (donc un tour)."""
    cycle = await _load_cycle(db, cycle_id)
    tontine = await _load_tontine(db, cycle.tontine_id)
    assoc = await _get_assoc_or_404(db, tontine.association_id)
    _check_access(current_user, assoc)

    if cycle.status != TontineCycleStatus.DRAFT:
        raise HTTPException(409, "Ce cycle n'est pas un brouillon.")
    if cycle.rounds_count < 1:
        raise HTTPException(422, "Ajoutez au moins un participant avant de démarrer le cycle.")

    cycle.status = TontineCycleStatus.ACTIVE
    cycle.current_round_number = 1
    for r in cycle.rounds:
        if r.round_number == 1:
            r.status = TontineRoundStatus.COLLECTING
    await db.commit()
    tontine = await _load_tontine(db, cycle.tontine_id)
    return await _tontine_detail(db, tontine)


@router.post("/cycles/{cycle_id}/rounds/{round_id}/payout", response_model=TontineCycleDetail)
async def payout_round(
    cycle_id: UUID,
    round_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cycle = await _load_cycle(db, cycle_id)
    tontine = await _load_tontine(db, cycle.tontine_id)
    assoc = await _get_assoc_or_404(db, tontine.association_id)
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
    fund = await _get_tontine_fund(db, treasury, tontine)
    if fund is None:
        raise HTTPException(500, "Fonds tontine introuvable")

    related = rnd.beneficiaries[0].membership_id if len(rnd.beneficiaries) == 1 else None
    movement = await post_movement(
        db,
        treasury=treasury,
        direction=MovementDirection.OUT,
        amount=pot,
        allocations=[Allocation(fund=fund, is_credit=False, amount=pot)],
        occurred_on=date.today(),
        source_type="tontine_payout",
        source_id=rnd.id,
        recorded_by_id=current_user.id,
        related_membership_id=related,
        description=f"Tontine {tontine.name} — tour {rnd.round_number}",
        commit=False,
    )
    rnd.status = TontineRoundStatus.PAID_OUT
    rnd.paid_out_date = date.today()
    rnd.paid_out_amount = pot
    rnd.collected_amount = pot
    rnd.payout_movement_id = movement.id

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

    await db.commit()
    cycle = await _load_cycle(db, cycle_id)
    mm = await _meeting_map_for_cycle(db, cycle.id)
    return _cycle_detail(cycle, mm)


@router.post("/cycles/{cycle_id}/cancel", response_model=TontineCycleDetail)
async def cancel_cycle(
    cycle_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cycle = await _load_cycle(db, cycle_id)
    tontine = await _load_tontine(db, cycle.tontine_id)
    assoc = await _get_assoc_or_404(db, tontine.association_id)
    _check_access(current_user, assoc)
    if cycle.status == TontineCycleStatus.COMPLETED:
        raise HTTPException(409, "Cycle déjà terminé")
    cycle.status = TontineCycleStatus.CANCELLED
    await db.commit()
    cycle = await _load_cycle(db, cycle_id)
    mm = await _meeting_map_for_cycle(db, cycle.id)
    return _cycle_detail(cycle, mm)


@router.patch("/cycles/{cycle_id}/rounds/{round_id}/meeting", response_model=TontineCycleDetail)
async def relink_round_to_meeting(
    cycle_id: UUID,
    round_id: UUID,
    meeting_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cycle = await _load_cycle(db, cycle_id)
    tontine = await _load_tontine(db, cycle.tontine_id)
    assoc = await _get_assoc_or_404(db, tontine.association_id)
    _check_access(current_user, assoc)

    rnd = next((r for r in cycle.rounds if r.id == round_id), None)
    if not rnd:
        raise HTTPException(404, "Tour introuvable")
    if rnd.status == TontineRoundStatus.PAID_OUT:
        raise HTTPException(409, "Tour déjà versé — non déplaçable.")

    res = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id, Meeting.association_id == assoc.id)
    )
    new_meeting = res.scalar_one_or_none()
    if not new_meeting:
        raise HTTPException(422, "Séance cible introuvable.")

    link_res = await db.execute(
        select(TontineMeetingLink).where(TontineMeetingLink.round_id == round_id)
    )
    link = link_res.scalar_one_or_none()
    if link and link.is_locked:
        raise HTTPException(409, "Lien tour ↔ séance verrouillé.")
    if link:
        link.meeting_id = new_meeting.id
    else:
        db.add(TontineMeetingLink(round_id=round_id, meeting_id=new_meeting.id))
    rnd.scheduled_date = new_meeting.scheduled_on

    await db.commit()
    cycle = await _load_cycle(db, cycle_id)
    mm = await _meeting_map_for_cycle(db, cycle.id)
    return _cycle_detail(cycle, mm)
