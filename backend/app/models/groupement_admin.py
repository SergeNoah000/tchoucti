"""GroupementAdmin link — user × groupement, with an `is_owner` flag.

A groupement has exactly one owner (the original creator or the user it was
transferred to) and zero-or-more co-admins. The owner is allowed to manage
the admin team; co-admins only manage operational data.

A user can theoretically admin multiple groupements (think consultant), so we
keep this as a many-to-many even though today the seed only links each user
once.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.groupement import Groupement
    from app.models.user import User


class GroupementAdmin(BaseModel):
    __tablename__ = "groupement_admins"
    __table_args__ = (
        UniqueConstraint("groupement_id", "user_id", name="uq_groupement_admins_pair"),
    )

    groupement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groupements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    is_owner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    added_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    groupement: Mapped["Groupement"] = relationship("Groupement", foreign_keys=[groupement_id])
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    added_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[added_by_id])

    def __repr__(self) -> str:
        suffix = " (owner)" if self.is_owner else ""
        return f"<GroupementAdmin user={self.user_id} grp={self.groupement_id}{suffix}>"
