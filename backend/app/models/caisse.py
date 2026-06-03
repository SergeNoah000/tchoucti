"""Caisse — user-facing fund concept that wraps a Fund with config rules.

Layered model:

    Caisse  (user-defined config: catégorie, récurrent, plafond, objectif…)
       │
       └── Fund  (existing accounting unit, maintains Σ funds = treasury)

Why two layers?
- Fund is the *accounting* primitive: the treasury invariant `Σ Fund = Treasury`
  must always hold. Existing modules (meeting close, tontine payout, loans)
  already route money through Fund.
- Caisse is the *user* primitive: the admin creates "Caisse Projet Puits" with
  its rules (récurrente à chaque séance, plafond 500 000, objectif fini avec
  deadline, cotisation obligatoire de 5 000 par membre).
- Each Caisse owns exactly one Fund (1-1 via fund_id). System caisses
  (Caisse générale, Caisse Tontine — XXX) wrap the existing FundKind rows so
  the old code keeps working.

Categories
----------
SYSTEM      : auto-créée, non supprimable. Caisse générale + 1 par tontine.
COLLECTIVE  : caisse partagée. Balance unique. Peut avoir plafond/objectif/cotisation obligatoire.
PROJECT     : variante de COLLECTIVE avec objectif fini + deadline. Se ferme
              automatiquement quand l'objectif est atteint.
PERSONAL    : épargne personnelle. Un solde par membre via MemberCaisseBalance.
              Toutes les contributions tracent membership_id sur LedgerEntry.
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
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.association import Association
    from app.models.finance import Fund
    from app.models.role import Membership


class CaisseCategory(str, Enum):
    SYSTEM = "system"           # caisse générale + caisses tontine (auto)
    COLLECTIVE = "collective"   # caisse partagée (avec plafond/objectif optionnels)
    PROJECT = "project"         # objectif fini + deadline
    PERSONAL = "personal"       # épargne personnelle, 1 balance par membre


class InterestDistribution(str, Enum):
    """Sort des intérêts perçus par la caisse (Phase 7 — modèle Fred)."""

    KEPT = "kept"                       # actuel : intérêt vers le fonds INSURANCE
    SHARED_PRO_RATA = "shared_pro_rata" # redistribué aux cotisants au prorata


class DistributionPeriod(str, Enum):
    """Périodicité de clôture/redistribution des intérêts."""

    PER_MEETING = "per_meeting"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUALLY = "annually"


class WithdrawalMode(str, Enum):
    """Politique de retrait des apports par les cotisants."""

    NEVER = "never"                              # modèle Fred strict
    ANYTIME_IF_LIQUID = "anytime_if_liquid"      # quand la liquidité le permet
    END_OF_PERIOD_ONLY = "end_of_period_only"    # uniquement après distribution


class Caisse(BaseModel):
    """Caisse user-facing — règles métier + lien vers le Fund comptable."""

    __tablename__ = "caisses"
    __table_args__ = (
        UniqueConstraint(
            "association_id", "slug",
            name="uq_caisses_assoc_slug",
        ),
    )

    association_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("associations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Fund accounting backing this caisse (1-1).
    fund_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("funds.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    category: Mapped[CaisseCategory] = mapped_column(
        SQLEnum(CaisseCategory, name="caisse_category"),
        default=CaisseCategory.COLLECTIVE,
        nullable=False,
        index=True,
    )

    # Non supprimable et non éditable au-delà du nom/description.
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ── Règles de collecte ───────────────────────────────────────────────────

    # Collectée à chaque séance ? (ligne pré-remplie sur la page séance)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Montant pré-rempli si récurrente.
    recurring_amount: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # Chaque membre doit-il y cotiser ? (signal d'alerte si manquant à la clôture)
    is_member_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    member_required_amount: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # ── Plafond / objectif ───────────────────────────────────────────────────

    # Si has_ceiling : refuse les contributions au-delà.
    has_ceiling: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ceiling_amount: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # Si has_objective : on affiche une barre de progression. Pour PROJECT, on ferme
    # la caisse à objectif atteint.
    has_objective: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    objective_amount: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    objective_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # ── Phase 7 — modèle Fred : rendement partagé ────────────────────────────
    # Si SHARED_PRO_RATA, les intérêts perçus via remboursements de prêts dont
    # la source_caisse est CETTE caisse seront redistribués aux cotisants au
    # prorata de leur `apport_cum` à la clôture de chaque période.
    interest_distribution: Mapped[str] = mapped_column(
        String(30), default=InterestDistribution.KEPT.value, nullable=False,
        server_default=InterestDistribution.KEPT.value,
    )
    distribution_period: Mapped[str] = mapped_column(
        String(30), default=DistributionPeriod.PER_MEETING.value, nullable=False,
        server_default=DistributionPeriod.PER_MEETING.value,
    )
    withdrawal_mode: Mapped[str] = mapped_column(
        String(30), default=WithdrawalMode.NEVER.value, nullable=False,
        server_default=WithdrawalMode.NEVER.value,
    )
    last_distribution_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # ── Relationships ────────────────────────────────────────────────────────
    association: Mapped["Association"] = relationship("Association")
    fund: Mapped["Fund"] = relationship("Fund")
    member_balances: Mapped[List["MemberCaisseBalance"]] = relationship(
        "MemberCaisseBalance", back_populates="caisse", cascade="all, delete-orphan"
    )
    contributor_balances: Mapped[List["CaisseContributorBalance"]] = relationship(
        "CaisseContributorBalance", back_populates="caisse", cascade="all, delete-orphan"
    )
    distributions: Mapped[List["CaisseDistribution"]] = relationship(
        "CaisseDistribution", back_populates="caisse", cascade="all, delete-orphan"
    )


class MemberCaisseBalance(BaseModel):
    """Solde individuel d'un membre dans une caisse de catégorie PERSONAL.

    Seulement matérialisé pour les caisses PERSONAL. Pour SYSTEM / COLLECTIVE
    / PROJECT, on lit la contribution par membre via les `LedgerEntry` du
    Fund filtré par `related_membership_id`.

    Le solde est mis à jour à la validation de chaque entry de séance ciblant
    cette caisse.
    """

    __tablename__ = "member_caisse_balances"
    __table_args__ = (
        UniqueConstraint(
            "caisse_id", "membership_id",
            name="uq_member_caisse_balance",
        ),
    )

    caisse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("caisses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memberships.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    balance: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    caisse: Mapped["Caisse"] = relationship("Caisse", back_populates="member_balances")
    membership: Mapped["Membership"] = relationship("Membership")


# ── Phase 7 — modèle Fred ────────────────────────────────────────────────────


class CaisseContributorBalance(BaseModel):
    """Sous-soldes d'un cotisant dans une caisse en mode partagé.

    `apport_cum`                  : capital cumulé versé par le membre — base
                                    du prorata pour la redistribution.
    `apport_cum_at_period_start`  : snapshot de l'apport au début de la
                                    période en cours (« look-back » à la Fred).
    `interest_cum`                : cumul des intérêts reçus aux distributions
                                    successives. Pas inclus dans la base de
                                    calcul (pas de capitalisation).
    """

    __tablename__ = "caisse_contributor_balances"
    __table_args__ = (
        UniqueConstraint(
            "caisse_id", "membership_id",
            name="uq_caisse_contributor_balance",
        ),
    )

    caisse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("caisses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memberships.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    apport_cum: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    apport_cum_at_period_start: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False, server_default="0"
    )
    interest_cum: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    caisse: Mapped["Caisse"] = relationship("Caisse", back_populates="contributor_balances")
    membership: Mapped["Membership"] = relationship("Membership")


class CaisseDistribution(BaseModel):
    """Une clôture de période sur une caisse en mode partagé.

    Snapshot de l'intérêt collecté pendant la période et de la base utilisée
    pour le calcul du prorata. Les parts individuelles sont dans
    `caisse_distribution_shares`.
    """

    __tablename__ = "caisse_distributions"

    caisse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("caisses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_label: Mapped[str] = mapped_column(String(50), nullable=False)
    interest_pool: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_base: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    closed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    closed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    caisse: Mapped["Caisse"] = relationship("Caisse", back_populates="distributions")
    shares: Mapped[List["CaisseDistributionShare"]] = relationship(
        "CaisseDistributionShare", back_populates="distribution", cascade="all, delete-orphan"
    )


class CaisseDistributionShare(BaseModel):
    """Part individuelle attribuée à un cotisant lors d'une distribution."""

    __tablename__ = "caisse_distribution_shares"
    __table_args__ = (
        UniqueConstraint(
            "distribution_id", "membership_id",
            name="uq_caisse_distribution_share",
        ),
    )

    distribution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("caisse_distributions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memberships.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    base: Mapped[int] = mapped_column(BigInteger, nullable=False)
    share_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)

    distribution: Mapped["CaisseDistribution"] = relationship(
        "CaisseDistribution", back_populates="shares"
    )
    membership: Mapped["Membership"] = relationship("Membership")
