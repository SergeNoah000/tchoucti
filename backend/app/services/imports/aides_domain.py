"""Classeur « Aides » : Membres + Types d'aide + Demandes + Cotisations.

Import historique. Une demande crée un SocialAidCase ; si versée, un payout +
mouvement OUT (depuis le fonds de l'aide, sinon le fonds ASSURANCE). Les
cotisations (membres qui financent l'aide, surtout en mode ponctuel) créent un
mouvement IN crédité sur le fonds de l'aide.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.association import Association
from app.models.finance import Fund, FundKind, MovementDirection
from app.models.social_aid import (
    SocialAidCase,
    SocialAidCaseKind,
    SocialAidCaseStatus,
    SocialAidPayout,
)
from app.services.finance import Allocation, get_or_create_treasury, post_movement

from .aid_types import AidTypesImporter
from .base import Choice, DomainImporter, ImportColumn, Importer
from .members import MembersImporter

_STATUS = (
    Choice("paid", "Versée"),
    Choice("approved", "Approuvée"),
    Choice("requested", "Demandée"),
    Choice("rejected", "Rejetée"),
    Choice("cancelled", "Annulée"),
)


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


async def _aid_fund(db, treasury, fund_id):
    if fund_id:
        f = (await db.execute(select(Fund).where(Fund.id == fund_id))).scalar_one_or_none()
        if f is not None:
            return f
    return next((f for f in treasury.funds if f.kind == FundKind.INSURANCE), None)


# ─────────────────────────────────────────────────────────────────────────────
# Feuille 3 — Demandes.
# ─────────────────────────────────────────────────────────────────────────────
class AidRequestsSheet(Importer):
    entity = "aid_requests"
    sheet_key = "aid_requests"
    label = "Demandes"
    sheet_title = "Demandes"

    columns = [
        ImportColumn("reference", "Référence", required=True,
                     help="Identifiant unique de la demande (lie les cotisations).",
                     example="AID-2024-001"),
        ImportColumn("member_number", "N° adhérent (bénéficiaire)", required=True, example="M-001"),
        ImportColumn("aid_type", "Type d'aide", required=True,
                     help="Nom d'un type de la feuille « Types d'aide ».", example="Décès"),
        ImportColumn("title", "Intitulé", help="Facultatif.", example="Décès d'un parent"),
        ImportColumn("event_date", "Date de l'événement", help="JJ/MM/AAAA.", example="01/03/2024"),
        ImportColumn("requested_amount", "Montant demandé", help="Facultatif.", example="100000"),
        ImportColumn("approved_amount", "Montant accordé", help="Si validée/versée.", example="100000"),
        ImportColumn("status", "Statut", choices=_STATUS, help="Défaut : Versée."),
        ImportColumn("decided_date", "Date de décision", help="JJ/MM/AAAA.", example="03/03/2024"),
    ]

    async def new_ctx(self, db, association_id) -> dict:
        assoc = (await db.execute(select(Association).where(Association.id == association_id))).scalar_one()
        refs = (
            await db.execute(select(SocialAidCase.reference).where(SocialAidCase.association_id == association_id))
        ).scalars().all()
        return {"assoc": assoc, "aid_refs": {r.strip().lower() for r in refs}, "aid_case_by_ref": {}}

    async def validate_row(self, db, association_id, values, ctx):
        errors: list[str] = []
        ref = values.get("reference")
        if not ref:
            errors.append("Référence obligatoire.")
        elif ref.strip().lower() in ctx.get("aid_refs", set()):
            errors.append(f"Référence déjà utilisée : {ref}.")
        mid = ctx.get("membership_by_number", {}).get(values.get("member_number"))
        if not values.get("member_number"):
            errors.append("N° adhérent obligatoire.")
        elif mid is None:
            errors.append(f"N° adhérent introuvable : {values.get('member_number')}.")
        at = ctx.get("aid_type_by_name", {}).get((values.get("aid_type") or "").strip().lower())
        if not values.get("aid_type"):
            errors.append("Type d'aide obligatoire.")
        elif at is None:
            errors.append(f"Type d'aide introuvable : {values.get('aid_type')}.")
        status = values.get("status") or "paid"
        if status not in {c.value for c in _STATUS}:
            errors.append(f"Statut invalide : {values.get('status')}.")
        if errors:
            return None, errors
        ctx.setdefault("aid_refs", set()).add(ref.strip().lower())
        req = _int(values.get("requested_amount"))
        appr = _int(values.get("approved_amount"))
        return {
            "reference": ref, "membership_id": mid, "aid_type": at,
            "title": values.get("title") or (values.get("aid_type") or "Aide"),
            "event_date": _d(values.get("event_date")),
            "requested_amount": req if req is not None else (at["aid_ceiling_amount"] if at else 0),
            "approved_amount": appr or 0, "status": status,
            "decided_date": _d(values.get("decided_date")),
        }, []

    async def preview_register(self, payload, ctx):
        ctx.setdefault("aid_case_by_ref", {}).setdefault(
            payload["reference"].strip().lower(),
            {"case_id": "__preview__", "fund_id": (payload["aid_type"] or {}).get("fund_id")},
        )

    async def create_row(self, db, association_id, payload, ctx):
        at = payload["aid_type"]
        status = SocialAidCaseStatus(payload["status"])
        approved = payload["approved_amount"]
        if status in (SocialAidCaseStatus.PAID,) and not approved:
            approved = payload["requested_amount"]

        case = SocialAidCase(
            association_id=association_id, beneficiary_membership_id=payload["membership_id"],
            aid_type_id=at["id"] if at["id"] != "__preview__" else None,
            source_caisse_id=at.get("source_caisse_id"), reference=payload["reference"],
            kind=SocialAidCaseKind.OTHER, status=status, title=payload["title"],
            event_date=payload["event_date"],
            requested_on=payload["event_date"] or payload["decided_date"] or date.today(),
            decided_on=payload["decided_date"], requested_amount=payload["requested_amount"],
            approved_amount=approved,
            paid_amount=approved if status == SocialAidCaseStatus.PAID else 0,
        )
        db.add(case)
        await db.flush()
        ctx.setdefault("aid_case_by_ref", {})[payload["reference"].strip().lower()] = {
            "case_id": case.id, "fund_id": at.get("fund_id"),
        }

        # Versement au bénéficiaire (rejeu trésorerie) si payée.
        if status == SocialAidCaseStatus.PAID and approved > 0:
            treasury = await get_or_create_treasury(db, ctx["assoc"])
            fund = await _aid_fund(db, treasury, at.get("fund_id"))
            if fund is not None:
                mv = await post_movement(
                    db, treasury=treasury, direction=MovementDirection.OUT, amount=approved,
                    allocations=[Allocation(fund=fund, is_credit=False, amount=approved)],
                    occurred_on=case.decided_on or date.today(), source_type="import_aid_payout",
                    source_id=case.id, recorded_by_id=None,
                    related_membership_id=payload["membership_id"],
                    description=f"Aide {case.reference} (import)", commit=False, allow_overdraw=True,
                )
                db.add(SocialAidPayout(
                    case_id=case.id, paid_on=case.decided_on or date.today(),
                    amount=approved, movement_id=mv.id, notes="Import",
                ))


# ─────────────────────────────────────────────────────────────────────────────
# Feuille 4 — Cotisations (membres qui financent l'aide).
# ─────────────────────────────────────────────────────────────────────────────
class AidContributionsSheet(Importer):
    entity = "aid_contributions"
    sheet_key = "aid_contributions"
    label = "Cotisations"
    sheet_title = "Cotisations"

    columns = [
        ImportColumn("aid_reference", "Référence de la demande", required=True, example="AID-2024-001"),
        ImportColumn("member_number", "N° adhérent", required=True, example="M-002"),
        ImportColumn("amount", "Montant", required=True, example="2000"),
        ImportColumn("date", "Date", help="JJ/MM/AAAA.", example="03/03/2024"),
    ]

    async def new_ctx(self, db, association_id) -> dict:
        assoc = (await db.execute(select(Association).where(Association.id == association_id))).scalar_one()
        return {"assoc": assoc}

    async def validate_row(self, db, association_id, values, ctx):
        errors: list[str] = []
        ck = ctx.get("aid_case_by_ref", {}).get((values.get("aid_reference") or "").strip().lower())
        if not values.get("aid_reference"):
            errors.append("Référence de la demande obligatoire.")
        elif ck is None:
            errors.append(f"Demande d'aide introuvable : {values.get('aid_reference')}.")
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
        return {"case": ck, "membership_id": mid, "amount": amount, "date": _d(values.get("date")) or date.today()}, []

    async def create_row(self, db, association_id, payload, ctx):
        # Cotisation des membres pour financer l'aide → IN crédité sur le fonds.
        treasury = await get_or_create_treasury(db, ctx["assoc"])
        fund = await _aid_fund(db, treasury, payload["case"].get("fund_id"))
        if fund is not None:
            await post_movement(
                db, treasury=treasury, direction=MovementDirection.IN, amount=payload["amount"],
                allocations=[Allocation(fund=fund, is_credit=True, amount=payload["amount"])],
                occurred_on=payload["date"], source_type="import_aid_contribution",
                source_id=payload["case"]["case_id"] if payload["case"]["case_id"] != "__preview__" else None,
                recorded_by_id=None, related_membership_id=payload["membership_id"],
                description="Cotisation aide (import)", commit=False,
            )


class AidesDomainImporter(DomainImporter):
    entity = "aides_book"
    label = "Aides sociales (classeur complet)"
    description = (
        "Classeur Aides : membres, types d'aide, demandes et cotisations des "
        "membres pour financer les aides."
    )
    sheet_importers = [
        MembersImporter(),
        AidTypesImporter(),
        AidRequestsSheet(),
        AidContributionsSheet(),
    ]
