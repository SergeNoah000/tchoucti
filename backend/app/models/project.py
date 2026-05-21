"""Projects — projets votés par l'association (achat de bien commun, événement, etc.)

Chaque projet a son propre fonds dédié (Fund kind=PROJECT, ref_key=project.slug).
Les contributions des membres sont saisies via l'activité PROJECT_CONTRIBUTION
en réunion ou via décaissement direct.
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
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.finance import Fund
    from app.models.role import Membership


class ProjectStatus(str, Enum):
    DRAFT = "draft"
    OPEN = "open"           # collecte ouverte
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Project(BaseModel):
    """Un projet d'association avec collecte dédiée."""

    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("association_id", "slug", name="uq_projects_association_slug"),
    )

    association_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("associations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    target_amount: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    suggested_contribution: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    closed_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    status: Mapped[ProjectStatus] = mapped_column(
        SQLEnum(ProjectStatus, name="project_status"),
        default=ProjectStatus.DRAFT,
        nullable=False,
        index=True,
    )

    # Fonds dédié (PROJECT, ref_key=slug)
    fund_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("funds.id", ondelete="SET NULL"), nullable=True
    )

    is_contribution_required: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    contributions: Mapped[List["ProjectContribution"]] = relationship(
        "ProjectContribution", back_populates="project", cascade="all, delete-orphan"
    )


class ProjectContribution(BaseModel):
    """Contribution d'un membre à un projet, traçable indépendamment."""

    __tablename__ = "project_contributions"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
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

    entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meeting_activity_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="contributions")
    membership: Mapped["Membership"] = relationship("Membership")
