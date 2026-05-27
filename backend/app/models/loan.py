"""Loans — système complet : intérêts configurables, échéancier auto, pénalités de retard.

Règle métier (utilisateur) : "Système complet : intérêt configurable, échéancier
auto-calculé, pénalités de retard, intérêts versés dans le fonds Assurance/Imprévus".

Calcul standard d'un échéancier (intérêts simples mensuels):

  principal      = montant du prêt (capital)
  rate_pct       = taux d'intérêt mensuel (ex 5.0 = 5%)
  n              = nombre d'échéances mensuelles

  total_interest = principal × rate_pct/100 × n           (intérêts simples)
  total_due      = principal + total_interest
  installment    = ceil(total_due / n)                     (chaque échéance)
    └─ ventilation par échéance :
         interest_part  = ceil(principal × rate_pct / 100)
         principal_part = installment - interest_part

Si l'association veut un schéma "intérêts dégressifs" (sur capital restant) ou
"annuité constante", l'algorithme est extrait dans `app/services/loan_calculator.py`
(modifiable sans toucher au schéma).

Pénalités de retard :
  late_fee_pct (par mois de retard) appliqué sur l'échéance en retard.
  Les pénalités sont créditées au fonds INSURANCE (comme les intérêts).
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
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
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.association import Association
    from app.models.caisse import Caisse
    from app.models.finance import TreasuryMovement
    from app.models.role import Membership


class LoanStatus(str, Enum):
    REQUESTED = "requested"      # demande déposée
    APPROVED = "approved"        # approuvée par le bureau
    DISBURSED = "disbursed"      # décaissée (cash sorti)
    REPAYING = "repaying"        # en cours de remboursement
    PAID = "paid"                # entièrement remboursé
    REJECTED = "rejected"
    DEFAULTED = "defaulted"      # défaillant (radié)
    CANCELLED = "cancelled"


# ───────────────────────────────────────────────────
# LoanType — catalog of loan products an association offers (config-v2)
# ───────────────────────────────────────────────────
class LoanType(BaseModel):
    """Type de prêt configurable par l'admin.

    Définit les règles d'éligibilité, le coût (intérêt + pénalité) et la
    caisse depuis laquelle le capital est tiré. Les demandes de prêt (modèle
    `Loan`) référencent un LoanType pour copier ses paramètres au moment du
    décaissement (les changements ultérieurs au LoanType ne touchent pas les
    prêts déjà émis).
    """

    __tablename__ = "loan_types"
    __table_args__ = (
        UniqueConstraint(
            "association_id", "slug",
            name="uq_loan_types_assoc_slug",
        ),
    )

    association_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("associations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Caisse source — c'est de là que sort le capital.
    source_caisse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("caisses.id", ondelete="RESTRICT"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ── Éligibilité ──────────────────────────────────────────────────────────
    eligibility_min_seniority_months: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    eligibility_no_default: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    # Limites — max prêts actifs simultanés et max nouveau prêt par an pour un membre.
    max_simultaneous: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_per_year: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # ── Coût ────────────────────────────────────────────────────────────────
    # Taux d'intérêt mensuel (ex 5.0 = 5%)
    interest_rate_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=0, nullable=False
    )
    # Pénalité par mois de retard (% de l'échéance)
    late_fee_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=0, nullable=False
    )
    # Durée max en mois — l'admin du prêt ne peut pas dépasser
    max_duration_months: Mapped[int] = mapped_column(Integer, default=12, nullable=False)

    # ── Relationships ───────────────────────────────────────────────────────
    association: Mapped["Association"] = relationship("Association")
    source_caisse: Mapped["Caisse"] = relationship("Caisse")


class LoanInstallmentStatus(str, Enum):
    PENDING = "pending"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    LATE = "late"
    WAIVED = "waived"  # remise gracieuse (le bureau l'efface)


# ───────────────────────────────────────────────────
# Loan
# ───────────────────────────────────────────────────
class Loan(BaseModel):
    """Un prêt accordé à un membre."""

    __tablename__ = "loans"

    association_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("associations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    borrower_membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memberships.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    reference: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # ex: PRT-2026-001

    # Montants
    principal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    interest_rate_pct: Mapped[Decimal] = mapped_column(
        Numeric(6, 3), nullable=False
    )  # par mois, ex: 5.000
    late_fee_pct: Mapped[Decimal] = mapped_column(
        Numeric(6, 3), default=Decimal("0"), nullable=False
    )
    duration_months: Mapped[int] = mapped_column(Integer, nullable=False)

    # Calcul (snapshotté à l'approbation)
    total_interest: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_due: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    installment_amount: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # Soldes courants
    paid_principal: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    paid_interest: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    paid_late_fees: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # Dates
    requested_on: Mapped[date] = mapped_column(Date, nullable=False)
    approved_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    disbursed_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    first_due_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_due_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    closed_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    status: Mapped[LoanStatus] = mapped_column(
        SQLEnum(LoanStatus, name="loan_status"),
        default=LoanStatus.REQUESTED,
        nullable=False,
        index=True,
    )

    # Acteurs
    requested_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Mouvement de décaissement
    disbursement_movement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("treasury_movements.id", ondelete="SET NULL"),
        nullable=True,
    )

    purpose: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    # Métadonnées (snapshot config au moment de l'approbation)
    meta: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, server_default=text("'{}'::jsonb")
    )

    # Relationships
    borrower: Mapped["Membership"] = relationship(
        "Membership", foreign_keys=[borrower_membership_id]
    )
    installments: Mapped[List["LoanInstallment"]] = relationship(
        "LoanInstallment",
        back_populates="loan",
        cascade="all, delete-orphan",
        order_by="LoanInstallment.number",
    )
    repayments: Mapped[List["LoanRepayment"]] = relationship(
        "LoanRepayment", back_populates="loan", cascade="all, delete-orphan"
    )

    @property
    def remaining_balance(self) -> int:
        return max(0, self.total_due - (self.paid_principal + self.paid_interest))


# ───────────────────────────────────────────────────
# LoanInstallment — échéance prévisionnelle
# ───────────────────────────────────────────────────
class LoanInstallment(BaseModel):
    __tablename__ = "loan_installments"
    __table_args__ = (
        UniqueConstraint("loan_id", "number", name="uq_loan_installments_loan_number"),
    )

    loan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loans.id", ondelete="CASCADE"), nullable=False, index=True
    )

    number: Mapped[int] = mapped_column(Integer, nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Décomposition prévisionnelle
    principal_part: Mapped[int] = mapped_column(BigInteger, nullable=False)
    interest_part: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Soldes courants
    paid_principal: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    paid_interest: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    paid_late_fee: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    accumulated_late_fee: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    paid_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[LoanInstallmentStatus] = mapped_column(
        SQLEnum(LoanInstallmentStatus, name="loan_installment_status"),
        default=LoanInstallmentStatus.PENDING,
        nullable=False,
        index=True,
    )

    loan: Mapped["Loan"] = relationship("Loan", back_populates="installments")


# ───────────────────────────────────────────────────
# LoanRepayment — paiement effectif imputé sur une ou plusieurs échéances
# ───────────────────────────────────────────────────
class LoanRepayment(BaseModel):
    """Un paiement de remboursement.

    Source typique : un `MeetingActivityEntry` de type `LOAN_REPAYMENT`.
    Ventilation : principal + interest + late_fee, imputés sur la plus ancienne
    échéance pending puis sur les suivantes.
    """

    __tablename__ = "loan_repayments"

    loan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    installment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("loan_installments.id", ondelete="SET NULL"),
        nullable=True,
    )

    paid_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    total_paid: Mapped[int] = mapped_column(BigInteger, nullable=False)
    principal: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    interest: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    late_fee: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # Trace
    entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meeting_activity_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    movement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("treasury_movements.id", ondelete="SET NULL"),
        nullable=True,
    )

    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    loan: Mapped["Loan"] = relationship("Loan", back_populates="repayments")
    installment: Mapped[Optional["LoanInstallment"]] = relationship(
        "LoanInstallment", foreign_keys=[installment_id]
    )
