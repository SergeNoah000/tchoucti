"""Memberships CRUD endpoints (invite flow wired to the invitation engine)."""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import _user_has_bureau_role, get_current_user, get_db
from app.api.v1.invitations import (
    _send_invitation_email_safe,
    activation_url_for,
    hash_token,
)
from app.core.config import settings
from app.models.association import Association
from app.models.invitation import (
    Invitation,
    InvitationKind,
    InvitationStatus,
    generate_invitation_token,
)
from app.models.role import (
    MemberCategory,
    Membership,
    MembershipRole,
    MembershipStatus,
    Role,
)
from app.models.user import User, UserType
from app.schemas.membership import MembershipCreate, MembershipOut, MembershipUpdate

router = APIRouter()

# Role codes that grant association-admin level access (vs. plain member).
_ADMIN_ROLE_CODES = {"association_admin", "association_manager"}


async def _get_assoc_or_404(db: AsyncSession, association_id: UUID) -> Association:
    result = await db.execute(select(Association).where(Association.id == association_id))
    assoc = result.scalar_one_or_none()
    if not assoc:
        raise HTTPException(status_code=404, detail="Association not found")
    return assoc


def _check_assoc_access(user: User, assoc: Association) -> None:
    if user.is_super_admin:
        return
    if user.groupement_id != assoc.groupement_id:
        raise HTTPException(status_code=403, detail="Forbidden")


async def _load_membership(db: AsyncSession, membership_id: UUID) -> Membership:
    result = await db.execute(
        select(Membership)
        .options(
            selectinload(Membership.user),
            selectinload(Membership.membership_roles).selectinload(MembershipRole.role),
        )
        .where(Membership.id == membership_id)
    )
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Membership not found")
    return m


def _membership_to_out(m: Membership) -> MembershipOut:
    """Convert ORM Membership to MembershipOut (flatten roles)."""
    roles = [mr.role for mr in m.membership_roles]
    return MembershipOut(
        id=m.id,
        user_id=m.user_id,
        association_id=m.association_id,
        member_number=m.member_number,
        status=m.status.value if hasattr(m.status, "value") else m.status,
        category=m.category.value if hasattr(m.category, "value") else m.category,
        joined_at=m.joined_at,
        left_at=m.left_at,
        cumulative_contributions=m.cumulative_contributions,
        notes=m.notes,
        user=m.user,
        roles=roles,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


@router.get("", response_model=List[MembershipOut])
async def list_memberships(
    association_id: UUID = Query(..., description="Filter by association"),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assoc = await _get_assoc_or_404(db, association_id)
    _check_assoc_access(current_user, assoc)

    stmt = (
        select(Membership)
        .options(
            selectinload(Membership.user),
            selectinload(Membership.membership_roles).selectinload(MembershipRole.role),
        )
        .where(Membership.association_id == association_id)
    )
    if status_filter:
        stmt = stmt.where(Membership.status == status_filter)

    result = await db.execute(stmt)
    memberships = result.scalars().all()
    return [_membership_to_out(m) for m in memberships]


@router.get("/{membership_id}", response_model=MembershipOut)
async def get_membership(
    membership_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = await _load_membership(db, membership_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_assoc_access(current_user, assoc)
    return _membership_to_out(m)


class ActivationLinkOut(BaseModel):
    activation_url: str
    sent: bool          # True si l'email a bien été envoyé


@router.post("/{membership_id}/resend-invitation", response_model=ActivationLinkOut)
async def resend_member_invitation(
    membership_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """(Re)génère et renvoie le lien d'activation d'un membre non encore actif.
    Réservé au bureau/admin. Renvoie aussi l'URL pour la copier manuellement."""
    m = await _load_membership(db, membership_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_assoc_access(current_user, assoc)
    if not await _user_has_bureau_role(db, current_user, assoc.id):
        raise HTTPException(403, "Réservé aux admins et membres du bureau.")

    user = m.user
    email = user.email if user else ""
    if not email or "@" not in email or email.endswith(".import.local"):
        raise HTTPException(
            422,
            "Ce membre n'a pas d'email réel : impossible d'envoyer un lien "
            "d'activation. Définissez d'abord son email.",
        )
    if user.is_active:
        raise HTTPException(409, "Ce compte est déjà actif.")

    role_codes = {mr.role.code for mr in m.membership_roles}
    is_admin = bool(role_codes & _ADMIN_ROLE_CODES)
    kind = InvitationKind.ASSOCIATION_ADMIN if is_admin else InvitationKind.ASSOCIATION_MEMBER

    inv = (
        await db.execute(
            select(Invitation)
            .where(
                Invitation.email == email,
                Invitation.association_id == assoc.id,
            )
            .order_by(Invitation.created_at.desc())
        )
    ).scalars().first()

    plain = generate_invitation_token()
    if inv is None:
        inv = Invitation(
            email=email,
            full_name=user.full_name,
            kind=kind,
            status=InvitationStatus.PENDING,
            token_hash=hash_token(plain),
            groupement_id=assoc.groupement_id,
            association_id=assoc.id,
            invited_by_id=current_user.id,
            expires_at=Invitation.expiry_in(settings.INVITATION_EXPIRE_DAYS),
        )
        db.add(inv)
    else:
        inv.token_hash = hash_token(plain)
        inv.expires_at = Invitation.expiry_in(settings.INVITATION_EXPIRE_DAYS)
        inv.status = InvitationStatus.PENDING
        inv.resent_count = (inv.resent_count or 0) + 1
    await db.flush()

    sent = await _send_invitation_email_safe(
        invitation=inv, plain_token=plain, inviter=current_user, scope_name=assoc.name
    )
    await db.commit()
    return ActivationLinkOut(activation_url=activation_url_for(plain), sent=sent)


@router.post("", response_model=MembershipOut, status_code=status.HTTP_201_CREATED)
async def create_membership(
    payload: MembershipCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Invite a user to an association.

    - If `user_id` is given → link an existing user (no email).
    - If `email` is given (and user_id is None) → create a pending member: a
      new inactive user + an Invitation row, and send the activation email.
      The membership is created immediately so the org sees it as "pending"
      (its user.is_active stays false until the invite is accepted).
    """
    assoc = await _get_assoc_or_404(db, payload.association_id)
    _check_assoc_access(current_user, assoc)

    # Resolve user
    target_user: Optional[User] = None

    if payload.user_id:
        res = await db.execute(select(User).where(User.id == payload.user_id))
        target_user = res.scalar_one_or_none()
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")

    elif payload.email:
        email = payload.email.lower()
        res = await db.execute(select(User).where(User.email == email))
        target_user = res.scalar_one_or_none()
        if not target_user:
            if not payload.full_name:
                raise HTTPException(
                    status_code=422,
                    detail="full_name is required when creating a new user via email invite",
                )
            target_user = User(
                full_name=payload.full_name,
                email=email,
                groupement_id=assoc.groupement_id,
                user_type=UserType.MEMBER,
                is_active=False,  # activated via the invitation link
            )
            db.add(target_user)
            await db.flush()
    else:
        raise HTTPException(
            status_code=422, detail="Either user_id or email must be provided"
        )

    # Check duplicate membership
    existing = await db.execute(
        select(Membership).where(
            Membership.user_id == target_user.id,
            Membership.association_id == payload.association_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User is already a member of this association")

    # Resolve roles
    roles: List[Role] = []
    for code in payload.role_codes:
        res = await db.execute(select(Role).where(Role.code == code))
        role = res.scalar_one_or_none()
        if not role:
            raise HTTPException(status_code=422, detail=f"Role '{code}' not found")
        roles.append(role)

    # Create membership
    now = datetime.now(timezone.utc)
    membership = Membership(
        user_id=target_user.id,
        association_id=payload.association_id,
        member_number=payload.member_number,
        status=MembershipStatus.ACTIVE,
        joined_at=now,
        notes=payload.notes,
    )
    db.add(membership)
    await db.flush()

    for role in roles:
        db.add(MembershipRole(membership_id=membership.id, role_id=role.id, assigned_at=now))

    # Invited by email → always spin up an invitation and email it, whether the
    # account is brand-new OR an existing user being added to another association
    # of the same groupement (without this, existing users were added silently
    # and never received an invitation). Explicit user_id links stay email-less.
    activation_url: Optional[str] = None
    if payload.email and not payload.user_id:
        is_admin = any(c in _ADMIN_ROLE_CODES for c in payload.role_codes)
        kind = InvitationKind.ASSOCIATION_ADMIN if is_admin else InvitationKind.ASSOCIATION_MEMBER
        plain = generate_invitation_token()
        invitation = Invitation(
            email=target_user.email,
            full_name=payload.full_name,
            kind=kind,
            status=InvitationStatus.PENDING,
            token_hash=hash_token(plain),
            groupement_id=assoc.groupement_id,
            association_id=assoc.id,
            invited_by_id=current_user.id,
            expires_at=Invitation.expiry_in(settings.INVITATION_EXPIRE_DAYS),
        )
        db.add(invitation)
        await db.flush()
        await _send_invitation_email_safe(
            invitation=invitation, plain_token=plain, inviter=current_user, scope_name=assoc.name
        )
        activation_url = activation_url_for(plain)

    await db.commit()

    m = await _load_membership(db, membership.id)
    out = _membership_to_out(m)
    out.activation_url = activation_url
    return out


@router.patch("/{membership_id}", response_model=MembershipOut)
async def update_membership(
    membership_id: UUID,
    payload: MembershipUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = await _load_membership(db, membership_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_assoc_access(current_user, assoc)

    if payload.status is not None:
        try:
            m.status = MembershipStatus(payload.status)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid status '{payload.status}'")

    if payload.category is not None:
        try:
            m.category = MemberCategory(payload.category)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid category '{payload.category}'")

    if payload.member_number is not None:
        m.member_number = payload.member_number

    if payload.notes is not None:
        m.notes = payload.notes

    # Update roles if provided
    if payload.role_codes is not None:
        # Remove existing roles
        for mr in list(m.membership_roles):
            await db.delete(mr)
        await db.flush()

        # Add new roles
        now = datetime.now(timezone.utc)
        for code in payload.role_codes:
            res = await db.execute(select(Role).where(Role.code == code))
            role = res.scalar_one_or_none()
            if not role:
                raise HTTPException(status_code=422, detail=f"Role '{code}' not found")
            mr = MembershipRole(
                membership_id=m.id,
                role_id=role.id,
                assigned_at=now,
            )
            db.add(mr)

    await db.commit()
    m = await _load_membership(db, membership_id)
    return _membership_to_out(m)


@router.delete("/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_membership(
    membership_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Suspend (soft-delete) a membership."""
    m = await _load_membership(db, membership_id)
    assoc = await _get_assoc_or_404(db, m.association_id)
    _check_assoc_access(current_user, assoc)

    m.status = MembershipStatus.SUSPENDED
    m.left_at = datetime.now(timezone.utc)
    await db.commit()
