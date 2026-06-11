"""Pydantic schemas for AidType (config-v2 catalogue d'aides sociales)."""
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

FundingMode = Literal["fixed", "temporary", "member_insurance"]
AmountMode = Literal["ceiling", "objective"]


class AidTypeCreate(BaseModel):
    association_id: UUID

    # Mode de financement (coexistence) — voir AidType.funding_mode.
    funding_mode: FundingMode = "fixed"
    source_caisse_id: Optional[UUID] = None      # mode "fixed"
    auto_create_caisse: bool = False             # legacy / mode "temporary"
    insurance_caisse_id: Optional[UUID] = None   # mode "member_insurance"
    insurance_minimum: int = Field(0, ge=0)
    refill_period_days: int = Field(90, ge=1, le=730)

    name: str = Field(..., min_length=2, max_length=150)
    slug: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = Field(None, max_length=1000)

    # Cotisation membre
    member_contribution_amount: int = Field(0, ge=0)
    is_contribution_recurring: bool = False

    # Montant versé
    amount_mode: AmountMode = "ceiling"
    aid_ceiling_amount: int = Field(0, ge=0)
    objective_amount: int = Field(0, ge=0)

    # Contraintes
    max_claims_per_member_per_year: int = Field(1, ge=1, le=20)
    declaration_delay_days: int = Field(30, ge=0, le=365)

    @model_validator(mode="after")
    def _check(self):
        # Cohérence financement.
        if self.funding_mode == "temporary":
            self.auto_create_caisse = True
            self.source_caisse_id = None
        elif self.funding_mode == "member_insurance":
            self.auto_create_caisse = False
            self.source_caisse_id = None
            # insurance_caisse_id peut être None → la caisse perso d'assurance
            # est auto-créée côté endpoint.
        else:  # fixed
            self.auto_create_caisse = False
            if self.source_caisse_id is None:
                raise ValueError("source_caisse_id requis en mode 'fixed'")
        # Cohérence montant.
        if self.amount_mode == "objective" and self.objective_amount <= 0:
            raise ValueError("objective_amount > 0 requis en mode 'objective'")
        return self


class AidTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    description: Optional[str] = Field(None, max_length=1000)
    is_active: Optional[bool] = None
    source_caisse_id: Optional[UUID] = None
    auto_create_caisse: Optional[bool] = None
    funding_mode: Optional[FundingMode] = None
    insurance_caisse_id: Optional[UUID] = None
    insurance_minimum: Optional[int] = Field(None, ge=0)
    refill_period_days: Optional[int] = Field(None, ge=1, le=730)

    member_contribution_amount: Optional[int] = Field(None, ge=0)
    is_contribution_recurring: Optional[bool] = None
    amount_mode: Optional[AmountMode] = None
    aid_ceiling_amount: Optional[int] = Field(None, ge=0)
    objective_amount: Optional[int] = Field(None, ge=0)
    max_claims_per_member_per_year: Optional[int] = Field(None, ge=1, le=20)
    declaration_delay_days: Optional[int] = Field(None, ge=0, le=365)


class AidTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    association_id: UUID
    funding_mode: str = "fixed"
    source_caisse_id: Optional[UUID] = None
    source_caisse_name: Optional[str] = None
    auto_create_caisse: bool = False
    insurance_caisse_id: Optional[UUID] = None
    insurance_caisse_name: Optional[str] = None
    insurance_minimum: int = 0
    refill_period_days: int = 90
    name: str
    slug: str
    description: Optional[str]
    is_active: bool

    member_contribution_amount: int
    is_contribution_recurring: bool
    amount_mode: str = "ceiling"
    aid_ceiling_amount: int
    objective_amount: int = 0
    max_claims_per_member_per_year: int
    declaration_delay_days: int
