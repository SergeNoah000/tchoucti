"""Demande de sortie d'argent — file de validation du trésorier.

Toute sortie d'argent (décaissement prêt, versement aide, retrait caisse,
versement tontine, mouvement manuel OUT) est d'abord PRÉPARÉE par un membre du
bureau. Elle reste EN ATTENTE (`pending`) tant que le **trésorier** ne l'a pas
validée : c'est la validation qui déclenche réellement le `TreasuryMovement`
OUT. Le rejet la clôt sans mouvement.

Le modèle est volontairement générique : `kind` + `source_type`/`source_id`
identifient l'action métier, `payload` porte le contexte nécessaire pour
finaliser la transition du domaine au moment de la validation.
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class PayoutKind(str, Enum):
    LOAN_DISBURSEMENT = "loan_disbursement"
    AID_PAYOUT = "aid_payout"
    CAISSE_WITHDRAWAL = "caisse_withdrawal"
    TONTINE_PAYOUT = "tontine_payout"
    MANUAL_OUT = "manual_out"


class PayoutRequestStatus(str, Enum):
    PENDING = "pending"      # préparée, en attente du trésorier
    VALIDATED = "validated"  # validée → l'argent est sorti
    REJECTED = "rejected"    # refusée par le trésorier
    CANCELLED = "cancelled"  # annulée par le préparateur / l'admin


class PayoutRequest(BaseModel):
    __tablename__ = "payout_requests"

    association_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("associations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    kind: Mapped[PayoutKind] = mapped_column(
        SQLEnum(PayoutKind, name="payout_kind"), nullable=False, index=True
    )
    status: Mapped[PayoutRequestStatus] = mapped_column(
        SQLEnum(PayoutRequestStatus, name="payout_request_status"),
        nullable=False,
        default=PayoutRequestStatus.PENDING,
        index=True,
    )

    # Action métier ciblée (mêmes source_type que TreasuryMovement).
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    # Fonds à débiter (capturé à la préparation).
    fund_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("funds.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)

    related_membership_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memberships.id", ondelete="SET NULL"),
        nullable=True,
    )
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Contexte de finalisation propre au flux (JSON libre).
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    prepared_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    prepared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    decided_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Mouvement de trésorerie créé à la validation.
    movement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("treasury_movements.id", ondelete="SET NULL"),
        nullable=True,
    )

    prepared_by = relationship("User", foreign_keys=[prepared_by_id])
    decided_by = relationship("User", foreign_keys=[decided_by_id])
