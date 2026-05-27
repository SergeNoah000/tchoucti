"""AidType endpoints — admin-only catalogue of social-aid kinds (config-v2).

Workflow :
- Admin enables aids (Association.config.aids.enabled = true)
- Admin creates one or more AidType (cotisation, plafond, délai…)
- Case declarations reference an AidType to inherit its rules (snapshotted
  on the case so type edits don't retroactively change open cases).
"""
from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    _user_is_association_admin,
    get_current_user,
    get_db,
)
from app.models.association import Association
from app.models.caisse import Caisse
from app.models.social_aid import AidType, SocialAidCase
from app.models.user import User
from app.schemas.aid_type import AidTypeCreate, AidTypeOut, AidTypeUpdate
from app.services.meeting_agenda import upsert_aid_type_activity

router = APIRouter()


async def _check_access(db: AsyncSession, user: User, association_id: UUID) -> Association:
    res = await db.execute(select(Association).where(Association.id == association_id))
    assoc = res.scalar_one_or_none()
    if not assoc:
        raise HTTPException(404, "Association introuvable")
    if not user.is_super_admin and user.groupement_id != assoc.groupement_id:
        raise HTTPException(403, "Forbidden")
    return assoc


async def _require_admin(db: AsyncSession, user: User, association_id: UUID) -> None:
    if user.is_super_admin or user.is_groupement_admin:
        return
    if not await _user_is_association_admin(db, user, association_id):
        raise HTTPException(403, "Réservé à l'admin de cette association")


def _to_out(at: AidType, source_name: str | None = None) -> AidTypeOut:
    return AidTypeOut(
        id=at.id,
        association_id=at.association_id,
        source_caisse_id=at.source_caisse_id,
        source_caisse_name=source_name,
        name=at.name,
        slug=at.slug,
        description=at.description,
        is_active=at.is_active,
        member_contribution_amount=at.member_contribution_amount,
        is_contribution_recurring=at.is_contribution_recurring,
        aid_ceiling_amount=at.aid_ceiling_amount,
        max_claims_per_member_per_year=at.max_claims_per_member_per_year,
        declaration_delay_days=at.declaration_delay_days,
    )


@router.get("", response_model=List[AidTypeOut])
async def list_aid_types(
    association_id: UUID = Query(...),
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List aid types for the association. Open to any role with access."""
    await _check_access(db, current_user, association_id)
    stmt = (
        select(AidType, Caisse.name)
        .join(Caisse, Caisse.id == AidType.source_caisse_id)
        .where(AidType.association_id == association_id)
        .order_by(AidType.created_at)
    )
    if active_only:
        stmt = stmt.where(AidType.is_active.is_(True))
    res = await db.execute(stmt)
    return [_to_out(at, name) for at, name in res.all()]


@router.post("", response_model=AidTypeOut, status_code=status.HTTP_201_CREATED)
async def create_aid_type(
    payload: AidTypeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _check_access(db, current_user, payload.association_id)
    await _require_admin(db, current_user, payload.association_id)

    caisse_res = await db.execute(
        select(Caisse).where(
            Caisse.id == payload.source_caisse_id,
            Caisse.association_id == payload.association_id,
        )
    )
    caisse = caisse_res.scalar_one_or_none()
    if not caisse:
        raise HTTPException(422, "Caisse source introuvable dans cette association.")
    if caisse.category.value == "project":
        raise HTTPException(
            422,
            "Une caisse projet ne peut pas servir de source pour une aide sociale.",
        )

    dupe = await db.execute(
        select(AidType).where(
            AidType.association_id == payload.association_id,
            AidType.slug == payload.slug,
        )
    )
    if dupe.scalar_one_or_none():
        raise HTTPException(409, "Un type d'aide avec ce slug existe déjà.")

    at = AidType(
        association_id=payload.association_id,
        source_caisse_id=payload.source_caisse_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        member_contribution_amount=payload.member_contribution_amount,
        is_contribution_recurring=payload.is_contribution_recurring,
        aid_ceiling_amount=payload.aid_ceiling_amount,
        max_claims_per_member_per_year=payload.max_claims_per_member_per_year,
        declaration_delay_days=payload.declaration_delay_days,
    )
    db.add(at)
    await db.flush()

    # Phase 3 — auto-create the Activity. It stays hidden in séances by
    # default (is_visible_in_meeting=False) and gets toggled on by the agenda
    # endpoint only when an aid case of this type is being collected.
    await upsert_aid_type_activity(
        db,
        association_id=payload.association_id,
        aid_type_id=at.id,
        name=payload.name,
        slug=payload.slug,
        member_contribution_amount=payload.member_contribution_amount,
        is_recurring=payload.is_contribution_recurring,
    )

    await db.commit()
    await db.refresh(at)
    return _to_out(at, caisse.name)


@router.patch("/{aid_type_id}", response_model=AidTypeOut)
async def update_aid_type(
    aid_type_id: UUID,
    payload: AidTypeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    res = await db.execute(select(AidType).where(AidType.id == aid_type_id))
    at = res.scalar_one_or_none()
    if not at:
        raise HTTPException(404, "Type d'aide introuvable")
    await _check_access(db, current_user, at.association_id)
    await _require_admin(db, current_user, at.association_id)

    data = payload.model_dump(exclude_unset=True)
    if "source_caisse_id" in data and data["source_caisse_id"] != at.source_caisse_id:
        # Bloquer le changement si des dossiers vivants y réfèrent.
        live = await db.execute(
            select(SocialAidCase.id).where(
                SocialAidCase.aid_type_id == at.id,
                SocialAidCase.status.in_(["requested", "reviewing", "approved"]),
            )
        )
        if live.first():
            raise HTTPException(
                409,
                "Changement de caisse source interdit : des dossiers en cours référencent ce type.",
            )
        caisse_res = await db.execute(
            select(Caisse).where(
                Caisse.id == data["source_caisse_id"],
                Caisse.association_id == at.association_id,
            )
        )
        new_caisse = caisse_res.scalar_one_or_none()
        if not new_caisse:
            raise HTTPException(422, "Nouvelle caisse source invalide.")
        if new_caisse.category.value == "project":
            raise HTTPException(422, "Une caisse projet ne peut pas servir de source.")

    for field, value in data.items():
        setattr(at, field, value)
    await db.commit()
    await db.refresh(at)

    caisse_res = await db.execute(select(Caisse.name).where(Caisse.id == at.source_caisse_id))
    name = caisse_res.scalar_one_or_none()
    return _to_out(at, name)


@router.delete("/{aid_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_aid_type(
    aid_type_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    res = await db.execute(select(AidType).where(AidType.id == aid_type_id))
    at = res.scalar_one_or_none()
    if not at:
        raise HTTPException(404, "Type d'aide introuvable")
    await _check_access(db, current_user, at.association_id)
    await _require_admin(db, current_user, at.association_id)

    used = await db.execute(
        select(SocialAidCase.id).where(SocialAidCase.aid_type_id == at.id).limit(1)
    )
    if used.first():
        raise HTTPException(
            409,
            "Des dossiers référencent ce type. Désactive-le (is_active=false) plutôt "
            "que de le supprimer.",
        )

    await db.delete(at)
    await db.commit()
