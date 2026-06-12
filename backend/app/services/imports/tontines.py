"""Importer de TONTINES.

Crée la tontine + sa caisse système + son 1er cycle, en réutilisant le
constructeur de l'API (``_build_cycle``). Les participants sont facultatifs :
une liste de numéros d'adhérent dans l'ordre de passage → cycle actif ;
sinon → cycle brouillon (participants ajoutés ensuite depuis la config).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.association import Association
from app.models.caisse import Caisse, CaisseCategory
from app.models.finance import Fund, FundKind
from app.models.role import Membership
from app.models.tontine import Tontine
from app.services.finance import get_or_create_treasury

from .base import Choice, ImportColumn, Importer

_FREQ = (
    Choice("weekly", "Hebdomadaire"),
    Choice("biweekly", "Quinzaine"),
    Choice("monthly", "Mensuelle"),
    Choice("bimonthly", "Bimestrielle"),
)


def _parse_int(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    s = str(raw).replace(" ", "").replace(".", "").replace(",", "").strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _parse_date(raw: Any) -> Optional[date]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


class TontinesImporter(Importer):
    entity = "tontines"
    label = "Tontines"
    description = "Tontines de l'association (montant, cadence, ordre de passage)."
    sheet_title = "Tontines"

    columns = [
        ImportColumn("name", "Nom", required=True,
                     help="Nom de la tontine.", example="Tontine des Mamans"),
        ImportColumn("round_amount", "Montant par tour", required=True,
                     help="Montant que chaque participant verse à chaque tour.",
                     example="10000"),
        ImportColumn("frequency", "Cadence", choices=_FREQ,
                     help="Fréquence des tours. Par défaut : Mensuelle."),
        ImportColumn("beneficiaries_per_round", "Bénéficiaires par tour",
                     help="Combien de membres reçoivent à chaque tour. Par défaut : 1.",
                     example="1"),
        ImportColumn("start_date", "Date de début", required=True,
                     help="Format JJ/MM/AAAA.", example="01/02/2026"),
        ImportColumn("participants", "Participants (numéros d'adhérent, dans l'ordre)",
                     help="Facultatif. Numéros d'adhérent séparés par des virgules, "
                          "dans l'ordre de passage. Vide = à configurer ensuite.",
                     example="M-001, M-002, M-003"),
        ImportColumn("description", "Description", help="Facultatif."),
    ]

    async def new_ctx(self, db: AsyncSession, association_id) -> dict:
        assoc = (
            await db.execute(select(Association).where(Association.id == association_id))
        ).scalar_one()
        members = (
            await db.execute(
                select(Membership).where(Membership.association_id == association_id)
            )
        ).scalars().all()
        names = (
            await db.execute(
                select(Tontine.name).where(Tontine.association_id == association_id)
            )
        ).scalars().all()
        return {
            "assoc": assoc,
            "members_by_number": {
                (m.member_number or "").strip().lower(): m
                for m in members
                if m.member_number
            },
            "names": {n.strip().lower() for n in names},
            "seen_names": set(),
        }

    async def validate_row(self, db, association_id, values, ctx):
        errors: list[str] = []

        name = values.get("name")
        if not name:
            errors.append("Nom obligatoire.")
        elif name.strip().lower() in ctx["names"] or name.strip().lower() in ctx["seen_names"]:
            errors.append(f"Une tontine « {name} » existe déjà.")

        amount = _parse_int(values.get("round_amount")) or 0
        if amount <= 0:
            errors.append("Montant par tour > 0 requis.")

        frequency = values.get("frequency") or "monthly"
        if frequency not in {c.value for c in _FREQ}:
            errors.append(f"Cadence invalide : {values.get('frequency')}.")

        bpr = _parse_int(values.get("beneficiaries_per_round")) or 1
        if bpr < 1 or bpr > 20:
            errors.append("Bénéficiaires par tour hors limites (1–20).")

        start = _parse_date(values.get("start_date"))
        if values.get("start_date") and start is None:
            errors.append("Date de début illisible (attendu JJ/MM/AAAA).")
        if start is None:
            errors.append("Date de début obligatoire.")

        # Participants (facultatif) : numéros d'adhérent dans l'ordre.
        order: list = []
        raw_parts = values.get("participants")
        if raw_parts:
            nums = [p.strip() for p in str(raw_parts).split(",") if p.strip()]
            seen = set()
            for num in nums:
                m = ctx["members_by_number"].get(num.lower())
                if m is None:
                    errors.append(f"Numéro d'adhérent introuvable : {num}.")
                elif m.id in seen:
                    errors.append(f"Participant en double : {num}.")
                else:
                    seen.add(m.id)
                    order.append(m.id)

        if errors:
            return None, errors

        ctx["seen_names"].add(name.strip().lower())
        return {
            "name": name,
            "description": values.get("description"),
            "round_amount": amount,
            "frequency": frequency,
            "beneficiaries_per_round": bpr,
            "start_date": start,
            "order": order,
        }, []

    async def create_row(self, db, association_id, payload, ctx):
        # Imports paresseux : réutilise le constructeur de l'API tontines.
        from app.api.v1.tontines import _build_cycle, _unique_slug
        from app.services.meeting_agenda import upsert_tontine_activity

        assoc: Association = ctx["assoc"]
        slug = await _unique_slug(db, association_id, payload["name"])

        tontine = Tontine(
            association_id=association_id,
            name=payload["name"],
            slug=slug,
            description=payload["description"],
            round_amount=payload["round_amount"],
            frequency=payload["frequency"],
            beneficiaries_per_round=payload["beneficiaries_per_round"],
            beneficiary_pays=True,
            selection_method="manual",
        )
        db.add(tontine)
        await db.flush()

        treasury = await get_or_create_treasury(db, assoc)
        fund = Fund(
            treasury_id=treasury.id,
            kind=FundKind.TONTINE,
            ref_key=slug,
            name=f"Tontine — {payload['name']}",
            description="Fonds dédié à cette tontine.",
            is_system=True,
        )
        db.add(fund)
        await db.flush()
        db.add(
            Caisse(
                association_id=association_id,
                fund_id=fund.id,
                name=f"Tontine — {payload['name']}",
                slug=slug,
                description="Caisse système liée à cette tontine (auto-créée).",
                category=CaisseCategory.SYSTEM,
                is_system=True,
            )
        )

        await upsert_tontine_activity(
            db,
            association_id=association_id,
            cycle_id=tontine.id,
            name=payload["name"],
            slug=slug,
            round_amount=payload["round_amount"],
        )

        order = payload["order"]
        await _build_cycle(
            db,
            tontine=tontine,
            cycle_number=1,
            start_date=payload["start_date"],
            participant_order=order,
            is_mandatory=True,
            excluded_ids=[],
            activate=bool(order),
        )
