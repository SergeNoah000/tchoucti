"""Audit log — qui a fait quoi, quand, sur quelle entité."""
import uuid
from typing import Optional

from sqlalchemy import (
    ForeignKey,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class AuditLog(BaseModel):
    """Trace immuable d'une action utilisateur.

    Scope : peut être lié à un groupement, une association, ou les deux (null pour
    les actions super-admin globales).
    """

    __tablename__ = "audit_logs"

    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    groupement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groupements.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    association_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("associations.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # ex: "meeting.create", "loan.approve", "treasury.void_movement"

    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Diff before/after (utile pour reconstituer l'historique)
    payload: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, server_default=text("'{}'::jsonb")
    )
