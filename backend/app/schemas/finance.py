"""Pydantic schemas for the finance module."""
from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    ref_key: str
    name: str
    description: Optional[str]
    balance: int
    is_locked: bool
    is_system: bool


class TreasuryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    association_id: UUID
    balance: int
    currency: str
    is_locked: bool
    funds: List[FundOut] = []


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    direction: str
    amount: int
    balance_after: int
    occurred_on: date
    source_type: str
    source_id: Optional[UUID]
    related_membership_id: Optional[UUID]
    description: Optional[str]
    is_voided: bool
    created_at: datetime


class MovementCreate(BaseModel):
    """Manual movement posted by an admin (adjustment, external cash-in/out, transfer)."""

    association_id: UUID
    direction: str = Field(..., pattern=r"^(in|out|xfer)$")
    amount: int = Field(..., gt=0)
    # IN/OUT → target fund. XFER → source fund.
    fund_id: UUID
    # XFER only → destination fund.
    to_fund_id: Optional[UUID] = None
    occurred_on: date
    description: Optional[str] = Field(None, max_length=500)
    related_membership_id: Optional[UUID] = None


class VoidRequest(BaseModel):
    reason: str = Field(..., min_length=2, max_length=500)
