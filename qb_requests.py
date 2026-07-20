"""Builds qbXML requests and parses qbXML responses.

Covers JournalEntryAdd / AccountQuery (bank-side journal entries) and
CustomerAdd/VendorAdd/InvoiceAdd/BillAdd/ReceivePaymentAdd/
BillPaymentCheckAdd plus their Query counterparts (business transactions).

Kept as raw XML strings (not QBFC COM objects) per the build spec: easier to
debug, version, and unit-test outside of Windows/QuickBooks.

NOTE on element ordering: qbXML's parser is strict about the order of child
elements within each *Add request (see the JournalEntryAdd comments below for
a concrete example of how unforgiving it is about format details). The
orderings used for the newer Customer/Vendor/Invoice/Bill/Payment builders
below are believed correct from the qbXML 13.0 OSR but have not yet been
exercised against a real QuickBooks Desktop company file -- verify against
the OSR reference and a --commit dry run against a backup company file
before relying on them in production.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional, Set
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from schema import Bill, Customer, CustomerPayment, Invoice, JournalEntry, Vendor, VendorPayment

QBXML_VERSION = "13.0"

# QuickBooks' Currency List identifies currencies by descriptive name (e.g.
# "US Dollar"), not by ISO code — CurrencyRef's FullName must match the list
# exactly, or QuickBooks rejects it with statusCode 3140 ("invalid reference
# ... record does not exist"). This maps common ISO codes to QuickBooks'
# standard built-in names so batch files can keep using plain codes. Codes
# not in this table are passed through unchanged (assumed to already be the
# exact QuickBooks list name).
CURRENCY_NAMES = {
    "USD": "US Dollar",
    "CAD": "Canadian Dollar",
    "EUR": "Euro",
    "GBP": "British Pound",
    "CHF": "Swiss Franc",
    "JPY": "Japanese Yen",
    "AUD": "Australian Dollar",
    "HKD": "Hong Kong Dollar",
    "SGD": "Singapore Dollar",
    "CNY": "Chinese Yuan Renminbi",
    "INR": "Indian Rupee",
    "NZD": "New Zealand Dollar",
    "MXN": "Mexican Peso",
}


def currency_full_name(code: str) -> str:
    return CURRENCY_NAMES.get(code.upper(), code)


def _line_xml(tag: str, account: str, amount, memo: Optional[str]) -> str:
    # QuickBooks' AMTTYPE parser rejects amounts that aren't formatted with
    # exactly two decimal places (statusCode 3040) — e.g. "100.0" fails,
    # "100.00" doesn't. Decimal's default str() drops/keeps whatever
    # precision the input JSON happened to have, so it's normalized here.
    parts = [
        f"<{tag}>",
        f"<AccountRef><FullName>{escape(account)}</FullName></AccountRef>",
        f"<Amount>{amount:.2f}</Amount>",
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
    #
    # line_id is NOT put in RefNumber: QuickBooks Desktop caps RefNumber at
    # 11 characters and silently rejects longer ones (statusCode 3070), so
    # any non-trivial line_id would break. Instead it's prefixed onto each
    # line's memo, which has no such limit and is still visible in the
    # register.
    header = [f"<TxnDate>{entry.date.isoformat()}</TxnDate>"]
    if entry.currency:
        currency_name = currency_full_name(entry.currency)
        header.append(f"<CurrencyRef><FullName>{escape(currency_name)}</FullName></CurrencyRef>")
        header.append(f"<ExchangeRate>{entry.exchange_rate}</ExchangeRate>")

    tag_prefix = f"[{entry.line_id}] "
    lines: List[str] = []
    for line in entry.lines:
        memo = tag_prefix + (line.memo or entry.memo or "")
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


# -- Customers / Vendors -----------------------------------------------

def _address_xml(tag: str, lines: List[str]) -> str:
    parts = [f"<{tag}>"]
    for i, line in enumerate(lines[:5], start=1):
        parts.append(f"<Addr{i}>{escape(line)}</Addr{i}>")
    parts.append(f"</{tag}>")
    return "".join(parts)


def build_customer_add_rq(customer: Customer) -> str:
    parts = [f"<Name>{escape(customer.name)}</Name>"]
    if customer.company_name:
        parts.append(f"<CompanyName>{escape(customer.company_name)}</CompanyName>")
    if customer.address_lines:
        parts.append(_address_xml("BillAddress", customer.address_lines))
    if customer.phone:
        parts.append(f"<Phone>{escape(customer.phone)}</Phone>")
    if customer.email:
        parts.append(f"<Email>{escape(customer.email)}</Email>")
    if customer.memo:
        parts.append(f"<Notes>{escape(customer.memo)}</Notes>")
    if customer.currency:
        currency_name = currency_full_name(customer.currency)
        parts.append(f"<CurrencyRef><FullName>{escape(currency_name)}</FullName></CurrencyRef>")
    body = "".join(parts)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<?qbxml version="{QBXML_VERSION}"?>'
        '<QBXML><QBXMLMsgsRq onError="stopOnError">'
        f"<CustomerAddRq><CustomerAdd>{body}</CustomerAdd></CustomerAddRq>"
        "</QBXMLMsgsRq></QBXML>"
    )


def parse_customer_add_rs(response_xml: str) -> dict:
    root = ET.fromstring(response_xml)
    rs = root.find(".//CustomerAddRs")
    if rs is None:
        raise ValueError(f"unexpected response, no CustomerAddRs found: {response_xml}")
    status_code = rs.get("statusCode")
    status_message = rs.get("statusMessage")
    list_id_el = rs.find(".//ListID")
    name_el = rs.find(".//Name")
    return {
        "status_code": int(status_code) if status_code is not None else None,
        "status_message": status_message or "",
        "list_id": list_id_el.text if list_id_el is not None else None,
        "name": name_el.text if name_el is not None else None,
    }


def build_customer_query_rq(names: List[str]) -> str:
    names_xml = "".join(f"<FullName>{escape(n)}</FullName>" for n in names)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<?qbxml version="{QBXML_VERSION}"?>'
        '<QBXML><QBXMLMsgsRq onError="continueOnError">'
        f"<CustomerQueryRq>{names_xml}</CustomerQueryRq>"
        "</QBXMLMsgsRq></QBXML>"
    )


def parse_customer_query_rs(response_xml: str) -> Set[str]:
    root = ET.fromstring(response_xml)
    found = set()
    for el in root.findall(".//CustomerRet/FullName"):
        if el.text:
            found.add(el.text)
    return found


def build_vendor_add_rq(vendor: Vendor) -> str:
    parts = [f"<Name>{escape(vendor.name)}</Name>"]
    if vendor.company_name:
        parts.append(f"<CompanyName>{escape(vendor.company_name)}</CompanyName>")
    if vendor.address_lines:
        parts.append(_address_xml("VendorAddress", vendor.address_lines))
    if vendor.phone:
        parts.append(f"<Phone>{escape(vendor.phone)}</Phone>")
    if vendor.email:
        parts.append(f"<Email>{escape(vendor.email)}</Email>")
    if vendor.memo:
        parts.append(f"<Notes>{escape(vendor.memo)}</Notes>")
    if vendor.currency:
        currency_name = currency_full_name(vendor.currency)
        parts.append(f"<CurrencyRef><FullName>{escape(currency_name)}</FullName></CurrencyRef>")
    body = "".join(parts)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<?qbxml version="{QBXML_VERSION}"?>'
        '<QBXML><QBXMLMsgsRq onError="stopOnError">'
        f"<VendorAddRq><VendorAdd>{body}</VendorAdd></VendorAddRq>"
        "</QBXMLMsgsRq></QBXML>"
    )


def parse_vendor_add_rs(response_xml: str) -> dict:
    root = ET.fromstring(response_xml)
    rs = root.find(".//VendorAddRs")
    if rs is None:
        raise ValueError(f"unexpected response, no VendorAddRs found: {response_xml}")
    status_code = rs.get("statusCode")
    status_message = rs.get("statusMessage")
    list_id_el = rs.find(".//ListID")
    name_el = rs.find(".//Name")
    return {
        "status_code": int(status_code) if status_code is not None else None,
        "status_message": status_message or "",
        "list_id": list_id_el.text if list_id_el is not None else None,
        "name": name_el.text if name_el is not None else None,
    }


def build_vendor_query_rq(names: List[str]) -> str:
    names_xml = "".join(f"<FullName>{escape(n)}</FullName>" for n in names)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<?qbxml version="{QBXML_VERSION}"?>'
        '<QBXML><QBXMLMsgsRq onError="continueOnError">'
        f"<VendorQueryRq>{names_xml}</VendorQueryRq>"
        "</QBXMLMsgsRq></QBXML>"
    )


def parse_vendor_query_rs(response_xml: str) -> Set[str]:
    root = ET.fromstring(response_xml)
    found = set()
    for el in root.findall(".//VendorRet/FullName"):
        if el.text:
            found.add(el.text)
    return found


# -- Items (read-only existence check; items are assumed pre-existing) --

def build_item_query_rq(item_names: List[str]) -> str:
    names_xml = "".join(f"<FullName>{escape(n)}</FullName>" for n in item_names)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<?qbxml version="{QBXML_VERSION}"?>'
        '<QBXML><QBXMLMsgsRq onError="continueOnError">'
        f"<ItemQueryRq>{names_xml}</ItemQueryRq>"
        "</QBXMLMsgsRq></QBXML>"
    )


def parse_item_query_rs(response_xml: str) -> Set[str]:
    # ItemQueryRq is a single query across every item type (service,
    # non-inventory, inventory, ...); each match comes back as a distinct
    # Item*Ret element (ItemServiceRet, ItemNonInventoryRet, ...), but every
    # one of them carries a top-level FullName child, so we don't need to
    # enumerate the specific *Ret tag names.
    root = ET.fromstring(response_xml)
    found = set()
    rs = root.find(".//ItemQueryRs")
    if rs is None:
        return found
    for ret in rs:
        full_name = ret.find("FullName")
        if full_name is not None and full_name.text:
            found.add(full_name.text)
    return found


# -- Invoices -------------------------------------------------------------

def build_invoice_add_rq(invoice: Invoice) -> str:
    header = [f"<CustomerRef><FullName>{escape(invoice.customer)}</FullName></CustomerRef>"]
    if invoice.ar_account:
        header.append(f"<ARAccountRef><FullName>{escape(invoice.ar_account)}</FullName></ARAccountRef>")
    header.append(f"<TxnDate>{invoice.date.isoformat()}</TxnDate>")
    header.append(f"<RefNumber>{escape(invoice.ref_number)}</RefNumber>")
    if invoice.due_date:
        header.append(f"<DueDate>{invoice.due_date.isoformat()}</DueDate>")
    if invoice.terms:
        header.append(f"<TermsRef><FullName>{escape(invoice.terms)}</FullName></TermsRef>")
    if invoice.currency:
        currency_name = currency_full_name(invoice.currency)
        header.append(f"<CurrencyRef><FullName>{escape(currency_name)}</FullName></CurrencyRef>")
        header.append(f"<ExchangeRate>{invoice.exchange_rate}</ExchangeRate>")
    if invoice.memo:
        header.append(f"<Memo>{escape(invoice.memo)}</Memo>")

    lines: List[str] = []
    for line in invoice.lines:
        parts = ["<InvoiceLineAdd>", f"<ItemRef><FullName>{escape(line.item)}</FullName></ItemRef>"]
        if line.description:
            parts.append(f"<Desc>{escape(line.description)}</Desc>")
        if line.quantity is not None:
            parts.append(f"<Quantity>{line.quantity}</Quantity>")
        if line.rate is not None:
            parts.append(f"<Rate>{line.rate:.2f}</Rate>")
        # Same statusCode-3040 two-decimal-place requirement as journal
        # entry lines (see _line_xml above).
        parts.append(f"<Amount>{line.amount:.2f}</Amount>")
        parts.append("</InvoiceLineAdd>")
        lines.append("".join(parts))

    body = "".join(header) + "".join(lines)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<?qbxml version="{QBXML_VERSION}"?>'
        '<QBXML><QBXMLMsgsRq onError="stopOnError">'
        f"<InvoiceAddRq><InvoiceAdd>{body}</InvoiceAdd></InvoiceAddRq>"
        "</QBXMLMsgsRq></QBXML>"
    )


def parse_invoice_add_rs(response_xml: str) -> dict:
    root = ET.fromstring(response_xml)
    rs = root.find(".//InvoiceAddRs")
    if rs is None:
        raise ValueError(f"unexpected response, no InvoiceAddRs found: {response_xml}")
    status_code = rs.get("statusCode")
    status_message = rs.get("statusMessage")
    txn_id_el = rs.find(".//TxnID")
    return {
        "status_code": int(status_code) if status_code is not None else None,
        "status_message": status_message or "",
        "txn_id": txn_id_el.text if txn_id_el is not None else None,
    }


def build_invoice_query_rq(ref_number: str, customer: Optional[str] = None) -> str:
    parts = [
        "<RefNumberFilter>",
        "<MatchCriterion>Equals</MatchCriterion>",
        f"<RefNumber>{escape(ref_number)}</RefNumber>",
        "</RefNumberFilter>",
    ]
    if customer:
        # RefNumbers are business-controlled and not guaranteed unique
        # across customers, so scope the lookup by customer whenever known
        # to avoid resolving to the wrong invoice.
        parts.append(f"<EntityFilter><FullName>{escape(customer)}</FullName></EntityFilter>")
    body = "".join(parts)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<?qbxml version="{QBXML_VERSION}"?>'
        '<QBXML><QBXMLMsgsRq onError="continueOnError">'
        f"<InvoiceQueryRq>{body}</InvoiceQueryRq>"
        "</QBXMLMsgsRq></QBXML>"
    )


def parse_invoice_query_rs(response_xml: str) -> List[dict]:
    root = ET.fromstring(response_xml)
    results = []
    for ret in root.findall(".//InvoiceRet"):
        txn_id_el = ret.find("TxnID")
        ref_number_el = ret.find("RefNumber")
        customer_el = ret.find("CustomerRef/FullName")
        balance_el = ret.find("BalanceRemaining")
        results.append(
            {
                "txn_id": txn_id_el.text if txn_id_el is not None else None,
                "ref_number": ref_number_el.text if ref_number_el is not None else None,
                "customer": customer_el.text if customer_el is not None else None,
                "balance_remaining": balance_el.text if balance_el is not None else None,
            }
        )
    return results


# -- Bills ------------------------------------------------------------------

def build_bill_add_rq(bill: Bill) -> str:
    header = [f"<VendorRef><FullName>{escape(bill.vendor)}</FullName></VendorRef>"]
    if bill.ap_account:
        header.append(f"<APAccountRef><FullName>{escape(bill.ap_account)}</FullName></APAccountRef>")
    header.append(f"<TxnDate>{bill.date.isoformat()}</TxnDate>")
    header.append(f"<RefNumber>{escape(bill.ref_number)}</RefNumber>")
    if bill.due_date:
        header.append(f"<DueDate>{bill.due_date.isoformat()}</DueDate>")
    if bill.currency:
        currency_name = currency_full_name(bill.currency)
        header.append(f"<CurrencyRef><FullName>{escape(currency_name)}</FullName></CurrencyRef>")
        header.append(f"<ExchangeRate>{bill.exchange_rate}</ExchangeRate>")
    if bill.memo:
        header.append(f"<Memo>{escape(bill.memo)}</Memo>")

    lines: List[str] = []
    for line in bill.lines:
        parts = [
            "<ExpenseLineAdd>",
            f"<AccountRef><FullName>{escape(line.account)}</FullName></AccountRef>",
            f"<Amount>{line.amount:.2f}</Amount>",
        ]
        if line.description:
            parts.append(f"<Memo>{escape(line.description)}</Memo>")
        parts.append("</ExpenseLineAdd>")
        lines.append("".join(parts))

    body = "".join(header) + "".join(lines)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<?qbxml version="{QBXML_VERSION}"?>'
        '<QBXML><QBXMLMsgsRq onError="stopOnError">'
        f"<BillAddRq><BillAdd>{body}</BillAdd></BillAddRq>"
        "</QBXMLMsgsRq></QBXML>"
    )


def parse_bill_add_rs(response_xml: str) -> dict:
    root = ET.fromstring(response_xml)
    rs = root.find(".//BillAddRs")
    if rs is None:
        raise ValueError(f"unexpected response, no BillAddRs found: {response_xml}")
    status_code = rs.get("statusCode")
    status_message = rs.get("statusMessage")
    txn_id_el = rs.find(".//TxnID")
    return {
        "status_code": int(status_code) if status_code is not None else None,
        "status_message": status_message or "",
        "txn_id": txn_id_el.text if txn_id_el is not None else None,
    }


def build_bill_query_rq(ref_number: str, vendor: Optional[str] = None) -> str:
    parts = [
        "<RefNumberFilter>",
        "<MatchCriterion>Equals</MatchCriterion>",
        f"<RefNumber>{escape(ref_number)}</RefNumber>",
        "</RefNumberFilter>",
    ]
    if vendor:
        # Unlike invoice numbers, vendor-assigned bill numbers are
        # definitely not unique across different vendors, so this filter
        # matters even more here than on the invoice side.
        parts.append(f"<EntityFilter><FullName>{escape(vendor)}</FullName></EntityFilter>")
    body = "".join(parts)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<?qbxml version="{QBXML_VERSION}"?>'
        '<QBXML><QBXMLMsgsRq onError="continueOnError">'
        f"<BillQueryRq>{body}</BillQueryRq>"
        "</QBXMLMsgsRq></QBXML>"
    )


def parse_bill_query_rs(response_xml: str) -> List[dict]:
    root = ET.fromstring(response_xml)
    results = []
    for ret in root.findall(".//BillRet"):
        txn_id_el = ret.find("TxnID")
        ref_number_el = ret.find("RefNumber")
        vendor_el = ret.find("VendorRef/FullName")
        balance_el = ret.find("AmountDue")
        results.append(
            {
                "txn_id": txn_id_el.text if txn_id_el is not None else None,
                "ref_number": ref_number_el.text if ref_number_el is not None else None,
                "vendor": vendor_el.text if vendor_el is not None else None,
                "balance_remaining": balance_el.text if balance_el is not None else None,
            }
        )
    return results


# -- Payments (linked to specific invoices/bills via AppliedToTxnAdd) ------
#
# Builders take a pre-resolved ref -> TxnID map rather than resolving live
# inside the builder, so they stay pure functions testable with a fake dict
# -- resolution against real QuickBooks happens one layer up, in
# txn_lookup.py, since it needs a live QBSession.

def build_receive_payment_add_rq(payment: CustomerPayment, txn_ids: Dict[str, str]) -> str:
    total = sum((a.amount for a in payment.applications), Decimal("0"))
    header = [f"<CustomerRef><FullName>{escape(payment.customer)}</FullName></CustomerRef>"]
    if payment.ar_account:
        header.append(f"<ARAccountRef><FullName>{escape(payment.ar_account)}</FullName></ARAccountRef>")
    header.append(f"<TxnDate>{payment.date.isoformat()}</TxnDate>")
    if payment.ref_number:
        header.append(f"<RefNumber>{escape(payment.ref_number)}</RefNumber>")
    header.append(f"<TotalAmount>{total:.2f}</TotalAmount>")
    if payment.currency:
        currency_name = currency_full_name(payment.currency)
        header.append(f"<CurrencyRef><FullName>{escape(currency_name)}</FullName></CurrencyRef>")
        header.append(f"<ExchangeRate>{payment.exchange_rate}</ExchangeRate>")
    if payment.memo:
        header.append(f"<Memo>{escape(payment.memo)}</Memo>")
    header.append(
        f"<DepositToAccountRef><FullName>{escape(payment.deposit_to_account)}</FullName></DepositToAccountRef>"
    )
    if payment.payment_method:
        header.append(f"<PaymentMethodRef><FullName>{escape(payment.payment_method)}</FullName></PaymentMethodRef>")

    applied: List[str] = []
    for app in payment.applications:
        txn_id = txn_ids[app.invoice_ref]
        applied.append(
            "<AppliedToTxnAdd>"
            f"<TxnID>{escape(txn_id)}</TxnID>"
            f"<PaymentAmount>{app.amount:.2f}</PaymentAmount>"
            "</AppliedToTxnAdd>"
        )

    body = "".join(header) + "".join(applied)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<?qbxml version="{QBXML_VERSION}"?>'
        '<QBXML><QBXMLMsgsRq onError="stopOnError">'
        f"<ReceivePaymentAddRq><ReceivePaymentAdd>{body}</ReceivePaymentAdd></ReceivePaymentAddRq>"
        "</QBXMLMsgsRq></QBXML>"
    )


def parse_receive_payment_add_rs(response_xml: str) -> dict:
    root = ET.fromstring(response_xml)
    rs = root.find(".//ReceivePaymentAddRs")
    if rs is None:
        raise ValueError(f"unexpected response, no ReceivePaymentAddRs found: {response_xml}")
    status_code = rs.get("statusCode")
    status_message = rs.get("statusMessage")
    # ReceivePaymentRet's own TxnID appears before the nested
    # AppliedToTxnRet list in the response, so the first match is the
    # payment's TxnID, not one of the invoices it was applied to.
    txn_id_el = rs.find(".//TxnID")
    return {
        "status_code": int(status_code) if status_code is not None else None,
        "status_message": status_message or "",
        "txn_id": txn_id_el.text if txn_id_el is not None else None,
    }


def build_bill_payment_check_add_rq(payment: VendorPayment, txn_ids: Dict[str, str]) -> str:
    header = [f"<PayeeEntityRef><FullName>{escape(payment.vendor)}</FullName></PayeeEntityRef>"]
    if payment.ap_account:
        header.append(f"<APAccountRef><FullName>{escape(payment.ap_account)}</FullName></APAccountRef>")
    header.append(f"<BankAccountRef><FullName>{escape(payment.bank_account)}</FullName></BankAccountRef>")
    header.append(f"<TxnDate>{payment.date.isoformat()}</TxnDate>")
    if payment.check_number:
        header.append(f"<RefNumber>{escape(payment.check_number)}</RefNumber>")
        header.append("<IsToBePrinted>false</IsToBePrinted>")
    else:
        header.append("<IsToBePrinted>true</IsToBePrinted>")
    if payment.currency:
        currency_name = currency_full_name(payment.currency)
        header.append(f"<CurrencyRef><FullName>{escape(currency_name)}</FullName></CurrencyRef>")
        header.append(f"<ExchangeRate>{payment.exchange_rate}</ExchangeRate>")
    if payment.memo:
        header.append(f"<Memo>{escape(payment.memo)}</Memo>")

    applied: List[str] = []
    for app in payment.applications:
        txn_id = txn_ids[app.bill_ref]
        applied.append(
            "<AppliedToTxnAdd>"
            f"<TxnID>{escape(txn_id)}</TxnID>"
            f"<PaymentAmount>{app.amount:.2f}</PaymentAmount>"
            "</AppliedToTxnAdd>"
        )

    body = "".join(header) + "".join(applied)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<?qbxml version="{QBXML_VERSION}"?>'
        '<QBXML><QBXMLMsgsRq onError="stopOnError">'
        f"<BillPaymentCheckAddRq><BillPaymentCheckAdd>{body}</BillPaymentCheckAdd></BillPaymentCheckAddRq>"
        "</QBXMLMsgsRq></QBXML>"
    )


def parse_bill_payment_check_add_rs(response_xml: str) -> dict:
    root = ET.fromstring(response_xml)
    rs = root.find(".//BillPaymentCheckAddRs")
    if rs is None:
        raise ValueError(f"unexpected response, no BillPaymentCheckAddRs found: {response_xml}")
    status_code = rs.get("statusCode")
    status_message = rs.get("statusMessage")
    txn_id_el = rs.find(".//TxnID")
    return {
        "status_code": int(status_code) if status_code is not None else None,
        "status_message": status_message or "",
        "txn_id": txn_id_el.text if txn_id_el is not None else None,
    }
