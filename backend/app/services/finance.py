"""FinanceService — the single place that mutates treasury balances.

Every money operation goes through `post_movement`, which:
  1. creates one TreasuryMovement (amount always positive, direction gives sign),
  2. creates N LedgerEntry rows allocating it across funds,
  3. updates each Fund.balance and the Treasury.balance,

keeping the invariant  Σ Fund.balance == Treasury.balance.

Other modules (tontine payout, loan disbursement, meeting close…) should call
`post_movement` rather than touching balances directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.association import Association
from app.models.finance import (
    Fund,
    FundKind,
    LedgerEntry,
    MovementDirection,
    Treasury,
    TreasuryMovement,
)

# Default funds provisioned for every association treasury.
_DEFAULT_FUNDS = [
    (FundKind.GENERAL, "Fonds général"),
    (FundKind.TONTINE, "Fonds tontine"),
    (FundKind.INSURANCE, "Caisse sociale"),
    (FundKind.SAVINGS, "Épargne"),
]


@dataclass
class Allocation:
    """One ledger line: credit or debit a fund by `amount` (always positive)."""

    fund: Fund
    is_credit: bool
    amount: int


async def get_or_create_treasury(db: AsyncSession, association: Association) -> Treasury:
    """Return the association's treasury, creating it (+ default funds) if absent."""
    res = await db.execute(
        select(Treasury)
        .options(selectinload(Treasury.funds))
        .where(Treasury.association_id == association.id)
    )
    treasury = res.scalar_one_or_none()
    if treasury:
        return treasury

    treasury = Treasury(
        association_id=association.id,
        balance=0,
        currency=association.currency or "XAF",
    )
    db.add(treasury)
    await db.flush()

    for kind, name in _DEFAULT_FUNDS:
        db.add(
            Fund(
                treasury_id=treasury.id,
                kind=kind,
                ref_key="",
                name=name,
                balance=0,
                is_system=True,
            )
        )
    await db.commit()

    res = await db.execute(
        select(Treasury)
        .options(selectinload(Treasury.funds))
        .where(Treasury.id == treasury.id)
    )
    return res.scalar_one()


async def post_movement(
    db: AsyncSession,
    *,
    treasury: Treasury,
    direction: MovementDirection,
    amount: int,
    allocations: List[Allocation],
    occurred_on: date,
    source_type: str,
    source_id: Optional[UUID] = None,
    recorded_by_id: Optional[UUID] = None,
    related_membership_id: Optional[UUID] = None,
    description: Optional[str] = None,
    commit: bool = True,
) -> TreasuryMovement:
    """Post a balanced movement.

    `commit=True` (default) commits the transaction. Pass `commit=False` to
    batch several movements (e.g. meeting close) and let the caller commit once.

    Validation:
      IN   → every allocation is a CREDIT, Σ == amount, treasury += amount
      OUT  → every allocation is a DEBIT,  Σ == amount, treasury -= amount
      XFER → exactly one DEBIT + one CREDIT of equal `amount`, treasury unchanged
    """
    if amount <= 0:
        raise HTTPException(422, "Le montant doit être positif")
    if treasury.is_locked:
        raise HTTPException(409, "La caisse est verrouillée")

    credits = [a for a in allocations if a.is_credit]
    debits = [a for a in allocations if not a.is_credit]

    if direction == MovementDirection.IN:
        if debits or sum(a.amount for a in credits) != amount:
            raise HTTPException(422, "Ventilation IN invalide")
    elif direction == MovementDirection.OUT:
        if credits or sum(a.amount for a in debits) != amount:
            raise HTTPException(422, "Ventilation OUT invalide")
    else:  # XFER
        if len(credits) != 1 or len(debits) != 1 or credits[0].amount != amount or debits[0].amount != amount:
            raise HTTPException(422, "Un transfert doit débiter un fonds et en créditer un autre")
        if credits[0].fund.id == debits[0].fund.id:
            raise HTTPException(422, "Les fonds source et destination doivent différer")

    # Guard against overdrawing a fund.
    for a in debits:
        if a.fund.balance < a.amount:
            raise HTTPException(
                409, f"Solde insuffisant du fonds « {a.fund.name} »"
            )

    delta = amount if direction == MovementDirection.IN else (-amount if direction == MovementDirection.OUT else 0)
    new_treasury_balance = treasury.balance + delta

    movement = TreasuryMovement(
        treasury_id=treasury.id,
        direction=direction,
        amount=amount,
        balance_after=new_treasury_balance,
        occurred_on=occurred_on,
        source_type=source_type,
        source_id=source_id,
        recorded_by_id=recorded_by_id,
        related_membership_id=related_membership_id,
        description=description,
    )
    db.add(movement)
    await db.flush()

    for a in allocations:
        a.fund.balance += a.amount if a.is_credit else -a.amount
        db.add(
            LedgerEntry(
                movement_id=movement.id,
                fund_id=a.fund.id,
                is_credit=a.is_credit,
                amount=a.amount,
                fund_balance_after=a.fund.balance,
                description=description,
            )
        )

    treasury.balance = new_treasury_balance
    if commit:
        await db.commit()
        await db.refresh(movement)
    else:
        await db.flush()
    return movement


async def void_movement(
    db: AsyncSession,
    *,
    treasury: Treasury,
    movement: TreasuryMovement,
    reason: str,
) -> TreasuryMovement:
    """Reverse a movement's effect on balances and flag it voided."""
    if movement.is_voided:
        raise HTTPException(409, "Mouvement déjà annulé")

    res = await db.execute(
        select(LedgerEntry).where(LedgerEntry.movement_id == movement.id)
    )
    entries = res.scalars().all()

    fund_cache: dict[UUID, Fund] = {f.id: f for f in treasury.funds}
    for e in entries:
        fund = fund_cache.get(e.fund_id)
        if fund is None:
            fres = await db.execute(select(Fund).where(Fund.id == e.fund_id))
            fund = fres.scalar_one()
        # Reverse: a CREDIT added → now subtract; a DEBIT removed → now add back.
        fund.balance += -e.amount if e.is_credit else e.amount

    if movement.direction == MovementDirection.IN:
        treasury.balance -= movement.amount
    elif movement.direction == MovementDirection.OUT:
        treasury.balance += movement.amount

    movement.is_voided = True
    movement.voided_at = datetime.now(timezone.utc)
    movement.voided_reason = reason
    await db.commit()
    await db.refresh(movement)
    return movement
