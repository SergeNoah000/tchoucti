"""Meeting agenda helpers — wire config-v2 entities (Caisse / TontineCycle /
AidType) to the legacy Activity catalogue so the séance page picks them up.

Each config entity gets its own Activity row at creation time. The Activity
serves as the "row" the séance page renders; `Activity.config` carries the
back-pointer (caisse_id / cycle_id / aid_type_id) so meeting close can route
the resulting cash movement to the correct fund.

Idempotent: re-running upsert is safe (looks up by code).
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meeting import Activity, ActivityType


async def upsert_caisse_activity(
    db: AsyncSession,
    *,
    association_id: UUID,
    caisse_id: UUID,
    name: str,
    slug: str,
    is_recurring: bool,
    recurring_amount: int,
    is_member_required: bool,
    member_required_amount: int,
) -> Activity:
    """One Activity per Caisse (recurring/required) — visible in séance."""
    code = f"caisse-{slug}"
    res = await db.execute(
        select(Activity).where(
            Activity.association_id == association_id, Activity.code == code
        )
    )
    act = res.scalar_one_or_none()
    suggested = recurring_amount if is_recurring else member_required_amount
    config = {
        "caisse_id": str(caisse_id),
        "amount": int(suggested or 0),
        "is_recurring": bool(is_recurring),
        "is_member_required": bool(is_member_required),
    }
    if act is None:
        act = Activity(
            association_id=association_id,
            type=ActivityType.OTHER,
            code=code,
            name=name,
            description="Caisse — auto-créée depuis la config.",
            config=config,
            is_visible_in_meeting=bool(is_recurring or is_member_required),
            is_required=bool(is_member_required),
        )
        db.add(act)
    else:
        act.name = name
        act.config = config
        act.is_visible_in_meeting = bool(is_recurring or is_member_required)
        act.is_required = bool(is_member_required)
    return act


async def upsert_tontine_activity(
    db: AsyncSession,
    *,
    association_id: UUID,
    cycle_id: UUID,  # en pratique : l'id de la Tontine durable (Phase 6A)
    name: str,
    slug: str,
    round_amount: int,
) -> Activity:
    """One Activity per tontine — TONTINE_CONTRIBUTION type. `config.tontine_slug`
    sert au routage du fonds à la clôture (fund ref_key == slug)."""
    code = f"tontine-{slug}"
    res = await db.execute(
        select(Activity).where(
            Activity.association_id == association_id, Activity.code == code
        )
    )
    act = res.scalar_one_or_none()
    config = {"tontine_id": str(cycle_id), "amount": int(round_amount), "tontine_slug": slug}
    if act is None:
        act = Activity(
            association_id=association_id,
            type=ActivityType.TONTINE_CONTRIBUTION,
            code=code,
            name=f"Tontine — {name}",
            description="Cotisation tontine — auto-créée à la création du cycle.",
            config=config,
            is_visible_in_meeting=True,
            is_required=True,
        )
        db.add(act)
    else:
        act.name = f"Tontine — {name}"
        act.config = config
        act.is_visible_in_meeting = True
        act.is_required = True
    return act


async def upsert_aid_type_activity(
    db: AsyncSession,
    *,
    association_id: UUID,
    aid_type_id: UUID,
    name: str,
    slug: str,
    member_contribution_amount: int,
    is_recurring: bool,
) -> Activity:
    """One Activity per AidType — used when a case is being collected."""
    code = f"aid-{slug}"
    res = await db.execute(
        select(Activity).where(
            Activity.association_id == association_id, Activity.code == code
        )
    )
    act = res.scalar_one_or_none()
    config = {
        "aid_type_id": str(aid_type_id),
        "amount": int(member_contribution_amount or 0),
        "is_recurring": bool(is_recurring),
    }
    if act is None:
        act = Activity(
            association_id=association_id,
            type=ActivityType.OTHER,
            code=code,
            name=f"Aide — {name}",
            description="Cotisation pour aide sociale — auto-créée depuis la config.",
            config=config,
            # Visible seulement quand un dossier de ce type est en cours
            # (filtré côté agenda). Au catalogue ça reste actif.
            is_visible_in_meeting=False,
            is_required=False,
        )
        db.add(act)
    else:
        act.name = f"Aide — {name}"
        act.config = config
    return act
