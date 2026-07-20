"""Resolve invoice/bill RefNumbers to their QuickBooks TxnIDs.

Payments must be linked to the specific invoice(s)/bill(s) they settle via
qbXML's AppliedToTxnAdd, which needs the target transaction's TxnID -- not
its human-facing RefNumber. Source data only ever carries the RefNumber
(e.g. "INV-1001"), so this module resolves RefNumber -> TxnID by querying
QuickBooks live at payment-processing time.

This is deliberately independent of dedupe.py/the local import log: a
payment might be processed in a separate run/session from when the invoice
or bill was created, so the only trustworthy source for "does this
RefNumber exist and what's its TxnID" is QuickBooks itself, queried fresh
every time.
"""
from __future__ import annotations

from qb_requests import build_bill_query_rq, build_invoice_query_rq, parse_bill_query_rs, parse_invoice_query_rs
from qb_session import QBSession


class TxnResolutionError(RuntimeError):
    """Raised when a RefNumber does not resolve to exactly one TxnID."""


def resolve_invoice_txn_id(session: QBSession, ref_number: str, customer: str) -> str:
    request = build_invoice_query_rq(ref_number, customer)
    response = session.process(request)
    matches = parse_invoice_query_rs(response)
    if not matches:
        raise TxnResolutionError(
            f"invoice {ref_number!r} for customer {customer!r} was not found in QuickBooks"
        )
    if len(matches) > 1:
        raise TxnResolutionError(
            f"invoice {ref_number!r} for customer {customer!r} matched {len(matches)} "
            f"invoices in QuickBooks - ambiguous, refusing to guess"
        )
    return matches[0]["txn_id"]


def resolve_bill_txn_id(session: QBSession, ref_number: str, vendor: str) -> str:
    request = build_bill_query_rq(ref_number, vendor)
    response = session.process(request)
    matches = parse_bill_query_rs(response)
    if not matches:
        raise TxnResolutionError(
            f"bill {ref_number!r} for vendor {vendor!r} was not found in QuickBooks"
        )
    if len(matches) > 1:
        raise TxnResolutionError(
            f"bill {ref_number!r} for vendor {vendor!r} matched {len(matches)} bills "
            f"in QuickBooks - ambiguous, refusing to guess"
        )
    return matches[0]["txn_id"]
