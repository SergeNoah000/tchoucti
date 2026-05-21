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
# Cycle
# ───────────────────────────────────────────────────
class TontineCycle(BaseModel):
    """Un cycle de tontine fixe (rotation).

    Tous les participants versent `round_amount` à chaque tour. Le pot
    (round_amount × n_participants) est remis au bénéficiaire désigné du tour.
    """

    __tablename__ = "tontine_cycles"

    association_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("associations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    round_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rounds_count: Mapped[int] = mapped_column(Integer, nullable=False)  # = nb de participants
    current_round_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Stratégie d'ordonnancement des bénéficiaires
    order_strategy: Mapped[str] = mapped_column(
        String(20), default="manual", nullable=False
    )  # 'manual' | 'random' | 'seniority'

    status: Mapped[TontineCycleStatus] = mapped_column(
        SQLEnum(TontineCycleStatus, name="tontine_cycle_status"),
        default=TontineCycleStatus.DRAFT,
        nullable=False,
        index=True,
    )

    notes: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    association: Mapped["Association"] = relationship("Association", back_populates="tontine_cycles")
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
        UniqueConstraint(
            "cycle_id", "beneficiary_membership_id",
            name="uq_tontine_rounds_cycle_beneficiary",
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

    beneficiary_membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memberships.id", ondelete="RESTRICT"),
        nullable=False,
    )

    expected_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    collected_amount: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    paid_out_amount: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    status: Mapped[TontineRoundStatus] = mapped_column(
        SQLEnum(TontineRoundStatus, name="tontine_round_status"),
        default=TontineRoundStatus.PENDING,
        nullable=False,
    )

    # Mouvement de décaissement (vidage du fonds TONTINE vers le bénéficiaire)
    payout_movement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("treasury_movements.id", ondelete="SET NULL"),
        nullable=True,
    )

    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    cycle: Mapped["TontineCycle"] = relationship("TontineCycle", back_populates="rounds")
    beneficiary: Mapped["Membership"] = relationship(
        "Membership", foreign_keys=[beneficiary_membership_id]
    )
    contributions: Mapped[List["TontineContribution"]] = relationship(
        "TontineContribution", back_populates="round", cascade="all, delete-orphan"
    )


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
