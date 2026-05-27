"""Pydantic schemas for LoanType (config-v2 catalogue de prêts)."""
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LoanTypeCreate(BaseModel):
    association_id: UUID
    source_caisse_id: UUID
    name: str = Field(..., min_length=2, max_length=150)
    slug: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = Field(None, max_length=1000)

    eligibility_min_seniority_months: int = Field(0, ge=0, le=120)
    eligibility_no_default: bool = True
    max_simultaneous: int = Field(1, ge=1, le=10)
    max_per_year: int = Field(1, ge=1, le=20)

    # Taux mensuel et pénalité (%, ex 5.0 = 5%)
    interest_rate_pct: Decimal = Field(Decimal("0"), ge=0, le=100)
    late_fee_pct: Decimal = Field(Decimal("0"), ge=0, le=100)
    max_duration_months: int = Field(12, ge=1, le=120)


class LoanTypeUpdate(BaseModel):
    """Tous les champs sont optionnels. Slug + caisse source restent figés
    une fois que des prêts ont été émis avec ce type (validation côté API)."""

    name: Optional[str] = Field(None, min_length=2, max_length=150)
    description: Optional[str] = Field(None, max_length=1000)
    is_active: Optional[bool] = None
    source_caisse_id: Optional[UUID] = None

    eligibility_min_seniority_months: Optional[int] = Field(None, ge=0, le=120)
    eligibility_no_default: Optional[bool] = None
    max_simultaneous: Optional[int] = Field(None, ge=1, le=10)
    max_per_year: Optional[int] = Field(None, ge=1, le=20)

    interest_rate_pct: Optional[Decimal] = Field(None, ge=0, le=100)
    late_fee_pct: Optional[Decimal] = Field(None, ge=0, le=100)
    max_duration_months: Optional[int] = Field(None, ge=1, le=120)


class LoanTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    association_id: UUID
    source_caisse_id: UUID
    source_caisse_name: Optional[str] = None
    name: str
    slug: str
    description: Optional[str]
    is_active: bool

    eligibility_min_seniority_months: int
    eligibility_no_default: bool
    max_simultaneous: int
    max_per_year: int

    interest_rate_pct: Decimal
    late_fee_pct: Decimal
    max_duration_months: int
