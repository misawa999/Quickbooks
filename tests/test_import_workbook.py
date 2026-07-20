import pytest

import import_workbook
from import_workbook import (
    group_tidy_rows,
    print_workbook_dry_run_report,
    run_workbook_commit,
)
from schema import WorkbookBatch


# -- group_tidy_rows ----------------------------------------------------

def test_group_tidy_rows_groups_lines_under_shared_header():
    rows = [
        {"invoice_number": "INV-1", "customer_name": "Acme Corp", "item_name": "Consulting", "amount": 1500},
        {"invoice_number": "INV-1", "customer_name": "Acme Corp", "item_name": "Product A", "amount": 200},
    ]
    groups = group_tidy_rows(
        rows, "invoice_number", header_cols=["customer_name"], line_cols=["item_name", "amount"]
    )
    assert len(groups) == 1
    assert groups[0]["key"] == "INV-1"
    assert groups[0]["header"] == {"customer_name": "Acme Corp"}
    assert len(groups[0]["lines"]) == 2


def test_group_tidy_rows_raises_on_inconsistent_header_within_group():
    rows = [
        {"invoice_number": "INV-1", "customer_name": "Acme Corp", "item_name": "Consulting", "amount": 1500},
        {"invoice_number": "INV-1", "customer_name": "Other Corp", "item_name": "Product A", "amount": 200},
    ]
    with pytest.raises(ValueError, match="INV-1"):
        group_tidy_rows(rows, "invoice_number", header_cols=["customer_name"], line_cols=["item_name", "amount"])


def test_group_tidy_rows_raises_on_missing_key():
    rows = [{"invoice_number": None, "customer_name": "Acme Corp"}]
    with pytest.raises(ValueError):
        group_tidy_rows(rows, "invoice_number", header_cols=["customer_name"], line_cols=[])


def test_group_tidy_rows_preserves_order_across_distinct_keys():
    rows = [
        {"invoice_number": "INV-2", "item_name": "X", "amount": 1},
        {"invoice_number": "INV-1", "item_name": "Y", "amount": 2},
    ]
    groups = group_tidy_rows(rows, "invoice_number", header_cols=[], line_cols=["item_name", "amount"])
    assert [g["key"] for g in groups] == ["INV-2", "INV-1"]


# -- print_workbook_dry_run_report (the seam gui.py depends on) --------

def make_workbook():
    return WorkbookBatch.model_validate(
        {
            "customers": [{"name": "Acme Corp"}],
            "vendors": [{"name": "Acme Supplier"}],
            "invoices": [
                {
                    "ref_number": "INV-1001",
                    "customer": "Acme Corp",
                    "date": "2026-07-01",
                    "lines": [{"item": "Consulting", "amount": 1500}],
                }
            ],
            "bills": [
                {
                    "ref_number": "B-100",
                    "vendor": "Acme Supplier",
                    "date": "2026-07-01",
                    "lines": [{"account": "Office Supplies", "amount": 250}],
                }
            ],
            "customer_payments": [
                {
                    "payment_id": "p1",
                    "customer": "Acme Corp",
                    "date": "2026-07-15",
                    "deposit_to_account": "Undeposited Funds",
                    "applications": [{"invoice_ref": "INV-1001", "amount": 1500}],
                }
            ],
            "vendor_payments": [],
        }
    )


def test_print_workbook_dry_run_report_uses_custom_emit_not_stdout():
    lines = []
    print_workbook_dry_run_report(
        make_workbook(), skip_ids=set(), missing_account_names=[], missing_item_names=[],
        existing_customers=set(), existing_vendors=set(),
        invoice_resolution={}, bill_resolution={}, emit=lines.append,
    )
    text = "\n".join(lines)
    assert "Acme Corp" in text
    assert "INV-1001" in text
    assert "Office Supplies" in text
    assert "not checked - QuickBooks unreachable" in text


def test_print_workbook_dry_run_report_shows_preflight_failures():
    lines = []
    print_workbook_dry_run_report(
        make_workbook(), skip_ids=set(), missing_account_names=["Ghost Account"], missing_item_names=["Ghost Item"],
        existing_customers=set(), existing_vendors=set(),
        invoice_resolution={}, bill_resolution={}, emit=lines.append,
    )
    text = "\n".join(lines)
    assert "PREFLIGHT FAILED - accounts not found" in text
    assert "Ghost Account" in text
    assert "PREFLIGHT FAILED - items not found" in text
    assert "Ghost Item" in text


def test_print_workbook_dry_run_report_flags_existing_and_duplicate():
    lines = []
    print_workbook_dry_run_report(
        make_workbook(), skip_ids={"inv-Acme Corp-INV-1001"}, missing_account_names=[], missing_item_names=[],
        existing_customers={"Acme Corp"}, existing_vendors=set(),
        invoice_resolution={("Acme Corp", "INV-1001"): "80000012-1234567890"}, bill_resolution={},
        emit=lines.append,
    )
    text = "\n".join(lines)
    assert "ALREADY EXISTS IN QB" in text
    assert "DUPLICATE - already imported" in text
    assert "TxnID 80000012-1234567890" in text


# -- run_workbook_commit against a fake session --------------------------

ACCOUNT_QUERY_OK = """<?xml version="1.0"?>
<QBXML><QBXMLMsgsRs><AccountQueryRs>
  <AccountRet><FullName>Office Supplies</FullName></AccountRet>
  <AccountRet><FullName>Undeposited Funds</FullName></AccountRet>
  <AccountRet><FullName>Bank Account</FullName></AccountRet>
</AccountQueryRs></QBXMLMsgsRs></QBXML>"""

ITEM_QUERY_OK = """<?xml version="1.0"?>
<QBXML><QBXMLMsgsRs><ItemQueryRs>
  <ItemServiceRet><FullName>Consulting</FullName></ItemServiceRet>
</ItemQueryRs></QBXMLMsgsRs></QBXML>"""

CUSTOMER_QUERY_NONE_EXIST = """<?xml version="1.0"?>
<QBXML><QBXMLMsgsRs><CustomerQueryRs></CustomerQueryRs></QBXMLMsgsRs></QBXML>"""

VENDOR_QUERY_ALREADY_EXISTS = """<?xml version="1.0"?>
<QBXML><QBXMLMsgsRs><VendorQueryRs>
  <VendorRet><FullName>Acme Supplier</FullName></VendorRet>
</VendorQueryRs></QBXMLMsgsRs></QBXML>"""

CUSTOMER_ADD_OK = """<?xml version="1.0"?>
<QBXML><QBXMLMsgsRs><CustomerAddRs statusCode="0" statusMessage="Status OK">
  <CustomerRet><ListID>800000-1</ListID><Name>Acme Corp</Name></CustomerRet>
</CustomerAddRs></QBXMLMsgsRs></QBXML>"""

INVOICE_ADD_OK = """<?xml version="1.0"?>
<QBXML><QBXMLMsgsRs><InvoiceAddRs statusCode="0" statusMessage="Status OK">
  <InvoiceRet><TxnID>INV-TXN-1</TxnID></InvoiceRet>
</InvoiceAddRs></QBXMLMsgsRs></QBXML>"""

BILL_ADD_OK = """<?xml version="1.0"?>
<QBXML><QBXMLMsgsRs><BillAddRs statusCode="0" statusMessage="Status OK">
  <BillRet><TxnID>BILL-TXN-1</TxnID></BillRet>
</BillAddRs></QBXMLMsgsRs></QBXML>"""

INVOICE_QUERY_MATCH = """<?xml version="1.0"?>
<QBXML><QBXMLMsgsRs><InvoiceQueryRs>
  <InvoiceRet><TxnID>INV-TXN-1</TxnID><RefNumber>INV-1001</RefNumber>
    <CustomerRef><FullName>Acme Corp</FullName></CustomerRef></InvoiceRet>
</InvoiceQueryRs></QBXMLMsgsRs></QBXML>"""

BILL_QUERY_MATCH = """<?xml version="1.0"?>
<QBXML><QBXMLMsgsRs><BillQueryRs>
  <BillRet><TxnID>BILL-TXN-1</TxnID><RefNumber>B-100</RefNumber>
    <VendorRef><FullName>Acme Supplier</FullName></VendorRef></BillRet>
</BillQueryRs></QBXMLMsgsRs></QBXML>"""

RECEIVE_PAYMENT_ADD_OK = """<?xml version="1.0"?>
<QBXML><QBXMLMsgsRs><ReceivePaymentAddRs statusCode="0" statusMessage="Status OK">
  <ReceivePaymentRet><TxnID>PMT-TXN-1</TxnID></ReceivePaymentRet>
</ReceivePaymentAddRs></QBXMLMsgsRs></QBXML>"""

BILL_PAYMENT_ADD_OK = """<?xml version="1.0"?>
<QBXML><QBXMLMsgsRs><BillPaymentCheckAddRs statusCode="0" statusMessage="Status OK">
  <BillPaymentCheckRet><TxnID>BPC-TXN-1</TxnID></BillPaymentCheckRet>
</BillPaymentCheckAddRs></QBXMLMsgsRs></QBXML>"""


class FakeSession:
    def __init__(self):
        self.calls = []

    def process(self, request_xml: str) -> str:
        self.calls.append(request_xml)
        dispatch = [
            ("<AccountQueryRq>", ACCOUNT_QUERY_OK),
            ("<ItemQueryRq>", ITEM_QUERY_OK),
            ("<CustomerQueryRq>", CUSTOMER_QUERY_NONE_EXIST),
            ("<VendorQueryRq>", VENDOR_QUERY_ALREADY_EXISTS),
            ("<CustomerAddRq>", CUSTOMER_ADD_OK),
            ("<InvoiceAddRq>", INVOICE_ADD_OK),
            ("<BillAddRq>", BILL_ADD_OK),
            ("<InvoiceQueryRq>", INVOICE_QUERY_MATCH),
            ("<BillQueryRq>", BILL_QUERY_MATCH),
            ("<ReceivePaymentAddRq>", RECEIVE_PAYMENT_ADD_OK),
            ("<BillPaymentCheckAddRq>", BILL_PAYMENT_ADD_OK),
        ]
        for tag, response in dispatch:
            if tag in request_xml:
                return response
        raise AssertionError(f"unexpected request (no fake handler): {request_xml}")


class FakeQBSessionContext:
    def __init__(self, fake_session: FakeSession):
        self._fake = fake_session

    def __enter__(self):
        return self._fake

    def __exit__(self, exc_type, exc, tb):
        return False


def full_workbook():
    return WorkbookBatch.model_validate(
        {
            "customers": [{"name": "Acme Corp"}],
            "vendors": [{"name": "Acme Supplier"}],
            "invoices": [
                {
                    "ref_number": "INV-1001",
                    "customer": "Acme Corp",
                    "date": "2026-07-01",
                    "lines": [{"item": "Consulting", "amount": 1500}],
                }
            ],
            "bills": [
                {
                    "ref_number": "B-100",
                    "vendor": "Acme Supplier",
                    "date": "2026-07-01",
                    "lines": [{"account": "Office Supplies", "amount": 250}],
                }
            ],
            "customer_payments": [
                {
                    "payment_id": "p1",
                    "customer": "Acme Corp",
                    "date": "2026-07-15",
                    "deposit_to_account": "Undeposited Funds",
                    "applications": [{"invoice_ref": "INV-1001", "amount": 1500}],
                }
            ],
            "vendor_payments": [
                {
                    "payment_id": "vp1",
                    "vendor": "Acme Supplier",
                    "date": "2026-07-15",
                    "bank_account": "Bank Account",
                    "applications": [{"bill_ref": "B-100", "amount": 250}],
                }
            ],
        }
    )


def test_run_workbook_commit_full_pipeline_ordering_and_tallies(tmp_path, monkeypatch):
    fake_session = FakeSession()
    monkeypatch.setattr(
        import_workbook, "QBSession", lambda company_file="": FakeQBSessionContext(fake_session)
    )

    lines = []
    result_code = run_workbook_commit(
        full_workbook(),
        company_file="",
        log_path=tmp_path / "log.jsonl",
        skip_ids=set(),
        force=False,
        continue_on_error=False,
        emit=lines.append,
    )

    assert result_code == 0
    text = "\n".join(lines)
    assert "customer: inserted=1 skipped=0 failed=0" in text
    assert "vendor: inserted=0 skipped=1 failed=0" in text  # already exists in QB
    assert "invoice: inserted=1 skipped=0 failed=0" in text
    assert "bill: inserted=1 skipped=0 failed=0" in text
    assert "customer_payment: inserted=1 skipped=0 failed=0" in text
    assert "vendor_payment: inserted=1 skipped=0 failed=0" in text

    log_text = (tmp_path / "log.jsonl").read_text()
    assert '"entity_type": "customer"' in log_text
    assert '"entity_type": "customer_payment"' in log_text
    assert '"line_id": "pmt-p1"' in log_text


def test_run_workbook_commit_skips_already_imported_via_skip_ids(tmp_path, monkeypatch):
    fake_session = FakeSession()
    monkeypatch.setattr(
        import_workbook, "QBSession", lambda company_file="": FakeQBSessionContext(fake_session)
    )

    lines = []
    result_code = run_workbook_commit(
        full_workbook(),
        company_file="",
        log_path=tmp_path / "log.jsonl",
        skip_ids={"cust-Acme Corp", "inv-Acme Corp-INV-1001", "bill-Acme Supplier-B-100", "pmt-p1", "vpmt-vp1"},
        force=False,
        continue_on_error=False,
        emit=lines.append,
    )

    assert result_code == 0
    text = "\n".join(lines)
    assert "customer: inserted=0 skipped=1 failed=0" in text
    assert "invoice: inserted=0 skipped=1 failed=0" in text
    assert "bill: inserted=0 skipped=1 failed=0" in text
    assert "customer_payment: inserted=0 skipped=1 failed=0" in text
    assert "vendor_payment: inserted=0 skipped=1 failed=0" in text
    # CustomerAddRq/InvoiceAddRq/etc. must never fire once skipped.
    assert not any("<CustomerAddRq>" in c for c in fake_session.calls)
    assert not any("<InvoiceAddRq>" in c for c in fake_session.calls)


def test_run_workbook_commit_aborts_on_missing_account(tmp_path, monkeypatch):
    class MissingAccountSession(FakeSession):
        def process(self, request_xml: str) -> str:
            if "<AccountQueryRq>" in request_xml:
                return """<?xml version="1.0"?><QBXML><QBXMLMsgsRs><AccountQueryRs></AccountQueryRs></QBXMLMsgsRs></QBXML>"""
            return super().process(request_xml)

    fake_session = MissingAccountSession()
    monkeypatch.setattr(
        import_workbook, "QBSession", lambda company_file="": FakeQBSessionContext(fake_session)
    )

    lines = []
    result_code = run_workbook_commit(
        full_workbook(),
        company_file="",
        log_path=tmp_path / "log.jsonl",
        skip_ids=set(),
        force=False,
        continue_on_error=False,
        emit=lines.append,
    )

    assert result_code == 1
    text = "\n".join(lines)
    assert "Aborting: preflight failed" in text
    # Nothing should have been written once preflight fails.
    assert not any("<CustomerAddRq>" in c for c in fake_session.calls)
