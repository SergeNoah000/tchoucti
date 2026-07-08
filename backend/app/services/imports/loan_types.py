"""Importer de TYPES DE PRÊTS.

Chaque type référence une caisse source (par son nom) d'où sort le capital.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.caisse import Caisse
from app.models.loan import LoanType

from .base import ImportColumn, Importer


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


def _parse_dec(raw: Any) -> Optional[Decimal]:
    if raw is None:
        return None
    s = str(raw).replace("%", "").replace(",", ".").strip()
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


class LoanTypesImporter(Importer):
    entity = "loan_types"
    label = "Types de prêts"
    description = "Catalogue des types de prêts (taux, durée, caisse source…)."
    sheet_title = "Types de prêts"

    columns = [
        ImportColumn("name", "Nom", required=True,
                     help="Nom du type de prêt.", example="Prêt ordinaire"),
        ImportColumn("source_caisse", "Caisse source", required=True,
                     help="Nom exact de la caisse d'où sort le capital prêté.",
                     example="Caisse générale"),
        ImportColumn("interest_rate_pct", "Taux d'intérêt (%/mois)",
                     help="Taux mensuel. Par défaut : 0.", example="5"),
        ImportColumn("late_fee_pct", "Pénalité de retard (%)",
                     help="Par défaut : 0.", example="2"),
        ImportColumn("max_duration_months", "Durée max (mois)",
                     help="Par défaut : 12.", example="12"),
        ImportColumn("max_simultaneous", "Prêts simultanés max",
                     help="Par défaut : 1.", example="1"),
        ImportColumn("max_per_year", "Prêts max / an",
                     help="Par défaut : 1.", example="2"),
        ImportColumn("eligibility_min_seniority_months", "Ancienneté min (mois)",
                     help="Ancienneté minimale du membre. Par défaut : 0.", example="6"),
        ImportColumn("description", "Description", help="Facultatif."),
    ]

    async def export_rows(self, db, association_id, ctx):
        from .export_helpers import caisse_name_by_id_map

        caisse_name = await caisse_name_by_id_map(db, association_id, ctx)
        res = await db.execute(
            select(LoanType)
            .where(LoanType.association_id == association_id)
            .order_by(LoanType.name)
        )
        rows = []
        for lt in res.scalars().all():
            rows.append({
                "name": lt.name,
                "source_caisse": caisse_name.get(lt.source_caisse_id),
                "interest_rate_pct": lt.interest_rate_pct,
                "late_fee_pct": lt.late_fee_pct,
                "max_duration_months": lt.max_duration_months,
                "max_simultaneous": lt.max_simultaneous,
                "max_per_year": lt.max_per_year,
                "eligibility_min_seniority_months": lt.eligibility_min_seniority_months,
                "description": lt.description,
            })
        return rows

    async def new_ctx(self, db: AsyncSession, association_id) -> dict:
        caisses = (
            await db.execute(
                select(Caisse).where(Caisse.association_id == association_id)
            )
        ).scalars().all()
        slugs = (
            await db.execute(
                select(LoanType.slug).where(LoanType.association_id == association_id)
            )
        ).scalars().all()
        # Cache de liaison (classeur Prêts) : nom du type → infos (id, caisse
        # source + son fonds, taux, durée). Préchargé avec les types existants.
        existing = (
            await db.execute(
                select(LoanType).where(LoanType.association_id == association_id)
            )
        ).scalars().all()
        caisse_fund = {c.id: c.fund_id for c in caisses}
        loan_type_by_name = {
            lt.name.strip().lower(): {
                "id": lt.id,
                "source_caisse_id": lt.source_caisse_id,
                "fund_id": caisse_fund.get(lt.source_caisse_id),
                "interest_rate_pct": lt.interest_rate_pct,
                "late_fee_pct": lt.late_fee_pct,
                "max_duration_months": lt.max_duration_months,
            }
            for lt in existing
        }
        return {
            "caisses_by_name": {c.name.strip().lower(): c for c in caisses},
            "slugs": set(slugs),
            "loan_type_by_name": loan_type_by_name,
        }

    async def validate_row(self, db, association_id, values, ctx):
        errors: list[str] = []

        name = values.get("name")
        if not name:
            errors.append("Nom obligatoire.")

        src = values.get("source_caisse")
        caisse = ctx["caisses_by_name"].get(src.strip().lower()) if src else None
        if not src:
            errors.append("Caisse source obligatoire.")
        elif caisse is None:
            errors.append(f"Caisse source introuvable : « {src} ».")
        elif caisse.category.value == "project":
            errors.append("Une caisse Projet ne peut pas servir de source de prêt.")

        slug = slugify(name)[:100] if name else ""
        if slug and slug in ctx["slugs"]:
            errors.append(f"Un type de prêt « {name} » existe déjà.")

        rate = _parse_dec(values.get("interest_rate_pct")) or Decimal("0")
        late = _parse_dec(values.get("late_fee_pct")) or Decimal("0")
        duration = _parse_int(values.get("max_duration_months")) or 12
        simul = _parse_int(values.get("max_simultaneous")) or 1
        per_year = _parse_int(values.get("max_per_year")) or 1
        seniority = _parse_int(values.get("eligibility_min_seniority_months")) or 0

        if not (0 <= rate <= 100):
            errors.append("Taux d'intérêt hors limites (0–100).")
        if duration < 1 or duration > 120:
            errors.append("Durée max hors limites (1–120 mois).")

        if errors:
            return None, errors

        ctx["slugs"].add(slug)
        return {
            "name": name, "slug": slug, "source_caisse_id": caisse.id,
            "description": values.get("description"),
            "interest_rate_pct": rate, "late_fee_pct": late,
            "max_duration_months": duration, "max_simultaneous": simul,
            "max_per_year": per_year, "eligibility_min_seniority_months": seniority,
        }, []

    async def create_row(self, db, association_id, payload, ctx):
        lt = LoanType(
            association_id=association_id,
            source_caisse_id=payload["source_caisse_id"],
            name=payload["name"],
            slug=payload["slug"],
            description=payload["description"],
            eligibility_min_seniority_months=payload["eligibility_min_seniority_months"],
            eligibility_no_default=True,
            max_simultaneous=payload["max_simultaneous"],
            max_per_year=payload["max_per_year"],
            interest_rate_pct=payload["interest_rate_pct"],
            late_fee_pct=payload["late_fee_pct"],
            max_duration_months=payload["max_duration_months"],
        )
        db.add(lt)
        await db.flush()

        # Alimente le cache de liaison (classeur Prêts).
        caisse = ctx.get("caisses_by_name", {})
        fund_id = None
        for c in caisse.values():
            if c.id == payload["source_caisse_id"]:
                fund_id = c.fund_id
                break
        ctx.setdefault("loan_type_by_name", {})[payload["name"].strip().lower()] = {
            "id": lt.id, "source_caisse_id": payload["source_caisse_id"], "fund_id": fund_id,
            "interest_rate_pct": payload["interest_rate_pct"],
            "late_fee_pct": payload["late_fee_pct"],
            "max_duration_months": payload["max_duration_months"],
        }

    async def preview_register(self, payload, ctx):
        ctx.setdefault("loan_type_by_name", {}).setdefault(
            payload["name"].strip().lower(),
            {"id": "__preview__", "source_caisse_id": payload["source_caisse_id"],
             "fund_id": "__preview__", "interest_rate_pct": payload["interest_rate_pct"],
             "late_fee_pct": payload["late_fee_pct"],
             "max_duration_months": payload["max_duration_months"]},
        )
