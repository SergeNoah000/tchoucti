"""Importer de TYPES D'AIDES.

Aligné sur la config simplifiée : nom + source (caisse individuelle/assurance
ou collective/secours, par son nom) + montant à donner au demandeur.
"""
from __future__ import annotations

from typing import Any, Optional

from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.caisse import Caisse
from app.models.social_aid import AidType
from app.services.meeting_agenda import upsert_aid_type_activity

from .base import Choice, ImportColumn, Importer

_SOURCE = (
    Choice("collective", "Caisse collective (secours)"),
    Choice("individual", "Caisse individuelle (assurance)"),
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


class AidTypesImporter(Importer):
    entity = "aid_types"
    label = "Types d'aides"
    description = "Catalogue des types d'aides sociales (source + montant)."
    sheet_title = "Types d'aides"

    columns = [
        ImportColumn("name", "Nom", required=True,
                     help="Nom du type d'aide.", example="Décès d'un parent"),
        ImportColumn("source_mode", "Type de source", required=True, choices=_SOURCE,
                     help="Collective : tout sort d'une caisse partagée. "
                          "Individuelle : le montant est divisé par le nombre de "
                          "membres et débité sur la caisse perso de chacun."),
        ImportColumn("source_caisse", "Caisse source", required=True,
                     help="Nom exact de la caisse. Collective → caisse partagée ; "
                          "Individuelle → caisse « personnelle » (un solde par membre).",
                     example="Caisse de secours"),
        ImportColumn("amount", "Montant à donner", required=True,
                     help="Montant versé au membre qui fait la demande.",
                     example="100000"),
        ImportColumn("description", "Description", help="Facultatif."),
    ]

    async def new_ctx(self, db: AsyncSession, association_id) -> dict:
        caisses = (
            await db.execute(
                select(Caisse).where(Caisse.association_id == association_id)
            )
        ).scalars().all()
        slugs = (
            await db.execute(
                select(AidType.slug).where(AidType.association_id == association_id)
            )
        ).scalars().all()
        fund_by_caisse = {c.id: c.fund_id for c in caisses}
        existing = (
            await db.execute(select(AidType).where(AidType.association_id == association_id))
        ).scalars().all()
        aid_type_by_name = {
            at.name.strip().lower(): {
                "id": at.id, "funding_mode": at.funding_mode,
                "source_caisse_id": at.source_caisse_id,
                "insurance_caisse_id": at.insurance_caisse_id,
                "fund_id": fund_by_caisse.get(at.source_caisse_id or at.insurance_caisse_id),
                "aid_ceiling_amount": at.aid_ceiling_amount,
            }
            for at in existing
        }
        return {
            "caisses_by_name": {c.name.strip().lower(): c for c in caisses},
            "slugs": set(slugs),
            "aid_type_by_name": aid_type_by_name,
        }

    async def validate_row(self, db, association_id, values, ctx):
        errors: list[str] = []

        name = values.get("name")
        if not name:
            errors.append("Nom obligatoire.")

        mode = values.get("source_mode")
        if mode not in {c.value for c in _SOURCE}:
            errors.append(f"Type de source invalide : {values.get('source_mode')}.")

        src = values.get("source_caisse")
        caisse = ctx["caisses_by_name"].get(src.strip().lower()) if src else None
        if not src:
            errors.append("Caisse source obligatoire.")
        elif caisse is None:
            errors.append(f"Caisse source introuvable : « {src} ».")
        elif mode == "individual" and caisse.category.value != "personal":
            errors.append("Source individuelle : la caisse doit être « personnelle ».")
        elif mode == "collective" and caisse.category.value not in ("collective",):
            errors.append("Source collective : la caisse doit être « collective ».")

        amount = _parse_int(values.get("amount")) or 0
        if amount <= 0:
            errors.append("Montant à donner > 0 requis.")

        slug = slugify(name)[:100] if name else ""
        if slug and slug in ctx["slugs"]:
            errors.append(f"Un type d'aide « {name} » existe déjà.")

        if errors:
            return None, errors

        ctx["slugs"].add(slug)
        funding_mode = "member_insurance" if mode == "individual" else "fixed"
        return {
            "name": name, "slug": slug, "description": values.get("description"),
            "funding_mode": funding_mode,
            "source_caisse_id": caisse.id if mode == "collective" else None,
            "insurance_caisse_id": caisse.id if mode == "individual" else None,
            "aid_ceiling_amount": amount,
        }, []

    async def create_row(self, db, association_id, payload, ctx):
        at = AidType(
            association_id=association_id,
            funding_mode=payload["funding_mode"],
            source_caisse_id=payload["source_caisse_id"],
            insurance_caisse_id=payload["insurance_caisse_id"],
            name=payload["name"],
            slug=payload["slug"],
            description=payload["description"],
            amount_mode="ceiling",
            aid_ceiling_amount=payload["aid_ceiling_amount"],
        )
        db.add(at)
        await db.flush()

        # Alimente le cache de liaison (classeur Aides).
        cby = ctx.get("caisses_by_name", {})
        caisse_id = payload["source_caisse_id"] or payload["insurance_caisse_id"]
        fund_id = next((c.fund_id for c in cby.values() if c.id == caisse_id), None)
        ctx.setdefault("aid_type_by_name", {})[payload["name"].strip().lower()] = {
            "id": at.id, "funding_mode": payload["funding_mode"],
            "source_caisse_id": payload["source_caisse_id"],
            "insurance_caisse_id": payload["insurance_caisse_id"],
            "fund_id": fund_id, "aid_ceiling_amount": payload["aid_ceiling_amount"],
        }

        await upsert_aid_type_activity(
            db,
            association_id=association_id,
            aid_type_id=at.id,
            name=payload["name"],
            slug=payload["slug"],
            member_contribution_amount=0,
            is_recurring=False,
        )

    async def preview_register(self, payload, ctx):
        ctx.setdefault("aid_type_by_name", {}).setdefault(
            payload["name"].strip().lower(),
            {"id": "__preview__", "funding_mode": payload["funding_mode"],
             "source_caisse_id": payload["source_caisse_id"],
             "insurance_caisse_id": payload["insurance_caisse_id"],
             "fund_id": "__preview__", "aid_ceiling_amount": payload["aid_ceiling_amount"]},
        )
