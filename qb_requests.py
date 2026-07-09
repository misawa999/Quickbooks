"""Builds qbXML requests and parses qbXML responses for JournalEntryAdd / AccountQuery.

Kept as raw XML strings (not QBFC COM objects) per the build spec: easier to
debug, version, and unit-test outside of Windows/QuickBooks.
"""
from __future__ import annotations

from typing import List, Optional, Set
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from schema import JournalEntry

QBXML_VERSION = "13.0"


def _line_xml(tag: str, account: str, amount, memo: Optional[str]) -> str:
    parts = [
        f"<{tag}>",
        f"<AccountRef><FullName>{escape(account)}</FullName></AccountRef>",
        f"<Amount>{amount}</Amount>",
    ]
    if memo:
        parts.append(f"<Memo>{escape(memo)}</Memo>")
    parts.append(f"</{tag}>")
    return "".join(parts)


def build_journal_entry_add_rq(entry: JournalEntry) -> str:
    # Element order below matches the qbXML JournalEntryAdd schema exactly.
    # QuickBooks' parser is strict about both order and which elements are
    # valid at all — e.g. there is no header-level <Memo> on this request
    # type, only per-line, so entry.memo is applied to each line instead.
    header = [f"<TxnDate>{entry.date.isoformat()}</TxnDate>"]
    # line_id goes in RefNumber: stable, searchable, and shows up in the QB UI register.
    header.append(f"<RefNumber>{escape(entry.line_id)}</RefNumber>")
    if entry.currency:
        header.append(f"<CurrencyRef><FullName>{escape(entry.currency)}</FullName></CurrencyRef>")
        header.append(f"<ExchangeRate>{entry.exchange_rate}</ExchangeRate>")

    lines: List[str] = []
    for line in entry.lines:
        memo = line.memo or entry.memo
        if line.debit > 0:
            lines.append(_line_xml("JournalDebitLine", line.account, line.debit, memo))
        else:
            lines.append(_line_xml("JournalCreditLine", line.account, line.credit, memo))

    body = "".join(header) + "".join(lines)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<?qbxml version="{QBXML_VERSION}"?>'
        '<QBXML><QBXMLMsgsRq onError="stopOnError">'
        f"<JournalEntryAddRq><JournalEntryAdd>{body}</JournalEntryAdd></JournalEntryAddRq>"
        "</QBXMLMsgsRq></QBXML>"
    )


def parse_journal_entry_add_rs(response_xml: str) -> dict:
    root = ET.fromstring(response_xml)
    rs = root.find(".//JournalEntryAddRs")
    if rs is None:
        raise ValueError(f"unexpected response, no JournalEntryAddRs found: {response_xml}")
    status_code = rs.get("statusCode")
    status_message = rs.get("statusMessage")
    txn_id_el = rs.find(".//TxnID")
    return {
        "status_code": int(status_code) if status_code is not None else None,
        "status_message": status_message or "",
        "txn_id": txn_id_el.text if txn_id_el is not None else None,
    }


def build_account_query_rq(account_names: List[str]) -> str:
    names_xml = "".join(f"<FullName>{escape(n)}</FullName>" for n in account_names)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<?qbxml version="{QBXML_VERSION}"?>'
        '<QBXML><QBXMLMsgsRq onError="continueOnError">'
        f"<AccountQueryRq>{names_xml}</AccountQueryRq>"
        "</QBXMLMsgsRq></QBXML>"
    )


def parse_account_query_rs(response_xml: str) -> Set[str]:
    root = ET.fromstring(response_xml)
    found = set()
    for el in root.findall(".//AccountRet/FullName"):
        if el.text:
            found.add(el.text)
    return found
