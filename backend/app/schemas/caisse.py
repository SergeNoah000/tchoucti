"""Pydantic schemas for Caisse (config-v2 layer over Fund)."""
from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.caisse import CaisseCategory


class CaisseCreate(BaseModel):
    """Create a custom caisse. System caisses are auto-created at association
    creation; admins can only create COLLECTIVE / PROJECT / PERSONAL ones here."""

    association_id: UUID
    name: str = Field(..., min_length=2, max_length=150)
    slug: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = Field(None, max_length=1000)
    category: CaisseCategory

    is_recurring: bool = False
    recurring_amount: int = Field(0, ge=0)

    is_member_required: bool = False
    member_required_amount: int = Field(0, ge=0)

    has_ceiling: bool = False
    ceiling_amount: int = Field(0, ge=0)

    has_objective: bool = False
    objective_amount: int = Field(0, ge=0)
    objective_deadline: Optional[date] = None

    @model_validator(mode="after")
    def _validate(self) -> "CaisseCreate":
        if self.category == CaisseCategory.SYSTEM:
            raise ValueError("Les caisses système sont auto-créées.")
        if self.is_recurring and self.recurring_amount <= 0:
            raise ValueError("Une caisse récurrente doit avoir un montant > 0.")
        if self.is_member_required and self.member_required_amount <= 0:
            raise ValueError("Une cotisation obligatoire doit avoir un montant > 0.")
        if self.has_ceiling and self.ceiling_amount <= 0:
            raise ValueError("Le plafond doit être > 0.")
        if self.has_objective and self.objective_amount <= 0:
            raise ValueError("L'objectif doit être > 0.")
        if self.category == CaisseCategory.PROJECT and not self.has_objective:
            raise ValueError("Une caisse projet doit avoir un objectif.")
        return self


class CaisseUpdate(BaseModel):
    """Editable fields of an existing caisse. Slug/category are immutable."""

    name: Optional[str] = Field(None, min_length=2, max_length=150)
    description: Optional[str] = Field(None, max_length=1000)
    is_active: Optional[bool] = None

    is_recurring: Optional[bool] = None
    recurring_amount: Optional[int] = Field(None, ge=0)

    is_member_required: Optional[bool] = None
    member_required_amount: Optional[int] = Field(None, ge=0)

    has_ceiling: Optional[bool] = None
    ceiling_amount: Optional[int] = Field(None, ge=0)

    has_objective: Optional[bool] = None
    objective_amount: Optional[int] = Field(None, ge=0)
    objective_deadline: Optional[date] = None


class CaisseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    association_id: UUID
    fund_id: UUID
    name: str
    slug: str
    description: Optional[str]
    category: CaisseCategory
    is_system: bool
    is_active: bool

    is_recurring: bool
    recurring_amount: int

    is_member_required: bool
    member_required_amount: int

    has_ceiling: bool
    ceiling_amount: int

    has_objective: bool
    objective_amount: int
    objective_deadline: Optional[date]
