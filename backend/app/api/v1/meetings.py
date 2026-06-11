"""Meetings CRUD + lifecycle (open/close) + attendances + entries."""
from datetime import date as date_cls, datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import _user_has_bureau_role, get_current_user, get_db
from app.models.association import Association
from app.models.caisse import Caisse, CaisseContributorBalance
from app.models.finance import Fund, FundKind, MovementDirection
from app.models.loan import Loan, LoanInstallment, LoanInstallmentStatus, LoanStatus
from app.models.role import Membership, MembershipStatus
from app.models.social_aid import AidType, SocialAidCase, SocialAidCaseStatus
from app.models.meeting import (
    Activity,
    ActivityType,
    AttendanceStatus,
    EntryStatus,
    Meeting,
    MeetingActivityEntry,
    MeetingAttendance,
    MeetingStatus,
)
from app.models.tontine import (
    Tontine,
    TontineCycle,
    TontineMeetingLink,
    TontineParticipation,
    TontineRound,
    TontineRoundBeneficiary,
    TontineRoundStatus,
)
from app.models.user import User
from app.services.finance import Allocation, get_or_create_treasury, post_movement
from app.services import planning

# Which fund each meeting activity type feeds when the meeting is closed.
_ACTIVITY_FUND: dict[ActivityType, FundKind] = {
    ActivityType.MONTHLY_CONTRIBUTION: FundKind.GENERAL,
    ActivityType.INSURANCE_CONTRIBUTION: FundKind.INSURANCE,
    ActivityType.TONTINE_CONTRIBUTION: FundKind.TONTINE,
    ActivityType.LOAN_REPAYMENT: FundKind.GENERAL,
    ActivityType.PENALTY: FundKind.GENERAL,
    ActivityType.SAVINGS_DEPOSIT: FundKind.SAVINGS,
    ActivityType.EXCEPTIONAL_DONATION: FundKind.GENERAL,
    ActivityType.PROJECT_CONTRIBUTION: FundKind.GENERAL,
    ActivityType.OTHER: FundKind.GENERAL,
}


async def _resolve_fund_for_entry(
    db: AsyncSession,
    treasury,
    funds_by_kind: dict[FundKind, "Fund"],
    activity: Activity | None,
) -> "Fund | None":
    """Phase 3 fund routing — driven by activity.config when set.

    Precedence:
      1. config.caisse_id     → Caisse.fund (custom caisses + system aid caisse).
      2. config.cycle_id      → Fund(kind=TONTINE, ref_key=cycle.slug).
      3. config.aid_type_id   → AidType.source_caisse → fund.
      4. _ACTIVITY_FUND[type] → legacy mapping.
    """
    if activity is None:
        return funds_by_kind.get(FundKind.GENERAL)
    cfg = activity.config or {}

    # 1. Direct caisse pin — most common for Phase 3 (custom caisses).
    caisse_id_raw = cfg.get("caisse_id")
    if caisse_id_raw:
        try:
            cid = UUID(caisse_id_raw) if isinstance(caisse_id_raw, str) else caisse_id_raw
            res = await db.execute(select(Caisse).where(Caisse.id == cid))
            caisse = res.scalar_one_or_none()
            if caisse:
                fund_res = await db.execute(select(Fund).where(Fund.id == caisse.fund_id))
                fund = fund_res.scalar_one_or_none()
                if fund:
                    return fund
        except (ValueError, TypeError):
            pass

    # 2. Tontine pin — fonds dédié TONTINE par ref_key == tontine.slug.
    tontine_slug = cfg.get("tontine_slug")
    if tontine_slug:
        for f in treasury.funds:
            if f.kind == FundKind.TONTINE and f.ref_key == tontine_slug:
                return f

    # 3. Aid type pin — route to the type's source caisse.
    aid_type_id_raw = cfg.get("aid_type_id")
    if aid_type_id_raw:
        try:
            aid_id = UUID(aid_type_id_raw) if isinstance(aid_type_id_raw, str) else aid_type_id_raw
            res = await db.execute(
                select(Fund)
                .join(Caisse, Caisse.fund_id == Fund.id)
                .join(AidType, AidType.source_caisse_id == Caisse.id)
                .where(AidType.id == aid_id)
            )
            fund = res.scalar_one_or_none()
            if fund:
                return fund
        except (ValueError, TypeError):
            pass

    # 4. Legacy: fall back to the type → fund kind mapping.
    kind = _ACTIVITY_FUND.get(activity.type, FundKind.GENERAL)
    return funds_by_kind.get(kind) or funds_by_kind.get(FundKind.GENERAL)
from app.schemas.meeting import (
    AgendaRow,
    AttendanceOut,
    AttendanceUpsert,
    EntryCreate,
    EntryOut,
    EntryUpdate,
    MeetingAgenda,
    MeetingCreate,
    MeetingDetail,
    MeetingGenerateRequest,
    MeetingGenerateResult,
    MemberAgenda,
    MemberSavePayload,
    MeetingOut,
    MeetingUpdate,
)

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────

async def _get_assoc_or_404(db: AsyncSession, association_id: UUID) -> Association:
    result = await db.execute(select(Association).where(Association.id == association_id))
    assoc = result.scalar_one_or_none()
    if not assoc:
        raise HTTPException(status_code=404, detail="Association not found")
    return assoc


def _check_access(user: User, assoc: Association) -> None:
    if user.is_super_admin:
        return
    if user.groupement_id != assoc.groupement_id:
        raise HTTPException(status_code=403, detail="Forbidden")


async def _require_bureau(db: AsyncSession, user: User, assoc: Association) -> None:
    """Gate les actions opérationnelles de séance (créer / ouvrir / clôturer /
    annuler une séance, saisir des données). Réservé aux admins et membres du
    bureau ; un membre simple ne peut pas agir."""
    if not await _user_has_bureau_role(db, user, assoc.id):
        raise HTTPException(
            status_code=403,
            detail="Réservé au bureau de l'association (admin, trésorier, secrétaire…).",
        )


async def _get_meeting_or_404(db: AsyncSession, meeting_id: UUID) -> Meeting:
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return m


async def _load_meeting_detail(db: AsyncSession, meeting_id: UUID) -> Meeting:
    result = await db.execute(
        select(Meeting)
        .options(
            selectinload(Meeting.attendances),
            selectinload(Meeting.entries),
        )
        .where(Meeting.id == meeting_id)
    )
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return m


def _meeting_to_out(m: Meeting) -> MeetingOut:
    return MeetingOut(
        id=m.id,
        association_id=m.association_id,
        title=m.title,
        description=m.description,
        scheduled_on=m.scheduled_on,
        started_at=m.started_at,
        closed_at=m.closed_at,
        location=m.location,
        status=m.status.value if hasattr(m.status, "value") else m.status,
        facilitator_id=m.facilitator_id,
        created_by_id=m.created_by_id,
        agenda=m.agenda,
        notes=m.notes,
        report_url=m.report_url,
        total_in=m.total_in,
        total_out=m.total_out,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _attendance_to_out(a: MeetingAttendance) -> AttendanceOut:
    return AttendanceOut(
        id=a.id,
        meeting_id=a.meeting_id,
        membership_id=a.membership_id,
        status=a.status.value if hasattr(a.status, "value") else a.status,
        notes=a.notes,
        excuse_reason=a.excuse_reason,
    )


def _entry_to_out(e: MeetingActivityEntry) -> EntryOut:
    return EntryOut(
        id=e.id,
        meeting_id=e.meeting_id,
        membership_id=e.membership_id,
        activity_id=e.activity_id,
        amount=e.amount,
        data=e.data,
        status=e.status.value if hasattr(e.status, "value") else e.status,
        movement_id=e.movement_id,
        recorded_by_id=e.recorded_by_id,
        recorded_at=e.recorded_at,
        corrects_entry_id=e.corrects_entry_id,
        correction_reason=e.correction_reason,
        notes=e.notes,
        created_at=e.created_at,
        updated_at=e.updated_at,
    )


# ── Meetings CRUD ──────────────────────────────────────────────────────────

@router.get("", response_model=List[MeetingOut])
async def list_meetings(
    association_id: UUID = Query(...),
    meeting_status: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assoc = await _get_assoc_or_404(db, association_id)
    _check_access(current_user, assoc)

    stmt = select(Meeting).where(Meeting.association_id == association_id)
    if meeting_status:
        stmt = stmt.where(Meeting.status == meeting_status)
    stmt = stmt.order_by(Meeting.scheduled_on.desc())
    result = await db.execute(stmt)
    return [_meeting_to_out(m) for m in result.scalars().all()]


@router.get("/{meeting_id}", response_model=MeetingDetail)
async def get_meeting(
    meeting_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = await _load_meeting_detail(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)

    attendances = m.attendances
    entries = m.entries

    # Visibilité : si l'asso restreint la vue (meetings.member_sees_all == False)
    # et que le demandeur n'est pas du bureau, il ne voit QUE ses propres lignes.
    member_sees_all = ((assoc.config or {}).get("meetings") or {}).get("member_sees_all", True)
    if not member_sees_all and not await _user_has_bureau_role(db, current_user, assoc.id):
        own = await db.execute(
            select(Membership.id).where(
                Membership.user_id == current_user.id,
                Membership.association_id == assoc.id,
            )
        )
        own_ids = set(own.scalars().all())
        attendances = [a for a in attendances if a.membership_id in own_ids]
        entries = [e for e in entries if e.membership_id in own_ids]

    return MeetingDetail(
        **_meeting_to_out(m).model_dump(),
        attendances=[_attendance_to_out(a) for a in attendances],
        entries=[_entry_to_out(e) for e in entries],
    )


@router.post("", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    payload: MeetingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assoc = await _get_assoc_or_404(db, payload.association_id)
    _check_access(current_user, assoc)
    await _require_bureau(db, current_user, assoc)

    if payload.scheduled_on < date_cls.today():
        raise HTTPException(422, "La date de la séance ne peut pas être dans le passé.")

    meeting = Meeting(
        association_id=payload.association_id,
        title=payload.title,
        description=payload.description,
        scheduled_on=payload.scheduled_on,
        location=payload.location,
        agenda=payload.agenda,
        facilitator_id=payload.facilitator_id,
        created_by_id=current_user.id,
        status=MeetingStatus.PLANNED,
    )
    db.add(meeting)
    await db.commit()
    await db.refresh(meeting)
    return _meeting_to_out(meeting)


@router.patch("/{meeting_id}", response_model=MeetingOut)
async def update_meeting(
    meeting_id: UUID,
    payload: MeetingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = await _get_meeting_or_404(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)
    await _require_bureau(db, current_user, assoc)

    if m.status == MeetingStatus.CLOSED:
        raise HTTPException(status_code=409, detail="Cannot edit a closed meeting")

    data = payload.model_dump(exclude_unset=True)
    if "status" in data:
        try:
            data["status"] = MeetingStatus(data["status"])
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid status '{data['status']}'")

    # Refus d'un (re)planning dans le passé.
    if (
        "scheduled_on" in data
        and data["scheduled_on"] != m.scheduled_on
        and data["scheduled_on"] < date_cls.today()
    ):
        raise HTTPException(422, "La date de la séance ne peut pas être dans le passé.")

    # Phase 4 — Si la date change ET un round tontine est rattaché à cette
    # séance, on synchronise round.scheduled_date (sauf lien locked).
    if "scheduled_on" in data and data["scheduled_on"] != m.scheduled_on:
        link_res = await db.execute(
            select(TontineMeetingLink, TontineRound)
            .join(TontineRound, TontineRound.id == TontineMeetingLink.round_id)
            .where(TontineMeetingLink.meeting_id == m.id)
        )
        rows = list(link_res.all())
        for link, rnd in rows:
            if link.is_locked:
                raise HTTPException(
                    409,
                    "Une tontine verrouillée est attachée à cette séance — "
                    "décale le cycle entier au lieu de cette séance.",
                )
            if rnd.status == TontineRoundStatus.PAID_OUT:
                raise HTTPException(
                    409,
                    "Un tour de tontine déjà versé est attaché à cette séance — "
                    "la date ne peut plus changer.",
                )
            rnd.scheduled_date = data["scheduled_on"]

    for field, value in data.items():
        setattr(m, field, value)

    await db.commit()
    await db.refresh(m)
    return _meeting_to_out(m)


@router.post("/{meeting_id}/cancel", response_model=MeetingOut)
async def cancel_meeting(
    meeting_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Annulation d'une séance individuelle (Phase 4).

    Si la séance héberge un tour de tontine non versé, on rattache le tour à
    la prochaine séance PLANNED de l'association ; si aucune n'est disponible,
    on génère un nouveau créneau via la cadence configurée.
    """
    m = await _get_meeting_or_404(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)
    await _require_bureau(db, current_user, assoc)

    if m.status == MeetingStatus.CLOSED:
        raise HTTPException(409, "Une séance clôturée ne peut plus être annulée.")
    if m.status == MeetingStatus.CANCELLED:
        return _meeting_to_out(m)

    # Tontine rounds attachés — réorienter ou repousser.
    link_res = await db.execute(
        select(TontineMeetingLink, TontineRound)
        .join(TontineRound, TontineRound.id == TontineMeetingLink.round_id)
        .where(TontineMeetingLink.meeting_id == m.id)
    )
    rows = list(link_res.all())
    for link, rnd in rows:
        if link.is_locked:
            raise HTTPException(
                409,
                "Une tontine verrouillée est attachée à cette séance — "
                "annule le cycle entier à la place.",
            )
        if rnd.status == TontineRoundStatus.PAID_OUT:
            raise HTTPException(
                409, "Un tour déjà versé empêche l'annulation de cette séance."
            )

        # Cherche la prochaine séance PLANNED ≥ m.scheduled_on (excluant celle
        # qu'on annule). Si rien, on génère un nouveau créneau via la cadence.
        next_res = await db.execute(
            select(Meeting)
            .where(
                Meeting.association_id == assoc.id,
                Meeting.status == MeetingStatus.PLANNED,
                Meeting.id != m.id,
                Meeting.scheduled_on >= m.scheduled_on,
            )
            .order_by(Meeting.scheduled_on)
            .limit(1)
        )
        target = next_res.scalar_one_or_none()
        if target is None:
            nxt_date = planning.next_date_after(assoc, m.scheduled_on)
            target = Meeting(
                association_id=assoc.id,
                title=planning.default_title(assoc, nxt_date),
                scheduled_on=nxt_date,
                location=planning.default_location(assoc),
                status=MeetingStatus.PLANNED,
            )
            db.add(target)
            await db.flush()
        link.meeting_id = target.id
        rnd.scheduled_date = target.scheduled_on

    m.status = MeetingStatus.CANCELLED
    await db.commit()
    await db.refresh(m)
    return _meeting_to_out(m)


# ── Lifecycle ──────────────────────────────────────────────────────────────

@router.post("/{meeting_id}/open", response_model=MeetingOut)
async def open_meeting(
    meeting_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Transition PLANNED → ONGOING."""
    m = await _get_meeting_or_404(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)
    await _require_bureau(db, current_user, assoc)

    if m.status != MeetingStatus.PLANNED:
        raise HTTPException(status_code=409, detail=f"Meeting is already {m.status.value}")

    m.status = MeetingStatus.ONGOING
    m.started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(m)
    return _meeting_to_out(m)


@router.post("/{meeting_id}/close", response_model=MeetingOut)
async def close_meeting(
    meeting_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Transition ONGOING → CLOSED. Validates all DRAFT entries → RECORDED."""
    m = await _load_meeting_detail(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)
    await _require_bureau(db, current_user, assoc)

    if m.status != MeetingStatus.ONGOING:
        raise HTTPException(status_code=409, detail=f"Meeting is not ongoing (status={m.status.value})")

    now = datetime.now(timezone.utc)

    # Validate all DRAFT entries → RECORDED.
    for entry in m.entries:
        if entry.status == EntryStatus.DRAFT:
            entry.status = EntryStatus.RECORDED
            entry.recorded_by_id = current_user.id
            entry.recorded_at = now

    # Post each non-voided entry to the treasury (one IN movement per entry).
    # Routing precedence (Phase 3):
    #   1. activity.config.caisse_id      → Caisse.fund (CUSTOM / SYSTEM)
    #   2. activity.config.cycle_id       → cycle-dedicated Fund(TONTINE, ref_key=slug)
    #   3. activity.config.aid_type_id    → AidType.source_caisse → fund
    #   4. _ACTIVITY_FUND[activity.type]  → legacy GENERAL/INSURANCE/TONTINE/SAVINGS
    treasury = await get_or_create_treasury(db, assoc)
    funds_by_kind = {f.kind: f for f in treasury.funds}

    act_res = await db.execute(
        select(Activity).where(Activity.association_id == m.association_id)
    )
    activities = {a.id: a for a in act_res.scalars().all()}

    # Phase 7 (Fred) — tracking apport_cum par cotisant. On garde la valeur pour
    # toutes les caisses (sauf TONTINE qui a sa logique cycle/tour). L'admin
    # peut basculer la caisse en mode SHARED_PRO_RATA quand il veut : le
    # compteur est déjà à jour.
    caisses_by_fund_id: dict = {}
    caisse_rows = await db.execute(
        select(Caisse).where(Caisse.association_id == m.association_id)
    )
    for c in caisse_rows.scalars().all():
        caisses_by_fund_id[c.fund_id] = c
    ccb_cache: dict[tuple, CaisseContributorBalance] = {}

    total_in = 0
    for entry in m.entries:
        if entry.status == EntryStatus.VOIDED or entry.movement_id is not None:
            continue
        if entry.amount <= 0:
            continue
        activity = activities.get(entry.activity_id)
        fund = await _resolve_fund_for_entry(db, treasury, funds_by_kind, activity)
        if fund is None:
            continue
        movement = await post_movement(
            db,
            treasury=treasury,
            direction=MovementDirection.IN,
            amount=entry.amount,
            allocations=[Allocation(fund=fund, is_credit=True, amount=entry.amount)],
            occurred_on=m.scheduled_on,
            source_type="meeting_entry",
            source_id=entry.id,
            recorded_by_id=current_user.id,
            related_membership_id=entry.membership_id,
            description=f"{m.title}",
            commit=False,
        )
        entry.movement_id = movement.id
        total_in += entry.amount

        # apport_cum tracking (Phase 7).
        caisse = caisses_by_fund_id.get(fund.id)
        if caisse and fund.kind != FundKind.TONTINE:
            key = (caisse.id, entry.membership_id)
            bal = ccb_cache.get(key)
            if bal is None:
                res = await db.execute(
                    select(CaisseContributorBalance).where(
                        CaisseContributorBalance.caisse_id == caisse.id,
                        CaisseContributorBalance.membership_id == entry.membership_id,
                    )
                )
                bal = res.scalar_one_or_none()
                if bal is None:
                    bal = CaisseContributorBalance(
                        caisse_id=caisse.id,
                        membership_id=entry.membership_id,
                        apport_cum=0,
                        apport_cum_at_period_start=0,
                        interest_cum=0,
                    )
                    db.add(bal)
                    await db.flush()
                ccb_cache[key] = bal
            bal.apport_cum += entry.amount

    m.status = MeetingStatus.CLOSED
    m.closed_at = now
    m.total_in = total_in

    # PV auto : Document + PDF visible à tous les membres (sur MinIO). Échec
    # silencieux — la clôture ne doit jamais bloquer.
    from app.services.meeting_report import generate_meeting_report

    await generate_meeting_report(
        db,
        meeting=m,
        association=assoc,
        activities=activities.values(),
        recorded_by=current_user,
    )

    # Phase 7 (Fred) — auto-trigger des distributions sur les caisses SHARED_PRO_RATA
    # dont la cadence est due (per_meeting / fin de mois / fin de trimestre / fin
    # d'année). Échec individuel silencieux pour ne pas bloquer la clôture.
    from app.services.caisse_distribution import close_distribution_period, is_period_due

    for caisse in caisses_by_fund_id.values():
        try:
            if is_period_due(caisse, m.scheduled_on):
                await close_distribution_period(
                    db,
                    caisse=caisse,
                    period_end=m.scheduled_on,
                    closed_by=current_user,
                    meeting_title=m.title,
                )
        except Exception:  # pragma: no cover — best effort.
            import logging
            logging.getLogger(__name__).exception(
                "Échec de l'auto-distribution pour la caisse %s", caisse.id
            )

    # ── Email de récap envoyé à tous les membres actifs ──────────────────────
    # Calculé maintenant pour pouvoir passer les chiffres au mailer après commit.
    by_status: dict[str, int] = {}
    for a in m.attendances:
        key = a.status.value if hasattr(a.status, "value") else str(a.status)
        by_status[key] = by_status.get(key, 0) + 1
    recap_present = by_status.get("present", 0) + by_status.get("late", 0)
    recap_absent = by_status.get("absent", 0)
    recap_excused = by_status.get("excused", 0)
    recap_total_str = f"{total_in:,}".replace(",", " ") + f" {assoc.currency}"
    recap_title = m.title
    recap_notes = m.notes
    recap_agenda = m.description
    recap_report_url = m.report_url
    recap_date_str = m.scheduled_on.strftime("%d/%m/%Y")

    # Rolling auto-extension: if the future-PLANNED window has fallen below the
    # configured horizon, top it up by one. Cheap (one row added).
    await _auto_extend_planning(db, assoc)

    await db.commit()
    await db.refresh(m)

    # ── Notification email de récap (post-commit, best effort) ──────────────
    try:
        from app.services.mailer import MailError, send_meeting_recap_email
        from app.models.user import User as _User

        members_res = await db.execute(
            select(Membership, _User)
            .join(_User, _User.id == Membership.user_id)
            .where(
                Membership.association_id == assoc.id,
                Membership.status == MembershipStatus.ACTIVE,
                _User.is_active.is_(True),
                _User.email.is_not(None),
            )
        )
        for mem, usr in members_res.all():
            if not usr.email:
                continue
            try:
                await send_meeting_recap_email(
                    to=usr.email,
                    member_name=usr.full_name,
                    association_name=assoc.name,
                    meeting_title=recap_title,
                    meeting_date=recap_date_str,
                    presents=recap_present,
                    absents=recap_absent,
                    excused=recap_excused,
                    total_collected=recap_total_str,
                    agenda=recap_agenda,
                    notes=recap_notes,
                    report_url=recap_report_url,
                )
            except MailError:
                pass  # SMTP down → on continue avec les autres membres
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "Échec de l'envoi du récap de clôture (séance %s)", m.id
        )

    return _meeting_to_out(m)


async def _auto_extend_planning(db: AsyncSession, assoc: Association) -> None:
    """Maintain the rolling window of N future PLANNED meetings.

    Called after closing a meeting: if `planned_count < horizon`, append exactly
    one new meeting at the cadence date that follows the latest known one.
    Schedules in the past (e.g. cadence wasn't configured before) are skipped.
    """
    today = date_cls.today()
    res = await db.execute(
        select(Meeting).where(
            Meeting.association_id == assoc.id,
            Meeting.status == MeetingStatus.PLANNED,
            Meeting.scheduled_on >= today,
        )
    )
    planned_future = list(res.scalars().all())
    target = planning.horizon(assoc)
    if len(planned_future) >= target:
        return

    last_res = await db.execute(
        select(Meeting)
        .where(Meeting.association_id == assoc.id)
        .order_by(Meeting.scheduled_on.desc())
        .limit(1)
    )
    last = last_res.scalar_one_or_none()
    anchor = last.scheduled_on if last else today
    nxt = planning.next_date_after(assoc, anchor)
    if nxt < today:
        return
    db.add(
        Meeting(
            association_id=assoc.id,
            title=planning.default_title(assoc, nxt),
            scheduled_on=nxt,
            location=planning.default_location(assoc),
            status=MeetingStatus.PLANNED,
        )
    )


# ── Attendances ────────────────────────────────────────────────────────────

@router.get("/{meeting_id}/attendances", response_model=List[AttendanceOut])
async def list_attendances(
    meeting_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = await _get_meeting_or_404(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)

    result = await db.execute(
        select(MeetingAttendance).where(MeetingAttendance.meeting_id == meeting_id)
    )
    return [_attendance_to_out(a) for a in result.scalars().all()]


@router.put("/{meeting_id}/attendances", response_model=List[AttendanceOut])
async def upsert_attendances(
    meeting_id: UUID,
    payload: List[AttendanceUpsert],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk upsert attendances for a meeting."""
    m = await _get_meeting_or_404(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)
    await _require_bureau(db, current_user, assoc)

    if m.status == MeetingStatus.CLOSED:
        raise HTTPException(status_code=409, detail="Cannot edit attendances of a closed meeting")

    result = await db.execute(
        select(MeetingAttendance).where(MeetingAttendance.meeting_id == meeting_id)
    )
    existing = {a.membership_id: a for a in result.scalars().all()}

    out = []
    for item in payload:
        if item.membership_id in existing:
            att = existing[item.membership_id]
            att.status = item.status
            att.notes = item.notes
            att.excuse_reason = item.excuse_reason
        else:
            att = MeetingAttendance(
                meeting_id=meeting_id,
                membership_id=item.membership_id,
                status=item.status,
                notes=item.notes,
                excuse_reason=item.excuse_reason,
            )
            db.add(att)
        out.append(att)

    await db.commit()
    for att in out:
        await db.refresh(att)
    return [_attendance_to_out(a) for a in out]


# ── Entries ────────────────────────────────────────────────────────────────

@router.get("/{meeting_id}/entries", response_model=List[EntryOut])
async def list_entries(
    meeting_id: UUID,
    membership_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = await _get_meeting_or_404(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)

    stmt = select(MeetingActivityEntry).where(MeetingActivityEntry.meeting_id == meeting_id)
    if membership_id:
        stmt = stmt.where(MeetingActivityEntry.membership_id == membership_id)
    result = await db.execute(stmt)
    return [_entry_to_out(e) for e in result.scalars().all()]


@router.post("/{meeting_id}/entries", response_model=EntryOut, status_code=status.HTTP_201_CREATED)
async def create_entry(
    meeting_id: UUID,
    payload: EntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a DRAFT entry for a member × activity."""
    m = await _get_meeting_or_404(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)
    await _require_bureau(db, current_user, assoc)

    if m.status == MeetingStatus.CLOSED:
        raise HTTPException(status_code=409, detail="Cannot add entries to a closed meeting")

    # Validate activity belongs to same association
    res = await db.execute(select(Activity).where(Activity.id == payload.activity_id))
    act = res.scalar_one_or_none()
    if not act or act.association_id != m.association_id:
        raise HTTPException(status_code=422, detail="Activity does not belong to this association")

    entry = MeetingActivityEntry(
        meeting_id=meeting_id,
        membership_id=payload.membership_id,
        activity_id=payload.activity_id,
        amount=payload.amount,
        data=payload.data,
        notes=payload.notes,
        status=EntryStatus.DRAFT,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _entry_to_out(entry)


@router.patch("/{meeting_id}/entries/{entry_id}", response_model=EntryOut)
async def update_entry(
    meeting_id: UUID,
    entry_id: UUID,
    payload: EntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = await _get_meeting_or_404(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)
    await _require_bureau(db, current_user, assoc)

    res = await db.execute(
        select(MeetingActivityEntry).where(
            MeetingActivityEntry.id == entry_id,
            MeetingActivityEntry.meeting_id == meeting_id,
        )
    )
    entry = res.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    if entry.status == EntryStatus.VOIDED:
        raise HTTPException(status_code=409, detail="Cannot edit a voided entry")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)

    await db.commit()
    await db.refresh(entry)
    return _entry_to_out(entry)


@router.delete("/{meeting_id}/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def void_entry(
    meeting_id: UUID,
    entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Void (soft-delete) a DRAFT entry."""
    m = await _get_meeting_or_404(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)

    res = await db.execute(
        select(MeetingActivityEntry).where(
            MeetingActivityEntry.id == entry_id,
            MeetingActivityEntry.meeting_id == meeting_id,
        )
    )
    entry = res.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    if entry.status == EntryStatus.RECORDED:
        raise HTTPException(
            status_code=409,
            detail="Cannot void a recorded entry. Use correction instead.",
        )

    entry.status = EntryStatus.VOIDED
    await db.commit()


# ── Per-member bulk save (collapse-close flow) ─────────────────────────────


@router.post("/{meeting_id}/member-save", response_model=MeetingDetail)
async def save_member(
    meeting_id: UUID,
    payload: MemberSavePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save a member's full meeting record (attendance + entries) in one call.

    Used by the redesigned séance page: each member is a collapsible row, and
    closing the collapse fires this endpoint once.

    - Attendance is upserted if `attendance` is provided.
    - All DRAFT entries for this (meeting, member) are wiped and replaced by
      the supplied list. RECORDED entries are never touched.
    """
    m = await _load_meeting_detail(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)
    await _require_bureau(db, current_user, assoc)

    if m.status == MeetingStatus.CLOSED:
        raise HTTPException(409, "Réunion clôturée — saisies verrouillées")
    if m.status == MeetingStatus.CANCELLED:
        raise HTTPException(409, "Réunion annulée")

    now = datetime.now(timezone.utc)

    # ── Snapshot de l'état AVANT (pour le journal d'éditions) ──
    old_att_obj = next(
        (a for a in m.attendances if a.membership_id == payload.membership_id), None
    )
    old_attendance = old_att_obj.status.value if old_att_obj and old_att_obj.status else None
    old_amounts = {
        str(e.activity_id): e.amount
        for e in m.entries
        if e.membership_id == payload.membership_id and e.status == EntryStatus.DRAFT
    }

    # ── Attendance ──
    if payload.attendance is not None:
        try:
            new_status = AttendanceStatus(payload.attendance)
        except ValueError:
            raise HTTPException(422, f"Statut de présence invalide : '{payload.attendance}'")

        existing_att = next(
            (a for a in m.attendances if a.membership_id == payload.membership_id), None
        )
        if existing_att:
            existing_att.status = new_status
            existing_att.notes = payload.attendance_notes
            existing_att.excuse_reason = payload.excuse_reason
        else:
            db.add(
                MeetingAttendance(
                    meeting_id=m.id,
                    membership_id=payload.membership_id,
                    status=new_status,
                    notes=payload.attendance_notes,
                    excuse_reason=payload.excuse_reason,
                )
            )

    # ── Entries: wipe drafts, replace with payload ──
    for entry in m.entries:
        if entry.membership_id == payload.membership_id and entry.status == EntryStatus.DRAFT:
            await db.delete(entry)
    await db.flush()

    for item in payload.entries:
        if item.amount <= 0:
            continue
        db.add(
            MeetingActivityEntry(
                meeting_id=m.id,
                membership_id=payload.membership_id,
                activity_id=item.activity_id,
                amount=item.amount,
                data=item.data,
                notes=item.notes,
                status=EntryStatus.DRAFT,
                recorded_by_id=current_user.id,
                recorded_at=now,
            )
        )

    # ── Journal d'éditions : si des données existaient et qu'elles ont changé. ──
    new_attendance = payload.attendance if payload.attendance is not None else old_attendance
    new_amounts: dict[str, int] = {
        str(item.activity_id): item.amount for item in payload.entries if item.amount > 0
    }
    had_data = bool(old_attendance) or bool(old_amounts)
    changed = (old_attendance != new_attendance) or (old_amounts != new_amounts)
    if had_data and changed:
        member_name = None
        mem_res = await db.execute(
            select(Membership).options(selectinload(Membership.user)).where(
                Membership.id == payload.membership_id
            )
        )
        mem = mem_res.scalar_one_or_none()
        if mem and mem.user:
            member_name = mem.user.full_name
        m.edit_history = list(m.edit_history or []) + [
            {
                "at": now.isoformat(),
                "by": str(current_user.id),
                "by_name": current_user.full_name,
                "membership_id": str(payload.membership_id),
                "member_name": member_name,
                "before": {"attendance": old_attendance, "amounts": old_amounts},
                "after": {"attendance": new_attendance, "amounts": new_amounts},
            }
        ]

    await db.commit()
    db.expire_all()
    m = await _load_meeting_detail(db, meeting_id)
    return MeetingDetail(
        **_meeting_to_out(m).model_dump(),
        attendances=[_attendance_to_out(a) for a in m.attendances],
        entries=[_entry_to_out(e) for e in m.entries],
    )


# ── Auto-planning ──────────────────────────────────────────────────────────


@router.post("/generate", response_model=MeetingGenerateResult, status_code=status.HTTP_201_CREATED)
async def generate_meetings(
    payload: MeetingGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pre-generate N future PLANNED meetings from the association cadence.

    Dates already occupied by an existing meeting (any status) are skipped so
    the endpoint is safe to call again with the same parameters.
    """
    assoc = await _get_assoc_or_404(db, payload.association_id)
    _check_access(current_user, assoc)
    await _require_bureau(db, current_user, assoc)

    if payload.start_from is not None and payload.start_from < date_cls.today():
        raise HTTPException(422, "La date de départ ne peut pas être dans le passé.")

    start = payload.start_from
    if start is None:
        # Continue after the latest known meeting (or one cadence step from today
        # if the association has no meetings yet).
        res = await db.execute(
            select(Meeting)
            .where(Meeting.association_id == assoc.id)
            .order_by(Meeting.scheduled_on.desc())
            .limit(1)
        )
        last = res.scalar_one_or_none()
        start = planning.next_date_after(assoc, last.scheduled_on if last else None)

    dates = planning.generate_dates(assoc, payload.count, start)
    if not dates:
        return MeetingGenerateResult(created=[], skipped_existing=0)

    existing_res = await db.execute(
        select(Meeting.scheduled_on).where(
            Meeting.association_id == assoc.id,
            Meeting.scheduled_on.in_(dates),
        )
    )
    taken = {d for d in existing_res.scalars().all()}

    created: List[Meeting] = []
    for d in dates:
        if d in taken:
            continue
        m = Meeting(
            association_id=assoc.id,
            title=planning.default_title(assoc, d),
            scheduled_on=d,
            location=planning.default_location(assoc),
            status=MeetingStatus.PLANNED,
            created_by_id=current_user.id,
        )
        db.add(m)
        created.append(m)

    await db.commit()
    for m in created:
        await db.refresh(m)

    return MeetingGenerateResult(
        created=[_meeting_to_out(m) for m in created],
        skipped_existing=len(taken),
    )


# ── Phase 3b — Per-member agenda computed from config-v2 ───────────────────


@router.get("/{meeting_id}/agenda", response_model=MeetingAgenda)
async def meeting_agenda(
    meeting_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compute, for each active member, the rows that should appear in the
    séance UI. Driven entirely by config-v2 :

      - tontines : un cycle propose une ligne au membre s'il est participant
        ET que cette séance héberge un de ses tours (TontineMeetingLink).
      - caisses : caisses récurrentes ou obligatoires (auto-Activity créée
        à la création de la caisse).
      - aides : aid cases approuvées de type récurrent ; contribution membre.
      - prêts : prêts actifs du membre, échéance suggérée = montant attendu
        de la prochaine installment non encore payée.
    """
    m = await _get_meeting_or_404(db, meeting_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_access(current_user, assoc)

    # ── Catalogue : tous les Activity actifs de l'asso ─────────────────────
    act_res = await db.execute(
        select(Activity).where(Activity.association_id == assoc.id, Activity.is_active.is_(True))
    )
    activities = list(act_res.scalars().all())
    by_code = {a.code: a for a in activities}
    loan_activity = next(
        (a for a in activities if a.type == ActivityType.LOAN_REPAYMENT), None
    )

    # ── Membres actifs ─────────────────────────────────────────────────────
    mem_res = await db.execute(
        select(Membership)
        .options(selectinload(Membership.user))
        .where(
            Membership.association_id == assoc.id,
            Membership.status == MembershipStatus.ACTIVE,
        )
        .order_by(Membership.created_at)
    )
    members = list(mem_res.scalars().all())
    member_ids = [m.id for m in members]

    # ── Rounds tontine hébergés par CETTE séance ───────────────────────────
    rnd_res = await db.execute(
        select(TontineRound, TontineMeetingLink, TontineCycle, Tontine)
        .join(TontineMeetingLink, TontineMeetingLink.round_id == TontineRound.id)
        .join(TontineCycle, TontineCycle.id == TontineRound.cycle_id)
        .join(Tontine, Tontine.id == TontineCycle.tontine_id)
        .where(TontineMeetingLink.meeting_id == meeting_id)
    )
    rounds_here = list(rnd_res.all())

    # Pour chaque cycle, on a besoin de savoir qui participe.
    cycle_ids = {c.id for _r, _l, c, _t in rounds_here}
    opted_out: set[tuple[UUID, UUID]] = set()  # (cycle_id, membership_id)
    if cycle_ids:
        op_res = await db.execute(
            select(TontineParticipation).where(
                TontineParticipation.cycle_id.in_(cycle_ids),
                TontineParticipation.is_participating.is_(False),
            )
        )
        opted_out = {(p.cycle_id, p.membership_id) for p in op_res.scalars().all()}

    # ── Prêts actifs de l'asso (avec leur prochaine installment) ───────────
    loan_rows: dict[UUID, tuple[Loan, LoanInstallment | None]] = {}
    if loan_activity:
        loans_res = await db.execute(
            select(Loan)
            .options(selectinload(Loan.installments))
            .where(
                Loan.association_id == assoc.id,
                Loan.status.in_([LoanStatus.DISBURSED, LoanStatus.REPAYING]),
                Loan.borrower_membership_id.in_(member_ids),
            )
        )
        for loan in loans_res.scalars().all():
            next_inst = next(
                (
                    inst
                    for inst in sorted(loan.installments, key=lambda i: i.number)
                    if inst.status not in (LoanInstallmentStatus.PAID, LoanInstallmentStatus.WAIVED)
                ),
                None,
            )
            loan_rows[loan.id] = (loan, next_inst)

    # ── Aides en cours — récurrentes uniquement ────────────────────────────
    aid_res = await db.execute(
        select(SocialAidCase, AidType)
        .join(AidType, AidType.id == SocialAidCase.aid_type_id)
        .where(
            SocialAidCase.association_id == assoc.id,
            SocialAidCase.status == SocialAidCaseStatus.APPROVED,
            AidType.is_contribution_recurring.is_(True),
        )
    )
    aid_cases = list(aid_res.all())

    # ── Assemblage par membre ──────────────────────────────────────────────
    member_agendas: list[MemberAgenda] = []
    for mem in members:
        # Tontines : un round par cycle où mem est participant.
        tontines: list[AgendaRow] = []
        for rnd, _link, cycle, tontine in rounds_here:
            if (cycle.id, mem.id) in opted_out:
                continue
            code = f"tontine-{tontine.slug}"
            act = by_code.get(code)
            if not act:
                continue
            tontines.append(
                AgendaRow(
                    activity_id=act.id,
                    label=f"Tontine {tontine.name} — Tour {rnd.round_number}",
                    default_amount=cycle.round_amount,
                    is_required=cycle.is_mandatory,
                    context={
                        "tontine_id": str(tontine.id),
                        "cycle_id": str(cycle.id),
                        "round_id": str(rnd.id),
                        "round_number": rnd.round_number,
                    },
                )
            )

        # Caisses : Activities visibles pinnées sur une caisse.
        caisses_rows: list[AgendaRow] = []
        for act in activities:
            cfg = act.config or {}
            if not act.is_visible_in_meeting:
                continue
            if not cfg.get("caisse_id"):
                continue
            caisses_rows.append(
                AgendaRow(
                    activity_id=act.id,
                    label=act.name,
                    default_amount=int(cfg.get("amount") or 0),
                    is_required=act.is_required,
                    context={"caisse_id": cfg.get("caisse_id")},
                )
            )

        # Aides : 1 ligne par AidCase APPROVED de type récurrent.
        aids: list[AgendaRow] = []
        for case, atype in aid_cases:
            code = f"aid-{atype.slug}"
            act = by_code.get(code)
            if not act:
                continue
            aids.append(
                AgendaRow(
                    activity_id=act.id,
                    label=f"{atype.name} — {case.reference}",
                    default_amount=int(atype.member_contribution_amount or 0),
                    is_required=True,
                    context={
                        "aid_case_id": str(case.id),
                        "aid_type_id": str(atype.id),
                    },
                )
            )

        # Prêts : 1 ligne par prêt actif du membre.
        loans_section: list[AgendaRow] = []
        if loan_activity:
            for loan, next_inst in loan_rows.values():
                if loan.borrower_membership_id != mem.id:
                    continue
                expected = (
                    (next_inst.expected_amount - next_inst.paid_principal - next_inst.paid_interest)
                    if next_inst
                    else 0
                )
                loans_section.append(
                    AgendaRow(
                        activity_id=loan_activity.id,
                        label=f"Prêt {loan.reference}"
                        + (f" — Échéance {next_inst.number}" if next_inst else " — Soldé"),
                        default_amount=max(0, expected),
                        is_required=False,
                        context={
                            "loan_id": str(loan.id),
                            "installment_id": str(next_inst.id) if next_inst else None,
                        },
                    )
                )

        u = getattr(mem, "user", None)
        member_agendas.append(
            MemberAgenda(
                membership_id=mem.id,
                member_name=getattr(u, "full_name", None),
                tontines=tontines,
                caisses=caisses_rows,
                aids=aids,
                loans=loans_section,
            )
        )

    return MeetingAgenda(meeting_id=meeting_id, members=member_agendas)
