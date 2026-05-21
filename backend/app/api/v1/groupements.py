"""Groupements CRUD + admin team management."""
from typing import List
from uuid import UUID

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.api.v1.invitations import (
    _send_invitation_email_safe,
    activation_url_for,
    hash_token,
    is_admin_of,
    is_owner_of,
    revoke_pending,
)
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.association import Association
from app.models.groupement import Groupement
from app.models.groupement_admin import GroupementAdmin
from app.models.invitation import (
    Invitation,
    InvitationKind,
    InvitationStatus,
    generate_invitation_token,
)
from app.models.role import Membership, MembershipRole
from app.models.user import User, UserType
from app.schemas.groupement import GroupementCreate, GroupementOut, GroupementUpdate
from app.schemas.membership import MembershipOut
from app.schemas.invitation import (
    GroupementAdminOut,
    InvitationCreate,
    InvitationCreated,
    InvitationOut,
    TransferOwnershipRequest,
)

router = APIRouter()


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────
def _require_super_admin(user: User) -> None:
    if not user.is_super_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin only")


async def _require_owner_or_super(db: AsyncSession, user: User, groupement_id: UUID) -> None:
    if user.is_super_admin:
        return
    if await is_owner_of(db, user.id, groupement_id):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner only")


async def _require_admin_or_super(db: AsyncSession, user: User, groupement_id: UUID) -> None:
    if user.is_super_admin:
        return
    if await is_admin_of(db, user.id, groupement_id):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _admin_link_to_out(row: GroupementAdmin) -> GroupementAdminOut:
    user = row.user
    return GroupementAdminOut(
        id=row.id,
        user_id=row.user_id,
        groupement_id=row.groupement_id,
        is_owner=row.is_owner,
        added_at=row.added_at,
        user_email=user.email if user else None,
        user_full_name=user.full_name if user else None,
        user_is_active=user.is_active if user else None,
    )


# ──────────────────────────────────────────────────────────────────────────
# CRUD
# ──────────────────────────────────────────────────────────────────────────
@router.get("", response_model=List[GroupementOut])
async def list_groupements(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.is_super_admin:
        result = await db.execute(select(Groupement).order_by(Groupement.name))
        return result.scalars().all()
    if not current_user.groupement_id:
        return []
    result = await db.execute(
        select(Groupement).where(Groupement.id == current_user.groupement_id)
    )
    g = result.scalar_one_or_none()
    return [g] if g else []


@router.get("/me", response_model=GroupementOut)
async def get_my_groupement(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the groupement the current user belongs to (or admins)."""
    if not current_user.groupement_id:
        raise HTTPException(404, "No groupement attached to your account")
    result = await db.execute(select(Groupement).where(Groupement.id == current_user.groupement_id))
    g = result.scalar_one_or_none()
    if not g:
        raise HTTPException(404, "Groupement not found")
    return g


@router.get("/{groupement_id}", response_model=GroupementOut)
async def get_groupement(
    groupement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Groupement).where(Groupement.id == groupement_id))
    g = result.scalar_one_or_none()
    if not g:
        raise HTTPException(status_code=404, detail="Groupement not found")
    if not current_user.is_super_admin and current_user.groupement_id != g.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return g


@router.post("", response_model=GroupementOut, status_code=status.HTTP_201_CREATED)
async def create_groupement(
    payload: GroupementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)

    existing = await db.execute(select(Groupement).where(Groupement.slug == payload.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Slug already taken")

    existing_user = await db.execute(select(User).where(User.email == payload.admin_email))
    if existing_user.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Admin email already in use")

    g = Groupement(
        name=payload.name,
        slug=payload.slug,
        subdomain=payload.slug,
        description=payload.description,
        email=payload.email,
        phone=payload.phone,
        address=payload.address,
        city=payload.city,
        country=payload.country,
        primary_color=payload.primary_color,
    )
    db.add(g)
    await db.flush()

    admin_user = User(
        email=payload.admin_email,
        full_name=payload.admin_name,
        hashed_password=get_password_hash(payload.admin_password),
        user_type=UserType.GROUPEMENT_ADMIN,
        groupement_id=g.id,
        is_active=True,
    )
    db.add(admin_user)
    await db.flush()

    # First admin is the owner.
    db.add(
        GroupementAdmin(
            user_id=admin_user.id,
            groupement_id=g.id,
            is_owner=True,
            added_by_id=current_user.id,
        )
    )
    await db.commit()
    await db.refresh(g)
    return g


@router.patch("/{groupement_id}", response_model=GroupementOut)
async def update_groupement(
    groupement_id: UUID,
    payload: GroupementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Groupement).where(Groupement.id == groupement_id))
    g = result.scalar_one_or_none()
    if not g:
        raise HTTPException(status_code=404, detail="Groupement not found")

    if not current_user.is_super_admin:
        # Only the owner may edit the groupement profile
        if not await is_owner_of(db, current_user.id, g.id):
            raise HTTPException(status_code=403, detail="Owner only")

    # `is_active` is super-admin only (suspending a tenant is platform-level)
    data = payload.model_dump(exclude_unset=True)
    if "is_active" in data and not current_user.is_super_admin:
        raise HTTPException(status_code=403, detail="Only super-admin can suspend a groupement")

    for field, value in data.items():
        setattr(g, field, value)

    await db.commit()
    await db.refresh(g)
    return g


# ──────────────────────────────────────────────────────────────────────────
# Admin team
# ──────────────────────────────────────────────────────────────────────────
@router.get("/{groupement_id}/admins", response_model=List[GroupementAdminOut])
async def list_groupement_admins(
    groupement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List admins of a groupement. Visible to super-admin and to any admin of that groupement."""
    await _require_admin_or_super(db, current_user, groupement_id)

    res = await db.execute(
        select(GroupementAdmin)
        .where(GroupementAdmin.groupement_id == groupement_id)
        .order_by(GroupementAdmin.is_owner.desc(), GroupementAdmin.added_at)
    )
    rows = res.scalars().all()
    # Eager-load users
    out: List[GroupementAdminOut] = []
    for row in rows:
        u = await db.execute(select(User).where(User.id == row.user_id))
        row.user = u.scalar_one_or_none()  # type: ignore[attr-defined]
        out.append(_admin_link_to_out(row))
    return out


@router.post(
    "/{groupement_id}/admins",
    response_model=InvitationCreated,
    status_code=status.HTTP_201_CREATED,
)
async def invite_groupement_admin(
    groupement_id: UUID,
    payload: InvitationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Invite a new admin to a groupement. Owner-only (or super-admin)."""
    await _require_owner_or_super(db, current_user, groupement_id)

    res = await db.execute(select(Groupement).where(Groupement.id == groupement_id))
    groupement = res.scalar_one_or_none()
    if not groupement:
        raise HTTPException(404, "Groupement not found")

    email = payload.email.lower()

    # If the email is already an admin of this groupement, reject
    existing_user = await db.execute(select(User).where(User.email == email))
    user = existing_user.scalar_one_or_none()
    if user:
        already = await db.execute(
            select(GroupementAdmin).where(
                GroupementAdmin.user_id == user.id,
                GroupementAdmin.groupement_id == groupement_id,
            )
        )
        if already.scalar_one_or_none():
            raise HTTPException(409, "Cette personne est déjà admin de ce groupement")

    # Revoke any prior pending invitation for this scope
    await revoke_pending(db, email=email, groupement_id=groupement_id, kind=InvitationKind.GROUPEMENT_ADMIN)

    plain = generate_invitation_token()
    inv = Invitation(
        email=email,
        full_name=payload.full_name,
        message=payload.message,
        kind=InvitationKind.GROUPEMENT_ADMIN,
        status=InvitationStatus.PENDING,
        token_hash=hash_token(plain),
        groupement_id=groupement_id,
        invited_by_id=current_user.id,
        expires_at=Invitation.expiry_in(settings.INVITATION_EXPIRE_DAYS),
    )
    db.add(inv)
    await db.flush()

    await _send_invitation_email_safe(
        invitation=inv, plain_token=plain, inviter=current_user,
        scope_name=groupement.name if groupement else None,
    )

    await db.commit()
    await db.refresh(inv)

    return InvitationCreated(
        **InvitationOut.model_validate(inv).model_dump(),
        activation_url=activation_url_for(plain),
    )


@router.delete("/{groupement_id}/admins/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_groupement_admin(
    groupement_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove an admin from a groupement. Owner-only (or super-admin)."""
    await _require_owner_or_super(db, current_user, groupement_id)

    res = await db.execute(
        select(GroupementAdmin).where(
            GroupementAdmin.user_id == user_id,
            GroupementAdmin.groupement_id == groupement_id,
        )
    )
    link = res.scalar_one_or_none()
    if not link:
        raise HTTPException(404, "Admin link not found")

    if link.is_owner:
        raise HTTPException(409, "Vous ne pouvez pas retirer le propriétaire — transférez d'abord la propriété")

    await db.delete(link)
    await db.commit()
    return None


@router.post("/{groupement_id}/transfer-ownership", response_model=List[GroupementAdminOut])
async def transfer_ownership(
    groupement_id: UUID,
    payload: TransferOwnershipRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Transfer ownership of a groupement to another existing admin."""
    await _require_owner_or_super(db, current_user, groupement_id)

    # Current owner row
    res = await db.execute(
        select(GroupementAdmin).where(
            GroupementAdmin.groupement_id == groupement_id,
            GroupementAdmin.is_owner.is_(True),
        )
    )
    current_owner_link = res.scalar_one_or_none()

    # Target must be an existing admin of this groupement
    res = await db.execute(
        select(GroupementAdmin).where(
            GroupementAdmin.groupement_id == groupement_id,
            GroupementAdmin.user_id == payload.target_user_id,
        )
    )
    target_link = res.scalar_one_or_none()
    if not target_link:
        raise HTTPException(404, "Cible non admin de ce groupement")
    if target_link.is_owner:
        raise HTTPException(409, "Cette personne est déjà propriétaire")

    if current_owner_link:
        current_owner_link.is_owner = False
    target_link.is_owner = True
    await db.commit()

    # Return refreshed list
    return await list_groupement_admins(groupement_id=groupement_id, db=db, current_user=current_user)


# ──────────────────────────────────────────────────────────────────────────
# Per-groupement invitations list
# ──────────────────────────────────────────────────────────────────────────
@router.get("/{groupement_id}/invitations", response_model=List[InvitationOut])
async def list_groupement_invitations(
    groupement_id: UUID,
    only_pending: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_admin_or_super(db, current_user, groupement_id)
    stmt = select(Invitation).where(Invitation.groupement_id == groupement_id)
    if only_pending:
        stmt = stmt.where(Invitation.status == InvitationStatus.PENDING)
    stmt = stmt.order_by(Invitation.created_at.desc())
    res = await db.execute(stmt)
    rows = res.scalars().all()
    # Auto-flag expired
    changed = False
    for inv in rows:
        if inv.status == InvitationStatus.PENDING and inv.is_expired():
            inv.status = InvitationStatus.EXPIRED
            changed = True
    if changed:
        await db.commit()
    return rows


# ──────────────────────────────────────────────────────────────────────────
# Centralised members view — every member across the groupement's associations
# ──────────────────────────────────────────────────────────────────────────
@router.get("/{groupement_id}/members", response_model=List[MembershipOut])
async def list_groupement_members(
    groupement_id: UUID,
    association_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """All memberships across the groupement's associations (read-only roll-up).

    Optionally filter by `association_id`. Visible to super-admin and any admin
    of the groupement.
    """
    await _require_admin_or_super(db, current_user, groupement_id)

    # Associations in this groupement (name lookup)
    ares = await db.execute(
        select(Association).where(Association.groupement_id == groupement_id)
    )
    associations = {a.id: a for a in ares.scalars().all()}
    if not associations:
        return []

    target_ids = [association_id] if association_id else list(associations.keys())
    target_ids = [aid for aid in target_ids if aid in associations]
    if not target_ids:
        return []

    from app.api.v1.memberships import _membership_to_out

    stmt = (
        select(Membership)
        .options(
            selectinload(Membership.user),
            selectinload(Membership.membership_roles).selectinload(MembershipRole.role),
        )
        .where(Membership.association_id.in_(target_ids))
        .order_by(Membership.joined_at.desc())
    )
    res = await db.execute(stmt)
    out = []
    for m in res.scalars().all():
        item = _membership_to_out(m)
        assoc = associations.get(m.association_id)
        item.association_name = assoc.name if assoc else None
        out.append(item)
    return out
