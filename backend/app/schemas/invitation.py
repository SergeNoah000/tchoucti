"""Pydantic schemas for invitations + groupement admins."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.invitation import InvitationKind, InvitationStatus


class InvitationCreate(BaseModel):
    """Inputs accepted by the inviter — kind & scope are inferred at the route level."""

    email: EmailStr
    full_name: Optional[str] = Field(None, max_length=255)
    message: Optional[str] = Field(None, max_length=1000)


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    kind: InvitationKind
    status: InvitationStatus
    full_name: Optional[str] = None
    message: Optional[str] = None
    groupement_id: Optional[UUID] = None
    association_id: Optional[UUID] = None
    invited_by_id: Optional[UUID] = None
    expires_at: datetime
    sent_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    resent_count: int
    created_at: datetime


class InvitationCreated(InvitationOut):
    """Returned right after creating/resending — embeds the plain activation URL.

    The plain token is NOT persisted in DB (only its hash). We hand the URL to
    the caller so the inviter can copy/share it manually if email delivery is
    flaky.
    """

    activation_url: str


class GroupementAdminOut(BaseModel):
    """Membership of a user in a groupement's admin team."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    groupement_id: UUID
    is_owner: bool
    added_at: datetime
    # Denormalised user info for the admin list UI
    user_email: Optional[str] = None
    user_full_name: Optional[str] = None
    user_is_active: Optional[bool] = None


class TransferOwnershipRequest(BaseModel):
    target_user_id: UUID
