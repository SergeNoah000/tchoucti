"""Pydantic schemas for Meeting, Activity, Attendance, MeetingActivityEntry."""
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Activity ───────────────────────────────────────────────────────────────

class ActivityCreate(BaseModel):
    association_id: UUID
    type: str  # ActivityType value
    code: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    color: str = Field("#0F766E", pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: Optional[str] = Field(None, max_length=50)
    config: Dict[str, Any] = Field(default_factory=dict)
    is_visible_in_meeting: bool = True
    is_required: bool = False
    sort_order: int = 0


class ActivityUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: Optional[str] = Field(None, max_length=50)
    config: Optional[Dict[str, Any]] = None
    is_visible_in_meeting: Optional[bool] = None
    is_required: Optional[bool] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    association_id: UUID
    type: str
    code: str
    name: str
    description: Optional[str]
    color: str
    icon: Optional[str]
    config: Dict[str, Any]
    is_visible_in_meeting: bool
    is_required: bool
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ── Meeting ────────────────────────────────────────────────────────────────

class MeetingCreate(BaseModel):
    association_id: UUID
    title: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    scheduled_on: date
    location: Optional[str] = Field(None, max_length=255)
    agenda: Dict[str, Any] = Field(default_factory=dict)
    facilitator_id: Optional[UUID] = None


class MeetingUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    scheduled_on: Optional[date] = None
    location: Optional[str] = Field(None, max_length=255)
    agenda: Optional[Dict[str, Any]] = None
    facilitator_id: Optional[UUID] = None
    status: Optional[str] = None  # planned|ongoing|closed|cancelled


class MeetingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    association_id: UUID
    title: str
    description: Optional[str]
    scheduled_on: date
    started_at: Optional[datetime]
    closed_at: Optional[datetime]
    location: Optional[str]
    status: str
    facilitator_id: Optional[UUID]
    created_by_id: Optional[UUID]
    agenda: Dict[str, Any]
    report_url: Optional[str]
    total_in: int
    total_out: int
    created_at: datetime
    updated_at: datetime


# ── Attendance ─────────────────────────────────────────────────────────────

class AttendanceUpsert(BaseModel):
    membership_id: UUID
    status: str = "present"  # present|absent|excused|late
    notes: Optional[str] = Field(None, max_length=500)
    excuse_reason: Optional[str] = Field(None, max_length=500)


class AttendanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    meeting_id: UUID
    membership_id: UUID
    status: str
    notes: Optional[str]
    excuse_reason: Optional[str]


# ── MeetingActivityEntry ───────────────────────────────────────────────────

class EntryCreate(BaseModel):
    meeting_id: UUID
    membership_id: UUID
    activity_id: UUID
    amount: int = Field(..., gt=0)
    data: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = Field(None, max_length=1000)


class EntryUpdate(BaseModel):
    amount: Optional[int] = Field(None, gt=0)
    data: Optional[Dict[str, Any]] = None
    notes: Optional[str] = Field(None, max_length=1000)
    correction_reason: Optional[str] = Field(None, max_length=500)


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    meeting_id: UUID
    membership_id: UUID
    activity_id: UUID
    amount: int
    data: Dict[str, Any]
    status: str
    movement_id: Optional[UUID]
    recorded_by_id: Optional[UUID]
    recorded_at: Optional[datetime]
    corrects_entry_id: Optional[UUID]
    correction_reason: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


# ── Meeting detail (with attendances + entries) ────────────────────────────

class MeetingDetail(MeetingOut):
    attendances: List[AttendanceOut] = []
    entries: List[EntryOut] = []
