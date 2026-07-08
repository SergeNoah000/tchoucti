"""Aides partagées pour l'export (résolution des liaisons → libellés lisibles).

Les caches sont mémorisés dans le `ctx` d'export pour éviter les requêtes N+1
entre feuilles d'un même classeur.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.caisse import Caisse
from app.models.role import Membership
from app.models.tontine import Tontine
from app.models.user import User


def is_placeholder_email(email: Optional[str]) -> bool:
    """Email fabriqué pour un membre « papier » sans email réel (à ne pas
    exporter)."""
    return bool(email) and email.endswith(".import.local")


async def membership_number_map(
    db: AsyncSession, association_id, ctx: dict
) -> dict[UUID, Optional[str]]:
    """membership_id → numéro d'adhérent (ou None)."""
    cache = ctx.get("_exp_mem_number")
    if cache is None:
        res = await db.execute(
            select(Membership.id, Membership.member_number).where(
                Membership.association_id == association_id
            )
        )
        cache = {mid: num for mid, num in res.all()}
        ctx["_exp_mem_number"] = cache
    return cache


async def membership_name_map(
    db: AsyncSession, association_id, ctx: dict
) -> dict[UUID, Optional[str]]:
    """membership_id → nom complet (ou None)."""
    cache = ctx.get("_exp_mem_name")
    if cache is None:
        res = await db.execute(
            select(Membership.id, User.full_name)
            .join(User, User.id == Membership.user_id)
            .where(Membership.association_id == association_id)
        )
        cache = {mid: name for mid, name in res.all()}
        ctx["_exp_mem_name"] = cache
    return cache


async def tontine_name_map(
    db: AsyncSession, association_id, ctx: dict
) -> dict[UUID, str]:
    """tontine_id → nom."""
    cache = ctx.get("_exp_tontine_name")
    if cache is None:
        res = await db.execute(
            select(Tontine.id, Tontine.name).where(
                Tontine.association_id == association_id
            )
        )
        cache = {tid: name for tid, name in res.all()}
        ctx["_exp_tontine_name"] = cache
    return cache


async def caisse_name_by_id_map(
    db: AsyncSession, association_id, ctx: dict
) -> dict[UUID, str]:
    """caisse_id → nom."""
    cache = ctx.get("_exp_caisse_name")
    if cache is None:
        res = await db.execute(
            select(Caisse.id, Caisse.name).where(Caisse.association_id == association_id)
        )
        cache = {cid: name for cid, name in res.all()}
        ctx["_exp_caisse_name"] = cache
    return cache


async def caisse_name_by_fund_map(
    db: AsyncSession, association_id, ctx: dict
) -> dict[UUID, str]:
    """fund_id → nom de caisse (pour retrouver la caisse d'un mouvement de
    trésorerie via son fonds)."""
    cache = ctx.get("_exp_caisse_by_fund")
    if cache is None:
        res = await db.execute(
            select(Caisse.fund_id, Caisse.name).where(
                Caisse.association_id == association_id
            )
        )
        cache = {fid: name for fid, name in res.all() if fid is not None}
        ctx["_exp_caisse_by_fund"] = cache
    return cache
