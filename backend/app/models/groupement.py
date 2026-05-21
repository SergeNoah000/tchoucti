"""Groupement = tenant level 1. Mapped to a subdomain."""
import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.association import Association
    from app.models.role import Role
    from app.models.user import User


class SubscriptionStatus(str, Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Groupement(BaseModel):
    """A `Groupement` is the top-level tenant.

    It owns multiple associations, has its own admins, sits on its own
    subdomain `{slug}.tchoucti.com` and has its own subscription/billing.
    """

    __tablename__ = "groupements"

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    subdomain: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    custom_domain: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)

    # Contact / branding
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(String(50), default="Cameroun", nullable=False)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[str] = mapped_column(String(7), default="#0F766E", nullable=False)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Subscription (simple version for now)
    subscription_status: Mapped[str] = mapped_column(
        String(20), default=SubscriptionStatus.TRIAL.value, nullable=False
    )
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    subscription_starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    subscription_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    billing_cycle: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)

    # Quotas
    max_associations: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    max_users: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    max_storage_mb: Mapped[int] = mapped_column(Integer, default=500, nullable=False)

    # Relationships
    associations: Mapped[List["Association"]] = relationship(
        "Association", back_populates="groupement", cascade="all, delete-orphan"
    )
    users: Mapped[List["User"]] = relationship("User", back_populates="groupement")
    roles: Mapped[List["Role"]] = relationship(
        "Role", back_populates="groupement", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Groupement {self.slug}>"
