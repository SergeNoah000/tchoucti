"""Pydantic schemas for Membership, Role, Permission."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ── Role / Permission (read-only) ──────────────────────────────────────────

class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: Optional[str]
    category: str
    scope: str


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    code: str
    description: Optional[str]
    scope: str
    is_system: bool
    groupement_id: Optional[UUID]
    association_id: Optional[UUID]


class RoleWithPermissionsOut(RoleOut):
    permissions: List[PermissionOut] = []


# ── User (nested in membership) ────────────────────────────────────────────

class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str
    phone: Optional[str]
    is_active: bool


# ── Membership ─────────────────────────────────────────────────────────────

class MembershipCreate(BaseModel):
    """Invite a user to an association.

    If `user_id` is provided, the existing user is linked.
    If only `email` is provided, a new user is created (invite flow).
    """
    association_id: UUID
    user_id: Optional[UUID] = None
    email: Optional[EmailStr] = None          # used when creating a new user
    full_name: Optional[str] = Field(None, max_length=255)
    role_codes: List[str] = Field(default_factory=lambda: ["member"])
    member_number: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = Field(None, max_length=1000)


class MembershipUpdate(BaseModel):
    status: Optional[str] = None              # active | suspended | resigned
    role_codes: Optional[List[str]] = None
    member_number: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = Field(None, max_length=1000)


class MembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    association_id: UUID
    member_number: Optional[str]
    status: str
    joined_at: datetime
    left_at: Optional[datetime]
    cumulative_contributions: int
    notes: Optional[str]
    user: UserBrief
    roles: List[RoleOut] = []
    created_at: datetime
    updated_at: datetime
    # Populated contextually — never stored on the model.
    activation_url: Optional[str] = None        # set on create when an invite was sent
    association_name: Optional[str] = None       # set by the groupement-wide members list
