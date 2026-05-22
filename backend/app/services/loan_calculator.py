"""Loan schedule calculator — simple monthly interest.

  total_interest = principal × rate_pct/100 × n
  total_due      = principal + total_interest
  installment    = ceil(total_due / n)
  per installment: interest_part = ceil(principal × rate_pct/100)
                   principal_part = installment − interest_part
  The last installment absorbs rounding so Σ == total_due.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import List


@dataclass
class ScheduledInstallment:
    number: int
    due_on: date
    principal_part: int
    interest_part: int
    expected_amount: int


@dataclass
class LoanSchedule:
    total_interest: int
    total_due: int
    installment_amount: int
    installments: List[ScheduledInstallment]

    @property
    def first_due_on(self) -> date:
        return self.installments[0].due_on

    @property
    def last_due_on(self) -> date:
        return self.installments[-1].due_on


def compute_schedule(
    *,
    principal: int,
    interest_rate_pct: Decimal | float | str,
    duration_months: int,
    first_due_on: date,
) -> LoanSchedule:
    """Build the full amortisation schedule. Due dates are spaced 30 days apart."""
    if principal <= 0:
        raise ValueError("principal must be positive")
    if duration_months <= 0:
        raise ValueError("duration_months must be positive")

    rate = Decimal(str(interest_rate_pct)) / Decimal(100)
    n = duration_months

    total_interest = int(
        (Decimal(principal) * rate * Decimal(n)).to_integral_value(rounding=ROUND_HALF_UP)
    )
    total_due = principal + total_interest
    installment_amount = math.ceil(total_due / n)
    interest_per = int((Decimal(principal) * rate).to_integral_value(rounding=ROUND_HALF_UP))

    installments: List[ScheduledInstallment] = []
    remaining_principal = principal
    remaining_total = total_due

    for i in range(1, n + 1):
        due_on = first_due_on + timedelta(days=30 * (i - 1))
        if i < n:
            amount = installment_amount
            interest_part = min(interest_per, amount)
            principal_part = amount - interest_part
        else:
            # Last installment absorbs all rounding residue.
            amount = remaining_total
            principal_part = remaining_principal
            interest_part = amount - principal_part
        installments.append(
            ScheduledInstallment(
                number=i,
                due_on=due_on,
                principal_part=principal_part,
                interest_part=interest_part,
                expected_amount=amount,
            )
        )
        remaining_principal -= principal_part
        remaining_total -= amount

    return LoanSchedule(
        total_interest=total_interest,
        total_due=total_due,
        installment_amount=installment_amount,
        installments=installments,
    )
