from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.auth import UserPublic

router = APIRouter()

@router.get("", response_model=List[UserPublic])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List users.
    - Super admin → all users.
    - Groupement admin -> users of their groupement
    """
    if current_user.is_super_admin:
        result = await db.execute(select(User).order_by(User.email))
        return result.scalars().all()
    elif current_user.is_groupement_admin:
        result = await db.execute(select(User).where(User.groupement_id == current_user.groupement_id).order_by(User.email))
        return result.scalars().all()
    else:
        raise HTTPException(status_code=403, detail="Forbidden")

