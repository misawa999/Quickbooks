from schema import Batch
from qb_requests import (
    build_account_query_rq,
    build_journal_entry_add_rq,
    parse_account_query_rs,
    parse_journal_entry_add_rs,
)


def test_build_journal_entry_add_rq_home_currency():
    batch = Batch.model_validate(
        {
            "batch_id": "b1",
            "transactions": [
                {
                    "line_id": "je1",
                    "date": "2026-07-01",
                    "memo": "rent",
                    "lines": [
                        {"account": "Bank", "credit": 100},
                        {"account": "Expenses", "debit": 100, "memo": "office rent"},
                    ],
                }
            ],
        }
    )
    xml = build_journal_entry_add_rq(batch.transactions[0])

    assert "<TxnDate>2026-07-01</TxnDate>" in xml
    assert "<RefNumber>je1</RefNumber>" in xml
    assert "CurrencyRef" not in xml
    assert "ExchangeRate" not in xml
    assert "<JournalCreditLine>" in xml
    assert "<JournalDebitLine>" in xml
    assert "<FullName>Bank</FullName>" in xml
    assert "<Amount>100</Amount>" in xml
    assert "office rent" in xml


def test_build_journal_entry_add_rq_multicurrency():
    batch = Batch.model_validate(
        {
            "batch_id": "b1",
            "transactions": [
                {
                    "line_id": "je2",
                    "date": "2026-07-01",
                    "currency": "CHF",
                    "exchange_rate": 1.0962,
                    "lines": [
                        {"account": "OCBC Bank (CHF)", "credit": 1250},
                        {"account": "Uncategorized Expenses", "debit": 1250},
                    ],
                }
            ],
        }
    )
    xml = build_journal_entry_add_rq(batch.transactions[0])

    assert "<CurrencyRef><FullName>CHF</FullName></CurrencyRef>" in xml
    assert "<ExchangeRate>1.0962</ExchangeRate>" in xml
    # rate convention: home currency per 1 unit foreign, per the SDK's OSR docs.
    assert xml.index("ExchangeRate") > 0


def test_parse_journal_entry_add_rs_success():
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <JournalEntryAddRs statusCode="0" statusMessage="Status OK">
        <JournalEntryRet><TxnID>ABC-123</TxnID></JournalEntryRet>
      </JournalEntryAddRs>
    </QBXMLMsgsRs></QBXML>"""
    result = parse_journal_entry_add_rs(response)
    assert result == {"status_code": 0, "status_message": "Status OK", "txn_id": "ABC-123"}


def test_parse_journal_entry_add_rs_error():
    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <JournalEntryAddRs statusCode="3140" statusMessage="Account not found">
      </JournalEntryAddRs>
    </QBXMLMsgsRs></QBXML>"""
    result = parse_journal_entry_add_rs(response)
    assert result["status_code"] == 3140
    assert result["txn_id"] is None


def test_account_query_round_trip():
    request = build_account_query_rq(["Bank", "Expenses"])
    assert "<FullName>Bank</FullName>" in request
    assert "<FullName>Expenses</FullName>" in request

    response = """<?xml version="1.0"?>
    <QBXML><QBXMLMsgsRs>
      <AccountQueryRs>
        <AccountRet><FullName>Bank</FullName></AccountRet>
      </AccountQueryRs>
    </QBXMLMsgsRs></QBXML>"""
    found = parse_account_query_rs(response)
    assert found == {"Bank"}
