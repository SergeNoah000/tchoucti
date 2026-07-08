"""Importer de CAISSES.

Crée Fund + Caisse + Activity, comme l'endpoint POST /caisses. Les booléens
(récurrente, plafond, objectif, cotisation obligatoire) sont dérivés du fait
qu'un montant est renseigné, pour garder le template simple.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.association import Association
from app.models.caisse import Caisse, CaisseCategory
from app.models.finance import Fund, FundKind
from app.services.finance import get_or_create_treasury
from app.services.meeting_agenda import upsert_caisse_activity

from .base import Choice, ImportColumn, Importer

_CATEGORY = (
    Choice("collective", "Collective (partagée)"),
    Choice("personal", "Individuelle (un solde par membre)"),
    Choice("project", "Projet (objectif + échéance)"),
)
_YESNO = (Choice("yes", "Oui"), Choice("no", "Non"))


def _parse_int(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    s = str(raw).replace(" ", "").replace(" ", "").replace(".", "").replace(",", "")
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


class CaissesImporter(Importer):
    entity = "caisses"
    label = "Caisses"
    description = "Caisses de l'association (collectives, individuelles, projets)."
    sheet_title = "Caisses"

    columns = [
        ImportColumn("name", "Nom", required=True,
                     help="Nom de la caisse.", example="Caisse de secours"),
        ImportColumn("category", "Type", required=True, choices=_CATEGORY,
                     help="Collective (un solde partagé), Individuelle (un solde "
                          "par membre), ou Projet (objectif à atteindre)."),
        ImportColumn("description", "Description", help="Facultatif."),
        ImportColumn("collected_each_meeting", "Collectée à chaque séance",
                     choices=_YESNO, help="Si Oui, la caisse apparaît en séance. "
                     "Par défaut : Non."),
        ImportColumn("recurring_amount", "Montant par séance",
                     help="Facultatif. Vide = montant libre (chaque membre verse "
                          "ce qu'il veut). Ignoré si non collectée à chaque séance.",
                     example="2000"),
        ImportColumn("member_required_amount", "Cotisation obligatoire",
                     help="Facultatif. Montant minimum dû par membre (> 0 pour "
                          "rendre la cotisation obligatoire).",
                     example="5000"),
        ImportColumn("ceiling_amount", "Plafond",
                     help="Facultatif. Montant maximum que la caisse peut atteindre.",
                     example="1000000"),
        ImportColumn("objective_amount", "Objectif",
                     help="Obligatoire pour une caisse Projet : montant cible.",
                     example="500000"),
        ImportColumn("objective_deadline", "Échéance objectif",
                     help="Facultatif. Format JJ/MM/AAAA.", example="31/12/2026"),
    ]

    async def export_rows(self, db, association_id, ctx):
        res = await db.execute(
            select(Caisse)
            .where(Caisse.association_id == association_id)
            .order_by(Caisse.name)
        )
        rows = []
        for c in res.scalars().all():
            if getattr(c, "is_system", False):
                continue  # caisses système (fonds tontine/assurance) non éditables
            rows.append({
                "name": c.name,
                "category": c.category,
                "description": c.description,
                "collected_each_meeting": "yes" if c.is_recurring else "no",
                "recurring_amount": c.recurring_amount or None,
                "member_required_amount": (c.member_required_amount or None) if c.is_member_required else None,
                "ceiling_amount": (c.ceiling_amount or None) if c.has_ceiling else None,
                "objective_amount": (c.objective_amount or None) if c.has_objective else None,
                "objective_deadline": c.objective_deadline,
            })
        return rows

    async def new_ctx(self, db: AsyncSession, association_id) -> dict:
        assoc = (
            await db.execute(select(Association).where(Association.id == association_id))
        ).scalar_one()
        rows = (
            await db.execute(
                select(Caisse.id, Caisse.name, Caisse.slug, Caisse.category, Caisse.fund_id).where(
                    Caisse.association_id == association_id
                )
            )
        ).all()
        # Cache de liaison partagé : nom/slug (minuscule) → infos caisse, pour
        # que la feuille « mouvements » résolve la caisse cible.
        caisse_by_key: dict = {}
        for cid, cname, cslug, ccat, cfund in rows:
            info = {"id": cid, "fund_id": cfund, "category": ccat.value if hasattr(ccat, "value") else ccat}
            caisse_by_key[(cname or "").strip().lower()] = info
            caisse_by_key[(cslug or "").strip().lower()] = info
        return {
            "assoc": assoc,
            "slugs": {s for _, _, s, _, _ in rows},
            "caisse_by_key": caisse_by_key,
        }

    async def validate_row(self, db, association_id, values, ctx):
        errors: list[str] = []

        name = values.get("name")
        if not name:
            errors.append("Nom obligatoire.")

        category = values.get("category")
        if category not in {c.value for c in _CATEGORY}:
            errors.append(f"Type invalide : {values.get('category')}.")

        slug = slugify(name)[:100] if name else ""
        if slug and slug in ctx["slugs"]:
            errors.append(f"Une caisse nommée « {name} » existe déjà.")

        recurring_amount = _parse_int(values.get("recurring_amount")) or 0
        member_required_amount = _parse_int(values.get("member_required_amount")) or 0
        ceiling_amount = _parse_int(values.get("ceiling_amount")) or 0
        objective_amount = _parse_int(values.get("objective_amount")) or 0
        deadline = _parse_date(values.get("objective_deadline"))
        if values.get("objective_deadline") and deadline is None:
            errors.append("Échéance objectif illisible (attendu JJ/MM/AAAA).")

        collected = (values.get("collected_each_meeting") or "no") == "yes"

        if category == "project" and objective_amount <= 0:
            errors.append("Une caisse Projet doit avoir un Objectif > 0.")

        if errors:
            return None, errors

        ctx["slugs"].add(slug)
        return {
            "name": name,
            "slug": slug,
            "description": values.get("description"),
            "category": category,
            "is_recurring": collected,
            "recurring_amount": recurring_amount,
            "is_member_required": member_required_amount > 0,
            "member_required_amount": member_required_amount,
            "has_ceiling": ceiling_amount > 0,
            "ceiling_amount": ceiling_amount,
            "has_objective": objective_amount > 0,
            "objective_amount": objective_amount,
            "objective_deadline": deadline,
        }, []

    async def preview_register(self, payload, ctx):
        # Aperçu : simule la caisse pour la feuille « mouvements ».
        info = {"id": "__preview__", "fund_id": "__preview__", "category": payload["category"]}
        cache = ctx.setdefault("caisse_by_key", {})
        cache.setdefault(payload["name"].strip().lower(), info)
        cache.setdefault(payload["slug"].strip().lower(), info)

    async def create_row(self, db, association_id, payload, ctx):
        assoc: Association = ctx["assoc"]
        treasury = await get_or_create_treasury(db, assoc)

        fund = Fund(
            treasury_id=treasury.id,
            kind=FundKind.CUSTOM,
            ref_key=payload["slug"],
            name=payload["name"],
            description=payload["description"],
            is_system=False,
        )
        db.add(fund)
        await db.flush()

        caisse = Caisse(
            association_id=association_id,
            fund_id=fund.id,
            name=payload["name"],
            slug=payload["slug"],
            description=payload["description"],
            category=CaisseCategory(payload["category"]),
            is_system=False,
            is_recurring=payload["is_recurring"],
            recurring_amount=payload["recurring_amount"],
            is_member_required=payload["is_member_required"],
            member_required_amount=payload["member_required_amount"],
            has_ceiling=payload["has_ceiling"],
            ceiling_amount=payload["ceiling_amount"],
            has_objective=payload["has_objective"],
            objective_amount=payload["objective_amount"],
            objective_deadline=payload["objective_deadline"],
        )
        db.add(caisse)
        await db.flush()

        # Alimente le cache de liaison (classeurs multi-feuilles).
        info = {"id": caisse.id, "fund_id": fund.id, "category": payload["category"]}
        cache = ctx.setdefault("caisse_by_key", {})
        cache[payload["name"].strip().lower()] = info
        cache[payload["slug"].strip().lower()] = info

        await upsert_caisse_activity(
            db,
            association_id=association_id,
            caisse_id=caisse.id,
            name=payload["name"],
            slug=payload["slug"],
            is_recurring=payload["is_recurring"],
            recurring_amount=payload["recurring_amount"],
            is_member_required=payload["is_member_required"],
            member_required_amount=payload["member_required_amount"],
        )
