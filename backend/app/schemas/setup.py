"""Schemas for the admin setup wizard (Phase 1 — config-v2)."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.association import MembershipCriterionType


class SetupStateOut(BaseModel):
    """Where the admin is in the onboarding wizard."""

    setup_complete: bool = False
    setup_step: int = 0


class SetupAdvanceRequest(BaseModel):
    """Mark a wizard step done (advance) or finalise setup."""

    step: Optional[int] = Field(None, ge=0, le=5, description="0..5; 5 = wizard finished")
    complete: Optional[bool] = None


class RegistrationFeeUpdate(BaseModel):
    registration_fee: int = Field(..., ge=0, le=10_000_000)


# ── MembershipCriterion ────────────────────────────────────────────────────

class CriterionCreate(BaseModel):
    type: MembershipCriterionType
    label: str = Field(..., min_length=1, max_length=150)
    value: str = Field(..., min_length=1, max_length=255)
    is_required: bool = True
    sort_order: int = 0


class CriterionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    association_id: UUID
    type: MembershipCriterionType
    label: str
    value: str
    is_required: bool
    sort_order: int


# ── Documents ──────────────────────────────────────────────────────────────

class DocumentOut(BaseModel):
    """A legal document attached to an association (statuts, ROI, récépissé…)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    association_id: UUID
    title: str
    description: Optional[str] = None
    kind: str
    file_url: str
    file_name: str
    file_mime: str
    file_size: int
    visibility: str
    uploaded_by_id: Optional[UUID] = None
    created_at: datetime
