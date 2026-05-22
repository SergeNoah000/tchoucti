"""Pydantic schemas for the loans module."""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LoanCreate(BaseModel):
    association_id: UUID
    borrower_membership_id: UUID
    principal: int = Field(..., gt=0)
    duration_months: int = Field(..., ge=1, le=120)
    interest_rate_pct: Decimal = Field(..., ge=0, le=100)   # monthly
    late_fee_pct: Decimal = Field(Decimal("0"), ge=0, le=100)
    purpose: Optional[str] = Field(None, max_length=500)


class LoanApprove(BaseModel):
    # Optional first due date — defaults to approval date + 30 days.
    first_due_on: Optional[date] = None


class LoanReject(BaseModel):
    reason: str = Field(..., min_length=2, max_length=1000)


class LoanRepay(BaseModel):
    amount: int = Field(..., gt=0)
    paid_on: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=500)


class InstallmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    number: int
    due_on: date
    principal_part: int
    interest_part: int
    expected_amount: int
    paid_principal: int
    paid_interest: int
    paid_late_fee: int
    paid_on: Optional[date]
    status: str


class RepaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paid_on: date
    total_paid: int
    principal: int
    interest: int
    late_fee: int
    movement_id: Optional[UUID]


class LoanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    association_id: UUID
    borrower_membership_id: UUID
    borrower_name: Optional[str] = None
    reference: str
    principal: int
    interest_rate_pct: Decimal
    late_fee_pct: Decimal
    duration_months: int
    total_interest: int
    total_due: int
    installment_amount: int
    paid_principal: int
    paid_interest: int
    paid_late_fees: int
    remaining_balance: int
    requested_on: date
    approved_on: Optional[date]
    disbursed_on: Optional[date]
    first_due_on: Optional[date]
    last_due_on: Optional[date]
    status: str
    purpose: Optional[str]
    created_at: datetime


class LoanDetail(LoanOut):
    installments: List[InstallmentOut] = []
    repayments: List[RepaymentOut] = []
