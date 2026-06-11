"""AidType endpoints — admin-only catalogue of social-aid kinds (config-v2).

Workflow :
- Admin enables aids (Association.config.aids.enabled = true)
- Admin creates one or more AidType (cotisation, plafond, délai…)
- Case declarations reference an AidType to inherit its rules (snapshotted
  on the case so type edits don't retroactively change open cases).
"""
from __future__ import annotations

from typing import List
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    _user_is_association_admin,
    get_current_user,
    get_db,
)
from app.models.association import Association
from app.models.caisse import Caisse, CaisseCategory
from app.models.finance import Fund, FundKind, Treasury
from app.models.social_aid import AidType, SocialAidCase
from app.models.user import User
from app.schemas.aid_type import AidTypeCreate, AidTypeOut, AidTypeUpdate
from app.services.finance import get_or_create_treasury
from app.services.meeting_agenda import upsert_aid_type_activity

router = APIRouter()


async def _create_personal_insurance_caisse(
    db: AsyncSession, *, association_id: UUID, aid_name: str, slug: str
) -> Caisse:
    """Crée une caisse PERSONAL (solde par membre) servant de caisse d'assurance
    individuelle pour un type d'aide en mode member_insurance."""
    assoc_res = await db.execute(select(Association).where(Association.id == association_id))
    assoc = assoc_res.scalar_one()
    treasury = await get_or_create_treasury(db, assoc)
    ins_slug = f"assurance-{slug}"[:100]
    # Slug unique
    dupe = await db.execute(
        select(Caisse).where(Caisse.association_id == association_id, Caisse.slug == ins_slug)
    )
    if dupe.scalar_one_or_none():
        ins_slug = f"{ins_slug}-{uuid4().hex[:6]}"
    fund = Fund(
        treasury_id=treasury.id,
        kind=FundKind.INSURANCE,
        ref_key=ins_slug,
        name=f"Assurance — {aid_name}",
        description="Caisse d'assurance individuelle (par membre) liée à une aide.",
        is_system=False,
    )
    db.add(fund)
    await db.flush()
    caisse = Caisse(
        association_id=association_id,
        fund_id=fund.id,
        name=f"Assurance — {aid_name}",
        slug=ins_slug,
        description="Caisse d'assurance individuelle ; chaque membre y maintient un minimum.",
        category=CaisseCategory.PERSONAL,
        is_system=False,
    )
    db.add(caisse)
    await db.flush()
    return caisse


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


def _to_out(at: AidType, source_name: str | None = None, insurance_name: str | None = None) -> AidTypeOut:
    return AidTypeOut(
        id=at.id,
        association_id=at.association_id,
        funding_mode=at.funding_mode,
        source_caisse_id=at.source_caisse_id,
        source_caisse_name=source_name,
        auto_create_caisse=at.auto_create_caisse,
        insurance_caisse_id=at.insurance_caisse_id,
        insurance_caisse_name=insurance_name,
        insurance_minimum=at.insurance_minimum,
        refill_period_days=at.refill_period_days,
        name=at.name,
        slug=at.slug,
        description=at.description,
        is_active=at.is_active,
        member_contribution_amount=at.member_contribution_amount,
        is_contribution_recurring=at.is_contribution_recurring,
        amount_mode=at.amount_mode,
        aid_ceiling_amount=at.aid_ceiling_amount,
        objective_amount=at.objective_amount,
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
        # Outer join : les types « caisse temporaire » n'ont pas de caisse source.
        .outerjoin(Caisse, Caisse.id == AidType.source_caisse_id)
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

    dupe = await db.execute(
        select(AidType).where(
            AidType.association_id == payload.association_id,
            AidType.slug == payload.slug,
        )
    )
    if dupe.scalar_one_or_none():
        raise HTTPException(409, "Un type d'aide avec ce slug existe déjà.")

    caisse = None            # caisse source (mode fixed) — pour le nom en sortie
    insurance_caisse = None  # caisse perso d'assurance (mode member_insurance)

    if payload.funding_mode == "fixed":
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
                422, "Une caisse projet ne peut pas servir de source pour une aide sociale."
            )
        fund_res = await db.execute(select(Fund.kind).where(Fund.id == caisse.fund_id))
        if fund_res.scalar_one_or_none() == FundKind.TONTINE:
            raise HTTPException(
                422, "Une caisse de tontine ne peut pas servir de source d'aide sociale."
            )

    elif payload.funding_mode == "member_insurance":
        if payload.insurance_caisse_id is not None:
            ins_res = await db.execute(
                select(Caisse).where(
                    Caisse.id == payload.insurance_caisse_id,
                    Caisse.association_id == payload.association_id,
                )
            )
            insurance_caisse = ins_res.scalar_one_or_none()
            if not insurance_caisse:
                raise HTTPException(422, "Caisse d'assurance introuvable.")
            if insurance_caisse.category != CaisseCategory.PERSONAL:
                raise HTTPException(
                    422, "La caisse d'assurance doit être de catégorie « personnelle »."
                )
        else:
            # Auto-création d'une caisse PERSONAL dédiée à l'assurance de ce type.
            insurance_caisse = await _create_personal_insurance_caisse(
                db, association_id=payload.association_id, aid_name=payload.name, slug=payload.slug
            )

    at = AidType(
        association_id=payload.association_id,
        funding_mode=payload.funding_mode,
        source_caisse_id=payload.source_caisse_id,
        auto_create_caisse=payload.auto_create_caisse,
        insurance_caisse_id=insurance_caisse.id if insurance_caisse else None,
        insurance_minimum=payload.insurance_minimum,
        refill_period_days=payload.refill_period_days,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        member_contribution_amount=payload.member_contribution_amount,
        is_contribution_recurring=payload.is_contribution_recurring,
        amount_mode=payload.amount_mode,
        aid_ceiling_amount=payload.aid_ceiling_amount,
        objective_amount=payload.objective_amount,
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
    return _to_out(
        at,
        caisse.name if caisse else None,
        insurance_caisse.name if insurance_caisse else None,
    )


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
        # None = bascule vers une caisse temporaire (auto) : pas de caisse à valider.
        if data["source_caisse_id"] is not None:
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
