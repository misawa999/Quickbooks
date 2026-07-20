import pytest

from txn_lookup import TxnResolutionError, resolve_bill_txn_id, resolve_invoice_txn_id


class FakeSession:
    def __init__(self, response: str):
        self.response = response
        self.requests = []

    def process(self, request_xml: str) -> str:
        self.requests.append(request_xml)
        return self.response


def test_resolve_invoice_txn_id_success():
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <InvoiceQueryRs>
        <InvoiceRet>
          <TxnID>80000012-1234567890</TxnID>
          <RefNumber>INV-1001</RefNumber>
          <CustomerRef><FullName>Acme Corp</FullName></CustomerRef>
        </InvoiceRet>
      </InvoiceQueryRs>
    </QBXMLMsgsRs></QBXML>"""
    session = FakeSession(response)
    txn_id = resolve_invoice_txn_id(session, "INV-1001", "Acme Corp")
    assert txn_id == "80000012-1234567890"
    assert "<RefNumber>INV-1001</RefNumber>" in session.requests[0]
    assert "<EntityFilter><FullName>Acme Corp</FullName></EntityFilter>" in session.requests[0]


def test_resolve_invoice_txn_id_not_found():
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs><InvoiceQueryRs></InvoiceQueryRs></QBXMLMsgsRs></QBXML>"""
    session = FakeSession(response)
    with pytest.raises(TxnResolutionError, match="not found"):
        resolve_invoice_txn_id(session, "INV-9999", "Acme Corp")


def test_resolve_invoice_txn_id_ambiguous():
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <InvoiceQueryRs>
        <InvoiceRet><TxnID>t1</TxnID><RefNumber>INV-1</RefNumber></InvoiceRet>
        <InvoiceRet><TxnID>t2</TxnID><RefNumber>INV-1</RefNumber></InvoiceRet>
      </InvoiceQueryRs>
    </QBXMLMsgsRs></QBXML>"""
    session = FakeSession(response)
    with pytest.raises(TxnResolutionError, match="ambiguous|matched 2"):
        resolve_invoice_txn_id(session, "INV-1", "Acme Corp")


def test_resolve_bill_txn_id_success():
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <BillQueryRs>
        <BillRet>
          <TxnID>80000020-1234567890</TxnID>
          <RefNumber>B-100</RefNumber>
          <VendorRef><FullName>Acme Supplier</FullName></VendorRef>
        </BillRet>
      </BillQueryRs>
    </QBXMLMsgsRs></QBXML>"""
    session = FakeSession(response)
    txn_id = resolve_bill_txn_id(session, "B-100", "Acme Supplier")
    assert txn_id == "80000020-1234567890"


def test_resolve_bill_txn_id_not_found():
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs><BillQueryRs></BillQueryRs></QBXMLMsgsRs></QBXML>"""
    session = FakeSession(response)
    with pytest.raises(TxnResolutionError, match="not found"):
        resolve_bill_txn_id(session, "B-999", "Acme Supplier")


def test_resolve_bill_txn_id_ambiguous():
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <BillQueryRs>
        <BillRet><TxnID>t1</TxnID><RefNumber>B-1</RefNumber></BillRet>
        <BillRet><TxnID>t2</TxnID><RefNumber>B-1</RefNumber></BillRet>
      </BillQueryRs>
    </QBXMLMsgsRs></QBXML>"""
    session = FakeSession(response)
    with pytest.raises(TxnResolutionError, match="ambiguous|matched 2"):
        resolve_bill_txn_id(session, "B-1", "Acme Supplier")
