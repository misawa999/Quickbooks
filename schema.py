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


# -- Business transactions (customers/vendors/invoices/bills/payments) ------
#
# QuickBooks Desktop caps RefNumber at 11 characters and silently rejects
# longer ones (statusCode 3070) -- see qb_requests.build_journal_entry_add_rq
# for the same limit on journal entries. Invoices/Bills/Payments use
# RefNumber as their human-facing business identifier (that's the whole
# point of referencing them by number), so unlike journal entries there's no
# way to route around the limit -- it's enforced here as a hard validation
# rule instead.
MAX_REF_NUMBER_LEN = 11


def _check_ref_number(value: Optional[str], field_label: str) -> Optional[str]:
    if value is not None and len(value) > MAX_REF_NUMBER_LEN:
        raise ValueError(
            f"{field_label} {value!r} is {len(value)} characters; QuickBooks caps "
            f"RefNumber at {MAX_REF_NUMBER_LEN} characters (statusCode 3070)"
        )
    return value


def _check_currency_pair(currency: Optional[str], exchange_rate: Optional[Decimal], label: str) -> None:
    if currency and exchange_rate is None:
        raise ValueError(f"{label}: currency set but exchange_rate missing")
    if exchange_rate is not None and exchange_rate <= 0:
        raise ValueError(f"{label}: exchange_rate must be > 0")


class Customer(BaseModel):
    name: str
    company_name: Optional[str] = None
    currency: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address_lines: List[str] = []
    memo: Optional[str] = None


class Vendor(BaseModel):
    name: str
    company_name: Optional[str] = None
    currency: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address_lines: List[str] = []
    memo: Optional[str] = None


class InvoiceLine(BaseModel):
    item: str
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    rate: Optional[Decimal] = None
    amount: Decimal

    @model_validator(mode="after")
    def qty_rate_reconciles_with_amount(self) -> "InvoiceLine":
        if self.quantity is not None and self.rate is not None:
            expected = self.quantity * self.rate
            if abs(expected - self.amount) > Decimal("0.01"):
                raise ValueError(
                    f"{self.item}: quantity * rate ({expected}) does not match "
                    f"amount ({self.amount})"
                )
        return self


class Invoice(BaseModel):
    ref_number: str
    customer: str
    date: date_type
    due_date: Optional[date_type] = None
    terms: Optional[str] = None
    currency: Optional[str] = None
    exchange_rate: Optional[Decimal] = None
    ar_account: Optional[str] = None
    memo: Optional[str] = None
    lines: List[InvoiceLine]

    @field_validator("ref_number")
    @classmethod
    def ref_number_length(cls, v: str) -> str:
        return _check_ref_number(v, "invoice_number")

    @field_validator("lines")
    @classmethod
    def min_one_line(cls, v: List[InvoiceLine]) -> List[InvoiceLine]:
        if len(v) < 1:
            raise ValueError("an invoice needs at least 1 line")
        return v

    @model_validator(mode="after")
    def currency_pair(self) -> "Invoice":
        _check_currency_pair(self.currency, self.exchange_rate, self.ref_number)
        return self


class BillLine(BaseModel):
    account: str
    description: Optional[str] = None
    amount: Decimal

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("bill line amount must be > 0")
        return v


class Bill(BaseModel):
    ref_number: str
    vendor: str
    date: date_type
    due_date: Optional[date_type] = None
    currency: Optional[str] = None
    exchange_rate: Optional[Decimal] = None
    ap_account: Optional[str] = None
    memo: Optional[str] = None
    lines: List[BillLine]

    @field_validator("ref_number")
    @classmethod
    def ref_number_length(cls, v: str) -> str:
        return _check_ref_number(v, "bill_number")

    @field_validator("lines")
    @classmethod
    def min_one_line(cls, v: List[BillLine]) -> List[BillLine]:
        if len(v) < 1:
            raise ValueError("a bill needs at least 1 line")
        return v

    @model_validator(mode="after")
    def currency_pair(self) -> "Bill":
        _check_currency_pair(self.currency, self.exchange_rate, self.ref_number)
        return self


class AppliedInvoicePayment(BaseModel):
    invoice_ref: str
    amount: Decimal

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("applied amount must be > 0")
        return v


class CustomerPayment(BaseModel):
    payment_id: str
    customer: str
    date: date_type
    deposit_to_account: str
    ar_account: Optional[str] = None
    currency: Optional[str] = None
    exchange_rate: Optional[Decimal] = None
    payment_method: Optional[str] = None
    ref_number: Optional[str] = None
    memo: Optional[str] = None
    applications: List[AppliedInvoicePayment]

    @field_validator("ref_number")
    @classmethod
    def ref_number_length(cls, v: Optional[str]) -> Optional[str]:
        return _check_ref_number(v, "ref_number")

    @field_validator("applications")
    @classmethod
    def applications_valid(cls, v: List[AppliedInvoicePayment]) -> List[AppliedInvoicePayment]:
        if len(v) < 1:
            raise ValueError("a payment needs at least 1 applied invoice")
        seen = set()
        for a in v:
            if a.invoice_ref in seen:
                raise ValueError(f"duplicate applied invoice_ref within payment: {a.invoice_ref}")
            seen.add(a.invoice_ref)
        return v

    @model_validator(mode="after")
    def currency_pair(self) -> "CustomerPayment":
        _check_currency_pair(self.currency, self.exchange_rate, self.payment_id)
        return self


class AppliedBillPayment(BaseModel):
    bill_ref: str
    amount: Decimal

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("applied amount must be > 0")
        return v


class VendorPayment(BaseModel):
    payment_id: str
    vendor: str
    date: date_type
    bank_account: str
    ap_account: Optional[str] = None
    currency: Optional[str] = None
    exchange_rate: Optional[Decimal] = None
    check_number: Optional[str] = None
    memo: Optional[str] = None
    applications: List[AppliedBillPayment]

    @field_validator("check_number")
    @classmethod
    def check_number_length(cls, v: Optional[str]) -> Optional[str]:
        return _check_ref_number(v, "check_number")

    @field_validator("applications")
    @classmethod
    def applications_valid(cls, v: List[AppliedBillPayment]) -> List[AppliedBillPayment]:
        if len(v) < 1:
            raise ValueError("a payment needs at least 1 applied bill")
        seen = set()
        for a in v:
            if a.bill_ref in seen:
                raise ValueError(f"duplicate applied bill_ref within payment: {a.bill_ref}")
            seen.add(a.bill_ref)
        return v

    @model_validator(mode="after")
    def currency_pair(self) -> "VendorPayment":
        _check_currency_pair(self.currency, self.exchange_rate, self.payment_id)
        return self


class WorkbookBatch(BaseModel):
    customers: List[Customer] = []
    vendors: List[Vendor] = []
    invoices: List[Invoice] = []
    bills: List[Bill] = []
    customer_payments: List[CustomerPayment] = []
    vendor_payments: List[VendorPayment] = []

    @field_validator("customers")
    @classmethod
    def unique_customer_names(cls, v: List[Customer]) -> List[Customer]:
        seen = set()
        for c in v:
            if c.name in seen:
                raise ValueError(f"duplicate customer_name in Customers sheet: {c.name}")
            seen.add(c.name)
        return v

    @field_validator("vendors")
    @classmethod
    def unique_vendor_names(cls, v: List[Vendor]) -> List[Vendor]:
        seen = set()
        for vendor in v:
            if vendor.name in seen:
                raise ValueError(f"duplicate vendor_name in Vendors sheet: {vendor.name}")
            seen.add(vendor.name)
        return v

    @field_validator("invoices")
    @classmethod
    def unique_invoice_refs(cls, v: List[Invoice]) -> List[Invoice]:
        seen = set()
        for inv in v:
            key = (inv.customer, inv.ref_number)
            if key in seen:
                raise ValueError(f"duplicate invoice_number for customer {inv.customer}: {inv.ref_number}")
            seen.add(key)
        return v

    @field_validator("bills")
    @classmethod
    def unique_bill_refs(cls, v: List[Bill]) -> List[Bill]:
        seen = set()
        for b in v:
            key = (b.vendor, b.ref_number)
            if key in seen:
                raise ValueError(f"duplicate bill_number for vendor {b.vendor}: {b.ref_number}")
            seen.add(key)
        return v

    @field_validator("customer_payments")
    @classmethod
    def unique_customer_payment_ids(cls, v: List[CustomerPayment]) -> List[CustomerPayment]:
        seen = set()
        for p in v:
            if p.payment_id in seen:
                raise ValueError(f"duplicate payment_id in CustomerPayments sheet: {p.payment_id}")
            seen.add(p.payment_id)
        return v

    @field_validator("vendor_payments")
    @classmethod
    def unique_vendor_payment_ids(cls, v: List[VendorPayment]) -> List[VendorPayment]:
        seen = set()
        for p in v:
            if p.payment_id in seen:
                raise ValueError(f"duplicate payment_id in VendorPayments sheet: {p.payment_id}")
            seen.add(p.payment_id)
        return v

    @model_validator(mode="after")
    def customer_and_vendor_currency_consistent(self) -> "WorkbookBatch":
        # Soft cross-sheet check: a customer/vendor's currency is fixed for
        # its lifetime in QuickBooks multicurrency, so every invoice/bill
        # against it (when both the master record and the transaction set a
        # currency) must agree, or QuickBooks itself will reject the Add.
        customer_currency = {c.name: c.currency for c in self.customers if c.currency}
        for inv in self.invoices:
            expected = customer_currency.get(inv.customer)
            if expected and inv.currency and inv.currency != expected:
                raise ValueError(
                    f"invoice {inv.ref_number}: currency {inv.currency!r} does not match "
                    f"customer {inv.customer!r}'s currency {expected!r}"
                )
        vendor_currency = {v.name: v.currency for v in self.vendors if v.currency}
        for bill in self.bills:
            expected = vendor_currency.get(bill.vendor)
            if expected and bill.currency and bill.currency != expected:
                raise ValueError(
                    f"bill {bill.ref_number}: currency {bill.currency!r} does not match "
                    f"vendor {bill.vendor!r}'s currency {expected!r}"
                )
        return self
