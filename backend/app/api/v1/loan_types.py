"""LoanType endpoints — admin-only catalogue of loan products (config-v2).

Workflow :
- Admin enables loans (Association.config.loans.enabled = true)
- Admin creates one or more LoanType (eligibility, interest, source caisse…)
- Loan requests reference a LoanType to inherit its rules (snapshotted on
  the Loan at creation so type edits don't retroactively change live loans).
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
from app.models.loan import Loan, LoanType
from app.models.user import User
from app.schemas.loan_type import LoanTypeCreate, LoanTypeOut, LoanTypeUpdate

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


def _to_out(lt: LoanType, source_name: str | None = None) -> LoanTypeOut:
    return LoanTypeOut(
        id=lt.id,
        association_id=lt.association_id,
        source_caisse_id=lt.source_caisse_id,
        source_caisse_name=source_name,
        name=lt.name,
        slug=lt.slug,
        description=lt.description,
        is_active=lt.is_active,
        eligibility_min_seniority_months=lt.eligibility_min_seniority_months,
        eligibility_no_default=lt.eligibility_no_default,
        max_simultaneous=lt.max_simultaneous,
        max_per_year=lt.max_per_year,
        interest_rate_pct=lt.interest_rate_pct,
        late_fee_pct=lt.late_fee_pct,
        max_duration_months=lt.max_duration_months,
    )


@router.get("", response_model=List[LoanTypeOut])
async def list_loan_types(
    association_id: UUID = Query(...),
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List loan types for the association. Open to any role with access
    (the loan-request UI needs to show available types to non-admins)."""
    await _check_access(db, current_user, association_id)
    stmt = (
        select(LoanType, Caisse.name)
        .join(Caisse, Caisse.id == LoanType.source_caisse_id)
        .where(LoanType.association_id == association_id)
        .order_by(LoanType.created_at)
    )
    if active_only:
        stmt = stmt.where(LoanType.is_active.is_(True))
    res = await db.execute(stmt)
    return [_to_out(lt, name) for lt, name in res.all()]


@router.post("", response_model=LoanTypeOut, status_code=status.HTTP_201_CREATED)
async def create_loan_type(
    payload: LoanTypeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _check_access(db, current_user, payload.association_id)
    await _require_admin(db, current_user, payload.association_id)

    # Caisse source : doit appartenir à la même asso et ne pas être un projet
    # à objectif fini (sortir des fonds d'un projet à objectif est rare).
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
            "Une caisse projet ne peut pas servir de source — utilise une caisse "
            "collective ou la caisse générale.",
        )

    # Slug unique per association
    dupe = await db.execute(
        select(LoanType).where(
            LoanType.association_id == payload.association_id,
            LoanType.slug == payload.slug,
        )
    )
    if dupe.scalar_one_or_none():
        raise HTTPException(409, "Un type de prêt avec ce slug existe déjà.")

    lt = LoanType(
        association_id=payload.association_id,
        source_caisse_id=payload.source_caisse_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        eligibility_min_seniority_months=payload.eligibility_min_seniority_months,
        eligibility_no_default=payload.eligibility_no_default,
        max_simultaneous=payload.max_simultaneous,
        max_per_year=payload.max_per_year,
        interest_rate_pct=payload.interest_rate_pct,
        late_fee_pct=payload.late_fee_pct,
        max_duration_months=payload.max_duration_months,
    )
    db.add(lt)
    await db.commit()
    await db.refresh(lt)
    return _to_out(lt, caisse.name)


@router.patch("/{loan_type_id}", response_model=LoanTypeOut)
async def update_loan_type(
    loan_type_id: UUID,
    payload: LoanTypeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    res = await db.execute(select(LoanType).where(LoanType.id == loan_type_id))
    lt = res.scalar_one_or_none()
    if not lt:
        raise HTTPException(404, "Type de prêt introuvable")
    await _check_access(db, current_user, lt.association_id)
    await _require_admin(db, current_user, lt.association_id)

    data = payload.model_dump(exclude_unset=True)

    # Caisse source : si modifiée, valider qu'elle appartient à la même asso
    # et n'est pas un projet. Mais surtout : interdire si un prêt vivant
    # référence ce type (changement rétroactif dangereux).
    if "source_caisse_id" in data and data["source_caisse_id"] != lt.source_caisse_id:
        live = await db.execute(
            select(Loan.id).where(
                Loan.loan_type_id == lt.id,
                Loan.status.in_(["approved", "disbursed", "repaying"]),
            )
        )
        if live.first():
            raise HTTPException(
                409, "Changement de caisse source interdit : des prêts vivants "
                "référencent ce type."
            )
        caisse_res = await db.execute(
            select(Caisse).where(
                Caisse.id == data["source_caisse_id"],
                Caisse.association_id == lt.association_id,
            )
        )
        new_caisse = caisse_res.scalar_one_or_none()
        if not new_caisse:
            raise HTTPException(422, "Nouvelle caisse source invalide.")
        if new_caisse.category.value == "project":
            raise HTTPException(422, "Une caisse projet ne peut pas servir de source.")

    for field, value in data.items():
        setattr(lt, field, value)
    await db.commit()
    await db.refresh(lt)

    caisse_res = await db.execute(select(Caisse.name).where(Caisse.id == lt.source_caisse_id))
    name = caisse_res.scalar_one_or_none()
    return _to_out(lt, name)


@router.delete("/{loan_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_loan_type(
    loan_type_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    res = await db.execute(select(LoanType).where(LoanType.id == loan_type_id))
    lt = res.scalar_one_or_none()
    if not lt:
        raise HTTPException(404, "Type de prêt introuvable")
    await _check_access(db, current_user, lt.association_id)
    await _require_admin(db, current_user, lt.association_id)

    # Refuse delete si des prêts (même clos) y réfèrent — l'historique
    # doit pouvoir remonter au type. Préfère is_active=False.
    used = await db.execute(select(Loan.id).where(Loan.loan_type_id == lt.id).limit(1))
    if used.first():
        raise HTTPException(
            409,
            "Des prêts référencent ce type. Désactive-le (is_active=false) plutôt "
            "que de le supprimer.",
        )

    await db.delete(lt)
    await db.commit()
