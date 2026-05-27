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

    Flags are derived from User.user_type AND membership roles:
      - `is_platform_admin`     : user_type == SUPER_ADMIN
      - `is_groupement_admin`   : user_type == GROUPEMENT_ADMIN
      - `is_association_admin`  : has at least one Membership with role
                                  `association_admin`. ONLY this flag unlocks
                                  the configuration UI (silo principle).
      - `has_association_role`  : has any active Membership (admin, treasurer,
                                  secretary, censor, manager, member). Used to
                                  route to operational pages.

    The frontend uses these flags to pick the dashboard and gate the config
    section (cf. `useCanConfigure()`).
    """

    id: UUID
    email: EmailStr
    full_name: str
    phone: Optional[str] = None
    is_active: bool
    is_platform_admin: bool
    is_groupement_admin: bool = False
    is_association_admin: bool = False
    has_association_role: bool = False
    # True if the user holds any role other than plain "member" on a membership
    # (treasurer, secretary, manager, admin). Used to unlock bureau-only
    # operational actions during meetings.
    has_bureau_role: bool = False
    avatar_url: Optional[str] = None
    groupement_id: Optional[UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}
