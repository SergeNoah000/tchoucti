"""Notifications in-app (V1)."""
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class NotificationKind(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    # Métier
    MEETING_PLANNED = "meeting_planned"
    MEETING_REMINDER = "meeting_reminder"
    LOAN_APPROVED = "loan_approved"
    LOAN_INSTALLMENT_DUE = "loan_installment_due"
    AID_DECIDED = "aid_decided"
    TONTINE_TURN = "tontine_turn"
    INVITATION = "invitation"


class Notification(BaseModel):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    association_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("associations.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    kind: Mapped[NotificationKind] = mapped_column(
        SQLEnum(NotificationKind, name="notification_kind"),
        default=NotificationKind.INFO,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Lien d'action (deep-link in-app)
    action_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    data: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, server_default=text("'{}'::jsonb")
    )

    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
