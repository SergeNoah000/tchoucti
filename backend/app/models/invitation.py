"""Invitation model — invites users to a groupement (as admin) or an association.

Tokens are random opaque strings, hashed-at-rest. Only one invitation row is
active per (email + target) at any time: resending generates a new token and
revokes the previous row.
"""
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.association import Association
    from app.models.groupement import Groupement
    from app.models.user import User


class InvitationKind(str, Enum):
    """What the invitation grants the invitee."""

    GROUPEMENT_ADMIN = "groupement_admin"
    ASSOCIATION_ADMIN = "association_admin"
    ASSOCIATION_MEMBER = "association_member"


class InvitationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


# Length of the plain token returned to the user (URL-safe).
_TOKEN_BYTES = 32


def generate_invitation_token() -> str:
    """Cryptographically random URL-safe token. Returned plain *once*."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


class Invitation(BaseModel):
    __tablename__ = "invitations"

    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    kind: Mapped[InvitationKind] = mapped_column(
        SQLEnum(InvitationKind, name="invitation_kind"), nullable=False
    )
    status: Mapped[InvitationStatus] = mapped_column(
        SQLEnum(InvitationStatus, name="invitation_status"),
        default=InvitationStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Hash of the token (sha256 hex). Plain token is shown once at creation and never persisted.
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)

    # Scope
    groupement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groupements.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    association_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("associations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Invitee identity hint (full_name pre-filled by the inviter)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    message: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Lifecycle
    invited_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    groupement: Mapped[Optional["Groupement"]] = relationship(
        "Groupement", foreign_keys=[groupement_id]
    )
    association: Mapped[Optional["Association"]] = relationship(
        "Association", foreign_keys=[association_id]
    )
    invited_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[invited_by_id])
    accepted_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[accepted_by_id])

    @staticmethod
    def expiry_in(days: int) -> datetime:
        return datetime.now(timezone.utc) + timedelta(days=days)

    def is_expired(self) -> bool:
        now = datetime.now(timezone.utc)
        exp = self.expires_at
        # `expires_at` may come back naive depending on the driver — normalise.
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return now >= exp

    def __repr__(self) -> str:
        return f"<Invitation {self.email} kind={self.kind.value} status={self.status.value}>"
