"""Finance core — caisse hybride (modèle B+C choisi par l'utilisateur).

ARCHITECTURE
============

  Association
       │
       └─── Treasury  (1-1, la "caisse globale" physique de l'association)
                │
                ├─── Fund (GENERAL)       ┐  Les fonds = sous-comptes virtuels.
                ├─── Fund (TONTINE)       │  La somme des soldes des fonds == solde
                ├─── Fund (INSURANCE)     │  total de la Treasury (INVARIANT).
                ├─── Fund (SAVINGS)       │
                └─── Fund (PROJECT:xxx)   ┘

  TreasuryMovement       = un seul mouvement d'argent (cash-in / cash-out)
                           pour l'association. Ex: "Cotisation Akono Jean = 5000 IN".
                           Porte un solde absolu de référence post-opération.

  LedgerEntry (1-N par   = ventilation du mouvement entre fonds. Chaque entrée
   TreasuryMovement)       crédite (CREDIT) ou débite (DEBIT) un Fund précis.
                           SOMME(LedgerEntry.amount * sign) == TreasuryMovement.amount
                           pour les opérations IN (et l'inverse pour OUT).

OPÉRATIONS COURANTES (modèle métier)
====================================

  • Cotisation mensuelle      → IN 5000  ⇒ ledger: +5000 sur GENERAL
  • Cotisation assurance      → IN 2000  ⇒ ledger: +2000 sur INSURANCE
  • Versement tontine         → IN 10000 ⇒ ledger: +10000 sur TONTINE
  • Décaissement tontine      → OUT 100k ⇒ ledger: -100k sur TONTINE
  • Octroi prêt               → OUT 50k  ⇒ ledger: -50k  sur GENERAL
  • Remboursement prêt        → IN 51k   ⇒ ledger: +50k GENERAL + 1k INSURANCE (intérêt)
  • Pénalité retard prêt      → IN 500   ⇒ ledger: +500 INSURANCE
  • Aide sociale décès        → OUT 100k ⇒ ledger: -100k sur INSURANCE
  • Amende membre             → IN 1000  ⇒ ledger: +1000 sur GENERAL
  • Épargne libre             → IN 5000  ⇒ ledger: +5000 sur SAVINGS (tracké par membre)
  • Contribution projet X     → IN 2000  ⇒ ledger: +2000 sur PROJECT:X
  • Transfert inter-fonds     → 2 ledger entries (DEBIT fund A + CREDIT fund B), 0 cash net

INVARIANT (vérifié par le service `FinanceService`):
    Σ Fund.balance  ==  Treasury.balance  ==  Σ TreasuryMovement.signed_amount
"""
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
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.association import Association


# ───────────────────────────────────────────────────
# Enums
# ───────────────────────────────────────────────────
class FundKind(str, Enum):
    """Types de fonds gérés.

    GENERAL    : fonds opérationnel (cotisations, dons, amendes, capital prêts)
    TONTINE    : pot du cycle de tontine en cours (vidé à chaque tour)
    INSURANCE  : fonds d'imprévus collectif (assurance + intérêts + pénalités)
    SAVINGS    : épargne libre — suivi individuel par membre (cf. SavingsBalance)
    PROJECT    : fonds dédié à un projet (linké via project_id)
    EXTERNAL   : fonds externe (banque, mobile money, autre — usage futur)
    """

    GENERAL = "general"
    TONTINE = "tontine"
    INSURANCE = "insurance"
    SAVINGS = "savings"
    PROJECT = "project"
    EXTERNAL = "external"


class MovementDirection(str, Enum):
    IN = "in"     # Entrée (cash-in)
    OUT = "out"   # Sortie (cash-out)
    XFER = "xfer" # Transfert inter-fonds (net = 0)


# ───────────────────────────────────────────────────
# Treasury (1-1 avec Association)
# ───────────────────────────────────────────────────
class Treasury(BaseModel):
    """Caisse globale d'une association. Crée automatiquement à la création de l'asso."""

    __tablename__ = "treasuries"

    association_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("associations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Solde absolu de la caisse (somme de tous les mouvements signés).
    # Tenu à jour à chaque mouvement (par service / trigger).
    balance: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False, server_default="0"
    )
    currency: Mapped[str] = mapped_column(String(3), default="XAF", nullable=False)

    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locked_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    association: Mapped["Association"] = relationship("Association", back_populates="treasury")
    funds: Mapped[List["Fund"]] = relationship(
        "Fund", back_populates="treasury", cascade="all, delete-orphan"
    )
    movements: Mapped[List["TreasuryMovement"]] = relationship(
        "TreasuryMovement", back_populates="treasury", cascade="all, delete-orphan"
    )


# ───────────────────────────────────────────────────
# Fund (sous-compte virtuel)
# ───────────────────────────────────────────────────
class Fund(BaseModel):
    """Fonds virtuel d'une Treasury (ex: GENERAL, TONTINE, INSURANCE, PROJECT:X)."""

    __tablename__ = "funds"
    __table_args__ = (
        UniqueConstraint(
            "treasury_id", "kind", "ref_key",
            name="uq_funds_treasury_kind_ref",
        ),
    )

    treasury_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("treasuries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[FundKind] = mapped_column(
        SQLEnum(FundKind, name="fund_kind"), nullable=False, index=True
    )
    # Discriminant supplémentaire (vide pour les fonds standards, sinon ex: project slug)
    ref_key: Mapped[str] = mapped_column(String(100), default="", nullable=False)

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    balance: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False, server_default="0"
    )
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Permet de marquer certains fonds comme "auto-créés", non supprimables.
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    treasury: Mapped["Treasury"] = relationship("Treasury", back_populates="funds")
    ledger_entries: Mapped[List["LedgerEntry"]] = relationship(
        "LedgerEntry", back_populates="fund", cascade="all, delete-orphan"
    )


# ───────────────────────────────────────────────────
# TreasuryMovement — un mouvement physique d'argent
# ───────────────────────────────────────────────────
class TreasuryMovement(BaseModel):
    """Mouvement de caisse atomique (cash-in, cash-out ou transfert inter-fonds).

    `amount` est TOUJOURS POSITIF. La direction donne le sens.
    `balance_after` est snapshotté pour audit/reconciliation.
    """

    __tablename__ = "treasury_movements"

    treasury_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("treasuries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    direction: Mapped[MovementDirection] = mapped_column(
        SQLEnum(MovementDirection, name="movement_direction"),
        nullable=False,
        index=True,
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)

    occurred_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Source / référence métier (polymorphique). Exemples :
    #   source_type = "meeting_entry"     source_id = <entry uuid>
    #   source_type = "loan_disbursement" source_id = <loan uuid>
    #   source_type = "loan_repayment"    source_id = <repayment uuid>
    #   source_type = "tontine_payout"    source_id = <round uuid>
    #   source_type = "aid_payout"        source_id = <case uuid>
    #   source_type = "manual"            source_id = NULL
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Acteurs
    recorded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Membre concerné (si applicable). Permet le filtrage "tout l'historique de Akono Jean".
    related_membership_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memberships.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    meta: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, server_default=text("'{}'::jsonb")
    )

    # Statut comptable : un mouvement peut être annulé (réservation, erreur de saisie).
    is_voided: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    voided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    void_of_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("treasury_movements.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    treasury: Mapped["Treasury"] = relationship("Treasury", back_populates="movements")
    ledger_entries: Mapped[List["LedgerEntry"]] = relationship(
        "LedgerEntry",
        back_populates="movement",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def signed_amount(self) -> int:
        """Retourne le montant signé (positif si IN, négatif si OUT, 0 pour XFER pur)."""
        if self.is_voided:
            return 0
        if self.direction == MovementDirection.IN:
            return self.amount
        if self.direction == MovementDirection.OUT:
            return -self.amount
        return 0  # XFER : net nul sur la caisse


# ───────────────────────────────────────────────────
# LedgerEntry — ventilation par fonds
# ───────────────────────────────────────────────────
class LedgerEntry(BaseModel):
    """Ligne de ventilation d'un TreasuryMovement vers un Fund.

    Signe (`is_credit`):
      - True  (CREDIT) → augmente le solde du fonds
      - False (DEBIT)  → diminue le solde du fonds

    Pour un IN simple : 1 ligne CREDIT.
    Pour un OUT simple : 1 ligne DEBIT.
    Pour un transfert : 1 DEBIT (fonds source) + 1 CREDIT (fonds destination).
    Pour un remboursement de prêt avec intérêt : 1 CREDIT GENERAL (capital)
       + 1 CREDIT INSURANCE (intérêt).
    """

    __tablename__ = "ledger_entries"

    movement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("treasury_movements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fund_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("funds.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    is_credit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # always positive
    fund_balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)

    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    movement: Mapped["TreasuryMovement"] = relationship(
        "TreasuryMovement", back_populates="ledger_entries"
    )
    fund: Mapped["Fund"] = relationship("Fund", back_populates="ledger_entries")

    @property
    def signed_amount(self) -> int:
        return self.amount if self.is_credit else -self.amount
