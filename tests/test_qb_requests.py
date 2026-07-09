from schema import Batch
from qb_requests import (
    build_account_query_rq,
    build_journal_entry_add_rq,
    currency_full_name,
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
    # RefNumber is never used: QuickBooks caps it at 11 chars (statusCode
    # 3070 on anything longer), so line_id goes in each line's Memo instead.
    assert "<RefNumber>" not in xml
    assert "CurrencyRef" not in xml
    assert "ExchangeRate" not in xml
    # JournalEntryAdd has no header-level Memo; entry.memo falls back onto
    # each line that doesn't have its own line-level memo, all prefixed
    # with [line_id] for traceability in the QB register.
    assert xml.count("<Memo>") == 2
    assert "<JournalCreditLine>" in xml
    assert "<JournalDebitLine>" in xml
    assert "<FullName>Bank</FullName>" in xml
    assert "<Amount>100.00</Amount>" in xml
    assert "<Memo>[je1] office rent</Memo>" in xml
    assert "<Memo>[je1] rent</Memo>" in xml  # entry-level memo applied to the credit line


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

    # CHF -> "Swiss Franc": QuickBooks' Currency List uses descriptive
    # names, not ISO codes, as the CurrencyRef FullName.
    assert "<CurrencyRef><FullName>Swiss Franc</FullName></CurrencyRef>" in xml
    assert "<ExchangeRate>1.0962</ExchangeRate>" in xml
    # rate convention: home currency per 1 unit foreign, per the SDK's OSR docs.
    assert xml.index("ExchangeRate") > 0
    assert "<RefNumber>" not in xml
    # No memo was set on the entry or either line, but each line still gets
    # tagged with [line_id] so it's traceable in the QB register.
    assert xml.count("<Memo>[je2] </Memo>") == 2


def test_currency_full_name_translation():
    assert currency_full_name("USD") == "US Dollar"
    assert currency_full_name("usd") == "US Dollar"
    assert currency_full_name("CAD") == "Canadian Dollar"
    # Unrecognized codes pass through unchanged rather than being dropped.
    assert currency_full_name("XYZ") == "XYZ"


def test_amount_always_has_two_decimal_places():
    # QuickBooks rejects amounts without exactly two decimals (statusCode
    # 3040, "error when converting the amount") — e.g. "100.0" fails,
    # "100.00" doesn't. Values that round-trip through JSON as a whole
    # number or with only one decimal place must still come out as X.XX.
    batch = Batch.model_validate(
        {
            "batch_id": "b1",
            "transactions": [
                {
                    "line_id": "je3",
                    "date": "2026-07-01",
                    "lines": [
                        {"account": "Bank", "credit": 100},
                        {"account": "Expenses", "debit": 100},
                    ],
                }
            ],
        }
    )
    xml = build_journal_entry_add_rq(batch.transactions[0])
    assert "<Amount>100.00</Amount>" in xml
    assert "<Amount>100.0</Amount>" not in xml
    assert "<Amount>100</Amount>" not in xml


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
