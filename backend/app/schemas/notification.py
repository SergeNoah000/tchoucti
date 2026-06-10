"""Schemas for in-app notifications."""
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    title: str
    body: Optional[str] = None
    action_url: Optional[str] = None
    data: Dict[str, Any] = {}
    read_at: Optional[datetime] = None
    is_archived: bool = False
    association_id: Optional[UUID] = None
    created_at: datetime


class UnreadCountOut(BaseModel):
    unread: int
