"""Schémas des demandes de sortie d'argent (validation trésorier)."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PayoutRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    association_id: UUID
    kind: str
    status: str
    source_type: str
    source_id: Optional[UUID] = None
    amount: int
    currency: Optional[str] = None
    description: Optional[str] = None

    fund_id: Optional[UUID] = None
    fund_name: Optional[str] = None

    related_membership_id: Optional[UUID] = None
    beneficiary_name: Optional[str] = None

    prepared_by_id: Optional[UUID] = None
    prepared_by_name: Optional[str] = None
    prepared_at: datetime

    decided_by_id: Optional[UUID] = None
    decided_by_name: Optional[str] = None
    decided_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    movement_id: Optional[UUID] = None

    created_at: datetime


class PayoutDecision(BaseModel):
    """Note optionnelle jointe à une validation / un refus."""

    note: Optional[str] = None
