"""Classeur « Tontines » : Membres + Tontines (config) + Séances + Participations
+ Gagnants. Import HISTORIQUE fidèle : les tours/participations/gagnants sont
explicites (pas d'auto-génération de rotation). Les mouvements d'argent rejouent
la trésorerie ; une tontine en avoir physique ne touche pas la trésorerie.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.association import Association
from app.models.caisse import Caisse, CaisseCategory
from app.models.finance import Fund, FundKind, MovementDirection
from app.models.role import Membership
from app.models.tontine import (
    Tontine,
    TontineContribution,
    TontineCycle,
    TontineCycleStatus,
    TontineRound,
    TontineRoundBeneficiary,
    TontineRoundStatus,
)
from app.services.finance import Allocation, get_or_create_treasury, post_movement

from .base import Choice, DomainImporter, ImportColumn, Importer
from .members import MembersImporter

_FREQ = (
    Choice("weekly", "Hebdomadaire"),
    Choice("biweekly", "Quinzaine"),
    Choice("monthly", "Mensuelle"),
    Choice("bimonthly", "Bimestrielle"),
)
_KIND = (Choice("money", "Argent"), Choice("asset", "Avoir physique"))
_RSTATUS = (
    Choice("collecting", "En collecte"),
    Choice("paid_out", "Versé"),
    Choice("pending", "À venir"),
)
_YESNO = (Choice("yes", "Oui"), Choice("no", "Non"))


def _int(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    s = str(raw).replace(" ", "").replace(".", "").replace(",", "").strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _d(raw: Any) -> Optional[date]:
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


# ─────────────────────────────────────────────────────────────────────────────
# Feuille 2 — Tontines (config) : crée la tontine + un cycle ACTIF vide.
# ─────────────────────────────────────────────────────────────────────────────
class TontineConfigSheet(Importer):
    entity = "tontine_config"
    sheet_key = "tontine_config"
    label = "Tontines"
    sheet_title = "Tontines"

    columns = [
        ImportColumn("name", "Nom", required=True, help="Nom de la tontine.",
                     example="Tontine des Mamans"),
        ImportColumn("round_amount", "Montant / quantité par tour", required=True,
                     help="Argent versé (ou quantité de l'avoir) par participant et par tour.",
                     example="10000"),
        ImportColumn("contribution_kind", "Nature", choices=_KIND,
                     help="Argent ou avoir physique. Défaut : Argent."),
        ImportColumn("asset_label", "Nom de l'avoir",
                     help="Si avoir physique : nom de l'objet.", example="Sac de riz 25 kg"),
        ImportColumn("frequency", "Cadence", choices=_FREQ, help="Défaut : Mensuelle."),
        ImportColumn("start_date", "Date de début", required=True,
                     help="Format JJ/MM/AAAA.", example="01/02/2024"),
        ImportColumn("description", "Description", help="Facultatif."),
    ]

    async def new_ctx(self, db, association_id) -> dict:
        assoc = (
            await db.execute(select(Association).where(Association.id == association_id))
        ).scalar_one()
        names = (
            await db.execute(select(Tontine.name).where(Tontine.association_id == association_id))
        ).scalars().all()
        return {"assoc": assoc, "tontine_names": {n.strip().lower() for n in names}, "tontine_by_name": {}}

    async def validate_row(self, db, association_id, values, ctx):
        errors: list[str] = []
        name = values.get("name")
        if not name:
            errors.append("Nom obligatoire.")
        elif name.strip().lower() in ctx.get("tontine_names", set()):
            errors.append(f"Une tontine « {name} » existe déjà.")
        amount = _int(values.get("round_amount")) or 0
        if amount <= 0:
            errors.append("Montant/quantité par tour > 0 requis.")
        kind = values.get("contribution_kind") or "money"
        if kind not in {c.value for c in _KIND}:
            errors.append(f"Nature invalide : {values.get('contribution_kind')}.")
        if kind == "asset" and not (values.get("asset_label") or "").strip():
            errors.append("Nom de l'avoir requis pour une tontine en avoir physique.")
        freq = values.get("frequency") or "monthly"
        start = _d(values.get("start_date"))
        if start is None:
            errors.append("Date de début obligatoire (JJ/MM/AAAA).")
        if errors:
            return None, errors
        ctx.setdefault("tontine_names", set()).add(name.strip().lower())
        return {
            "name": name, "round_amount": amount, "contribution_kind": kind,
            "asset_label": values.get("asset_label") if kind == "asset" else None,
            "frequency": freq, "start_date": start, "description": values.get("description"),
        }, []

    async def preview_register(self, payload, ctx):
        ctx.setdefault("tontine_by_name", {}).setdefault(
            payload["name"].strip().lower(),
            {"cycle_id": "__preview__", "fund_id": None, "kind": payload["contribution_kind"]},
        )

    async def create_row(self, db, association_id, payload, ctx):
        from app.api.v1.tontines import _unique_slug
        from app.services.meeting_agenda import upsert_tontine_activity

        assoc: Association = ctx["assoc"]
        slug = await _unique_slug(db, association_id, payload["name"])
        is_asset = payload["contribution_kind"] == "asset"

        tontine = Tontine(
            association_id=association_id, name=payload["name"], slug=slug,
            description=payload["description"], round_amount=payload["round_amount"],
            contribution_kind=payload["contribution_kind"],
            asset_label=payload["asset_label"], frequency=payload["frequency"],
            beneficiary_pays=True, selection_method="manual",
        )
        db.add(tontine)
        await db.flush()

        fund_id = None
        if not is_asset:
            treasury = await get_or_create_treasury(db, assoc)
            fund = Fund(
                treasury_id=treasury.id, kind=FundKind.TONTINE, ref_key=slug,
                name=f"Tontine — {payload['name']}", description="Fonds dédié à cette tontine.",
                is_system=True,
            )
            db.add(fund)
            await db.flush()
            fund_id = fund.id
            db.add(Caisse(
                association_id=association_id, fund_id=fund.id,
                name=f"Tontine — {payload['name']}", slug=slug,
                description="Caisse système liée à cette tontine (auto-créée).",
                category=CaisseCategory.SYSTEM, is_system=True,
            ))
            await upsert_tontine_activity(
                db, association_id=association_id, cycle_id=tontine.id,
                name=payload["name"], slug=slug, round_amount=payload["round_amount"],
            )

        cycle = TontineCycle(
            tontine_id=tontine.id, cycle_number=1, round_amount=payload["round_amount"],
            rounds_count=0, current_round_number=1, start_date=payload["start_date"],
            order_strategy="manual", status=TontineCycleStatus.ACTIVE, is_mandatory=True,
        )
        db.add(cycle)
        await db.flush()
        ctx.setdefault("tontine_by_name", {})[payload["name"].strip().lower()] = {
            "tontine_id": tontine.id, "cycle_id": cycle.id, "fund_id": fund_id,
            "kind": payload["contribution_kind"],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Feuille 3 — Séances / Tours.
# ─────────────────────────────────────────────────────────────────────────────
class TontineRoundsSheet(Importer):
    entity = "tontine_rounds"
    sheet_key = "tontine_rounds"
    label = "Séances / Tours"
    sheet_title = "Séances"

    columns = [
        ImportColumn("tontine", "Tontine", required=True, help="Nom de la tontine.",
                     example="Tontine des Mamans"),
        ImportColumn("round_number", "N° tour", required=True, example="1"),
        ImportColumn("date", "Date du tour", help="Format JJ/MM/AAAA.", example="01/03/2024"),
        ImportColumn("expected_amount", "Cagnotte attendue", help="Facultatif.", example="100000"),
        ImportColumn("status", "Statut", choices=_RSTATUS, help="Défaut : En collecte."),
    ]

    async def new_ctx(self, db, association_id) -> dict:
        return {}

    def _ton(self, ctx, name):
        return ctx.get("tontine_by_name", {}).get((name or "").strip().lower())

    async def validate_row(self, db, association_id, values, ctx):
        errors: list[str] = []
        ton = self._ton(ctx, values.get("tontine"))
        if not values.get("tontine"):
            errors.append("Tontine obligatoire.")
        elif ton is None:
            errors.append(f"Tontine introuvable : {values.get('tontine')}.")
        num = _int(values.get("round_number"))
        if num is None or num < 1:
            errors.append(f"N° tour invalide : {values.get('round_number')}.")
        status = values.get("status") or "collecting"
        if status not in {c.value for c in _RSTATUS}:
            errors.append(f"Statut invalide : {values.get('status')}.")
        if errors:
            return None, errors
        return {
            "tontine": ton, "tontine_name": values.get("tontine"), "round_number": num,
            "date": _d(values.get("date")), "expected_amount": _int(values.get("expected_amount")) or 0,
            "status": status,
        }, []

    async def preview_register(self, payload, ctx):
        ctx.setdefault("round_by_key", {})[
            (payload["tontine_name"].strip().lower(), payload["round_number"])
        ] = {"round_id": "__preview__", "tontine": payload["tontine"]}

    async def create_row(self, db, association_id, payload, ctx):
        ton = payload["tontine"]
        st = {
            "collecting": TontineRoundStatus.COLLECTING,
            "paid_out": TontineRoundStatus.PAID_OUT,
            "pending": TontineRoundStatus.PENDING,
        }[payload["status"]]
        rnd = TontineRound(
            cycle_id=ton["cycle_id"], round_number=payload["round_number"],
            scheduled_date=payload["date"], expected_amount=payload["expected_amount"], status=st,
        )
        db.add(rnd)
        await db.flush()
        ctx.setdefault("round_by_key", {})[
            (payload["tontine_name"].strip().lower(), payload["round_number"])
        ] = {"round_id": rnd.id, "tontine": ton}
        # Tient à jour le nombre de tours du cycle.
        cyc = (await db.execute(select(TontineCycle).where(TontineCycle.id == ton["cycle_id"]))).scalar_one_or_none()
        if cyc and payload["round_number"] > cyc.rounds_count:
            cyc.rounds_count = payload["round_number"]


# ─────────────────────────────────────────────────────────────────────────────
# Feuille 4 — Participations (cotisations versées par tour).
# ─────────────────────────────────────────────────────────────────────────────
class TontineContributionsSheet(Importer):
    entity = "tontine_contributions"
    sheet_key = "tontine_contributions"
    label = "Participations"
    sheet_title = "Participations"

    columns = [
        ImportColumn("tontine", "Tontine", required=True, example="Tontine des Mamans"),
        ImportColumn("round_number", "N° tour", required=True, example="1"),
        ImportColumn("member_number", "N° adhérent", required=True, example="M-001"),
        ImportColumn("amount", "Montant / quantité", required=True, example="10000"),
        ImportColumn("date", "Date", help="Format JJ/MM/AAAA.", example="01/03/2024"),
        ImportColumn("late", "En retard", choices=_YESNO, help="Défaut : Non."),
    ]

    async def new_ctx(self, db, association_id) -> dict:
        assoc = (await db.execute(select(Association).where(Association.id == association_id))).scalar_one()
        return {"assoc": assoc}

    def _round(self, ctx, name, num):
        return ctx.get("round_by_key", {}).get(((name or "").strip().lower(), num))

    async def validate_row(self, db, association_id, values, ctx):
        errors: list[str] = []
        num = _int(values.get("round_number"))
        rk = self._round(ctx, values.get("tontine"), num) if num else None
        if rk is None:
            errors.append(f"Tour introuvable : {values.get('tontine')} / tour {values.get('round_number')}.")
        mid = ctx.get("membership_by_number", {}).get(values.get("member_number"))
        if not values.get("member_number"):
            errors.append("N° adhérent obligatoire.")
        elif mid is None:
            errors.append(f"N° adhérent introuvable : {values.get('member_number')}.")
        amount = _int(values.get("amount"))
        if amount is None or amount <= 0:
            errors.append(f"Montant invalide : {values.get('amount')}.")
        if errors:
            return None, errors
        return {
            "round": rk, "membership_id": mid, "amount": amount,
            "date": _d(values.get("date")) or date.today(),
            "late": (values.get("late") or "no") == "yes",
        }, []

    async def create_row(self, db, association_id, payload, ctx):
        rk = payload["round"]
        db.add(TontineContribution(
            round_id=rk["round_id"], membership_id=payload["membership_id"],
            amount=payload["amount"], contributed_on=payload["date"], is_late=payload["late"],
        ))
        rnd = (await db.execute(select(TontineRound).where(TontineRound.id == rk["round_id"]))).scalar_one_or_none()
        if rnd:
            rnd.collected_amount = (rnd.collected_amount or 0) + payload["amount"]
        # Argent : crédite le fonds de la tontine (rejeu trésorerie).
        fund_id = rk["tontine"].get("fund_id")
        if fund_id:
            assoc: Association = ctx["assoc"]
            treasury = await get_or_create_treasury(db, assoc)
            fund = (await db.execute(select(Fund).where(Fund.id == fund_id))).scalar_one_or_none()
            if fund is not None:
                await post_movement(
                    db, treasury=treasury, direction=MovementDirection.IN, amount=payload["amount"],
                    allocations=[Allocation(fund=fund, is_credit=True, amount=payload["amount"])],
                    occurred_on=payload["date"], source_type="import_tontine_contribution",
                    source_id=rk["round_id"], recorded_by_id=None,
                    related_membership_id=payload["membership_id"],
                    description="Cotisation tontine (import)", commit=False,
                )


# ─────────────────────────────────────────────────────────────────────────────
# Feuille 5 — Gagnants (bénéficiaires par tour).
# ─────────────────────────────────────────────────────────────────────────────
class TontineWinnersSheet(Importer):
    entity = "tontine_winners"
    sheet_key = "tontine_winners"
    label = "Gagnants"
    sheet_title = "Gagnants"

    columns = [
        ImportColumn("tontine", "Tontine", required=True, example="Tontine des Mamans"),
        ImportColumn("round_number", "N° tour", required=True, example="1"),
        ImportColumn("member_number", "N° adhérent (gagnant)", required=True, example="M-001"),
        ImportColumn("name_label", "Nom de la part",
                     help="Facultatif (si le membre a plusieurs noms).", example="Awa 1"),
        ImportColumn("share_amount", "Montant reçu", required=True, example="100000"),
        ImportColumn("paid_date", "Date de versement", help="Si versé. JJ/MM/AAAA.",
                     example="01/03/2024"),
    ]

    async def new_ctx(self, db, association_id) -> dict:
        assoc = (await db.execute(select(Association).where(Association.id == association_id))).scalar_one()
        return {"assoc": assoc}

    def _round(self, ctx, name, num):
        return ctx.get("round_by_key", {}).get(((name or "").strip().lower(), num))

    async def validate_row(self, db, association_id, values, ctx):
        errors: list[str] = []
        num = _int(values.get("round_number"))
        rk = self._round(ctx, values.get("tontine"), num) if num else None
        if rk is None:
            errors.append(f"Tour introuvable : {values.get('tontine')} / tour {values.get('round_number')}.")
        mid = ctx.get("membership_by_number", {}).get(values.get("member_number"))
        if not values.get("member_number"):
            errors.append("N° adhérent obligatoire.")
        elif mid is None:
            errors.append(f"N° adhérent introuvable : {values.get('member_number')}.")
        share = _int(values.get("share_amount"))
        if share is None or share <= 0:
            errors.append(f"Montant reçu invalide : {values.get('share_amount')}.")
        if errors:
            return None, errors
        return {
            "round": rk, "membership_id": mid, "name_label": values.get("name_label"),
            "share": share, "paid_date": _d(values.get("paid_date")),
        }, []

    async def create_row(self, db, association_id, payload, ctx):
        rk = payload["round"]
        db.add(TontineRoundBeneficiary(
            round_id=rk["round_id"], membership_id=payload["membership_id"],
            name_label=payload["name_label"], share_amount=payload["share"], share_parts=1,
        ))
        rnd = (await db.execute(select(TontineRound).where(TontineRound.id == rk["round_id"]))).scalar_one_or_none()
        if rnd and payload["paid_date"]:
            rnd.status = TontineRoundStatus.PAID_OUT
            rnd.paid_out_date = payload["paid_date"]
            rnd.paid_out_amount = (rnd.paid_out_amount or 0) + payload["share"]
            # Argent : débite le fonds de la tontine (versement).
            fund_id = rk["tontine"].get("fund_id")
            if fund_id:
                assoc: Association = ctx["assoc"]
                treasury = await get_or_create_treasury(db, assoc)
                fund = (await db.execute(select(Fund).where(Fund.id == fund_id))).scalar_one_or_none()
                if fund is not None:
                    await post_movement(
                        db, treasury=treasury, direction=MovementDirection.OUT, amount=payload["share"],
                        allocations=[Allocation(fund=fund, is_credit=False, amount=payload["share"])],
                        occurred_on=payload["paid_date"], source_type="import_tontine_payout",
                        source_id=rk["round_id"], recorded_by_id=None,
                        related_membership_id=payload["membership_id"],
                        description="Versement tontine (import)", commit=False,
                    )


class TontinesDomainImporter(DomainImporter):
    entity = "tontines_book"
    label = "Tontines (classeur complet)"
    description = (
        "Classeur Tontines : membres, config des tontines, séances (tours), "
        "participations (cotisations) et gagnants."
    )
    sheet_importers = [
        MembersImporter(),
        TontineConfigSheet(),
        TontineRoundsSheet(),
        TontineContributionsSheet(),
        TontineWinnersSheet(),
    ]
