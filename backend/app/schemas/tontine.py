"""Pydantic schemas for the tontine module."""
from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TontineParticipant(BaseModel):
    """One beneficiary slot inside a round.

    `share_parts` lets the admin tune unequal splits (e.g. 2+1 for 2/3 vs 1/3).
    Default 1 = equal split among everyone in the same round.
    """

    membership_id: UUID
    share_parts: int = Field(1, ge=1, le=100)


class TontineRoundConfig(BaseModel):
    """The beneficiary set of one round."""

    beneficiaries: List[TontineParticipant] = Field(..., min_length=1, max_length=20)


class TontineCycleCreate(BaseModel):
    association_id: UUID
    name: str = Field(..., min_length=2, max_length=150)
    description: Optional[str] = Field(None, max_length=500)
    round_amount: int = Field(..., gt=0, description="Montant versé par participant à chaque tour")
    start_date: date
    rounds: List[TontineRoundConfig] = Field(..., min_length=1, max_length=50)
    shuffle: bool = False
    # Phase 2c — Multi-tontines + meeting binding
    is_mandatory: bool = Field(
        True,
        description="Si False, l'admin peut opt-out certains membres via excluded_membership_ids.",
    )
    excluded_membership_ids: List[UUID] = Field(
        default_factory=list,
        description="Memberships exclus de ce cycle (utile uniquement si is_mandatory=False).",
    )
    meeting_ids: Optional[List[UUID]] = Field(
        None,
        description=(
            "Mapping explicite tour → séance hôte (taille = nb de tours). "
            "Si null : auto-pick des N prochaines séances PLANNED après start_date "
            "(génère des séances manquantes via la cadence asso si besoin)."
        ),
    )


class TontineBeneficiaryOut(BaseModel):
    membership_id: UUID
    name: Optional[str] = None
    share_amount: int
    share_parts: int


class TontineRoundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    round_number: int
    scheduled_date: Optional[date]
    paid_out_date: Optional[date]
    beneficiaries: List[TontineBeneficiaryOut] = []
    expected_amount: int
    collected_amount: int
    paid_out_amount: int
    status: str
    # Phase 2c — séance hôte du tour (null si pas encore mappée)
    meeting_id: Optional[UUID] = None
    meeting_title: Optional[str] = None


class TontineCycleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    association_id: UUID
    name: str
    slug: str
    description: Optional[str]
    round_amount: int
    rounds_count: int
    current_round_number: int
    start_date: date
    end_date: Optional[date]
    order_strategy: str
    status: str
    is_mandatory: bool = True
    created_at: datetime


class TontineCycleDetail(TontineCycleOut):
    rounds: List[TontineRoundOut] = []
    # round_amount × number of unique beneficiaries across the cycle
    pot_amount: int = 0
