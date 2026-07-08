"""Service des demandes de sortie d'argent (validation trésorier).

Un membre du bureau PRÉPARE une sortie (`create_request`) ; le **trésorier**
la valide (déclenche l'argent) ou la refuse. La finalisation métier propre à
chaque flux (décaissement prêt, versement aide…) vit dans le fichier du domaine
concerné et est appelée par le routeur de validation via un dispatch sur `kind`.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payout_request import (
    PayoutKind,
    PayoutRequest,
    PayoutRequestStatus,
)
from app.models.role import (
    Membership,
    MembershipRole,
    MembershipStatus,
    Role,
)
from app.models.user import User, UserType


# ── RBAC : qui peut valider une sortie ? ────────────────────────────────────
async def user_can_validate_payout(
    db: AsyncSession, user: User, association_id: UUID
) -> bool:
    """Le trésorier valide les sorties. Les admins (plateforme / groupement /
    admin d'association) le peuvent aussi en tant que sur-ensemble."""
    if user.user_type in (UserType.SUPER_ADMIN, UserType.GROUPEMENT_ADMIN):
        return True
    stmt = (
        select(Role.code)
        .join(MembershipRole, MembershipRole.role_id == Role.id)
        .join(Membership, Membership.id == MembershipRole.membership_id)
        .where(
            Membership.user_id == user.id,
            Membership.association_id == association_id,
            Membership.status == MembershipStatus.ACTIVE,
            Role.code.in_(("treasurer", "association_admin")),
        )
    )
    res = await db.execute(stmt)
    return res.first() is not None


# ── Création / lecture ──────────────────────────────────────────────────────
async def pending_for_source(
    db: AsyncSession, source_type: str, source_id: UUID
) -> Optional[PayoutRequest]:
    """Demande EN ATTENTE déjà ouverte pour cette action métier (anti-doublon)."""
    res = await db.execute(
        select(PayoutRequest).where(
            PayoutRequest.source_type == source_type,
            PayoutRequest.source_id == source_id,
            PayoutRequest.status == PayoutRequestStatus.PENDING,
        )
    )
    return res.scalar_one_or_none()


async def pending_source_ids(
    db: AsyncSession, source_type: str, source_ids: list[UUID]
) -> set[UUID]:
    """Sous-ensemble des `source_ids` ayant une sortie EN ATTENTE (pour marquer
    une liste sans requête N+1)."""
    if not source_ids:
        return set()
    res = await db.execute(
        select(PayoutRequest.source_id).where(
            PayoutRequest.source_type == source_type,
            PayoutRequest.source_id.in_(source_ids),
            PayoutRequest.status == PayoutRequestStatus.PENDING,
        )
    )
    return {row[0] for row in res.all()}


async def create_request(
    db: AsyncSession,
    *,
    association_id: UUID,
    kind: PayoutKind,
    source_type: str,
    amount: int,
    prepared_by_id: UUID,
    source_id: Optional[UUID] = None,
    fund_id: Optional[UUID] = None,
    related_membership_id: Optional[UUID] = None,
    description: Optional[str] = None,
    payload: Optional[dict] = None,
    enforce_unique: bool = True,
    commit: bool = True,
) -> PayoutRequest:
    """Enregistre une sortie EN ATTENTE (aucun argent ne bouge).

    `enforce_unique=True` interdit deux demandes en attente pour la même action
    (ex. un prêt). Le mettre à False pour les flux où plusieurs demandes en
    attente coexistent sur une même source (ex. retraits d'une même caisse)."""
    if amount <= 0:
        raise HTTPException(422, "Le montant doit être positif")
    if enforce_unique and source_id is not None:
        existing = await pending_for_source(db, source_type, source_id)
        if existing is not None:
            raise HTTPException(
                409, "Une demande de sortie est déjà en attente pour cette opération."
            )
    req = PayoutRequest(
        association_id=association_id,
        kind=kind,
        status=PayoutRequestStatus.PENDING,
        source_type=source_type,
        source_id=source_id,
        fund_id=fund_id,
        amount=amount,
        related_membership_id=related_membership_id,
        description=description,
        payload=payload or {},
        prepared_by_id=prepared_by_id,
    )
    db.add(req)
    if commit:
        await db.commit()
        await db.refresh(req)
    else:
        await db.flush()
    return req


async def get_request_or_404(db: AsyncSession, request_id: UUID) -> PayoutRequest:
    res = await db.execute(
        select(PayoutRequest).where(PayoutRequest.id == request_id)
    )
    req = res.scalar_one_or_none()
    if req is None:
        raise HTTPException(404, "Demande de sortie introuvable")
    return req
