"""Meetings (séances) + Activities + saisies par membre (cœur de la page séance)."""
import uuid
from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.association import Association
    from app.models.finance import TreasuryMovement
    from app.models.role import Membership


# ───────────────────────────────────────────────────
# Enums
# ───────────────────────────────────────────────────
class MeetingStatus(str, Enum):
    PLANNED = "planned"     # programmée
    ONGOING = "ongoing"     # en cours (page de saisie active)
    CLOSED = "closed"       # clôturée, PV généré
    CANCELLED = "cancelled"


class AttendanceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    EXCUSED = "excused"     # absence justifiée
    LATE = "late"


class ActivityType(str, Enum):
    """Catalogue des types d'activités saisissables en réunion (V1)."""

    MONTHLY_CONTRIBUTION = "monthly_contribution"   # cotisation mensuelle → GENERAL
    INSURANCE_CONTRIBUTION = "insurance_contribution"  # cotisation assurance → INSURANCE
    TONTINE_CONTRIBUTION = "tontine_contribution"   # versement tontine → TONTINE
    LOAN_REPAYMENT = "loan_repayment"               # remboursement prêt → GENERAL+INSURANCE
    PENALTY = "penalty"                             # amende → GENERAL
    SAVINGS_DEPOSIT = "savings_deposit"             # épargne libre → SAVINGS
    EXCEPTIONAL_DONATION = "exceptional_donation"   # don exceptionnel → GENERAL
    PROJECT_CONTRIBUTION = "project_contribution"   # contribution projet voté → PROJECT:X
    OTHER = "other"                                 # libre (manager précise)


class EntryStatus(str, Enum):
    DRAFT = "draft"           # saisie en cours / non validée
    RECORDED = "recorded"     # validée → mouvement de caisse créé
    CORRECTED = "corrected"   # corrigée (l'ancienne saisie a été remplacée)
    VOIDED = "voided"         # annulée


# ───────────────────────────────────────────────────
# Activity — catalogue d'activités d'une association
# ───────────────────────────────────────────────────
class Activity(BaseModel):
    """Activité paramétrable d'une association (instance d'un ActivityType).

    Une association peut avoir plusieurs activités du même type ?
    Non — règle métier V1 : 1 par type, sauf PROJECT_CONTRIBUTION (1 par projet)
    et OTHER (illimité). Contrainte appliquée au niveau service.

    `config` contient les paramètres :
      monthly_contribution: { "amount": 5000, "is_required": true }
      insurance_contribution: { "amount": 2000, "is_required": true }
      tontine_contribution: { "amount": 10000, "cycle_id": "<uuid>" }
      penalty: { "presets": [{"label": "Retard", "amount": 500}, {"label": "Absence", "amount": 2000}] }
      project_contribution: { "project_id": "<uuid>", "suggested_amount": 1000 }
    """

    __tablename__ = "activities"
    __table_args__ = (
        UniqueConstraint(
            "association_id", "code",
            name="uq_activities_association_code",
        ),
    )

    association_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("associations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    type: Mapped[ActivityType] = mapped_column(
        SQLEnum(ActivityType, name="activity_type"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)  # ex: 'monthly', 'projet-puits'
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    color: Mapped[str] = mapped_column(String(7), default="#0F766E", nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # lucide icon name

    config: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, server_default=text("'{}'::jsonb")
    )
    # Affiché dans la page de saisie de réunion ?
    is_visible_in_meeting: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Activité obligatoire pour chaque membre (warning si non saisie à la clôture) ?
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    association: Mapped["Association"] = relationship("Association", back_populates="activities")
    entries: Mapped[List["MeetingActivityEntry"]] = relationship(
        "MeetingActivityEntry", back_populates="activity", cascade="all, delete-orphan"
    )


# ───────────────────────────────────────────────────
# Meeting
# ───────────────────────────────────────────────────
class Meeting(BaseModel):
    """Une séance de réunion d'association."""

    __tablename__ = "meetings"

    association_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("associations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    scheduled_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    status: Mapped[MeetingStatus] = mapped_column(
        SQLEnum(MeetingStatus, name="meeting_status"),
        default=MeetingStatus.PLANNED,
        nullable=False,
        index=True,
    )

    # Le manager qui anime / saisit
    facilitator_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Agenda + notes libres (sections, décisions, prochaines actions)
    agenda: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, server_default=text("'{}'::jsonb")
    )

    # PDF du procès-verbal (URL MinIO)
    report_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    report_generated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Total de la séance (calculé à la clôture, snapshotté)
    total_in: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False, server_default="0")
    total_out: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False, server_default="0")

    # Relationships
    association: Mapped["Association"] = relationship("Association", back_populates="meetings")
    attendances: Mapped[List["MeetingAttendance"]] = relationship(
        "MeetingAttendance", back_populates="meeting", cascade="all, delete-orphan"
    )
    entries: Mapped[List["MeetingActivityEntry"]] = relationship(
        "MeetingActivityEntry", back_populates="meeting", cascade="all, delete-orphan"
    )


# ───────────────────────────────────────────────────
# Attendance
# ───────────────────────────────────────────────────
class MeetingAttendance(BaseModel):
    __tablename__ = "meeting_attendances"
    __table_args__ = (
        UniqueConstraint(
            "meeting_id", "membership_id",
            name="uq_meeting_attendances_meeting_member",
        ),
    )

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memberships.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[AttendanceStatus] = mapped_column(
        SQLEnum(AttendanceStatus, name="attendance_status"),
        default=AttendanceStatus.PRESENT,
        nullable=False,
    )
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    excuse_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="attendances")
    membership: Mapped["Membership"] = relationship("Membership")


# ───────────────────────────────────────────────────
# MeetingActivityEntry — la saisie unitaire d'un membre × activité
# (cœur du PDF "Idee_Page_gestion_Seance-Reunion")
# ───────────────────────────────────────────────────
class MeetingActivityEntry(BaseModel):
    """Saisie d'une activité pour un membre lors d'une réunion.

    Une "entrée" = un membre + une activité + un montant + des données métier.
    Au moment du RECORDED, le service crée:
      - 1 `TreasuryMovement` (avec source_type="meeting_entry", source_id=cet entry)
      - N `LedgerEntry` (ventilation par fonds selon ActivityType)
      - met à jour `membership.cumulative_contributions` si pertinent
      - met à jour les soldes savings/loan/tontine selon le type.

    Re-saisie d'une activité déjà RECORDED → la nouvelle entry passe en RECORDED et
    void l'ancienne (statut CORRECTED), avec création d'un mouvement contre-passation.
    """

    __tablename__ = "meeting_activity_entries"
    __table_args__ = (
        # Empêche les doublons en attente DRAFT ; on autorise plusieurs RECORDED
        # historisées (avec une seule "active" à la fois — géré au service).
        UniqueConstraint(
            "meeting_id", "membership_id", "activity_id", "status",
            name="uq_meeting_entries_unique_active",
        ),
    )

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memberships.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activities.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Montant saisi (positif). Le sens (IN/OUT) est déterminé par l'ActivityType.
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Données spécifiques au type d'activité.
    # Exemples :
    #   loan_repayment:        { "loan_id": "<uuid>", "installment_id": "<uuid>",
    #                            "principal": 4000, "interest": 1000, "late_fee": 0 }
    #   penalty:               { "reason": "absence non excusée" }
    #   tontine_contribution:  { "cycle_id": "<uuid>", "round_id": "<uuid>" }
    #   project_contribution:  { "project_id": "<uuid>" }
    #   exceptional_donation:  { "purpose": "soutien funérailles tante du Président" }
    data: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, server_default=text("'{}'::jsonb")
    )

    status: Mapped[EntryStatus] = mapped_column(
        SQLEnum(EntryStatus, name="entry_status"),
        default=EntryStatus.DRAFT,
        nullable=False,
        index=True,
    )

    # Lien vers le mouvement de caisse une fois RECORDED
    movement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("treasury_movements.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Audit
    recorded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    recorded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Si correction d'une entrée précédente
    corrects_entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meeting_activity_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    correction_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Relationships
    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="entries")
    membership: Mapped["Membership"] = relationship("Membership")
    activity: Mapped["Activity"] = relationship("Activity", back_populates="entries")
    movement: Mapped[Optional["TreasuryMovement"]] = relationship(
        "TreasuryMovement", foreign_keys=[movement_id]
    )


# ───────────────────────────────────────────────────
# MeetingReminder — one row per (meeting, days_before) sent
# Purely an idempotency ledger for the Celery reminder task.
# ───────────────────────────────────────────────────
class MeetingReminder(BaseModel):
    """A reminder dispatch for a meeting at a given offset.

    The reminder worker writes one row per (meeting_id, days_before) pair the
    moment it sends, so the next scan won't double-fire. `recipients_count`
    records how many emails actually went out (useful for the audit page).
    """

    __tablename__ = "meeting_reminders"
    __table_args__ = (
        UniqueConstraint(
            "meeting_id", "days_before",
            name="uq_meeting_reminders_meeting_offset",
        ),
    )

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 0 = day of meeting, 1 = day before, 7 = a week before, …
    days_before: Mapped[int] = mapped_column(Integer, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recipients_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
