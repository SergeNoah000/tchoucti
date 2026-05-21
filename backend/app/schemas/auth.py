"""Auth schemas — token + user payloads exposed to the frontend."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ActivateRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


class UserPublic(BaseModel):
    """Shape consumed by the Next.js frontend (see frontend/src/lib/types.ts).

    `is_platform_admin`, `is_groupement_admin`, `is_association_admin` are
    mutually exclusive flags derived from `User.user_type`. The frontend uses
    them to pick the appropriate role-specific dashboard and navigation.
    """

    id: UUID
    email: EmailStr
    full_name: str
    phone: Optional[str] = None
    is_active: bool
    is_platform_admin: bool
    is_groupement_admin: bool = False
    is_association_admin: bool = False
    avatar_url: Optional[str] = None
    groupement_id: Optional[UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}
