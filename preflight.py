"""Read-only checks against QuickBooks before any write."""
from __future__ import annotations

from typing import List

from qb_requests import build_account_query_rq, parse_account_query_rs
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
