"""Pydantic schemas for Association.

`config` (JSONB) holds the operational settings the admin tunes. Expected shape
(all keys optional — the settings UI patches per section):

    {
      "tontine":       {contribution_amount, frequency, cycle_duration_months,
                        participants_count, allocation_method},
      "social_fund":   {contribution_amount, conditions,
                        events: {death, illness, marriage, birth}},
      "payments":      {cash, mtn_momo, orange_money, bank_transfer},   # bool
      "meetings":      {frequency, mode, quorum, auto_notify},
      "notifications": {contribution_reminder, meeting, penalty,
                        tour_allocation, birthday, loan_due},           # bool
    }
"""
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.association import AssociationType


class AssociationBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = Field(None, max_length=1000)
    type: AssociationType = AssociationType.ASSOCIATION
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=30)
    currency: str = Field("XAF", max_length=3)
    timezone: str = Field("Africa/Douala", max_length=50)
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=100)
    primary_color: str = Field("#0F766E", pattern=r"^#[0-9A-Fa-f]{6}$")
    config: Dict[str, Any] = Field(default_factory=dict)


class AssociationCreate(AssociationBase):
    groupement_id: UUID


class AssociationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    type: Optional[AssociationType] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=30)
    currency: Optional[str] = Field(None, max_length=3)
    timezone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=100)
    primary_color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class AssociationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    description: Optional[str]
    type: AssociationType
    email: Optional[str]
    phone: Optional[str]
    logo_url: Optional[str]
    primary_color: str
    currency: str
    timezone: str
    address: Optional[str]
    city: Optional[str]
    config: Dict[str, Any]
    is_active: bool
    groupement_id: UUID
    created_at: datetime
    updated_at: datetime
