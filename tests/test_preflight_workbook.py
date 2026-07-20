"""Covers missing_accounts (existing, previously untested) plus the new
existence-check functions, all against a lightweight fake session -- a stub
exposing .process(xml) -> str, not a real QBSession/COM mock, matching the
pure-Python testability the rest of this codebase relies on.
"""
from preflight import (
    existing_customer_names,
    existing_vendor_names,
    missing_accounts,
    missing_items,
)


class FakeSession:
    def __init__(self, response: str):
        self.response = response
        self.requests = []

    def process(self, request_xml: str) -> str:
        self.requests.append(request_xml)
        return self.response


def test_missing_accounts_returns_not_found_subset():
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <AccountQueryRs>
        <AccountRet><FullName>Bank</FullName></AccountRet>
      </AccountQueryRs>
    </QBXMLMsgsRs></QBXML>"""
    session = FakeSession(response)
    result = missing_accounts(session, ["Bank", "Ghost Account"])
    assert result == ["Ghost Account"]


def test_missing_accounts_empty_input_short_circuits():
    session = FakeSession("<QBXML/>")
    assert missing_accounts(session, []) == []
    assert session.requests == []


def test_missing_items_returns_not_found_subset():
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <ItemQueryRs>
        <ItemServiceRet><FullName>Consulting</FullName></ItemServiceRet>
      </ItemQueryRs>
    </QBXMLMsgsRs></QBXML>"""
    session = FakeSession(response)
    result = missing_items(session, ["Consulting", "Ghost Item"])
    assert result == ["Ghost Item"]


def test_existing_customer_names_returns_found_subset():
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <CustomerQueryRs>
        <CustomerRet><FullName>Acme Corp</FullName></CustomerRet>
      </CustomerQueryRs>
    </QBXMLMsgsRs></QBXML>"""
    session = FakeSession(response)
    result = existing_customer_names(session, ["Acme Corp", "New Customer"])
    assert result == {"Acme Corp"}


def test_existing_customer_names_empty_input_short_circuits():
    session = FakeSession("<QBXML/>")
    assert existing_customer_names(session, []) == set()
    assert session.requests == []


def test_existing_vendor_names_returns_found_subset():
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <VendorQueryRs>
        <VendorRet><FullName>Acme Supplier</FullName></VendorRet>
      </VendorQueryRs>
    </QBXMLMsgsRs></QBXML>"""
    session = FakeSession(response)
    result = existing_vendor_names(session, ["Acme Supplier", "New Vendor"])
    assert result == {"Acme Supplier"}
