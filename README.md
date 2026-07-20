# Simple Journal Importer

A minimal tool to import business data into **QuickBooks Desktop Canada Pro
2021** via the QuickBooks SDK (qbXML over the `QBXMLRP2` COM interface). Two
independent flows, sharing one GUI, one CLI-style dry-run/`--commit` design,
and one import log:

- **Journal entries** (`import_batch.py`, one JSON batch file) — the
  original flow. Each entry optionally carries a foreign `currency` and
  `exchange_rate` for multicurrency postings.
- **Business transactions** (`import_workbook.py`, one Excel workbook) —
  Customers, Vendors, Invoices, Vendor Bills, Customer Payments, and Vendor
  Bill Payments, each with optional per-transaction `currency`/
  `exchange_rate`. Invoices reference pre-existing Items; Bills use plain
  expense accounts; Customer/Vendor Payments are linked to the specific
  invoice(s)/bill(s) they settle. See "Business transactions (Excel
  workbook)" below.

Both flows require Multicurrency to already be enabled in the company file
if you use `currency`/`exchange_rate` fields at all (see "First-time
QuickBooks setup"). No bank-statement parsing, no automatic FX rate lookup.
See "Non-goals" below.

## Quick start — for office staff (standalone .exe, no Python needed)

The maintainer builds `QuickBooks Importer.exe` once (see "Building the
standalone .exe" below) and hands that single file to coworkers — their
computer needs QuickBooks Desktop + the QuickBooks SDK installed (see
Requirements), but **not Python, not this repo, not pip installs**.

1. Make sure QuickBooks Desktop is open with the company file loaded.
2. Double-click **`QuickBooks Importer.exe`**. A window opens — no black
   console, no commands to type.
3. Click **Browse...** and pick the batch JSON file for this import.
4. The window automatically shows a dry-run report: exactly what would be
   imported, with any problems (missing accounts, can't reach QuickBooks)
   called out clearly. Nothing is written yet.
5. Read the report. If it looks right, click **Import into QuickBooks**,
   confirm the popup, and watch the result appear in the same window.

That's the entire workflow. The window enforces the safe order — it won't
let you click Import until a clean dry-run has run for the file you have
selected.

**Re-importing something already sent**, e.g. to redo a batch after fixing
a typo'd account name: check **"Force re-import"** before browsing/
importing. This only affects the currently selected batch — it re-sends
those specific entries even though they're already logged as done,
without touching the history of any other batch. This is almost always
what you want, rather than the blunter "Clear Import History..." button
next to the log file path, which wipes the de-duplication memory for
*every* past import (it backs up the old log with a timestamp instead of
deleting it, but you'd still lose track of what's already in QuickBooks
unless you go read that backup file yourself) — use that only if you
genuinely need a full reset, not just to redo one batch.

(Running `gui.py`/`QuickBooks Importer.bat` from source instead of the
packaged `.exe` works identically, just needs Python set up — see below.)

## Building the standalone .exe

On a machine with this repo and 32-bit Python set up (see Requirements),
double-click **`build_exe.bat`**. It installs `pyinstaller` and packages
`gui.py` into a single file at `dist\QuickBooks Importer.exe`. Copy that
one file to a coworker's computer — that's the entire distribution, no
folder of source files needed. Re-run `build_exe.bat` whenever `gui.py` or
anything it imports changes, and redistribute the new `.exe`.

Note this only packages the *app*; it does not and cannot bundle the
QuickBooks SDK itself, since installing that registers a COM component
with Windows (a system-level step, not something that fits inside a
portable `.exe`) — the SDK still needs installing separately on each
machine, same as QuickBooks Desktop itself.

## Quick start — for whoever maintains this tool (CLI, scriptable)

1. Make sure QuickBooks Desktop is open with your company file loaded.
2. Edit `sample_batch.json` (or make a copy) with your real transaction —
   see "Batch JSON format" below for the shape.
3. Double-click **`run_import.bat`**.
4. When prompted, type the batch file's name (or drag the file onto the
   window) and press Enter.
5. It runs a dry-run first and shows you exactly what would be imported.
   Review it, then type `YES` to actually import, or anything else to
   cancel — nothing is written unless you type `YES`.

Both `.bat` launchers are portable: they always run relative to their own
folder (not wherever they were launched from) and auto-detect whichever
32-bit Python is installed, so moving the whole folder to a different
computer works without editing anything — as long as that computer also
has 32-bit Python, QuickBooks Desktop, the QBSDK, and this tool's pip
packages installed (see Requirements below; `pip install -r
requirements.txt` needs to be re-run on each new computer, same as any
Python tool). Note the import log starts fresh per computer/user (it
lives under that user's Documents folder), so a batch already imported on
one machine won't be recognized as a duplicate on another — check the
dry-run report before committing if you're not sure.

Everything below is the "how it works" / troubleshooting reference.

## How it works

```
batch.json  →  validate (Pydantic)  →  dry-run report  →  operator reviews
                                              │
                                     --commit (explicit flag)
                                              ▼
                                  qbXML JournalEntryAddRq → QuickBooks
                                              │
                                              ▼
                                     import_log.jsonl (dedupe/audit trail)
```

- **Dry-run is the default.** Nothing is ever written to QuickBooks unless
  you pass `--commit`.
- Entries are inserted **one at a time**, not batched in a single request, so
  one bad entry doesn't poison the rest of the run.
- Every insert (success or failure) is appended to a log file. Re-running
  the same batch file skips any `line_id` already logged as `ok` — safe to
  re-run after a crash or partial failure. By default this log lives at
  `Documents\QuickBooks Importer\import_log.jsonl` (created automatically
  on first use) — override with `--log-file` if you want it elsewhere. The
  path in use is always printed at the top of every run.

## Requirements

**Every machine that runs this tool** (whether the packaged `.exe` or from
source) needs:

- **Windows**, with QuickBooks Desktop Canada Pro 2021 installed and the
  company file open.
- [QuickBooks SDK](https://developer.intuit.com/app/developer/qbdesktop/docs/get-started) — the last release (v16) works with QB 2021. This is the
  one piece that can't be packaged away — it registers a COM component
  with Windows, which is a system-level install step independent of
  Python or how the rest of the tool is distributed.

**Only the build/maintainer machine** — the one that produces `QuickBooks
Importer.exe` for everyone else — additionally needs:

- **32-bit Python**, specifically. QuickBooks Desktop 2021 is a 32-bit
  application, and its SDK's COM component can't reliably be driven from a
  64-bit process — with 64-bit Python you'll hit `Could not start
  QuickBooks` even though everything else is set up correctly. If you
  already have 64-bit Python installed for other things, that's fine,
  just install a 32-bit copy alongside it (installer at python.org, pick
  the file labeled "Windows installer (32-bit)"; uncheck "Add to PATH" so
  it doesn't fight with your existing install). Then find its version tag
  with:
  ```
  py -0
  ```
  which lists something like `-V:3.13-32   Python 3.13 (32-bit)`. The
  `.bat` launchers and `build_exe.bat` all detect this automatically — you
  only need the exact tag (e.g. `-3.13-32`) if running commands directly
  (see "Usage (manual / advanced)" below).
- With the right (32-bit) Python, install the packages this tool needs —
  substitute your own tag from `py -0`:
  ```
  py -3.13-32 -m pip install -r requirements.txt
  ```
  (`pydantic`, `pywin32` on Windows, `pytest` for the test suite.) This
  needs to be re-run once on each new computer you develop/build from.
- The GUI (`gui.py` / `QuickBooks Importer.bat`) uses `tkinter`, which
  ships built into the standard python.org Windows installer — nothing
  extra to install for it specifically.

Coworkers running the packaged `QuickBooks Importer.exe` need none of the
above Python setup — just QuickBooks Desktop and the SDK.

Schema validation, the dry-run report, and the test suite all run fine on
any OS with no QuickBooks installed — only `--commit` (or clicking Import
in the GUI) requires the real Windows/QuickBooks environment.

## First-time QuickBooks setup

1. Open the company file in QuickBooks Desktop.
2. Run the tool once (e.g. a dry-run against a real batch). QuickBooks will
   pop up an application-access dialog the first time it sees this tool
   (`SimpleJournalImporter`) — choose **"Yes, always; allow access even if
   QuickBooks is not running"** so subsequent runs don't need the UI open
   to be confirmed each time (you still need QuickBooks open for the COM
   call to succeed).
3. If you use multicurrency entries: **Multicurrency must already be
   enabled** in the company file (Edit → Preferences → Multiple Currencies).
   This is **irreversible** in QuickBooks — enable it deliberately, and test
   against a backup copy of the company file first, not production.

## Batch JSON format

```json
{
  "batch_id": "example_2026-07",
  "transactions": [
    {
      "line_id": "je-2026-07-001",
      "date": "2026-07-01",
      "memo": "Office rent, July",
      "currency": "CHF",
      "exchange_rate": 1.0962,
      "lines": [
        { "account": "OCBC Bank (CHF)", "credit": 1250.00 },
        { "account": "Uncategorized Expenses", "debit": 1250.00 }
      ]
    },
    {
      "line_id": "je-2026-07-002",
      "date": "2026-07-02",
      "lines": [
        { "account": "Uncategorised Deposits", "credit": 500.00 },
        { "account": "OCBC Bank (USD)", "debit": 500.00 }
      ]
    }
  ]
}
```

Field rules:
- `line_id`: unique per transaction, stable across re-runs. This is the
  dedupe key, and is prefixed as `[line_id]` onto every line's memo so you
  can find it in the register. (Not put in QuickBooks' `RefNumber` field —
  that's capped at 11 characters and silently rejects anything longer.)
- `lines`: at least 2. Each line has **exactly one** of `debit` or `credit`
  set (not both, not neither). The entry must balance (total debit == total
  credit) or it's rejected before anything is sent to QuickBooks.
- `memo` (entry-level, optional): QuickBooks' `JournalEntryAdd` request has
  no header-level memo field, so this is applied to every line that doesn't
  already have its own `memo`. Set a per-line `memo` instead if you want
  different text on the debit vs. credit side.
- `currency` / `exchange_rate`: both optional together. Omit both for a
  home-currency entry. If you set `currency`, `exchange_rate` is required
  and must be > 0. Convention: **home-currency units per 1 unit of foreign
  currency** (e.g. a CHF rate around 1.10, not 0.91) — this matches
  QuickBooks' own `ExchangeRate` field. If your numbers come out roughly
  inverted, check this first.
  Use a plain ISO code (`USD`, `CAD`, `EUR`, `GBP`, `CHF`, `JPY`, `AUD`,
  `HKD`, `SGD`, `CNY`, `INR`, `NZD`, `MXN`) — `qb_requests.py`'s
  `CURRENCY_NAMES` table translates it to QuickBooks' actual Currency List
  name (e.g. `USD` → "US Dollar"), since that's what `CurrencyRef` must
  match exactly, not the ISO code. A code outside that table is sent
  through unchanged, so use the exact QuickBooks list name for anything
  not listed. Requires Multicurrency to already be enabled in the company
  file (irreversible — see Phase 0 in the original build spec) and the
  currency to be **active**, not just present, in Lists → Currency List.
- `account`: exact QuickBooks account name (case-sensitive), checked to
  exist before any writes (see Preflight below).

See `sample_batch.json` for a working example (one multicurrency entry, one
home-currency entry).

## Business transactions (Excel workbook)

`import_workbook.py` (or the "Business Transactions (Excel)" tab in the GUI)
imports one `.xlsx` workbook with up to six sheets. Every sheet is optional
— a workbook can contain any subset. Sheet names and column headers are
matched exactly (case-sensitive); column order doesn't matter.

Invoices, Bills, CustomerPayments, and VendorPayments are "tidy" sheets: one
row per line item, with header fields (party name, date, currency, etc.)
repeated on every row that shares the same key column. All rows sharing a
key must agree on every header field, or the import fails with a clear error
naming the mismatch.

| Sheet | Key column | Header columns | Line columns |
|---|---|---|---|
| `Customers` | `customer_name` (one row per customer) | `company_name`, `currency`, `email`, `phone`, `bill_address_line1..5`, `memo` | — |
| `Vendors` | `vendor_name` (one row per vendor) | `company_name`, `currency`, `email`, `phone`, `address_line1..5`, `memo` | — |
| `Invoices` | `invoice_number` | `customer_name`, `invoice_date`, `due_date`, `terms`, `currency`, `exchange_rate`, `ar_account`, `memo` | `item_name`, `description`, `quantity`, `rate`, `amount` |
| `Bills` | `bill_number` | `vendor_name`, `bill_date`, `due_date`, `currency`, `exchange_rate`, `ap_account`, `memo` | `account`, `description`, `amount` |
| `CustomerPayments` | `payment_id` | `customer_name`, `payment_date`, `deposit_to_account`, `ar_account`, `currency`, `exchange_rate`, `payment_method`, `ref_number`, `memo` | `applied_invoice_number`, `applied_amount` |
| `VendorPayments` | `payment_id` | `vendor_name`, `payment_date`, `bank_account`, `ap_account`, `currency`, `exchange_rate`, `check_number`, `memo` | `applied_bill_number`, `applied_amount` |

Notes:

- **Invoice lines reference Items**, not accounts — `item_name` must match
  an existing entry in QuickBooks' Item List exactly. This is a qbXML
  requirement (`InvoiceAdd` lines use `ItemRef`), not a choice made here.
  Bill lines use plain expense accounts instead, same convention as journal
  entries.
- **Payments must be linked** to the specific invoice(s)/bill(s) they
  settle — there's no unapplied/on-account payment support. Each
  `CustomerPayments`/`VendorPayments` row applies a specific amount to one
  invoice/bill number; a payment settling several invoices is several rows
  sharing the same `payment_id`.
- `invoice_number` / `bill_number` / a payment's `ref_number` /
  `check_number` are all sent to QuickBooks as `RefNumber`, which QuickBooks
  Desktop caps at **11 characters** — anything longer is rejected during
  validation, before any QuickBooks call is made.
- `currency` / `exchange_rate` follow the same convention as journal
  entries (see above): both optional together, home-currency-per-foreign-
  unit, ISO codes translated via `CURRENCY_NAMES`. A customer's/vendor's
  currency is fixed for its lifetime in QuickBooks multicurrency, so if a
  `Customers`/`Vendors` sheet is present, every invoice/bill against that
  party must use the same currency (checked at load time, not just at
  QuickBooks-submission time).
- **Customers and Vendors are skip-if-exists**, not update — if a name
  already exists in QuickBooks (checked live on every run, not from the
  local log), the Add is skipped rather than erroring or overwriting.
- Processing order is fixed: Customers/Vendors → Invoices/Bills →
  CustomerPayments/VendorPayments, since each stage depends on records
  created by the one before it. Payments resolve their target invoice/bill
  number to QuickBooks' internal `TxnID` via a live query at commit time
  (`txn_lookup.py`) — this only succeeds once the invoice/bill actually
  exists in QuickBooks, whether created in this same run or an earlier one.

Same dry-run-first workflow as the journal entry flow:

```bash
python import_workbook.py transactions.xlsx                # dry run
python import_workbook.py transactions.xlsx --commit        # write to QuickBooks
```

## Usage (manual / advanced)

`run_import.bat` covers day-to-day use. For scripting, or when you need a
flag it doesn't expose, call the CLI directly (substitute your actual
32-bit Python command — `py -3.13-32` on the reference machine this was
built against, see "Requirements" below for how to find yours):

```bash
# Validate + preview, writes nothing
python import_batch.py sample_batch.json

# Actually import into QuickBooks
python import_batch.py sample_batch.json --commit

# Point at a specific company file instead of "whatever's currently open"
python import_batch.py sample_batch.json --commit --company-file "C:\path\to\Company.QBW"

# Use a different log file location than the Documents default
python import_batch.py sample_batch.json --commit --log-file "C:\path\to\import_log.jsonl"

# Re-import entries already marked ok in the log (use with care)
python import_batch.py sample_batch.json --commit --force

# Keep going past a failed entry instead of stopping at the first error
python import_batch.py sample_batch.json --commit --continue-on-error
```

Exit code is `0` if everything succeeded (or it was a clean dry-run), `1` if
anything failed or was aborted.

## Preflight checks

Before any write, the tool queries QuickBooks (read-only) for every account
name referenced in the batch. If any are missing, the whole run aborts with
no writes — no partial imports from a typo'd account name.

**Not included in this MVP:** a QuickBooks-side duplicate search (matching
existing transactions by date/amount/account). Dedupe here is local-log-only
(`import_log.jsonl`, keyed on `line_id`). This is a known simplification —
if you re-import a batch after deleting/editing `import_log.jsonl`, or hand
someone a batch with a reused `line_id` for a genuinely different
transaction, QuickBooks won't catch it. Review the dry-run report before
`--commit`.

## Logging

`import_log.jsonl` — append-only, one JSON object per attempted insert:

```json
{"ts": "...", "batch_id": "...", "line_id": "...", "status": "ok|error", "qb_txn_id": "...", "qbxml_status_code": 0, "message": ""}
```

Never edit this file by hand except to deliberately forget an entry (e.g.
to intentionally re-run it with `--force` semantics via a fresh log).

## Repo layout

```
build_exe.bat       # maintainer-only: packages gui.py -> dist\QuickBooks Importer.exe
QuickBooks Importer.bat  # GUI launcher (from source) -- or use the packaged .exe instead
run_import.bat      # CLI launcher: dry-run -> type YES -> commit
gui.py              # Tkinter GUI, two tabs: journal entries (JSON) + business transactions (Excel)
schema.py          # Pydantic models for both the journal-entry batch and the workbook entities
qb_requests.py      # qbXML request builders + response parsers (all entity types)
qb_session.py       # COM connection/session lifecycle (Windows-only at runtime)
preflight.py        # account/item existence checks, customer/vendor skip-if-exists checks
txn_lookup.py        # live RefNumber -> TxnID resolution for linking payments to invoices/bills
dedupe.py           # import_log.jsonl read/append (shared by both flows, namespaced keys)
import_batch.py     # CLI entry point + shared dry-run/commit logic for journal entries
import_workbook.py  # CLI entry point + shared dry-run/commit logic for business transactions
sample_batch.json   # example journal-entry batch (multicurrency + home-currency entries)
tests/               # schema, qbXML builder, dedupe, and emit-injection tests (no QuickBooks needed)
```

## Testing

```bash
pip install -r requirements.txt
pytest tests/ -v
```

All tests run on any OS (they test schema validation, qbXML string
generation, workbook loading, and log dedupe logic directly — no
COM/QuickBooks involved). The one thing tests can't cover is exact qbXML
element ordering for the newer Customer/Vendor/Invoice/Bill/Payment request
types — see the ordering note at the top of `qb_requests.py` and verify
against a backup company file before relying on them in production.

## Non-goals (v1)

- No bank statement parsing / PDF-CSV ingestion.
- No automatic FX rate lookup — rates go in the batch JSON / workbook.
- No update/edit of existing customers, vendors, invoices, or bills — only
  create-if-not-already-present.
- No unapplied/on-account payments — customer and vendor payments must be
  linked to specific invoices/bills.
- No modification or deletion of existing QuickBooks transactions.
- No QuickBooks-side duplicate search beyond RefNumber/name existence
  checks (see Preflight checks above).

## Safety notes

- There is **no undo** for a QuickBooks journal entry insert via this tool.
  Always review the dry-run output before `--commit`.
- Test against a **backup copy** of the company file before pointing this at
  production, especially the first time and especially for multicurrency
  entries.
- If a `--commit` run dies partway through, just re-run the same batch file —
  already-logged `ok` entries are skipped automatically.
