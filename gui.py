#!/usr/bin/env python3
"""Minimal GUI for the QuickBooks importer.

For non-technical users: browse for a file, review the dry-run report, then
click Import. No command line needed. Can run from source via "QuickBooks
Importer.bat", or as a standalone packaged .exe built by build_exe.bat (see
README) -- the packaged .exe has NO console window at all, so every error
path below is deliberately routed through a visible dialog rather than
printed text, or it would vanish with zero trace.

Two tabs, sharing one window and one import log:
  - "Journal Entries (JSON)": the original flow, one JSON batch file of
    general journal entries (import_batch.py).
  - "Business Transactions (Excel)": customers/vendors/invoices/bills/
    payments from one .xlsx workbook (import_workbook.py).

Runs QuickBooks calls in a background thread so the window never freezes,
since COM calls to QuickBooks can take a few seconds each. Tkinter itself is
not thread-safe, so the background thread only ever puts text onto a queue;
the main thread drains that queue on a timer and is the only thing that
touches widgets.
"""
from __future__ import annotations

import json
import queue
import sys
import threading
import traceback
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from pydantic import ValidationError

from dedupe import load_processed_line_ids
from import_batch import (
    DEFAULT_LOG_PATH,
    all_account_names,
    load_batch,
    print_dry_run_report,
    run_commit,
)
from import_workbook import (
    all_account_names as workbook_account_names,
    all_item_names,
    load_workbook,
    print_workbook_dry_run_report,
    run_workbook_commit,
    preview_bill_resolutions,
    preview_invoice_resolutions,
)
from preflight import (
    existing_customer_names,
    existing_vendor_names,
    missing_accounts,
    missing_items,
)
from qb_session import QBSession, QBSessionError


class _TabBase:
    """Shared threading/queue/output-pane plumbing for a single tab.

    Not a tk widget itself -- subclasses build their own widgets inside a
    frame handed to them and call these helpers. Each tab gets its own
    queue/output pane/busy state, since the two import flows are
    independent of each other and can be reviewed side by side.
    """

    def __init__(self, root: tk.Tk, output: scrolledtext.ScrolledText, status_label: tk.Label,
                 browse_btn: tk.Button, import_btn: tk.Button):
        self.root = root
        self.output = output
        self.status_label = status_label
        self.browse_btn = browse_btn
        self.import_btn = import_btn
        self.dry_run_ok = False
        self.busy = False
        # Carries ("text", line) for output and ("done", (ok, status)) for
        # background-thread completion. Everything from a worker thread
        # goes through this queue and is only ever touched here in methods
        # that run on the main thread via _poll_queue -- Tkinter widgets
        # (and .after()) must not be touched from other threads.
        self.msg_queue: "queue.Queue[tuple]" = queue.Queue()
        self._poll_queue()

    def emit(self, line: str) -> None:
        """Safe to call from the background thread: just queues text."""
        self.msg_queue.put(("text", line))

    def _signal_done(self, ok: bool | None, status: str) -> None:
        """Safe to call from the background thread: queues completion."""
        self.msg_queue.put(("done", (ok, status)))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "text":
                    self.output.configure(state="normal")
                    self.output.insert("end", payload + "\n")
                    self.output.see("end")
                    self.output.configure(state="disabled")
                elif kind == "done":
                    ok, status = payload
                    if ok is not None:
                        self.dry_run_ok = ok
                    self.set_busy(False, status)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def clear_output(self) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")

    def set_busy(self, busy: bool, status: str = "") -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.browse_btn.configure(state=state)
        self.import_btn.configure(state="disabled" if busy or not self.dry_run_ok else "normal")
        self.status_label.configure(text=status)

    def run_in_background(self, target) -> None:
        self.set_busy(True, "Working...")

        def guarded() -> None:
            # A packaged --windowed .exe has no console, so an uncaught
            # exception here would otherwise kill the thread silently: the
            # status bar would stay stuck on "Working..." forever with no
            # explanation and no way to tell it crashed vs. is just slow.
            try:
                target()
            except Exception:
                self.emit("Unexpected error:")
                self.emit(traceback.format_exc())
                self._signal_done(False, "Unexpected error - see above.")

        thread = threading.Thread(target=guarded, daemon=True)
        thread.start()


class JournalEntryTab(_TabBase):
    """Tab 1: one JSON batch file of general journal entries."""

    def __init__(self, root: tk.Tk, frame: tk.Frame):
        self.batch_path: Path | None = None
        self.batch = None
        self.force_var = tk.BooleanVar(value=False)

        top = tk.Frame(frame, padx=10, pady=10)
        top.pack(fill="x")
        tk.Label(top, text="1. Make sure QuickBooks Desktop is open with your company file loaded.").pack(
            anchor="w"
        )

        file_row = tk.Frame(top, pady=8)
        file_row.pack(fill="x")
        tk.Label(file_row, text="2. Batch file:").pack(side="left")
        self.file_label = tk.Label(file_row, text="(none selected)", fg="#555555", anchor="w")
        self.file_label.pack(side="left", padx=8, fill="x", expand=True)
        browse_btn = tk.Button(file_row, text="Browse...", command=self.on_browse)
        browse_btn.pack(side="right")

        force_row = tk.Frame(top)
        force_row.pack(fill="x")
        tk.Checkbutton(
            force_row,
            text="Force re-import (send this batch's entries even if already logged as imported)",
            variable=self.force_var,
        ).pack(anchor="w")

        tk.Label(top, text="3. Review the dry-run report below, then click Import.").pack(
            anchor="w", pady=(8, 0)
        )

        bottom = tk.Frame(frame, padx=10, pady=10)
        bottom.pack(side="bottom", fill="x")
        status_label = tk.Label(bottom, text="", anchor="w")
        status_label.pack(side="left", fill="x", expand=True)
        import_btn = tk.Button(bottom, text="Import into QuickBooks", command=self.on_import, state="disabled")
        import_btn.pack(side="right")

        output = scrolledtext.ScrolledText(frame, wrap="word", state="disabled")
        output.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        super().__init__(root, output, status_label, browse_btn, import_btn)

    def on_browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Select a batch JSON file", filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        self.batch_path = Path(path)
        self.file_label.configure(text=str(self.batch_path))
        self.dry_run_ok = False
        self.import_btn.configure(state="disabled")
        self.clear_output()
        force = self.force_var.get()
        self.run_in_background(lambda: self._dry_run_worker(force))

    def on_import(self) -> None:
        if not self.batch_path or not self.dry_run_ok:
            return
        if not messagebox.askyesno(
            "Confirm import",
            "This will write the entries above into QuickBooks. There is no undo. Continue?",
            icon="warning",
        ):
            return
        force = self.force_var.get()
        self.clear_output()
        self.run_in_background(lambda: self._commit_worker(force))

    def _dry_run_worker(self, force: bool) -> None:
        try:
            batch = load_batch(self.batch_path)
        except ValidationError as e:
            self.emit("Batch validation failed:")
            self.emit(str(e))
            self._signal_done(False, "Invalid batch file - see report above.")
            return
        except (json.JSONDecodeError, FileNotFoundError) as e:
            self.emit(f"Could not read batch file: {e}")
            self._signal_done(False, "Could not read batch file.")
            return

        self.batch = batch
        skip_ids = set() if force else load_processed_line_ids(DEFAULT_LOG_PATH)
        if force:
            self.emit("Force re-import is ON: already-imported entries will NOT be skipped.\n")

        missing: list[str] = []
        connected = True
        try:
            with QBSession("") as session:
                missing = missing_accounts(session, all_account_names(batch))
        except QBSessionError as e:
            connected = False
            self.emit(f"Could not connect to QuickBooks: {e}\n")

        print_dry_run_report(batch, skip_ids, missing, emit=self.emit)

        ok = connected and not missing
        if not connected:
            status = "Could not connect to QuickBooks - see above. Import is disabled until it connects."
        elif missing:
            status = "Some accounts were not found in QuickBooks - see above. Fix the batch file and browse again."
        else:
            self.emit('Looks good. Click "Import into QuickBooks" to proceed.')
            status = "Dry run OK. Review the report, then click Import."

        self._signal_done(ok, status)

    def _commit_worker(self, force: bool) -> None:
        skip_ids = set() if force else load_processed_line_ids(DEFAULT_LOG_PATH)
        try:
            result_code = run_commit(
                self.batch,
                company_file="",
                log_path=DEFAULT_LOG_PATH,
                skip_ids=skip_ids,
                force=force,
                continue_on_error=True,
                emit=self.emit,
            )
        except QBSessionError as e:
            self.emit(f"Could not connect to QuickBooks: {e}")
            result_code = 1

        status = "Import finished - see summary above." if result_code == 0 else "Import finished with errors - see above."
        # Require a fresh dry-run before importing again, so the report on
        # screen always matches what's about to be sent.
        self._signal_done(False, status)


class WorkbookTab(_TabBase):
    """Tab 2: one Excel workbook of customers/vendors/invoices/bills/payments."""

    def __init__(self, root: tk.Tk, frame: tk.Frame):
        self.workbook_path: Path | None = None
        self.workbook = None
        self.force_var = tk.BooleanVar(value=False)

        top = tk.Frame(frame, padx=10, pady=10)
        top.pack(fill="x")
        tk.Label(top, text="1. Make sure QuickBooks Desktop is open with your company file loaded.").pack(
            anchor="w"
        )

        file_row = tk.Frame(top, pady=8)
        file_row.pack(fill="x")
        tk.Label(file_row, text="2. Workbook file:").pack(side="left")
        self.file_label = tk.Label(file_row, text="(none selected)", fg="#555555", anchor="w")
        self.file_label.pack(side="left", padx=8, fill="x", expand=True)
        browse_btn = tk.Button(file_row, text="Browse...", command=self.on_browse)
        browse_btn.pack(side="right")

        force_row = tk.Frame(top)
        force_row.pack(fill="x")
        tk.Checkbutton(
            force_row,
            text="Force re-import (send records even if already logged as imported)",
            variable=self.force_var,
        ).pack(anchor="w")

        tk.Label(
            top,
            text="3. Review the dry-run report below, then click Import. "
            "Customers/Vendors/Invoices/Bills are created before payments that reference them.",
            wraplength=680,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

        bottom = tk.Frame(frame, padx=10, pady=10)
        bottom.pack(side="bottom", fill="x")
        status_label = tk.Label(bottom, text="", anchor="w")
        status_label.pack(side="left", fill="x", expand=True)
        import_btn = tk.Button(bottom, text="Import into QuickBooks", command=self.on_import, state="disabled")
        import_btn.pack(side="right")

        output = scrolledtext.ScrolledText(frame, wrap="word", state="disabled")
        output.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        super().__init__(root, output, status_label, browse_btn, import_btn)

    def on_browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Select a workbook file", filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")]
        )
        if not path:
            return
        self.workbook_path = Path(path)
        self.file_label.configure(text=str(self.workbook_path))
        self.dry_run_ok = False
        self.import_btn.configure(state="disabled")
        self.clear_output()
        force = self.force_var.get()
        self.run_in_background(lambda: self._dry_run_worker(force))

    def on_import(self) -> None:
        if not self.workbook_path or not self.dry_run_ok:
            return
        if not messagebox.askyesno(
            "Confirm import",
            "This will write the records above into QuickBooks. There is no undo. Continue?",
            icon="warning",
        ):
            return
        force = self.force_var.get()
        self.clear_output()
        self.run_in_background(lambda: self._commit_worker(force))

    def _dry_run_worker(self, force: bool) -> None:
        try:
            wb = load_workbook(self.workbook_path)
        except ValidationError as e:
            self.emit("Workbook validation failed:")
            self.emit(str(e))
            self._signal_done(False, "Invalid workbook file - see report above.")
            return
        except (ValueError, FileNotFoundError) as e:
            self.emit(f"Could not read workbook file: {e}")
            self._signal_done(False, "Could not read workbook file.")
            return

        self.workbook = wb
        skip_ids = set() if force else load_processed_line_ids(DEFAULT_LOG_PATH)
        if force:
            self.emit("Force re-import is ON: already-imported records will NOT be skipped.\n")

        missing_acc: list[str] = []
        missing_it: list[str] = []
        existing_cust: set = set()
        existing_vend: set = set()
        invoice_resolution: dict = {}
        bill_resolution: dict = {}
        connected = True
        try:
            with QBSession("") as session:
                missing_acc = missing_accounts(session, workbook_account_names(wb))
                missing_it = missing_items(session, all_item_names(wb))
                existing_cust = existing_customer_names(session, [c.name for c in wb.customers])
                existing_vend = existing_vendor_names(session, [v.name for v in wb.vendors])
                invoice_resolution = preview_invoice_resolutions(session, wb.customer_payments)
                bill_resolution = preview_bill_resolutions(session, wb.vendor_payments)
        except QBSessionError as e:
            connected = False
            self.emit(f"Could not connect to QuickBooks: {e}\n")

        print_workbook_dry_run_report(
            wb, skip_ids, missing_acc, missing_it, existing_cust, existing_vend,
            invoice_resolution, bill_resolution, emit=self.emit,
        )

        ok = connected and not missing_acc and not missing_it
        if not connected:
            status = "Could not connect to QuickBooks - see above. Import is disabled until it connects."
        elif missing_acc or missing_it:
            status = "Some accounts/items were not found in QuickBooks - see above. Fix the workbook and browse again."
        else:
            self.emit('Looks good. Click "Import into QuickBooks" to proceed.')
            status = "Dry run OK. Review the report, then click Import."

        self._signal_done(ok, status)

    def _commit_worker(self, force: bool) -> None:
        skip_ids = set() if force else load_processed_line_ids(DEFAULT_LOG_PATH)
        try:
            result_code = run_workbook_commit(
                self.workbook,
                company_file="",
                log_path=DEFAULT_LOG_PATH,
                skip_ids=skip_ids,
                force=force,
                continue_on_error=True,
                emit=self.emit,
            )
        except QBSessionError as e:
            self.emit(f"Could not connect to QuickBooks: {e}")
            result_code = 1

        status = "Import finished - see summary above." if result_code == 0 else "Import finished with errors - see above."
        self._signal_done(False, status)


class ImporterApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("QuickBooks Importer")
        self.root.geometry("760x620")

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=(10, 10), pady=(10, 0))

        je_frame = tk.Frame(notebook)
        wb_frame = tk.Frame(notebook)
        notebook.add(je_frame, text="Journal Entries (JSON)")
        notebook.add(wb_frame, text="Business Transactions (Excel)")

        self.journal_tab = JournalEntryTab(self.root, je_frame)
        self.workbook_tab = WorkbookTab(self.root, wb_frame)

        # Both tabs write to the same log file, so log-clearing lives
        # outside the notebook and is shared.
        log_row = tk.Frame(self.root, padx=10, pady=(4, 0))
        log_row.pack(fill="x")
        tk.Label(
            log_row, text=f"Log file: {DEFAULT_LOG_PATH}", fg="#777777", font=("TkDefaultFont", 8)
        ).pack(side="left", anchor="w")
        self.clear_log_btn = tk.Button(
            log_row, text="Clear Import History...", command=self.on_clear_log, font=("TkDefaultFont", 8)
        )
        self.clear_log_btn.pack(side="right")
        tk.Frame(self.root, height=10).pack()

    def on_clear_log(self) -> None:
        if self.journal_tab.busy or self.workbook_tab.busy:
            return
        if not DEFAULT_LOG_PATH.exists():
            messagebox.showinfo(
                "Clear Import History", "There is no import history yet - nothing to clear."
            )
            return
        if not messagebox.askyesno(
            "Clear Import History",
            "This clears the de-duplication history for ALL past imports done by this "
            "tool (both tabs), not just the currently selected file. After clearing, "
            "previously imported records will look brand new and could be inserted into "
            "QuickBooks AGAIN if you re-run an old batch/workbook file.\n\n"
            "This does NOT undo or remove anything already in QuickBooks - it only "
            "resets this tool's own memory of what it already sent.\n\n"
            "The current log will be backed up (not deleted) so it can be recovered "
            "if needed. Continue?",
            icon="warning",
        ):
            return
        try:
            backup_path = DEFAULT_LOG_PATH.with_name(
                f"{DEFAULT_LOG_PATH.stem}.backup-{datetime.now():%Y%m%d-%H%M%S}{DEFAULT_LOG_PATH.suffix}"
            )
            DEFAULT_LOG_PATH.rename(backup_path)
        except OSError as e:
            messagebox.showerror("Clear Import History", f"Could not clear the log: {e}")
            return
        messagebox.showinfo(
            "Clear Import History",
            f"Done. The previous log was backed up to:\n{backup_path}",
        )


def _show_fatal_error(message: str) -> None:
    """Last-resort error display. Tries a Tk dialog first; if Tk itself is
    broken, falls back to a raw Win32 message box (needs no Tk at all) so a
    startup failure is never completely invisible in a --windowed .exe."""
    try:
        messagebox.showerror("QuickBooks Importer - Error", message)
        return
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, "QuickBooks Importer - Error", 0x10)
        except Exception:
            pass


def main() -> None:
    try:
        root = tk.Tk()
    except Exception:
        _show_fatal_error(f"Could not start the GUI toolkit:\n\n{traceback.format_exc()}")
        return

    # Tkinter's default behavior for an exception raised inside a widget
    # callback (e.g. a button click) is to print it to stderr and keep
    # running -- invisible in a --windowed .exe with no stderr to see.
    def report_callback_exception(exc_type, exc_value, exc_tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        _show_fatal_error(f"QuickBooks Importer hit an unexpected error:\n\n{text}")

    root.report_callback_exception = report_callback_exception

    try:
        ImporterApp(root)
        root.mainloop()
    except Exception:
        _show_fatal_error(f"QuickBooks Importer crashed on startup:\n\n{traceback.format_exc()}")


if __name__ == "__main__":
    main()
