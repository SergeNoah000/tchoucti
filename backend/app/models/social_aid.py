"""Assistance sociale — décès, maladie, sinistres.

Fonds COLLECTIF (cf. décision utilisateur). Le bureau crée une "case", la valide,
puis un payout est décaissé depuis le fonds INSURANCE selon le barème
`association.config.social_aid_amounts`.
"""
import uuid
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    BigInteger,
    Date,
    Enum as SQLEnum,
    ForeignKey,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.finance import TreasuryMovement
    from app.models.role import Membership


class SocialAidCaseKind(str, Enum):
    """Catégories d'événements — barème dans `association.config.social_fund.events`."""

    DEATH = "death"        # décès
    ILLNESS = "illness"    # maladie
    MARRIAGE = "marriage"  # mariage
    BIRTH = "birth"        # naissance
    OTHER = "other"        # autre (montant fixé manuellement)


class SocialAidCaseStatus(str, Enum):
    REQUESTED = "requested"   # demande déposée
    REVIEWING = "reviewing"   # en cours d'examen
    APPROVED = "approved"     # validée
    PAID = "paid"             # décaissement effectué
    REJECTED = "rejected"
    CANCELLED = "cancelled"


# ───────────────────────────────────────────────────
# Case
# ───────────────────────────────────────────────────
class SocialAidCase(BaseModel):
    """Un dossier d'assistance sociale lié à un membre."""

    __tablename__ = "social_aid_cases"

    association_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("associations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    beneficiary_membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memberships.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    reference: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    kind: Mapped[SocialAidCaseKind] = mapped_column(
        SQLEnum(SocialAidCaseKind, name="social_aid_case_kind"), nullable=False
    )
    status: Mapped[SocialAidCaseStatus] = mapped_column(
        SQLEnum(SocialAidCaseStatus, name="social_aid_case_status"),
        default=SocialAidCaseStatus.REQUESTED,
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    event_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    requested_on: Mapped[date] = mapped_column(Date, nullable=False)
    decided_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Montant demandé / approuvé (snapshot du barème au moment de la décision)
    requested_amount: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    approved_amount: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    paid_amount: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # Pièces jointes (URLs MinIO)
    supporting_docs: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, server_default=text("'{}'::jsonb")
    )

    # Acteurs
    requested_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    beneficiary: Mapped["Membership"] = relationship(
        "Membership", foreign_keys=[beneficiary_membership_id]
    )
    payouts: Mapped[List["SocialAidPayout"]] = relationship(
        "SocialAidPayout", back_populates="case", cascade="all, delete-orphan"
    )


class SocialAidPayout(BaseModel):
    """Décaissement (partiel ou total) sur un dossier."""

    __tablename__ = "social_aid_payouts"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("social_aid_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)

    movement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("treasury_movements.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    case: Mapped["SocialAidCase"] = relationship("SocialAidCase", back_populates="payouts")
