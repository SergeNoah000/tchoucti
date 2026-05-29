"""Authentication endpoints: login, refresh, logout, me, activate."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api.deps import get_current_user, get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.models.role import Membership, MembershipRole, MembershipStatus, Role
from app.models.user import InviteStatus, User, UserType
from app.schemas.auth import (
    ActivateRequest,
    ChangePasswordRequest,
    RefreshRequest,
    TokenPair,
    UpdateProfileRequest,
    UserPublic,
)

router = APIRouter()


async def _public_user(db: AsyncSession, user: User) -> dict:
    """Adapt SQLAlchemy User → frontend-facing payload.

    Computes the role flags from membership data (not from `user.user_type`
    alone): only users with at least one `association_admin` role on an
    ACTIVE membership get `is_association_admin=True`. Treasurers, secretaries,
    censors and plain members get `has_association_role=True` instead and see
    only the operational dashboard.
    """
    is_assoc_admin = False
    has_assoc_role = False
    has_bureau_role = False
    if user.user_type in (UserType.ASSOCIATION_USER, UserType.MEMBER):
        stmt = (
            select(Role.code)
            .join(MembershipRole, MembershipRole.role_id == Role.id)
            .join(Membership, Membership.id == MembershipRole.membership_id)
            .where(
                Membership.user_id == user.id,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
        res = await db.execute(stmt)
        role_codes = {row[0] for row in res.all()}
        has_assoc_role = bool(role_codes)
        is_assoc_admin = "association_admin" in role_codes
        # Bureau = anything that lets the user act during meetings beyond just
        # attending. Plain "member" alone does NOT count.
        has_bureau_role = bool(role_codes - {"member"})

    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "is_active": user.is_active,
        "is_platform_admin": user.user_type == UserType.SUPER_ADMIN,
        "is_groupement_admin": user.user_type == UserType.GROUPEMENT_ADMIN,
        "is_association_admin": is_assoc_admin,
        "has_association_role": has_assoc_role,
        "has_bureau_role": has_bureau_role,
        "avatar_url": user.avatar_url,
        "groupement_id": user.groupement_id,
        "created_at": user.created_at,
    }


@router.post("/login", response_model=TokenPair)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """OAuth2-style login. Accepts form-encoded ``username`` + ``password``."""
    res = await db.execute(select(User).where(User.email == form.username.lower()))
    user = res.scalar_one_or_none()
    if not user or not user.hashed_password or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé",
        )

    extra = {"is_platform_admin": user.user_type == UserType.SUPER_ADMIN}
    access = create_access_token(user.id, extra_claims=extra)
    refresh = create_refresh_token(user.id)

    user.last_login_at = datetime.utcnow()
    await db.commit()

    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenPair)
async def refresh_tokens(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    data = decode_token(payload.refresh_token)
    if not data or data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    try:
        user_id = UUID(data["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User inactive")

    extra = {"is_platform_admin": user.user_type == UserType.SUPER_ADMIN}
    return TokenPair(
        access_token=create_access_token(user.id, extra_claims=extra),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/logout", status_code=204)
async def logout(_: User = Depends(get_current_user)):
    """Stateless logout — frontend just discards tokens."""
    return None


@router.get("/me", response_model=UserPublic)
async def me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _public_user(db, user)


@router.patch("/me", response_model=UserPublic)
async def update_me(
    payload: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the current user's own profile (display name, phone)."""
    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    if payload.phone is not None:
        user.phone = payload.phone.strip() or None
    await db.commit()
    await db.refresh(user)
    return await _public_user(db, user)


@router.post("/change-password", status_code=204)
async def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password (requires the current one)."""
    if not user.hashed_password or not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Mot de passe actuel incorrect")
    user.hashed_password = get_password_hash(payload.new_password)
    await db.commit()
    return None


@router.post("/activate", response_model=UserPublic)
async def activate(payload: ActivateRequest, db: AsyncSession = Depends(get_db)):
    data = decode_token(payload.token)
    if not data or data.get("type") != "invitation":
        raise HTTPException(status_code=400, detail="Lien d'activation invalide ou expiré")
    try:
        user_id = UUID(data["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Lien d'activation invalide")

    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    user.hashed_password = get_password_hash(payload.password)
    user.is_active = True
    user.is_verified = True
    user.invite_status = InviteStatus.ACCEPTED
    await db.commit()
    await db.refresh(user)
    return await _public_user(db, user)
