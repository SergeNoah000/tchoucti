"""Association = tenant level 2 (inside a Groupement)."""
import uuid
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Enum as SQLEnum, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class AssociationType(str, Enum):
    """Nature de l'association — choisie par l'admin dans les paramètres."""

    TONTINE = "tontine"
    MUTUELLE = "mutuelle"
    COOPERATIVE = "cooperative"
    ASSOCIATION = "association"
    AUTRE = "autre"

if TYPE_CHECKING:
    from app.models.finance import Treasury
    from app.models.groupement import Groupement
    from app.models.meeting import Activity, Meeting
    from app.models.role import Membership
    from app.models.tontine import TontineCycle


class Association(BaseModel):
    """An `Association` lives under a Groupement and owns members, meetings,
    treasury, tontine cycles, etc."""

    __tablename__ = "associations"
    __table_args__ = (
        UniqueConstraint("groupement_id", "slug", name="uq_associations_groupement_slug"),
    )

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[str] = mapped_column(String(7), default="#0F766E", nullable=False)

    # Type / nature (paramètres généraux)
    type: Mapped[AssociationType] = mapped_column(
        SQLEnum(AssociationType, name="association_type"),
        default=AssociationType.ASSOCIATION,
        nullable=False,
    )

    # Contact
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # Localisation / monnaie
    currency: Mapped[str] = mapped_column(String(3), default="XAF", nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="Africa/Douala", nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Configuration métier (montants par défaut). Tous montants en monnaie de l'association.
    # Exemples :
    #   {
    #     "monthly_contribution": 5000,
    #     "insurance_contribution": 2000,
    #     "default_tontine_amount": 10000,
    #     "loan_interest_rate_pct": 5.0,        # mensuel
    #     "loan_late_fee_pct": 1.0,             # par mois de retard
    #     "loan_max_multiplier": 3,             # multiple de cotisations cumulées
    #     "social_aid_amounts": {
    #         "death_parent": 100000,
    #         "death_spouse": 150000,
    #         "death_child": 100000,
    #         "hospitalisation": 50000,
    #         "sinister": 30000
    #     }
    #   }
    config: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, server_default=text("'{}'::jsonb")
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # FK
    groupement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groupements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Relationships
    groupement: Mapped["Groupement"] = relationship("Groupement", back_populates="associations")
    memberships: Mapped[List["Membership"]] = relationship(
        "Membership", back_populates="association", cascade="all, delete-orphan"
    )
    activities: Mapped[List["Activity"]] = relationship(
        "Activity", back_populates="association", cascade="all, delete-orphan"
    )
    meetings: Mapped[List["Meeting"]] = relationship(
        "Meeting", back_populates="association", cascade="all, delete-orphan"
    )
    tontine_cycles: Mapped[List["TontineCycle"]] = relationship(
        "TontineCycle", back_populates="association", cascade="all, delete-orphan"
    )
    treasury: Mapped[Optional["Treasury"]] = relationship(
        "Treasury",
        back_populates="association",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Association {self.slug}>"
