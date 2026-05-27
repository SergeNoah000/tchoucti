"""Pydantic schemas for the social-aid module."""
from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SocialAidCaseCreate(BaseModel):
    association_id: UUID
    beneficiary_membership_id: UUID
    kind: str = Field(..., pattern=r"^(death|illness|marriage|birth|other)$")
    title: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    event_date: Optional[date] = None
    # Phase 2e — référence optionnelle à un AidType configuré. Si fourni,
    # ses règles (plafond, délai, max claims) sont vérifiées et la caisse
    # source est snapshotée sur le dossier.
    aid_type_id: Optional[UUID] = None


class SocialAidApprove(BaseModel):
    # Optional override of the configured scale amount.
    approved_amount: Optional[int] = Field(None, ge=0)


class SocialAidReject(BaseModel):
    reason: str = Field(..., min_length=2, max_length=1000)


class SocialAidPayoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paid_on: date
    amount: int
    movement_id: Optional[UUID]
    notes: Optional[str]


class SocialAidCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    association_id: UUID
    beneficiary_membership_id: UUID
    beneficiary_name: Optional[str] = None
    aid_type_id: Optional[UUID] = None
    source_caisse_id: Optional[UUID] = None
    reference: str
    kind: str
    status: str
    title: str
    description: Optional[str]
    event_date: Optional[date]
    requested_on: date
    decided_on: Optional[date]
    requested_amount: Optional[int]
    approved_amount: int
    paid_amount: int
    rejection_reason: Optional[str]
    created_at: datetime


class SocialAidCaseDetail(SocialAidCaseOut):
    payouts: List[SocialAidPayoutOut] = []


# ── Phase 5 — historique des cotisations ──────────────────────────────────


class AidContributionOut(BaseModel):
    """Une cotisation d'un membre pour une aide sociale, capturée en séance."""

    model_config = ConfigDict(from_attributes=True)

    entry_id: UUID
    meeting_id: UUID
    meeting_title: str
    meeting_date: date
    membership_id: UUID
    member_name: Optional[str] = None
    aid_type_id: Optional[UUID] = None
    aid_type_name: Optional[str] = None
    amount: int
    status: str  # entry status (recorded / draft / voided / corrected)
