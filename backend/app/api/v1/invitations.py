"""Invitation lifecycle: create, list, resend, revoke, accept.

Activate flow:
  1. Inviter POSTs /api/groupements/{id}/admins (or /associations/.../invite later) →
     creates an Invitation row + sends email. The plain token is returned **once**
     (in the response payload) so the inviter can copy it if needed.
  2. Invitee opens /activate?token=<plain> → frontend calls POST /api/invitations/accept
     with {token, password, full_name}.
  3. Server hashes token, looks it up, creates User + GroupementAdmin link,
     marks invitation accepted.
"""
import hashlib
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.groupement import Groupement
from app.models.groupement_admin import GroupementAdmin
from app.models.invitation import (
    Invitation,
    InvitationKind,
    InvitationStatus,
    generate_invitation_token,
)
from app.models.user import InviteStatus, User, UserType
from app.schemas.invitation import InvitationCreated, InvitationOut
from app.services.mailer import MailError, send_invitation_email

router = APIRouter()


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────
def hash_token(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def activation_url_for(plain_token: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/activate?token={plain_token}"


def role_label(kind: InvitationKind) -> str:
    return {
        InvitationKind.GROUPEMENT_ADMIN: "Administrateur de groupement",
        InvitationKind.ASSOCIATION_ADMIN: "Administrateur d'association",
        InvitationKind.ASSOCIATION_MEMBER: "Membre d'association",
    }[kind]


async def is_owner_of(db: AsyncSession, user_id: UUID, groupement_id: UUID) -> bool:
    res = await db.execute(
        select(GroupementAdmin).where(
            GroupementAdmin.user_id == user_id,
            GroupementAdmin.groupement_id == groupement_id,
            GroupementAdmin.is_owner.is_(True),
        )
    )
    return res.scalar_one_or_none() is not None


async def is_admin_of(db: AsyncSession, user_id: UUID, groupement_id: UUID) -> bool:
    res = await db.execute(
        select(GroupementAdmin).where(
            GroupementAdmin.user_id == user_id,
            GroupementAdmin.groupement_id == groupement_id,
        )
    )
    return res.scalar_one_or_none() is not None


async def revoke_pending(db: AsyncSession, *, email: str, groupement_id: UUID, kind: InvitationKind):
    """Mark any existing pending invitation for (email,scope) as revoked."""
    res = await db.execute(
        select(Invitation).where(
            Invitation.email == email.lower(),
            Invitation.groupement_id == groupement_id,
            Invitation.kind == kind,
            Invitation.status == InvitationStatus.PENDING,
        )
    )
    for row in res.scalars().all():
        row.status = InvitationStatus.REVOKED


async def _send_invitation_email_safe(
    *,
    invitation: Invitation,
    plain_token: str,
    inviter: User,
    scope_name: Optional[str],
) -> bool:
    """Send the email but don't fail the API call if SMTP is unreachable.

    `scope_name` is the org the invitee is joining (groupement or association
    name). Returns True on success, False otherwise. The activation URL is
    always returned to the inviter so they can copy it manually as a fallback.
    """
    try:
        await send_invitation_email(
            to=invitation.email,
            invitee_name=invitation.full_name,
            activation_url=activation_url_for(plain_token),
            inviter_name=inviter.full_name,
            groupement_name=scope_name,
            role_label=role_label(invitation.kind),
            message=invitation.message,
            expires_in_days=settings.INVITATION_EXPIRE_DAYS,
        )
        invitation.sent_at = datetime.now(timezone.utc)
        return True
    except MailError:
        return False


# ──────────────────────────────────────────────────────────────────────────
# List / lifecycle
# ──────────────────────────────────────────────────────────────────────────
@router.get("/invitations", response_model=List[InvitationOut])
async def list_invitations(
    groupement_id: Optional[UUID] = None,
    only_pending: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List invitations the current user can see.

    - Super admin: all.
    - Groupement admin: invitations scoped to their groupement.
    """
    stmt = select(Invitation).order_by(Invitation.created_at.desc())
    if groupement_id is not None:
        stmt = stmt.where(Invitation.groupement_id == groupement_id)

    if not current_user.is_super_admin:
        # restrict to user's groupement
        if not current_user.groupement_id:
            return []
        stmt = stmt.where(Invitation.groupement_id == current_user.groupement_id)

    if only_pending:
        stmt = stmt.where(Invitation.status == InvitationStatus.PENDING)

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


@router.post("/invitations/{invitation_id}/resend", response_model=InvitationCreated)
async def resend_invitation(
    invitation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    res = await db.execute(select(Invitation).where(Invitation.id == invitation_id))
    inv = res.scalar_one_or_none()
    if not inv:
        raise HTTPException(404, "Invitation not found")

    # Permission: super admin OR owner of the target groupement
    if not current_user.is_super_admin:
        if not inv.groupement_id or not await is_owner_of(db, current_user.id, inv.groupement_id):
            raise HTTPException(403, "Forbidden")

    if inv.status == InvitationStatus.ACCEPTED:
        raise HTTPException(409, "Invitation already accepted")

    # Generate a fresh token (the old one is gone — only hash was stored)
    plain = generate_invitation_token()
    inv.token_hash = hash_token(plain)
    inv.expires_at = Invitation.expiry_in(settings.INVITATION_EXPIRE_DAYS)
    inv.status = InvitationStatus.PENDING
    inv.resent_count += 1

    # Scope name = the association (for member invites) or the groupement.
    scope_name: Optional[str] = None
    if inv.association_id:
        from app.models.association import Association

        ar = await db.execute(select(Association).where(Association.id == inv.association_id))
        assoc = ar.scalar_one_or_none()
        scope_name = assoc.name if assoc else None
    elif inv.groupement_id:
        gr = await db.execute(select(Groupement).where(Groupement.id == inv.groupement_id))
        grp = gr.scalar_one_or_none()
        scope_name = grp.name if grp else None

    await _send_invitation_email_safe(
        invitation=inv, plain_token=plain, inviter=current_user, scope_name=scope_name
    )

    await db.commit()
    await db.refresh(inv)

    return InvitationCreated(
        **InvitationOut.model_validate(inv).model_dump(),
        activation_url=activation_url_for(plain),
    )


@router.post("/invitations/{invitation_id}/revoke", response_model=InvitationOut)
async def revoke_invitation(
    invitation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    res = await db.execute(select(Invitation).where(Invitation.id == invitation_id))
    inv = res.scalar_one_or_none()
    if not inv:
        raise HTTPException(404, "Invitation not found")

    if not current_user.is_super_admin:
        if not inv.groupement_id or not await is_owner_of(db, current_user.id, inv.groupement_id):
            raise HTTPException(403, "Forbidden")

    if inv.status == InvitationStatus.ACCEPTED:
        raise HTTPException(409, "Invitation already accepted")

    inv.status = InvitationStatus.REVOKED
    await db.commit()
    await db.refresh(inv)
    return inv


# ──────────────────────────────────────────────────────────────────────────
# Public acceptance endpoint — no auth required.
# ──────────────────────────────────────────────────────────────────────────
class AcceptInvitationRequest(BaseModel):
    token: str
    # Optional: required only for accounts that don't have a password yet (new or
    # never-activated invitees). Existing active users joining another association
    # keep their current password.
    password: Optional[str] = Field(None, min_length=8, max_length=128)
    full_name: Optional[str] = Field(None, max_length=255)


class AcceptInvitationResponse(BaseModel):
    email: str
    activated: bool = True


@router.post("/invitations/accept", response_model=AcceptInvitationResponse)
async def accept_invitation(payload: AcceptInvitationRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hash_token(payload.token)
    res = await db.execute(select(Invitation).where(Invitation.token_hash == token_hash))
    inv = res.scalar_one_or_none()
    if not inv:
        raise HTTPException(400, "Lien d'activation invalide")

    if inv.status == InvitationStatus.REVOKED:
        raise HTTPException(400, "Cette invitation a été révoquée")
    if inv.status == InvitationStatus.ACCEPTED:
        raise HTTPException(400, "Cette invitation a déjà été utilisée")
    if inv.is_expired():
        inv.status = InvitationStatus.EXPIRED
        await db.commit()
        raise HTTPException(400, "Lien d'activation expiré, demandez un renvoi")

    # Find existing user or create one
    res = await db.execute(select(User).where(User.email == inv.email))
    user = res.scalar_one_or_none()
    full_name = payload.full_name or inv.full_name or inv.email.split("@")[0]

    if user is None:
        # New account → a password is mandatory.
        if not payload.password:
            raise HTTPException(400, "Mot de passe requis")
        # Decide user_type from invitation kind
        user_type = {
            InvitationKind.GROUPEMENT_ADMIN: UserType.GROUPEMENT_ADMIN,
            InvitationKind.ASSOCIATION_ADMIN: UserType.ASSOCIATION_USER,
            InvitationKind.ASSOCIATION_MEMBER: UserType.MEMBER,
        }[inv.kind]
        user = User(
            email=inv.email,
            full_name=full_name,
            hashed_password=get_password_hash(payload.password),
            user_type=user_type,
            groupement_id=inv.groupement_id,
            is_active=True,
            is_verified=True,
            invite_status=InviteStatus.ACCEPTED,
        )
        db.add(user)
        await db.flush()
    else:
        # Existing user accepting an additional invitation. Only set a password
        # if the account never had one (never activated); active users keep theirs.
        user.is_active = True
        user.is_verified = True
        user.invite_status = InviteStatus.ACCEPTED
        if not user.hashed_password:
            if not payload.password:
                raise HTTPException(400, "Mot de passe requis")
            user.hashed_password = get_password_hash(payload.password)

    # Apply the invitation effect
    if inv.kind == InvitationKind.GROUPEMENT_ADMIN and inv.groupement_id:
        # Add to admin team (not as owner — owner is set explicitly elsewhere)
        existing = await db.execute(
            select(GroupementAdmin).where(
                GroupementAdmin.user_id == user.id,
                GroupementAdmin.groupement_id == inv.groupement_id,
            )
        )
        if existing.scalar_one_or_none() is None:
            db.add(
                GroupementAdmin(
                    user_id=user.id,
                    groupement_id=inv.groupement_id,
                    is_owner=False,
                    added_by_id=inv.invited_by_id,
                )
            )
        if user.user_type == UserType.MEMBER:
            user.user_type = UserType.GROUPEMENT_ADMIN
        if user.groupement_id is None:
            user.groupement_id = inv.groupement_id

    elif inv.kind in (InvitationKind.ASSOCIATION_MEMBER, InvitationKind.ASSOCIATION_ADMIN) and inv.association_id:
        from app.models.role import Membership, MembershipRole, MembershipStatus, Role

        if user.groupement_id is None:
            user.groupement_id = inv.groupement_id
        if inv.kind == InvitationKind.ASSOCIATION_ADMIN and user.user_type == UserType.MEMBER:
            user.user_type = UserType.ASSOCIATION_USER

        # The membership is usually pre-created by POST /memberships. Ensure it
        # exists so accepting is idempotent even if it was removed meanwhile.
        mres = await db.execute(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.association_id == inv.association_id,
            )
        )
        membership = mres.scalar_one_or_none()
        if membership is None:
            membership = Membership(
                user_id=user.id,
                association_id=inv.association_id,
                status=MembershipStatus.ACTIVE,
                joined_at=datetime.now(timezone.utc),
            )
            db.add(membership)
            await db.flush()
            default_code = (
                "association_admin"
                if inv.kind == InvitationKind.ASSOCIATION_ADMIN
                else "member"
            )
            rres = await db.execute(select(Role).where(Role.code == default_code))
            role = rres.scalar_one_or_none()
            if role:
                db.add(
                    MembershipRole(
                        membership_id=membership.id,
                        role_id=role.id,
                        assigned_at=datetime.now(timezone.utc),
                    )
                )
        elif membership.status != MembershipStatus.ACTIVE:
            membership.status = MembershipStatus.ACTIVE

    # Mark accepted
    inv.status = InvitationStatus.ACCEPTED
    inv.accepted_at = datetime.now(timezone.utc)
    inv.accepted_by_id = user.id

    await db.commit()
    return AcceptInvitationResponse(email=user.email)


class PeekInvitationResponse(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    kind: InvitationKind
    groupement_name: Optional[str] = None
    association_name: Optional[str] = None
    expires_at: datetime
    invited_by_name: Optional[str] = None
    # True when the invitee already has an active account (joining another
    # association of the groupement) → the activation page skips the password step.
    existing_active: bool = False


@router.get("/invitations/peek", response_model=PeekInvitationResponse)
async def peek_invitation(token: str, db: AsyncSession = Depends(get_db)):
    """Public — let the activation page render context (who invited, role, etc.)."""
    token_hash = hash_token(token)
    res = await db.execute(select(Invitation).where(Invitation.token_hash == token_hash))
    inv = res.scalar_one_or_none()
    if not inv or inv.status != InvitationStatus.PENDING or inv.is_expired():
        raise HTTPException(404, "Invitation invalide ou expirée")

    groupement_name = None
    if inv.groupement_id:
        gr = await db.execute(select(Groupement).where(Groupement.id == inv.groupement_id))
        g = gr.scalar_one_or_none()
        groupement_name = g.name if g else None

    association_name = None
    if inv.association_id:
        from app.models.association import Association

        ar = await db.execute(select(Association).where(Association.id == inv.association_id))
        a = ar.scalar_one_or_none()
        association_name = a.name if a else None

    inviter_name = None
    if inv.invited_by_id:
        u = await db.execute(select(User).where(User.id == inv.invited_by_id))
        usr = u.scalar_one_or_none()
        inviter_name = usr.full_name if usr else None

    ures = await db.execute(select(User).where(User.email == inv.email))
    existing = ures.scalar_one_or_none()
    existing_active = bool(existing and existing.is_active and existing.hashed_password)

    return PeekInvitationResponse(
        email=inv.email,
        full_name=inv.full_name,
        kind=inv.kind,
        groupement_name=groupement_name,
        association_name=association_name,
        expires_at=inv.expires_at,
        invited_by_name=inviter_name,
        existing_active=existing_active,
    )
