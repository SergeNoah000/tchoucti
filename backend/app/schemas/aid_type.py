"""Pydantic schemas for AidType (config-v2 catalogue d'aides sociales)."""
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AidTypeCreate(BaseModel):
    association_id: UUID
    source_caisse_id: UUID
    name: str = Field(..., min_length=2, max_length=150)
    slug: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = Field(None, max_length=1000)

    # Cotisation membre
    member_contribution_amount: int = Field(0, ge=0)
    is_contribution_recurring: bool = False

    # Versement
    aid_ceiling_amount: int = Field(0, ge=0)

    # Contraintes
    max_claims_per_member_per_year: int = Field(1, ge=1, le=20)
    declaration_delay_days: int = Field(30, ge=0, le=365)


class AidTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    description: Optional[str] = Field(None, max_length=1000)
    is_active: Optional[bool] = None
    source_caisse_id: Optional[UUID] = None

    member_contribution_amount: Optional[int] = Field(None, ge=0)
    is_contribution_recurring: Optional[bool] = None
    aid_ceiling_amount: Optional[int] = Field(None, ge=0)
    max_claims_per_member_per_year: Optional[int] = Field(None, ge=1, le=20)
    declaration_delay_days: Optional[int] = Field(None, ge=0, le=365)


class AidTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    association_id: UUID
    source_caisse_id: UUID
    source_caisse_name: Optional[str] = None
    name: str
    slug: str
    description: Optional[str]
    is_active: bool

    member_contribution_amount: int
    is_contribution_recurring: bool
    aid_ceiling_amount: int
    max_claims_per_member_per_year: int
    declaration_delay_days: int
