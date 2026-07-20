import pytest
from pydantic import ValidationError

from schema import (
    AppliedBillPayment,
    AppliedInvoicePayment,
    Bill,
    BillLine,
    Customer,
    CustomerPayment,
    Invoice,
    InvoiceLine,
    Vendor,
    VendorPayment,
    WorkbookBatch,
)


def make_invoice(**overrides):
    base = {
        "ref_number": "INV-1001",
        "customer": "Acme Corp",
        "date": "2026-07-01",
        "lines": [{"item": "Consulting", "amount": 1500}],
    }
    base.update(overrides)
    return base


def make_bill(**overrides):
    base = {
        "ref_number": "B-100",
        "vendor": "Acme Supplier",
        "date": "2026-07-01",
        "lines": [{"account": "Office Supplies", "amount": 250}],
    }
    base.update(overrides)
    return base


def make_customer_payment(**overrides):
    base = {
        "payment_id": "p1",
        "customer": "Acme Corp",
        "date": "2026-07-15",
        "deposit_to_account": "Undeposited Funds",
        "applications": [{"invoice_ref": "INV-1001", "amount": 1500}],
    }
    base.update(overrides)
    return base


def make_vendor_payment(**overrides):
    base = {
        "payment_id": "vp1",
        "vendor": "Acme Supplier",
        "date": "2026-07-15",
        "bank_account": "OCBC Bank (USD)",
        "applications": [{"bill_ref": "B-100", "amount": 250}],
    }
    base.update(overrides)
    return base


# -- Customer / Vendor -------------------------------------------------

def test_valid_customer():
    c = Customer.model_validate({"name": "Acme Corp", "currency": "USD"})
    assert c.name == "Acme Corp"


def test_valid_vendor():
    v = Vendor.model_validate({"name": "Acme Supplier"})
    assert v.currency is None


# -- InvoiceLine qty*rate reconciliation --------------------------------

def test_invoice_line_qty_rate_reconciles():
    line = InvoiceLine.model_validate({"item": "Consulting", "quantity": 10, "rate": 150, "amount": 1500})
    assert line.amount == 1500


def test_invoice_line_qty_rate_mismatch_rejected():
    with pytest.raises(ValidationError):
        InvoiceLine.model_validate({"item": "Consulting", "quantity": 10, "rate": 150, "amount": 999})


def test_invoice_line_amount_only_is_fine():
    line = InvoiceLine.model_validate({"item": "Product A", "amount": 200})
    assert line.quantity is None


# -- Invoice --------------------------------------------------------------

def test_valid_invoice():
    inv = Invoice.model_validate(make_invoice())
    assert inv.ref_number == "INV-1001"


def test_invoice_ref_number_too_long_rejected():
    with pytest.raises(ValidationError):
        Invoice.model_validate(make_invoice(ref_number="INVOICE-NUMBER-TOO-LONG"))


def test_invoice_currency_without_rate_rejected():
    with pytest.raises(ValidationError):
        Invoice.model_validate(make_invoice(currency="CHF"))


def test_invoice_multicurrency_valid():
    inv = Invoice.model_validate(make_invoice(currency="CHF", exchange_rate=1.0962))
    assert inv.currency == "CHF"


def test_invoice_needs_at_least_one_line():
    with pytest.raises(ValidationError):
        Invoice.model_validate(make_invoice(lines=[]))


# -- Bill -------------------------------------------------------------------

def test_valid_bill():
    bill = Bill.model_validate(make_bill())
    assert bill.ref_number == "B-100"


def test_bill_ref_number_too_long_rejected():
    with pytest.raises(ValidationError):
        Bill.model_validate(make_bill(ref_number="BILL-NUMBER-TOO-LONG"))


def test_bill_line_amount_must_be_positive():
    with pytest.raises(ValidationError):
        Bill.model_validate(make_bill(lines=[{"account": "Office Supplies", "amount": 0}]))


def test_bill_needs_at_least_one_line():
    with pytest.raises(ValidationError):
        Bill.model_validate(make_bill(lines=[]))


# -- CustomerPayment / VendorPayment --------------------------------------

def test_valid_customer_payment():
    p = CustomerPayment.model_validate(make_customer_payment())
    assert p.applications[0].invoice_ref == "INV-1001"


def test_customer_payment_needs_at_least_one_application():
    with pytest.raises(ValidationError):
        CustomerPayment.model_validate(make_customer_payment(applications=[]))


def test_customer_payment_duplicate_invoice_ref_rejected():
    with pytest.raises(ValidationError):
        CustomerPayment.model_validate(
            make_customer_payment(
                applications=[
                    {"invoice_ref": "INV-1001", "amount": 500},
                    {"invoice_ref": "INV-1001", "amount": 1000},
                ]
            )
        )


def test_customer_payment_ref_number_too_long_rejected():
    with pytest.raises(ValidationError):
        CustomerPayment.model_validate(make_customer_payment(ref_number="WAY-TOO-LONG-REF"))


def test_customer_payment_currency_requires_rate():
    with pytest.raises(ValidationError):
        CustomerPayment.model_validate(make_customer_payment(currency="CHF"))


def test_valid_vendor_payment():
    p = VendorPayment.model_validate(make_vendor_payment())
    assert p.applications[0].bill_ref == "B-100"


def test_vendor_payment_check_number_too_long_rejected():
    with pytest.raises(ValidationError):
        VendorPayment.model_validate(make_vendor_payment(check_number="TOOLONGCHECKNUMBER"))


def test_vendor_payment_duplicate_bill_ref_rejected():
    with pytest.raises(ValidationError):
        VendorPayment.model_validate(
            make_vendor_payment(
                applications=[
                    {"bill_ref": "B-100", "amount": 100},
                    {"bill_ref": "B-100", "amount": 150},
                ]
            )
        )


def test_applied_amount_must_be_positive():
    with pytest.raises(ValidationError):
        AppliedInvoicePayment.model_validate({"invoice_ref": "INV-1001", "amount": 0})
    with pytest.raises(ValidationError):
        AppliedBillPayment.model_validate({"bill_ref": "B-100", "amount": -5})


# -- WorkbookBatch ----------------------------------------------------------

def test_workbook_batch_can_be_empty():
    wb = WorkbookBatch.model_validate({})
    assert wb.customers == []
    assert wb.invoices == []


def test_workbook_batch_duplicate_customer_name_rejected():
    with pytest.raises(ValidationError):
        WorkbookBatch.model_validate(
            {"customers": [{"name": "Acme Corp"}, {"name": "Acme Corp"}]}
        )


def test_workbook_batch_duplicate_invoice_ref_per_customer_rejected():
    with pytest.raises(ValidationError):
        WorkbookBatch.model_validate({"invoices": [make_invoice(), make_invoice()]})


def test_workbook_batch_same_invoice_ref_different_customer_ok():
    wb = WorkbookBatch.model_validate(
        {
            "invoices": [
                make_invoice(customer="Acme Corp"),
                make_invoice(customer="Other Corp"),
            ]
        }
    )
    assert len(wb.invoices) == 2


def test_workbook_batch_duplicate_bill_ref_per_vendor_rejected():
    with pytest.raises(ValidationError):
        WorkbookBatch.model_validate({"bills": [make_bill(), make_bill()]})


def test_workbook_batch_duplicate_payment_id_rejected():
    with pytest.raises(ValidationError):
        WorkbookBatch.model_validate(
            {"customer_payments": [make_customer_payment(), make_customer_payment()]}
        )
    with pytest.raises(ValidationError):
        WorkbookBatch.model_validate(
            {"vendor_payments": [make_vendor_payment(), make_vendor_payment()]}
        )


def test_workbook_batch_invoice_currency_must_match_customer_currency():
    with pytest.raises(ValidationError):
        WorkbookBatch.model_validate(
            {
                "customers": [{"name": "Acme Corp", "currency": "USD"}],
                "invoices": [make_invoice(currency="CHF", exchange_rate=1.1)],
            }
        )


def test_workbook_batch_invoice_currency_matching_customer_currency_ok():
    wb = WorkbookBatch.model_validate(
        {
            "customers": [{"name": "Acme Corp", "currency": "CHF"}],
            "invoices": [make_invoice(currency="CHF", exchange_rate=1.1)],
        }
    )
    assert wb.invoices[0].currency == "CHF"
