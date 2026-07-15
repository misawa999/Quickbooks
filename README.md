# Simple Journal Importer

A minimal tool to import a JSON batch of **general journal entries** into
**QuickBooks Desktop Canada Pro 2021** via the QuickBooks SDK (qbXML over the
`QBXMLRP2` COM interface). Each entry optionally carries a foreign `currency`
and `exchange_rate`, so it supports multicurrency journal entries as well as
plain home-currency ones.

This is intentionally a scoped-down MVP: **journal entries only**, no
bank-statement parsing, no auto-creation of accounts/names. See "Non-goals"
below.

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
gui.py              # Tkinter GUI (browse, review, click Import)
schema.py          # Pydantic models for the batch format
qb_requests.py      # qbXML request builders + response parsers
qb_session.py       # COM connection/session lifecycle (Windows-only at runtime)
preflight.py        # account-existence check
dedupe.py           # import_log.jsonl read/append
import_batch.py     # CLI entry point + shared dry-run/commit logic (used by gui.py too)
sample_batch.json   # example batch (multicurrency + home-currency entries)
tests/               # schema, qbXML builder, dedupe, and emit-injection tests (no QuickBooks needed)
```

## Testing

```bash
pip install -r requirements.txt
pytest tests/ -v
```

All 16 tests run on any OS (they test schema validation, qbXML string
generation, and log dedupe logic directly — no COM/QuickBooks involved).

## Non-goals (v1)

- No bank statement parsing / PDF-CSV ingestion.
- No automatic FX rate lookup — rates go in the batch JSON.
- No auto-creation of accounts, customers, or vendors.
- No deposit/cheque transaction types — journal entries only.
- No GUI.
- No modification or deletion of existing QuickBooks transactions.
- No QuickBooks-side duplicate search (see Preflight checks above).

## Safety notes

- There is **no undo** for a QuickBooks journal entry insert via this tool.
  Always review the dry-run output before `--commit`.
- Test against a **backup copy** of the company file before pointing this at
  production, especially the first time and especially for multicurrency
  entries.
- If a `--commit` run dies partway through, just re-run the same batch file —
  already-logged `ok` entries are skipped automatically.
