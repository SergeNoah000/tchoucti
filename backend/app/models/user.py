"""User model — global identity. Scoped to platform OR a groupement."""
import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.groupement import Groupement
    from app.models.role import Membership, UserPermission


class UserType(str, Enum):
    SUPER_ADMIN = "super_admin"           # plateforme
    GROUPEMENT_ADMIN = "groupement_admin" # admin d'un groupement
    ASSOCIATION_USER = "association_user" # admin association / manager / membre — scope via Membership
    MEMBER = "member"                     # ancien membre simple, gardé pour compat


class InviteStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"


class User(BaseModel):
    __tablename__ = "users"

    # Identité
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Auth
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    google_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)

    # Type / statut
    user_type: Mapped[UserType] = mapped_column(
        SQLEnum(UserType, name="user_type"),
        default=UserType.ASSOCIATION_USER,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Préférences
    language: Mapped[str] = mapped_column(String(5), default="fr", nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Invitation
    invited_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    invite_status: Mapped[Optional[str]] = mapped_column(
        SQLEnum(InviteStatus, name="invite_status"), nullable=True
    )

    # Tenant — null pour super_admin
    groupement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groupements.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    groupement: Mapped[Optional["Groupement"]] = relationship("Groupement", back_populates="users")
    memberships: Mapped[List["Membership"]] = relationship(
        "Membership", back_populates="user", cascade="all, delete-orphan",
        foreign_keys="Membership.user_id",
    )
    extra_permissions: Mapped[List["UserPermission"]] = relationship(
        "UserPermission", back_populates="user", cascade="all, delete-orphan"
    )

    # ── Helpers ──
    # These properties double as the fields exposed by `UserPublic` so
    # `from_attributes=True` can serialise a SQLAlchemy `User` directly.
    @property
    def is_super_admin(self) -> bool:
        return self.user_type == UserType.SUPER_ADMIN

    @property
    def is_platform_admin(self) -> bool:
        # Alias used by the frontend (`User.is_platform_admin`).
        return self.user_type == UserType.SUPER_ADMIN

    @property
    def is_groupement_admin(self) -> bool:
        return self.user_type == UserType.GROUPEMENT_ADMIN

    @property
    def is_association_admin(self) -> bool:
        return self.user_type == UserType.ASSOCIATION_USER

    def __repr__(self) -> str:
        return f"<User {self.email}>"
