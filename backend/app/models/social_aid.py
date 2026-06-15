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
    Boolean,
    Date,
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
    from app.models.caisse import Caisse
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
# AidType — catalog of social aid kinds an association offers (config-v2)
# ───────────────────────────────────────────────────
class AidType(BaseModel):
    """Type d'aide sociale configurable par l'admin.

    Définit le barème (combien chaque membre doit cotiser, plafond versé au
    bénéficiaire), la fréquence de cotisation et les contraintes (max demandes
    par membre par an, délai de déclaration).

    Si is_contribution_recurring : la cotisation est collectée à chaque séance
    pendant que l'aide est en cours. Sinon : collecte one-shot dès l'approbation.

    La caisse `source_caisse_id` reçoit les cotisations et finance le versement.
    """

    __tablename__ = "aid_types"
    __table_args__ = (
        UniqueConstraint(
            "association_id", "slug",
            name="uq_aid_types_assoc_slug",
        ),
    )

    association_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("associations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Caisse qui reçoit les cotisations et finance le versement. NULL si
    # `auto_create_caisse` : une caisse temporaire au nom du bénéficiaire est
    # alors créée à l'approbation de chaque demande.
    source_caisse_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("caisses.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # Si True : pas de caisse source fixe ; une caisse dédiée au bénéficiaire est
    # ouverte automatiquement quand sa demande d'aide est approuvée.
    auto_create_caisse: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ── Cotisation membre ───────────────────────────────────────────────────
    member_contribution_amount: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False
    )
    # True = collectée à chaque séance pendant que l'aide est en cours.
    # False = collecte one-shot lors de l'approbation.
    is_contribution_recurring: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # Mode "temporary" (cotisation ponctuelle) : la cotisation membre est-elle
    # obligatoire ? (sinon optionnelle).
    contribution_required: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false"
    )

    # ── Versement au bénéficiaire ────────────────────────────────────────────
    aid_ceiling_amount: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False
    )

    # Mode de calcul du montant : "ceiling" (plafond fixe) ou "objective"
    # (montant objectif réparti : part par membre = objectif / (nb_membres - 1),
    # le -1 excluant le demandeur).
    amount_mode: Mapped[str] = mapped_column(
        String(20), default="ceiling", nullable=False, server_default="ceiling"
    )
    objective_amount: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False, server_default="0"
    )

    # ── Mode de financement (coexistence) ────────────────────────────────────
    # "fixed"           : caisse source fixe (source_caisse_id).
    # "temporary"       : caisse temporaire au nom du bénéficiaire (auto_create).
    # "member_insurance": caisse perso d'assurance par membre, avec un minimum ;
    #                     à chaque aide on débite la caisse de chaque membre de
    #                     sa part, le membre re-remplit jusqu'au min.
    funding_mode: Mapped[str] = mapped_column(
        String(20), default="fixed", nullable=False, server_default="fixed"
    )
    # Caisse PERSONAL servant de caisse d'assurance individuelle (mode insurance).
    insurance_caisse_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("caisses.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Montant minimum que chaque membre doit maintenir dans sa caisse d'assurance.
    insurance_minimum: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False, server_default="0"
    )
    # Période (jours) sur laquelle le re-remplissage est attendu après un débit.
    refill_period_days: Mapped[int] = mapped_column(
        Integer, default=90, nullable=False, server_default="90"
    )

    # ── Contraintes ──────────────────────────────────────────────────────────
    max_claims_per_member_per_year: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
    # Délai max de déclaration après l'événement (jours).
    declaration_delay_days: Mapped[int] = mapped_column(
        Integer, default=30, nullable=False
    )

    # ── Relationships ───────────────────────────────────────────────────────
    association: Mapped["Association"] = relationship("Association")
    # Deux FK vers caisses (source_caisse_id + insurance_caisse_id) → il faut
    # préciser la colonne de jointure pour chaque relation.
    source_caisse: Mapped[Optional["Caisse"]] = relationship(
        "Caisse", foreign_keys=[source_caisse_id]
    )
    insurance_caisse: Mapped[Optional["Caisse"]] = relationship(
        "Caisse", foreign_keys=[insurance_caisse_id]
    )


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

    # Phase 2e — référence de l'AidType utilisé. NULL pour les dossiers legacy
    # déclarés via le kind enum hardcodé. `source_caisse_id` est snapshoté ici
    # (la caisse source du type peut bouger ; le dossier en cours reste figé).
    aid_type_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("aid_types.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_caisse_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("caisses.id", ondelete="RESTRICT"),
        nullable=True,
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
