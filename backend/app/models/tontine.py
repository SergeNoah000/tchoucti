"""Tontine fixe — rotation classique. 1 cycle actif à la fois par association."""
import uuid
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.association import Association
    from app.models.finance import TreasuryMovement
    from app.models.meeting import Meeting
    from app.models.role import Membership


class TontineCycleStatus(str, Enum):
    DRAFT = "draft"           # configuration en cours
    ACTIVE = "active"         # cycle en cours
    COMPLETED = "completed"   # tous les tours servis
    CANCELLED = "cancelled"


class TontineRoundStatus(str, Enum):
    PENDING = "pending"       # en attente (futur)
    COLLECTING = "collecting" # tour actif, contributions en cours
    PAID_OUT = "paid_out"     # bénéficiaire payé
    SKIPPED = "skipped"


# ───────────────────────────────────────────────────
# Tontine (entité durable, parent des cycles)
# ───────────────────────────────────────────────────
class Tontine(BaseModel):
    """Une tontine ("njangi") — entité durable d'une association.

    Une tontine vit dans le temps et enchaîne plusieurs **cycles** (une
    rotation complète chacun). Elle possède UNE caisse système dédiée
    (fund ref_key = slug), réutilisée par tous ses cycles (les cycles sont
    séquentiels, jamais simultanés). Sa config par défaut est héritée par
    chaque nouveau cycle.
    """

    __tablename__ = "tontines"
    __table_args__ = (
        UniqueConstraint("association_id", "slug", name="uq_tontines_assoc_slug"),
    )

    association_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("associations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ── Config par défaut (héritée par chaque cycle) ──────────────────────────
    round_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # weekly | biweekly | monthly | bimonthly | custom
    frequency: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)
    custom_interval_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    beneficiaries_per_round: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Le bénéficiaire d'un tour verse-t-il aussi sa cotisation à son propre tour ?
    beneficiary_pays: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # manual | random | seniority | vote | auction | need
    selection_method: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)

    association: Mapped["Association"] = relationship(
        "Association", back_populates="tontines"
    )
    cycles: Mapped[List["TontineCycle"]] = relationship(
        "TontineCycle",
        back_populates="tontine",
        cascade="all, delete-orphan",
        order_by="TontineCycle.cycle_number",
    )


# ───────────────────────────────────────────────────
# Cycle (une rotation complète d'une tontine)
# ───────────────────────────────────────────────────
class TontineCycle(BaseModel):
    """Un cycle = une rotation complète : la période pour que TOUS les
    participants reçoivent la cagnotte une fois. Enfant d'une `Tontine`.
    Le cycle N+1 hérite de toute la config + participants du précédent.
    """

    __tablename__ = "tontine_cycles"
    __table_args__ = (
        UniqueConstraint("tontine_id", "cycle_number", name="uq_tontine_cycles_number"),
    )

    tontine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tontines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3…

    # Snapshots de la config de la tontine au moment de la création du cycle.
    round_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rounds_count: Mapped[int] = mapped_column(Integer, nullable=False)
    current_round_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    order_strategy: Mapped[str] = mapped_column(
        String(20), default="manual", nullable=False
    )

    status: Mapped[TontineCycleStatus] = mapped_column(
        SQLEnum(TontineCycleStatus, name="tontine_cycle_status"),
        default=TontineCycleStatus.DRAFT,
        nullable=False,
        index=True,
    )
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    tontine: Mapped["Tontine"] = relationship("Tontine", back_populates="cycles")
    rounds: Mapped[List["TontineRound"]] = relationship(
        "TontineRound",
        back_populates="cycle",
        cascade="all, delete-orphan",
        order_by="TontineRound.round_number",
    )


# ───────────────────────────────────────────────────
# Round (un tour = un bénéficiaire)
# ───────────────────────────────────────────────────
class TontineRound(BaseModel):
    __tablename__ = "tontine_rounds"
    __table_args__ = (
        UniqueConstraint(
            "cycle_id", "round_number",
            name="uq_tontine_rounds_cycle_number",
        ),
    )

    cycle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tontine_cycles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    paid_out_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # NOTE: beneficiaries live in `TontineRoundBeneficiary` — a round can pay out
    # to several people who share the pot.

    expected_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    collected_amount: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    paid_out_amount: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    status: Mapped[TontineRoundStatus] = mapped_column(
        SQLEnum(TontineRoundStatus, name="tontine_round_status"),
        default=TontineRoundStatus.PENDING,
        nullable=False,
    )

    # Mouvement de décaissement (vidage du fonds TONTINE vers les bénéficiaires)
    payout_movement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("treasury_movements.id", ondelete="SET NULL"),
        nullable=True,
    )

    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    cycle: Mapped["TontineCycle"] = relationship("TontineCycle", back_populates="rounds")
    beneficiaries: Mapped[List["TontineRoundBeneficiary"]] = relationship(
        "TontineRoundBeneficiary",
        back_populates="round",
        cascade="all, delete-orphan",
    )
    contributions: Mapped[List["TontineContribution"]] = relationship(
        "TontineContribution", back_populates="round", cascade="all, delete-orphan"
    )


# ───────────────────────────────────────────────────
# RoundBeneficiary — one beneficiary share inside a round
# ───────────────────────────────────────────────────
class TontineRoundBeneficiary(BaseModel):
    """One slot ("name") that receives a share of a round's pot.

    Un membre peut tenir PLUSIEURS noms dans une tontine : chaque nom est un
    bénéficiaire distinct (sa propre position dans la rotation). `name_label`
    porte le libellé du nom (modifiable) ; à défaut, on affiche le nom du membre.
    """

    __tablename__ = "tontine_round_beneficiaries"
    # Pas de contrainte d'unicité (round, membership) : un membre peut occuper
    # plusieurs noms, donc potentiellement plusieurs slots dans un même tour.

    round_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tontine_rounds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memberships.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Libellé du nom/part (ex. « Awa », « Awa 2 »). NULL = nom du membre.
    name_label: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)

    # Snapshot of what this person receives — set at round creation (equal split
    # by default; admin may tune `share_parts` for unequal splits).
    share_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    share_parts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    round: Mapped["TontineRound"] = relationship("TontineRound", back_populates="beneficiaries")
    membership: Mapped["Membership"] = relationship("Membership", foreign_keys=[membership_id])


# ───────────────────────────────────────────────────
# Contribution (qui a versé combien pour un tour donné)
# ───────────────────────────────────────────────────
class TontineContribution(BaseModel):
    """Trace de la contribution d'un membre à un tour précis.

    Lié à un MeetingActivityEntry (la saisie de réunion qui a généré ce versement).
    """

    __tablename__ = "tontine_contributions"
    __table_args__ = (
        UniqueConstraint(
            "round_id", "membership_id",
            name="uq_tontine_contributions_round_member",
        ),
    )

    round_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tontine_rounds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memberships.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    contributed_on: Mapped[date] = mapped_column(Date, nullable=False)
    is_late: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Lien vers la saisie en réunion qui l'a déclenchée
    entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meeting_activity_entries.id", ondelete="SET NULL"),
        nullable=True,
    )

    round: Mapped["TontineRound"] = relationship("TontineRound", back_populates="contributions")
    membership: Mapped["Membership"] = relationship("Membership")


# ───────────────────────────────────────────────────
# TontineMeetingLink — which séance hosts which round (config-v2)
# ───────────────────────────────────────────────────
class TontineMeetingLink(BaseModel):
    """Mapping un tour de tontine ↔ une séance.

    À la création d'une tontine, on choisit pour chaque tour la séance hôte
    parmi les séances futures de l'association. Permet de :
      - savoir quelles tontines collecter à chaque séance ;
      - déplacer un tour individuellement (en changeant la séance hôte) sans
        toucher le reste du cycle.

    `is_locked` empêche le déplacement isolé (utile si le cycle est rigide).
    """

    __tablename__ = "tontine_meeting_links"
    __table_args__ = (
        UniqueConstraint("round_id", name="uq_tontine_meeting_links_round"),
    )

    round_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tontine_rounds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


# ───────────────────────────────────────────────────
# TontineParticipation — opt-in/opt-out per member per cycle
# ───────────────────────────────────────────────────
class TontineParticipation(BaseModel):
    """Participation d'un membre à un cycle de tontine.

    Par défaut OBLIGATOIRE (`is_participating=True`) pour chaque membre actif.
    L'admin peut opt-out un membre à la création du cycle (sauf si la tontine
    a `is_mandatory=True` au niveau du cycle).

    Présent uniquement pour les membres qui ont quelque chose à dire (opt-out
    ou statut spécial). Absence de ligne = par défaut, participe.
    """

    __tablename__ = "tontine_participations"
    __table_args__ = (
        UniqueConstraint(
            "cycle_id", "membership_id",
            name="uq_tontine_participations_pair",
        ),
    )

    cycle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tontine_cycles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memberships.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_participating: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
