"""Classeur « Prêts » : Membres + Types de prêt + Prêts + Remboursements.

Import historique : chaque prêt snapshote son échéancier (compute_schedule).
Si décaissé, un mouvement OUT sort de la caisse source. Chaque remboursement
ventile (intérêt avant capital, tour le plus ancien d'abord), met à jour les
échéances/soldes et crée un mouvement IN (capital → caisse source, intérêt →
assurance).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.association import Association
from app.models.finance import Fund, FundKind, MovementDirection
from app.models.loan import (
    Loan,
    LoanInstallment,
    LoanInstallmentStatus,
    LoanRepayment,
    LoanStatus,
)
from app.services.finance import Allocation, get_or_create_treasury, post_movement
from app.services.loan_calculator import compute_schedule

from .base import Choice, DomainImporter, ImportColumn, Importer
from .loan_types import LoanTypesImporter
from .members import MembersImporter

_STATUS = (
    Choice("disbursed", "Décaissé"),
    Choice("repaying", "En remboursement"),
    Choice("paid", "Soldé"),
    Choice("approved", "Approuvé (non décaissé)"),
    Choice("requested", "Demandé"),
    Choice("defaulted", "En défaut"),
    Choice("cancelled", "Annulé"),
)
_DISBURSED_STATES = {"disbursed", "repaying", "paid", "defaulted"}


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


async def _fund(db, fund_id):
    if not fund_id:
        return None
    return (await db.execute(select(Fund).where(Fund.id == fund_id))).scalar_one_or_none()


# ─────────────────────────────────────────────────────────────────────────────
# Feuille 3 — Prêts.
# ─────────────────────────────────────────────────────────────────────────────
class LoansSheet(Importer):
    entity = "loans"
    sheet_key = "loans"
    label = "Prêts"
    sheet_title = "Prêts"

    columns = [
        ImportColumn("reference", "Référence", required=True,
                     help="Identifiant unique du prêt (sert à lier les remboursements).",
                     example="PRT-2024-001"),
        ImportColumn("member_number", "N° adhérent (emprunteur)", required=True, example="M-001"),
        ImportColumn("loan_type", "Type de prêt", required=True,
                     help="Nom d'un type de la feuille « Types de prêt ».",
                     example="Prêt ordinaire"),
        ImportColumn("principal", "Capital", required=True, example="100000"),
        ImportColumn("requested_date", "Date de demande", help="JJ/MM/AAAA.", example="01/02/2024"),
        ImportColumn("disbursed_date", "Date de décaissement", help="JJ/MM/AAAA.", example="05/02/2024"),
        ImportColumn("status", "Statut", choices=_STATUS, help="Défaut : En remboursement."),
        ImportColumn("purpose", "Motif", help="Facultatif."),
    ]

    async def new_ctx(self, db, association_id) -> dict:
        assoc = (await db.execute(select(Association).where(Association.id == association_id))).scalar_one()
        refs = (
            await db.execute(select(Loan.reference).where(Loan.association_id == association_id))
        ).scalars().all()
        return {"assoc": assoc, "loan_refs": {r.strip().lower() for r in refs}, "loan_by_ref": {}}

    async def validate_row(self, db, association_id, values, ctx):
        errors: list[str] = []
        ref = values.get("reference")
        if not ref:
            errors.append("Référence obligatoire.")
        elif ref.strip().lower() in ctx.get("loan_refs", set()):
            errors.append(f"Référence déjà utilisée : {ref}.")
        mid = ctx.get("membership_by_number", {}).get(values.get("member_number"))
        if not values.get("member_number"):
            errors.append("N° adhérent obligatoire.")
        elif mid is None:
            errors.append(f"N° adhérent introuvable : {values.get('member_number')}.")
        lt = ctx.get("loan_type_by_name", {}).get((values.get("loan_type") or "").strip().lower())
        if not values.get("loan_type"):
            errors.append("Type de prêt obligatoire.")
        elif lt is None:
            errors.append(f"Type de prêt introuvable : {values.get('loan_type')}.")
        principal = _int(values.get("principal"))
        if principal is None or principal <= 0:
            errors.append(f"Capital invalide : {values.get('principal')}.")
        status = values.get("status") or "repaying"
        if status not in {c.value for c in _STATUS}:
            errors.append(f"Statut invalide : {values.get('status')}.")
        if errors:
            return None, errors
        ctx.setdefault("loan_refs", set()).add(ref.strip().lower())
        return {
            "reference": ref, "membership_id": mid, "loan_type": lt, "principal": principal,
            "requested_date": _d(values.get("requested_date")),
            "disbursed_date": _d(values.get("disbursed_date")),
            "status": status, "purpose": values.get("purpose"),
        }, []

    async def preview_register(self, payload, ctx):
        ctx.setdefault("loan_by_ref", {}).setdefault(
            payload["reference"].strip().lower(),
            {"loan_id": "__preview__", "fund_id": payload["loan_type"].get("fund_id")},
        )

    async def create_row(self, db, association_id, payload, ctx):
        lt = payload["loan_type"]
        rate = lt["interest_rate_pct"] or Decimal("0")
        duration = lt["max_duration_months"] or 12
        requested = payload["requested_date"] or date.today()
        disbursed = payload["disbursed_date"]
        first_due = (disbursed or requested) + timedelta(days=30)

        schedule = compute_schedule(
            principal=payload["principal"], interest_rate_pct=rate,
            duration_months=duration, first_due_on=first_due,
        )
        status = LoanStatus(payload["status"])
        loan = Loan(
            association_id=association_id, borrower_membership_id=payload["membership_id"],
            loan_type_id=lt["id"] if lt["id"] != "__preview__" else None,
            source_caisse_id=lt["source_caisse_id"], reference=payload["reference"],
            principal=payload["principal"], interest_rate_pct=rate,
            late_fee_pct=lt["late_fee_pct"] or Decimal("0"), duration_months=duration,
            total_interest=schedule.total_interest, total_due=schedule.total_due,
            installment_amount=schedule.installment_amount,
            requested_on=requested, first_due_on=schedule.first_due_on,
            last_due_on=schedule.last_due_on, status=status, purpose=payload["purpose"],
        )
        if payload["status"] in _DISBURSED_STATES or payload["status"] == "approved":
            loan.approved_on = requested
        if payload["status"] in _DISBURSED_STATES:
            loan.disbursed_on = disbursed or requested
        db.add(loan)
        await db.flush()

        for inst in schedule.installments:
            db.add(LoanInstallment(
                loan_id=loan.id, number=inst.number, due_on=inst.due_on,
                principal_part=inst.principal_part, interest_part=inst.interest_part,
                expected_amount=inst.expected_amount, status=LoanInstallmentStatus.PENDING,
            ))

        ctx.setdefault("loan_by_ref", {})[payload["reference"].strip().lower()] = {
            "loan_id": loan.id, "fund_id": lt.get("fund_id"),
        }

        # Décaissement : OUT de la caisse source (rejeu trésorerie).
        if payload["status"] in _DISBURSED_STATES:
            fund = await _fund(db, lt.get("fund_id"))
            if fund is None:
                fund = next((f for f in (await get_or_create_treasury(db, ctx["assoc"])).funds
                             if f.kind == FundKind.GENERAL), None)
            if fund is not None:
                treasury = await get_or_create_treasury(db, ctx["assoc"])
                await post_movement(
                    db, treasury=treasury, direction=MovementDirection.OUT, amount=payload["principal"],
                    allocations=[Allocation(fund=fund, is_credit=False, amount=payload["principal"])],
                    occurred_on=loan.disbursed_on, source_type="import_loan_disbursement",
                    source_id=loan.id, recorded_by_id=None,
                    related_membership_id=payload["membership_id"],
                    description=f"Décaissement prêt {loan.reference} (import)", commit=False, allow_overdraw=True,
                )


# ─────────────────────────────────────────────────────────────────────────────
# Feuille 4 — Remboursements.
# ─────────────────────────────────────────────────────────────────────────────
class LoanRepaymentsSheet(Importer):
    entity = "loan_repayments"
    sheet_key = "loan_repayments"
    label = "Remboursements"
    sheet_title = "Remboursements"

    columns = [
        ImportColumn("loan_reference", "Référence du prêt", required=True, example="PRT-2024-001"),
        ImportColumn("date", "Date", required=True, help="JJ/MM/AAAA.", example="05/03/2024"),
        ImportColumn("amount", "Montant", required=True, example="20000"),
        ImportColumn("notes", "Notes", help="Facultatif."),
    ]

    async def new_ctx(self, db, association_id) -> dict:
        assoc = (await db.execute(select(Association).where(Association.id == association_id))).scalar_one()
        return {"assoc": assoc}

    async def validate_row(self, db, association_id, values, ctx):
        errors: list[str] = []
        lk = ctx.get("loan_by_ref", {}).get((values.get("loan_reference") or "").strip().lower())
        if not values.get("loan_reference"):
            errors.append("Référence du prêt obligatoire.")
        elif lk is None:
            errors.append(f"Prêt introuvable : {values.get('loan_reference')}.")
        amount = _int(values.get("amount"))
        if amount is None or amount <= 0:
            errors.append(f"Montant invalide : {values.get('amount')}.")
        dt = _d(values.get("date"))
        if not dt:
            errors.append("Date obligatoire (JJ/MM/AAAA).")
        if errors:
            return None, errors
        return {"loan": lk, "amount": amount, "date": dt, "notes": values.get("notes")}, []

    async def create_row(self, db, association_id, payload, ctx):
        loan = (await db.execute(select(Loan).where(Loan.id == payload["loan"]["loan_id"]))).scalar_one_or_none()
        if loan is None:
            raise ValueError("Prêt introuvable.")
        installments = (
            await db.execute(
                select(LoanInstallment).where(LoanInstallment.loan_id == loan.id)
                .order_by(LoanInstallment.number)
            )
        ).scalars().all()

        # Ventilation : tour le plus ancien d'abord, intérêt avant capital.
        remaining = payload["amount"]
        paid_principal = paid_interest = 0
        for inst in installments:
            if remaining <= 0:
                break
            due_i = inst.interest_part - inst.paid_interest
            pay_i = min(due_i, remaining)
            inst.paid_interest += pay_i
            remaining -= pay_i
            paid_interest += pay_i
            due_p = inst.principal_part - inst.paid_principal
            pay_p = min(due_p, remaining)
            inst.paid_principal += pay_p
            remaining -= pay_p
            paid_principal += pay_p
            if inst.paid_interest >= inst.interest_part and inst.paid_principal >= inst.principal_part:
                inst.status = LoanInstallmentStatus.PAID
                inst.paid_on = payload["date"]
            elif inst.paid_interest > 0 or inst.paid_principal > 0:
                inst.status = LoanInstallmentStatus.PARTIALLY_PAID

        loan.paid_principal = (loan.paid_principal or 0) + paid_principal
        loan.paid_interest = (loan.paid_interest or 0) + paid_interest
        if loan.status in (LoanStatus.DISBURSED, LoanStatus.APPROVED):
            loan.status = LoanStatus.REPAYING
        if (loan.paid_principal + loan.paid_interest) >= loan.total_due:
            loan.status = LoanStatus.PAID
            loan.closed_on = payload["date"]

        db.add(LoanRepayment(
            loan_id=loan.id, paid_on=payload["date"], total_paid=payload["amount"],
            principal=paid_principal, interest=paid_interest, late_fee=0, notes=payload["notes"],
        ))

        # Rejeu trésorerie : capital → caisse source, intérêt → assurance.
        treasury = await get_or_create_treasury(db, ctx["assoc"])
        principal_fund = await _fund(db, payload["loan"].get("fund_id"))
        if principal_fund is None:
            principal_fund = next((f for f in treasury.funds if f.kind == FundKind.GENERAL), None)
        interest_fund = next((f for f in treasury.funds if f.kind == FundKind.INSURANCE), None)
        allocations = []
        if paid_principal > 0 and principal_fund is not None:
            allocations.append(Allocation(fund=principal_fund, is_credit=True, amount=paid_principal))
        if paid_interest > 0 and interest_fund is not None:
            allocations.append(Allocation(fund=interest_fund, is_credit=True, amount=paid_interest))
        if allocations:
            await post_movement(
                db, treasury=treasury, direction=MovementDirection.IN, amount=payload["amount"],
                allocations=allocations, occurred_on=payload["date"],
                source_type="import_loan_repayment", source_id=loan.id, recorded_by_id=None,
                related_membership_id=loan.borrower_membership_id,
                description=f"Remboursement prêt {loan.reference} (import)", commit=False,
            )


class LoansDomainImporter(DomainImporter):
    entity = "loans_book"
    label = "Prêts (classeur complet)"
    description = (
        "Classeur Prêts : membres, types de prêt, prêts (avec échéancier) et "
        "remboursements."
    )
    sheet_importers = [
        MembersImporter(),
        LoanTypesImporter(),
        LoansSheet(),
        LoanRepaymentsSheet(),
    ]
