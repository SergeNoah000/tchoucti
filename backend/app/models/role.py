"""RBAC: Role, Permission, RolePermission, Membership (user-in-association), UserPermission."""
import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
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
    from app.models.groupement import Groupement
    from app.models.user import User


class RoleScope(str, Enum):
    PLATFORM = "platform"        # rôles système
    GROUPEMENT = "groupement"    # rôles propres à un groupement
    ASSOCIATION = "association"  # rôles propres à une association


class MembershipStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    RESIGNED = "resigned"


# ───────────────────────────────────────────────────
# Permission
# ───────────────────────────────────────────────────
class Permission(BaseModel):
    """Permission = action atomique. Code = `domaine.action`.

    Exemples : `members.create`, `meetings.manage`, `loans.approve`,
    `finance.read`, `tontine.cycle.start`.
    """

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    scope: Mapped[RoleScope] = mapped_column(
        SQLEnum(RoleScope, name="permission_scope"),
        default=RoleScope.ASSOCIATION,
        nullable=False,
    )

    role_permissions: Mapped[List["RolePermission"]] = relationship(
        "RolePermission", back_populates="permission", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Permission {self.code}>"


# ───────────────────────────────────────────────────
# Role
# ───────────────────────────────────────────────────
class Role(BaseModel):
    """Role = bundle de permissions.

    - `is_system=True`  : rôle global non supprimable (Super Admin, Admin Groupement,
      Admin Association, Manager, Membre).
    - `is_system=False` : rôle métier custom (Trésorier, Président, Censeur, …)
      créé par l'association (`association_id` set) ou par le groupement.

    `scope` indique où il s'applique :
      - PLATFORM   → roles globaux
      - GROUPEMENT → roles assignés au niveau d'un groupement
      - ASSOCIATION → roles assignés via Membership
    """

    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint(
            "groupement_id", "association_id", "code",
            name="uq_roles_scope_code",
        ),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    scope: Mapped[RoleScope] = mapped_column(
        SQLEnum(RoleScope, name="role_scope"),
        default=RoleScope.ASSOCIATION,
        nullable=False,
    )

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

    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    groupement: Mapped[Optional["Groupement"]] = relationship("Groupement", back_populates="roles")
    role_permissions: Mapped[List["RolePermission"]] = relationship(
        "RolePermission", back_populates="role", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Role {self.code}>"


class RolePermission(BaseModel):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_perm"),
    )

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False
    )

    role: Mapped["Role"] = relationship("Role", back_populates="role_permissions")
    permission: Mapped["Permission"] = relationship("Permission", back_populates="role_permissions")


# ───────────────────────────────────────────────────
# Membership = User × Association (avec rôles multiples)
# ───────────────────────────────────────────────────
class Membership(BaseModel):
    """Adhésion d'un user à UNE association.

    Un user peut avoir plusieurs Membership (un par association). Chaque
    membership porte UN ou PLUSIEURS rôles (technique + métier) via la table
    `MembershipRole`.
    """

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "association_id", name="uq_memberships_user_association"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    association_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("associations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Numéro d'adhérent dans l'association
    member_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    status: Mapped[MembershipStatus] = mapped_column(
        SQLEnum(MembershipStatus, name="membership_status"),
        default=MembershipStatus.ACTIVE,
        nullable=False,
    )

    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Suivi cotisations cumulées (en XAF) — utile pour plafonner les prêts.
    # Mis à jour lors de la validation d'une saisie de réunion.
    cumulative_contributions: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False, server_default="0"
    )

    notes: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(
        "User", back_populates="memberships", foreign_keys=[user_id]
    )
    association: Mapped["Association"] = relationship("Association", back_populates="memberships")
    membership_roles: Mapped[List["MembershipRole"]] = relationship(
        "MembershipRole", back_populates="membership", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Membership user={self.user_id} assoc={self.association_id}>"


class MembershipRole(BaseModel):
    """Lien Membership ↔ Role (un membre peut avoir plusieurs rôles dans une assoc)."""

    __tablename__ = "membership_roles"
    __table_args__ = (
        UniqueConstraint("membership_id", "role_id", name="uq_membership_roles_pair"),
    )

    membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memberships.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    membership: Mapped["Membership"] = relationship("Membership", back_populates="membership_roles")
    role: Mapped["Role"] = relationship("Role")


# ───────────────────────────────────────────────────
# Per-user extra permissions (overrides)
# ───────────────────────────────────────────────────
class UserPermission(BaseModel):
    """Override par utilisateur d'une permission, scopé à une association."""

    __tablename__ = "user_permissions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "association_id", "permission_id",
            name="uq_user_permissions_triplet",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    association_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("associations.id", ondelete="CASCADE"),
        nullable=False,
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    granted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="extra_permissions")
    permission: Mapped["Permission"] = relationship("Permission")
