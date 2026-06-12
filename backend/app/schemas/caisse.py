"""Pydantic schemas for Caisse (config-v2 layer over Fund)."""
from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.caisse import (
    CaisseCategory,
    DistributionPeriod,
    InterestDistribution,
    WithdrawalMode,
)


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

    # Phase 7 (Fred) — mode rendement partagé. Défauts neutres.
    interest_distribution: InterestDistribution = InterestDistribution.KEPT
    distribution_period: DistributionPeriod = DistributionPeriod.PER_MEETING
    withdrawal_mode: WithdrawalMode = WithdrawalMode.NEVER

    @model_validator(mode="after")
    def _validate(self) -> "CaisseCreate":
        if self.category == CaisseCategory.SYSTEM:
            raise ValueError("Les caisses système sont auto-créées.")
        # Une caisse récurrente (collectée à chaque séance) n'est PAS obligée
        # d'avoir un montant de cotisation : 0 = montant libre, chaque membre
        # verse ce qu'il veut à chaque séance.
        #
        # Le montant d'une cotisation OBLIGATOIRE n'est plus un champ distinct :
        # il reprend celui collecté par séance (recurring_amount). Une cotisation
        # peut donc être obligatoire sans être fixe (montant = 0 = libre).
        if self.is_member_required:
            self.member_required_amount = self.recurring_amount
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

    # Phase 7 (Fred)
    interest_distribution: Optional[InterestDistribution] = None
    distribution_period: Optional[DistributionPeriod] = None
    withdrawal_mode: Optional[WithdrawalMode] = None


class CaisseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    association_id: UUID
    fund_id: UUID
    # Kind of the backing fund (general/insurance/tontine/custom/…). Lets the
    # frontend tell a tontine caisse apart from general/insurance — all SYSTEM
    # category, but tontine caisses must never be a loan/aid source.
    fund_kind: Optional[str] = None
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

    # Phase 7 (Fred)
    interest_distribution: str = InterestDistribution.KEPT.value
    distribution_period: str = DistributionPeriod.PER_MEETING.value
    withdrawal_mode: str = WithdrawalMode.NEVER.value
    last_distribution_at: Optional[date] = None


# ── Phase 7 (Fred) — sous-soldes, distributions ─────────────────────────────


class CaisseContributorBalanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    membership_id: UUID
    member_name: Optional[str] = None
    apport_cum: int
    apport_cum_at_period_start: int
    interest_cum: int


class CaisseDistributionShareOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    membership_id: UUID
    member_name: Optional[str] = None
    base: int
    share_amount: int


class CaisseDistributionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    caisse_id: UUID
    period_start: date
    period_end: date
    period_label: str
    interest_pool: int
    total_base: int
    closed_at: datetime
    closed_by_id: Optional[UUID] = None
    shares: List[CaisseDistributionShareOut] = []


class CaisseWithdrawRequest(BaseModel):
    membership_id: UUID
    amount: int = Field(..., gt=0)
    note: Optional[str] = Field(None, max_length=500)


class CaisseWithdrawResponse(BaseModel):
    movement_id: UUID
    amount: int
    apport_cum_after: int
    fund_balance_after: int


class MyShareItem(BaseModel):
    """Vue agrégée « ma part dans une caisse » pour un membre."""

    caisse_id: UUID
    caisse_name: str
    caisse_slug: str
    category: str
    interest_distribution: str
    apport_cum: int
    interest_cum: int
    total_apport: int  # Σ apport_cum de la caisse (pour calculer ma %)
    last_distribution_at: Optional[date] = None
