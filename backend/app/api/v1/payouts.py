"""Demandes de sortie d'argent — file de validation du trésorier.

- `GET  /payouts`            : liste (filtrable par statut) pour une association.
- `POST /payouts/{id}/validate` : le trésorier valide → l'argent sort réellement.
- `POST /payouts/{id}/reject`   : le trésorier refuse → clôture sans mouvement.
- `POST /payouts/{id}/cancel`   : le préparateur / admin annule une demande.

La finalisation métier (post_movement + transition du domaine) est déléguée à
une fonction `complete_*` du fichier domaine, sélectionnée sur `request.kind`.
"""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import _user_has_bureau_role, get_current_user, get_db
from app.models.association import Association
from app.models.finance import Fund
from app.models.payout_request import (
    PayoutKind,
    PayoutRequest,
    PayoutRequestStatus,
)
from app.models.role import Membership
from app.models.user import User
from app.schemas.payout import PayoutDecision, PayoutRequestOut
from app.models.notification import NotificationKind
from app.services import payouts
from app.services.notify import notify_user

router = APIRouter()


def _check_access(user: User, assoc: Association) -> None:
    if user.is_super_admin:
        return
    if user.groupement_id != assoc.groupement_id:
        raise HTTPException(403, "Forbidden")


async def _get_assoc_or_404(db: AsyncSession, association_id: UUID) -> Association:
    res = await db.execute(select(Association).where(Association.id == association_id))
    assoc = res.scalar_one_or_none()
    if not assoc:
        raise HTTPException(404, "Association introuvable")
    return assoc


async def _enrich(
    db: AsyncSession, reqs: List[PayoutRequest], currency: Optional[str]
) -> List[PayoutRequestOut]:
    user_ids = {r.prepared_by_id for r in reqs if r.prepared_by_id} | {
        r.decided_by_id for r in reqs if r.decided_by_id
    }
    mem_ids = {r.related_membership_id for r in reqs if r.related_membership_id}
    fund_ids = {r.fund_id for r in reqs if r.fund_id}

    users: dict[UUID, str] = {}
    if user_ids:
        res = await db.execute(select(User).where(User.id.in_(user_ids)))
        users = {u.id: u.full_name for u in res.scalars().all()}
    members: dict[UUID, str] = {}
    if mem_ids:
        res = await db.execute(
            select(Membership.id, User.full_name, Membership.member_number)
            .join(User, User.id == Membership.user_id)
            .where(Membership.id.in_(mem_ids))
        )
        for mid, full_name, num in res.all():
            members[mid] = full_name or (f"N°{num}" if num else None)
    funds: dict[UUID, str] = {}
    if fund_ids:
        res = await db.execute(select(Fund).where(Fund.id.in_(fund_ids)))
        funds = {f.id: f.name for f in res.scalars().all()}

    out: List[PayoutRequestOut] = []
    for r in reqs:
        o = PayoutRequestOut.model_validate(r)
        o.currency = currency
        o.prepared_by_name = users.get(r.prepared_by_id) if r.prepared_by_id else None
        o.decided_by_name = users.get(r.decided_by_id) if r.decided_by_id else None
        o.beneficiary_name = (
            members.get(r.related_membership_id) if r.related_membership_id else None
        )
        o.fund_name = funds.get(r.fund_id) if r.fund_id else None
        out.append(o)
    return out


@router.get("", response_model=List[PayoutRequestOut])
async def list_payouts(
    association_id: UUID = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assoc = await _get_assoc_or_404(db, association_id)
    _check_access(current_user, assoc)
    stmt = (
        select(PayoutRequest)
        .where(PayoutRequest.association_id == association_id)
        .order_by(PayoutRequest.prepared_at.desc())
    )
    if status_filter:
        stmt = stmt.where(
            PayoutRequest.status == PayoutRequestStatus(status_filter)
        )
    res = await db.execute(stmt)
    reqs = list(res.scalars().all())
    return await _enrich(db, reqs, assoc.currency)


async def _complete_by_kind(
    db: AsyncSession, req: PayoutRequest, current_user: User
):
    """Dispatch vers la finalisation métier. Import local → pas d'import circulaire."""
    if req.kind == PayoutKind.LOAN_DISBURSEMENT:
        from app.api.v1.loans import complete_loan_disbursement

        return await complete_loan_disbursement(db, req, current_user)
    if req.kind == PayoutKind.AID_PAYOUT:
        from app.api.v1.social_aid import complete_aid_payout

        return await complete_aid_payout(db, req, current_user)
    if req.kind == PayoutKind.TONTINE_PAYOUT:
        from app.api.v1.tontines import complete_tontine_payout

        return await complete_tontine_payout(db, req, current_user)
    if req.kind == PayoutKind.CAISSE_WITHDRAWAL:
        from app.api.v1.caisses import complete_caisse_withdrawal

        return await complete_caisse_withdrawal(db, req, current_user)
    # MANUAL_OUT n'est pas mis en file (sortie manuelle réservée au trésorier,
    # exécutée immédiatement) — il n'y a donc jamais de demande à finaliser ici.
    raise HTTPException(422, f"Type de sortie non finalisable : {req.kind}")


@router.post("/{request_id}/validate", response_model=PayoutRequestOut)
async def validate_payout(
    request_id: UUID,
    payload: PayoutDecision = PayoutDecision(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = await payouts.get_request_or_404(db, request_id)
    assoc = await _get_assoc_or_404(db, req.association_id)
    _check_access(current_user, assoc)
    if not await payouts.user_can_validate_payout(db, current_user, assoc.id):
        raise HTTPException(403, "Réservé au trésorier (ou à l'administrateur)")
    if req.status != PayoutRequestStatus.PENDING:
        raise HTTPException(409, "Cette demande a déjà été traitée")

    movement = await _complete_by_kind(db, req, current_user)

    req.status = PayoutRequestStatus.VALIDATED
    req.decided_by_id = current_user.id
    req.decided_at = datetime.now(timezone.utc)
    req.decision_note = payload.note
    req.movement_id = getattr(movement, "id", None)
    await db.commit()

    # Prévenir le préparateur que sa sortie a été validée.
    if req.prepared_by_id and req.prepared_by_id != current_user.id:
        res = await db.execute(select(User).where(User.id == req.prepared_by_id))
        preparer = res.scalar_one_or_none()
        if preparer:
            await notify_user(
                db,
                user=preparer,
                kind=NotificationKind.SUCCESS,
                title="Sortie validée",
                body=f"Votre sortie « {req.description or req.source_type} » "
                f"a été validée par le trésorier.",
                association_id=assoc.id,
                commit=True,
            )

    req = await payouts.get_request_or_404(db, request_id)
    return (await _enrich(db, [req], assoc.currency))[0]


@router.post("/{request_id}/reject", response_model=PayoutRequestOut)
async def reject_payout(
    request_id: UUID,
    payload: PayoutDecision = PayoutDecision(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = await payouts.get_request_or_404(db, request_id)
    assoc = await _get_assoc_or_404(db, req.association_id)
    _check_access(current_user, assoc)
    if not await payouts.user_can_validate_payout(db, current_user, assoc.id):
        raise HTTPException(403, "Réservé au trésorier (ou à l'administrateur)")
    if req.status != PayoutRequestStatus.PENDING:
        raise HTTPException(409, "Cette demande a déjà été traitée")

    req.status = PayoutRequestStatus.REJECTED
    req.decided_by_id = current_user.id
    req.decided_at = datetime.now(timezone.utc)
    req.decision_note = payload.note
    await db.commit()

    if req.prepared_by_id and req.prepared_by_id != current_user.id:
        res = await db.execute(select(User).where(User.id == req.prepared_by_id))
        preparer = res.scalar_one_or_none()
        if preparer:
            await notify_user(
                db,
                user=preparer,
                kind=NotificationKind.WARNING,
                title="Sortie refusée",
                body=f"Votre sortie « {req.description or req.source_type} » "
                f"a été refusée par le trésorier."
                + (f" Motif : {payload.note}" if payload.note else ""),
                association_id=assoc.id,
                commit=True,
            )

    req = await payouts.get_request_or_404(db, request_id)
    return (await _enrich(db, [req], assoc.currency))[0]


@router.post("/{request_id}/cancel", response_model=PayoutRequestOut)
async def cancel_payout(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Annulation par le préparateur (ou un membre du bureau) avant validation."""
    req = await payouts.get_request_or_404(db, request_id)
    assoc = await _get_assoc_or_404(db, req.association_id)
    _check_access(current_user, assoc)
    if not await _user_has_bureau_role(db, current_user, assoc.id):
        raise HTTPException(403, "Action réservée aux membres du bureau")
    if req.status != PayoutRequestStatus.PENDING:
        raise HTTPException(409, "Cette demande a déjà été traitée")

    req.status = PayoutRequestStatus.CANCELLED
    req.decided_by_id = current_user.id
    req.decided_at = datetime.now(timezone.utc)
    await db.commit()
    req = await payouts.get_request_or_404(db, request_id)
    return (await _enrich(db, [req], assoc.currency))[0]
