"""Public (unauthenticated) endpoints — used to render shareable, branded pages
such as the per-association login link `{grp}.myappsuite.com/a/{slug}`.

Exposes only non-sensitive branding (name, slug, logo, color) so the login page
and its Open Graph preview can be server-rendered before the user authenticates.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.association import Association
from app.models.groupement import Groupement

router = APIRouter()


class BrandingGroupement(BaseModel):
    name: str
    slug: str
    subdomain: str
    logo_url: Optional[str] = None
    primary_color: str


class BrandingAssociation(BaseModel):
    name: str
    slug: str
    logo_url: Optional[str] = None
    primary_color: str


class AssociationBrandingOut(BaseModel):
    groupement: BrandingGroupement
    association: BrandingAssociation


@router.get("/association-branding", response_model=AssociationBrandingOut)
async def association_branding(
    groupement: str,
    association: str,
    db: AsyncSession = Depends(get_db),
):
    """Resolve `{groupement}` (subdomain or slug) + `{association}` (slug) to the
    public branding used by the shared login link. 404 if not found/inactive."""
    g = (
        await db.execute(
            select(Groupement).where(
                or_(Groupement.subdomain == groupement.lower(), Groupement.slug == groupement.lower()),
                Groupement.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not g:
        raise HTTPException(404, "Groupement introuvable")

    a = (
        await db.execute(
            select(Association).where(
                Association.groupement_id == g.id,
                Association.slug == association.lower(),
                Association.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Association introuvable")

    return AssociationBrandingOut(
        groupement=BrandingGroupement(
            name=g.name,
            slug=g.slug,
            subdomain=g.subdomain,
            logo_url=g.logo_url,
            primary_color=g.primary_color,
        ),
        association=BrandingAssociation(
            name=a.name,
            slug=a.slug,
            logo_url=a.logo_url,
            primary_color=a.primary_color,
        ),
    )
