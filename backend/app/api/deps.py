"""Reusable FastAPI dependencies."""
from typing import AsyncGenerator
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security import decode_token
from app.db.session import AsyncSessionLocal
from app.models.association import Association
from app.models.role import Membership, MembershipRole, MembershipStatus, Role
from app.models.user import User, UserType

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    creds_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise creds_exc

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise creds_exc
    sub = payload.get("sub")
    if not sub:
        raise creds_exc
    try:
        user_id = UUID(sub)
    except (ValueError, TypeError):
        raise creds_exc

    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user or not user.is_active:
        raise creds_exc
    return user


async def _user_is_association_admin(
    db: AsyncSession, user: User, association_id: UUID | None = None
) -> bool:
    """True if `user` holds the `association_admin` role on at least one ACTIVE
    membership. If `association_id` is given, restrict the check to that
    association."""
    stmt = (
        select(Role.code)
        .join(MembershipRole, MembershipRole.role_id == Role.id)
        .join(Membership, Membership.id == MembershipRole.membership_id)
        .where(
            Membership.user_id == user.id,
            Membership.status == MembershipStatus.ACTIVE,
            Role.code == "association_admin",
        )
    )
    if association_id is not None:
        stmt = stmt.where(Membership.association_id == association_id)
    res = await db.execute(stmt)
    return res.first() is not None


async def require_association_admin(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Allow only platform / groupement admins, or users with the
    `association_admin` role. Used to gate the configuration endpoints
    (caisses, loan_types, aid_types, association settings, tontine setup…)
    so that operational roles (treasurer, secretary, member) can't touch them.
    """
    if user.user_type == UserType.SUPER_ADMIN:
        return user
    if user.user_type == UserType.GROUPEMENT_ADMIN:
        return user
    if await _user_is_association_admin(db, user):
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Réservé à l'administrateur d'association",
    )


async def require_association_admin_for(
    association_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Like `require_association_admin` but pinned to a specific association.

    Use when an endpoint takes an `association_id` path/query/body param and
    you want to make sure the caller is the admin OF THAT association (not
    just admin of some other one in the same groupement).
    """
    if user.user_type == UserType.SUPER_ADMIN:
        return user
    if user.user_type == UserType.GROUPEMENT_ADMIN:
        # Groupement admins manage all associations in their groupement.
        res = await db.execute(
            select(Association.groupement_id).where(Association.id == association_id)
        )
        gid = res.scalar_one_or_none()
        if gid is not None and gid == user.groupement_id:
            return user
    if await _user_is_association_admin(db, user, association_id):
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Réservé à l'administrateur de cette association",
    )
