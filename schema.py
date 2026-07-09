"""Pydantic models for the general journal entry batch format."""
from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, field_validator, model_validator


class JournalLine(BaseModel):
    account: str
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    memo: Optional[str] = None
    name: Optional[str] = None  # customer/vendor/employee/other name on the line

    @model_validator(mode="after")
    def one_side_only(self) -> "JournalLine":
        if self.debit < 0 or self.credit < 0:
            raise ValueError(f"{self.account}: debit/credit must not be negative")
        if (self.debit > 0) == (self.credit > 0):
            raise ValueError(
                f"{self.account}: exactly one of debit or credit must be > 0 "
                f"(got debit={self.debit}, credit={self.credit})"
            )
        return self


class JournalEntry(BaseModel):
    line_id: str
    date: date_type
    memo: Optional[str] = None
    currency: Optional[str] = None
    exchange_rate: Optional[Decimal] = None
    lines: List[JournalLine]

    @field_validator("lines")
    @classmethod
    def min_two_lines(cls, v: List[JournalLine]) -> List[JournalLine]:
        if len(v) < 2:
            raise ValueError("a journal entry needs at least 2 lines")
        return v

    @model_validator(mode="after")
    def balanced(self) -> "JournalEntry":
        total_debit = sum((l.debit for l in self.lines), Decimal("0"))
        total_credit = sum((l.credit for l in self.lines), Decimal("0"))
        if abs(total_debit - total_credit) > Decimal("0.01"):
            raise ValueError(
                f"{self.line_id}: unbalanced entry (debit={total_debit}, credit={total_credit})"
            )
        if self.currency and self.exchange_rate is None:
            raise ValueError(f"{self.line_id}: currency set but exchange_rate missing")
        if self.exchange_rate is not None and self.exchange_rate <= 0:
            raise ValueError(f"{self.line_id}: exchange_rate must be > 0")
        return self


class Batch(BaseModel):
    batch_id: str
    generated_at: Optional[str] = None
    transactions: List[JournalEntry]

    @field_validator("transactions")
    @classmethod
    def unique_line_ids_and_nonempty(cls, v: List[JournalEntry]) -> List[JournalEntry]:
        if not v:
            raise ValueError("batch has no transactions")
        seen = set()
        for t in v:
            if t.line_id in seen:
                raise ValueError(f"duplicate line_id within batch: {t.line_id}")
            seen.add(t.line_id)
        return v
