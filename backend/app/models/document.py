"""Documents — statuts, règlements, PV, rapports, pièces justificatives."""
import uuid
from enum import Enum
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Enum as SQLEnum,
    ForeignKey,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class DocumentVisibility(str, Enum):
    ADMINS_ONLY = "admins_only"   # bureau seulement
    MEMBERS = "members"           # tous les membres
    PUBLIC = "public"             # accessible sans auth (rare)


class Document(BaseModel):
    """Un fichier stocké dans MinIO, lié à une association et éventuellement à
    une entité métier (meeting, loan, social aid case, project)."""

    __tablename__ = "documents"

    association_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("associations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Type métier (libre : "statut", "reglement", "pv", "rapport", "justificatif", "autre")
    kind: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_mime: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)

    visibility: Mapped[DocumentVisibility] = mapped_column(
        SQLEnum(DocumentVisibility, name="document_visibility"),
        default=DocumentVisibility.MEMBERS,
        nullable=False,
    )

    # Entités liées (polymorphique simple)
    meeting_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True
    )
    loan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loans.id", ondelete="SET NULL"), nullable=True
    )
    social_aid_case_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("social_aid_cases.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )

    uploaded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
