"""Feuille « Mouvements de caisse » (classeur Caisses).

Une ligne = un dépôt ou un retrait sur une caisse, à une date donnée. Chaque
mouvement REJOUE la trésorerie : il crée un TreasuryMovement (IN pour un dépôt,
OUT pour un retrait) crédité/débité sur le fonds de la caisse, et met à jour le
solde du membre pour les caisses PERSONAL (MemberCaisseBalance) + sa cotisation
cumulée.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.association import Association
from app.models.caisse import MemberCaisseBalance
from app.models.finance import Fund, MovementDirection
from app.models.role import Membership
from app.services.finance import Allocation, get_or_create_treasury, post_movement

from .base import Choice, ImportColumn, Importer

_DIRECTION = (
    Choice("deposit", "Dépôt (entrée)"),
    Choice("withdrawal", "Retrait (sortie)"),
)


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


class CaisseMovementsSheet(Importer):
    entity = "caisse_movements"
    sheet_key = "caisse_movements"
    label = "Mouvements de caisse"
    description = "Dépôts et retraits historiques sur les caisses."
    sheet_title = "Mouvements"

    columns = [
        ImportColumn("caisse", "Caisse", required=True,
                     help="Nom (ou identifiant) d'une caisse de la feuille « Caisses » "
                          "ou déjà existante.",
                     example="Épargne projet"),
        ImportColumn("direction", "Sens", required=True, choices=_DIRECTION,
                     help="Dépôt (entrée d'argent) ou Retrait (sortie)."),
        ImportColumn("amount", "Montant", required=True,
                     help="Montant du mouvement (entier positif).", example="20000"),
        ImportColumn("member_number", "N° adhérent",
                     help="Requis pour une caisse individuelle (à quel membre est le "
                          "solde). Facultatif pour une caisse collective.",
                     example="M-001"),
        ImportColumn("date", "Date", required=True,
                     help="Format JJ/MM/AAAA.", example="15/03/2024"),
        ImportColumn("label", "Libellé",
                     help="Description facultative du mouvement.",
                     example="Cotisation mensuelle"),
    ]

    async def new_ctx(self, db: AsyncSession, association_id) -> dict:
        assoc = (
            await db.execute(select(Association).where(Association.id == association_id))
        ).scalar_one()
        return {"assoc": assoc}

    def _resolve_caisse(self, ctx: dict, name: Optional[str]) -> Optional[dict]:
        if not name:
            return None
        return ctx.get("caisse_by_key", {}).get(name.strip().lower())

    def _resolve_member(self, ctx: dict, number: Optional[str]) -> Optional[Any]:
        if not number:
            return None
        return ctx.get("membership_by_number", {}).get(number)

    async def validate_row(self, db, association_id, values, ctx):
        errors: list[str] = []

        caisse = self._resolve_caisse(ctx, values.get("caisse"))
        if values.get("caisse") and caisse is None:
            errors.append(f"Caisse introuvable : {values.get('caisse')}.")
        elif not values.get("caisse"):
            errors.append("Caisse obligatoire.")

        direction = values.get("direction")
        if direction not in {c.value for c in _DIRECTION}:
            errors.append(f"Sens invalide : {values.get('direction')}.")

        amount = _parse_int(values.get("amount"))
        if amount is None or amount <= 0:
            errors.append(f"Montant invalide : {values.get('amount')}.")

        dt = _parse_date(values.get("date"))
        if values.get("date") and dt is None:
            errors.append(f"Date illisible : {values.get('date')} (attendu JJ/MM/AAAA).")
        elif not values.get("date"):
            errors.append("Date obligatoire.")

        number = values.get("member_number")
        membership_id = self._resolve_member(ctx, number)
        if number and membership_id is None:
            errors.append(f"N° adhérent introuvable : {number}.")
        if caisse and caisse.get("category") == "personal" and membership_id is None:
            errors.append("N° adhérent requis pour une caisse individuelle.")

        if errors:
            return None, errors

        return {
            "caisse": caisse,
            "direction": direction,
            "amount": amount,
            "membership_id": membership_id,
            "date": dt,
            "label": values.get("label"),
        }, []

    async def create_row(self, db, association_id, payload, ctx):
        assoc: Association = ctx["assoc"]
        treasury = await get_or_create_treasury(db, assoc)
        fund = (
            await db.execute(select(Fund).where(Fund.id == payload["caisse"]["fund_id"]))
        ).scalar_one_or_none()
        if fund is None:
            raise ValueError("Fonds de la caisse introuvable.")

        is_deposit = payload["direction"] == "deposit"
        direction = MovementDirection.IN if is_deposit else MovementDirection.OUT
        amount = payload["amount"]

        await post_movement(
            db,
            treasury=treasury,
            direction=direction,
            amount=amount,
            allocations=[Allocation(fund=fund, is_credit=is_deposit, amount=amount)],
            occurred_on=payload["date"],
            source_type="import_caisse_movement",
            source_id=None,
            recorded_by_id=None,
            related_membership_id=payload["membership_id"],
            description=payload["label"] or ("Dépôt" if is_deposit else "Retrait"),
            commit=False,
        )

        # Caisse PERSONAL : met à jour le solde individuel du membre.
        if payload["caisse"].get("category") == "personal" and payload["membership_id"]:
            bal = (
                await db.execute(
                    select(MemberCaisseBalance).where(
                        MemberCaisseBalance.caisse_id == payload["caisse"]["id"],
                        MemberCaisseBalance.membership_id == payload["membership_id"],
                    )
                )
            ).scalar_one_or_none()
            if bal is None:
                bal = MemberCaisseBalance(
                    caisse_id=payload["caisse"]["id"],
                    membership_id=payload["membership_id"],
                    balance=0,
                )
                db.add(bal)
            bal.balance += amount if is_deposit else -amount

        # Cotisation cumulée du membre (pour les dépôts).
        if payload["membership_id"] and is_deposit:
            mem = (
                await db.execute(
                    select(Membership).where(Membership.id == payload["membership_id"])
                )
            ).scalar_one_or_none()
            if mem is not None:
                mem.cumulative_contributions = (mem.cumulative_contributions or 0) + amount
