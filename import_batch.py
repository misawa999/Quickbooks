#!/usr/bin/env python3
"""Import a JSON batch of general journal entries into QuickBooks Desktop.

Usage:
    python import_batch.py batch.json                # dry run (default, no writes)
    python import_batch.py batch.json --commit        # actually write to QuickBooks

Dry-run works without QuickBooks running (schema + account preflight are
skipped gracefully if a connection can't be made). --commit requires
QuickBooks Desktop to be open with the target company file, on Windows,
with the QBSDK + pywin32 installed.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Set

from pydantic import ValidationError

from dedupe import append_log, load_processed_line_ids
from preflight import missing_accounts
from qb_requests import build_journal_entry_add_rq, parse_journal_entry_add_rs
from qb_session import QBSession, QBSessionError
from schema import Batch


def load_batch(path: Path) -> Batch:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Batch.model_validate(raw)


def log_safely(log_path: Path, record: dict) -> None:
    """Append to the import log, but never let a logging failure hide a
    real QuickBooks result or crash mid-batch. Warn loudly instead."""
    try:
        append_log(log_path, record)
    except OSError as e:
        print(
            f"  WARNING: could not write to log file {log_path} ({e}). "
            f"The above result is accurate, but this entry (line_id={record['line_id']}) "
            f"will NOT be recognized as already-imported on the next run — "
            f"fix the log file location/permissions before re-running this batch."
        )


def all_account_names(batch: Batch) -> List[str]:
    names: List[str] = []
    for entry in batch.transactions:
        names.extend(line.account for line in entry.lines)
    return names


def print_dry_run_report(batch: Batch, skip_ids: Set[str], missing: List[str]) -> None:
    print(f"Batch: {batch.batch_id}  ({len(batch.transactions)} entries)\n")
    if missing:
        print("PREFLIGHT FAILED - accounts not found in QuickBooks:")
        for name in missing:
            print(f"  - {name}")
        print()

    for entry in batch.transactions:
        dup = "  [DUPLICATE - already imported]" if entry.line_id in skip_ids else ""
        cur = f"{entry.currency} @ {entry.exchange_rate}" if entry.currency else "home currency"
        print(f"[{entry.line_id}] {entry.date}  {cur}{dup}")
        if entry.memo:
            print(f"    memo: {entry.memo}")
        for line in entry.lines:
            side = f"DR {line.debit}" if line.debit > 0 else f"CR {line.credit}"
            extra = f"  ({line.memo})" if line.memo else ""
            print(f"    {side:>14}  {line.account}{extra}")
        print()


def run_commit(
    batch: Batch,
    company_file: str,
    log_path: Path,
    skip_ids: Set[str],
    force: bool,
    continue_on_error: bool,
) -> int:
    inserted = skipped = failed = 0
    with QBSession(company_file) as session:
        missing = missing_accounts(session, all_account_names(batch))
        if missing:
            print("Aborting: accounts not found in QuickBooks:")
            for name in missing:
                print(f"  - {name}")
            return 1

        for entry in batch.transactions:
            if entry.line_id in skip_ids and not force:
                print(f"[{entry.line_id}] skipped (already imported)")
                skipped += 1
                continue

            request = build_journal_entry_add_rq(entry)
            try:
                response = session.process(request)
                result = parse_journal_entry_add_rs(response)
            except Exception as e:
                # Report the real outcome BEFORE touching the log file — a
                # log-write failure must never hide whether QuickBooks
                # actually accepted or rejected the transaction.
                failed += 1
                print(f"[{entry.line_id}] ERROR: {e}")
                log_safely(
                    log_path,
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "batch_id": batch.batch_id,
                        "line_id": entry.line_id,
                        "status": "error",
                        "qb_txn_id": None,
                        "qbxml_status_code": None,
                        "message": str(e),
                    },
                )
                if not continue_on_error:
                    break
                continue

            if result["status_code"] == 0:
                inserted += 1
                print(f"[{entry.line_id}] OK -> TxnID {result['txn_id']}")
                log_safely(
                    log_path,
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "batch_id": batch.batch_id,
                        "line_id": entry.line_id,
                        "status": "ok",
                        "qb_txn_id": result["txn_id"],
                        "qbxml_status_code": result["status_code"],
                        "message": result["status_message"],
                    },
                )
            else:
                failed += 1
                print(f"[{entry.line_id}] FAILED ({result['status_code']}): {result['status_message']}")
                log_safely(
                    log_path,
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "batch_id": batch.batch_id,
                        "line_id": entry.line_id,
                        "status": "error",
                        "qb_txn_id": None,
                        "qbxml_status_code": result["status_code"],
                        "message": result["status_message"],
                    },
                )
                if not continue_on_error:
                    break

    print(f"\ninserted={inserted} skipped={skipped} failed={failed}")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import a JSON batch of general journal entries into QuickBooks Desktop."
    )
    parser.add_argument("batch_file", type=Path)
    parser.add_argument(
        "--company-file",
        default="",
        help="Path to the .qbw company file (blank = currently open file)",
    )
    parser.add_argument("--log-file", type=Path, default=Path("import_log.jsonl"))
    parser.add_argument(
        "--commit", action="store_true", help="Actually write to QuickBooks. Default is dry-run."
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-import entries already marked ok in the log."
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Keep going after a failed insert instead of stopping.",
    )
    args = parser.parse_args()

    try:
        batch = load_batch(args.batch_file)
    except ValidationError as e:
        print("Batch validation failed:")
        print(e)
        return 1
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Could not read batch file: {e}")
        return 1

    skip_ids = set() if args.force else load_processed_line_ids(args.log_file)

    if not args.commit:
        missing: List[str] = []
        try:
            with QBSession(args.company_file) as session:
                missing = missing_accounts(session, all_account_names(batch))
        except QBSessionError as e:
            print(f"(preflight skipped - could not connect to QuickBooks: {e})\n")
        print_dry_run_report(batch, skip_ids, missing)
        print("Dry run only - nothing was written. Re-run with --commit to import.")
        return 0

    try:
        return run_commit(
            batch, args.company_file, args.log_file, skip_ids, args.force, args.continue_on_error
        )
    except QBSessionError as e:
        print(f"Could not connect to QuickBooks: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
