"""Read-only checks against QuickBooks before any write."""
from __future__ import annotations

from typing import List, Set

from qb_requests import (
    build_account_query_rq,
    build_customer_query_rq,
    build_item_query_rq,
    build_vendor_query_rq,
    parse_account_query_rs,
    parse_customer_query_rs,
    parse_item_query_rs,
    parse_vendor_query_rs,
)
from qb_session import QBSession


def missing_accounts(session: QBSession, account_names: List[str]) -> List[str]:
    """Return the subset of account_names that do not exist in QuickBooks."""
    unique_names = sorted(set(account_names))
    if not unique_names:
        return []
    request = build_account_query_rq(unique_names)
    response = session.process(request)
    found = parse_account_query_rs(response)
    return [n for n in unique_names if n not in found]


def missing_items(session: QBSession, item_names: List[str]) -> List[str]:
    """Return the subset of item_names that do not exist in QuickBooks.

    Items are assumed pre-existing (invoice lines reference real Items set
    up ahead of time), so unlike customers/vendors this is a hard-fail
    check, not a skip-if-exists one -- same semantics as missing_accounts.
    """
    unique_names = sorted(set(item_names))
    if not unique_names:
        return []
    request = build_item_query_rq(unique_names)
    response = session.process(request)
    found = parse_item_query_rs(response)
    return [n for n in unique_names if n not in found]


def existing_customer_names(session: QBSession, names: List[str]) -> Set[str]:
    """Return the subset of names that already exist as Customers in QB.

    Always queried live against QuickBooks (never cached from the local
    dedupe log), so an Add is only skipped when QuickBooks itself already
    has the name -- self-healing across sessions.
    """
    unique_names = sorted(set(names))
    if not unique_names:
        return set()
    request = build_customer_query_rq(unique_names)
    response = session.process(request)
    return parse_customer_query_rs(response)


def existing_vendor_names(session: QBSession, names: List[str]) -> Set[str]:
    """Return the subset of names that already exist as Vendors in QB. See
    existing_customer_names for why this is always a live query."""
    unique_names = sorted(set(names))
    if not unique_names:
        return set()
    request = build_vendor_query_rq(unique_names)
    response = session.process(request)
    return parse_vendor_query_rs(response)
