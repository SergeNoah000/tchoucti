"""Roles & Permissions read-only endpoints."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.models.role import (
    Membership,
    MembershipRole,
    Permission,
    Role,
    RolePermission,
    UserPermission,
)
from app.models.user import User
from app.schemas.membership import PermissionOut, RoleOut, RoleWithPermissionsOut

router = APIRouter()


@router.get("/roles", response_model=List[RoleWithPermissionsOut])
async def list_roles(
    scope: Optional[str] = Query(None, description="Filter by scope: platform|groupement|association"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all roles (system + custom for user's groupement)."""
    stmt = select(Role).options(
        selectinload(Role.role_permissions).selectinload(RolePermission.permission)
    )
    if scope:
        stmt = stmt.where(Role.scope == scope)

    # Non-super-admin: only system roles + roles of their groupement
    if not current_user.is_super_admin:
        stmt = stmt.where(
            (Role.is_system == True) |  # noqa: E712
            (Role.groupement_id == current_user.groupement_id)
        )

    result = await db.execute(stmt)
    roles = result.scalars().all()

    out = []
    for role in roles:
        perms = [rp.permission for rp in role.role_permissions]
        out.append(
            RoleWithPermissionsOut(
                id=role.id,
                name=role.name,
                code=role.code,
                description=role.description,
                scope=role.scope.value if hasattr(role.scope, "value") else role.scope,
                is_system=role.is_system,
                groupement_id=role.groupement_id,
                association_id=role.association_id,
                permissions=[
                    PermissionOut(
                        id=p.id,
                        code=p.code,
                        name=p.name,
                        description=p.description,
                        category=p.category,
                        scope=p.scope.value if hasattr(p.scope, "value") else p.scope,
                    )
                    for p in perms
                ],
            )
        )
    return out


@router.get("/permissions", response_model=List[PermissionOut])
async def list_permissions(
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all permissions."""
    stmt = select(Permission)
    if category:
        stmt = stmt.where(Permission.category == category)
    stmt = stmt.order_by(Permission.category, Permission.code)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/me/permissions", response_model=List[str])
async def my_permissions(
    association_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the effective permission codes for the current user.

    If association_id is provided, includes permissions from membership roles
    in that association + any UserPermission overrides.
    """
    if current_user.is_super_admin:
        # Super admin has all permissions
        result = await db.execute(select(Permission.code))
        return [row[0] for row in result.all()]

    perm_codes: set[str] = set()

    if association_id:
        # Load membership roles for this association
        result = await db.execute(
            select(Membership)
            .options(
                selectinload(Membership.membership_roles)
                .selectinload(MembershipRole.role)
                .selectinload(Role.role_permissions)
                .selectinload(RolePermission.permission)
            )
            .where(
                Membership.user_id == current_user.id,
                Membership.association_id == association_id,
            )
        )
        membership = result.scalar_one_or_none()
        if membership:
            for mr in membership.membership_roles:
                for rp in mr.role.role_permissions:
                    perm_codes.add(rp.permission.code)

        # Apply UserPermission overrides
        result = await db.execute(
            select(UserPermission)
            .options(selectinload(UserPermission.permission))
            .where(
                UserPermission.user_id == current_user.id,
                UserPermission.association_id == association_id,
            )
        )
        for up in result.scalars().all():
            if up.granted:
                perm_codes.add(up.permission.code)
            else:
                perm_codes.discard(up.permission.code)

    return sorted(perm_codes)
