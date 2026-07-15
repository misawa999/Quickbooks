#!/usr/bin/env python3
"""Minimal GUI for the QuickBooks journal importer.

For non-technical users: browse for a batch JSON file, review the dry-run
report, then click Import. No command line needed. Can run from source via
"QuickBooks Importer.bat", or as a standalone packaged .exe built by
build_exe.bat (see README) -- the packaged .exe has NO console window at
all, so every error path below is deliberately routed through a visible
dialog rather than printed text, or it would vanish with zero trace.

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
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext

from pydantic import ValidationError

from dedupe import load_processed_line_ids
from import_batch import (
    DEFAULT_LOG_PATH,
    all_account_names,
    load_batch,
    print_dry_run_report,
    run_commit,
)
from preflight import missing_accounts
from qb_session import QBSession, QBSessionError


class ImporterApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("QuickBooks Journal Importer")
        self.root.geometry("720x560")

        self.batch_path: Path | None = None
        self.batch = None
        self.dry_run_ok = False
        # Carries ("text", line) for output and ("done", (ok, status)) for
        # background-thread completion. Everything from a worker thread
        # goes through this queue and is only ever touched here in
        # __init__/methods that run on the main thread via _poll_queue --
        # Tkinter widgets (and .after()) must not be touched from other
        # threads.
        self.msg_queue: "queue.Queue[tuple]" = queue.Queue()
        self.busy = False

        self._build_widgets()
        self._poll_queue()

    def _build_widgets(self) -> None:
        top = tk.Frame(self.root, padx=10, pady=10)
        top.pack(fill="x")

        tk.Label(top, text="1. Make sure QuickBooks Desktop is open with your company file loaded.").pack(
            anchor="w"
        )

        file_row = tk.Frame(top, pady=8)
        file_row.pack(fill="x")
        tk.Label(file_row, text="2. Batch file:").pack(side="left")
        self.file_label = tk.Label(file_row, text="(none selected)", fg="#555555", anchor="w")
        self.file_label.pack(side="left", padx=8, fill="x", expand=True)
        self.browse_btn = tk.Button(file_row, text="Browse...", command=self.on_browse)
        self.browse_btn.pack(side="right")

        log_row = tk.Frame(top)
        log_row.pack(fill="x")
        tk.Label(
            log_row, text=f"Log file: {DEFAULT_LOG_PATH}", fg="#777777", font=("TkDefaultFont", 8)
        ).pack(anchor="w")

        tk.Label(top, text="3. Review the dry-run report below, then click Import.").pack(
            anchor="w", pady=(8, 0)
        )

        # Pack the bottom bar with side="bottom" BEFORE the expanding text
        # box below, so it always reserves its own space first -- packed
        # in the other order, the text box's expand=True can claim space
        # the button row needs, clipping the button off the bottom edge.
        bottom = tk.Frame(self.root, padx=10, pady=10)
        bottom.pack(side="bottom", fill="x")
        self.status_label = tk.Label(bottom, text="", anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True)
        self.import_btn = tk.Button(
            bottom, text="Import into QuickBooks", command=self.on_import, state="disabled"
        )
        self.import_btn.pack(side="right")

        self.output = scrolledtext.ScrolledText(self.root, wrap="word", state="disabled")
        self.output.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    # -- UI helpers -------------------------------------------------
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

    # -- Actions ------------------------------------------------------
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
        self._run_in_background(self._dry_run_worker)

    def on_import(self) -> None:
        if not self.batch_path or not self.dry_run_ok:
            return
        if not messagebox.askyesno(
            "Confirm import",
            "This will write the entries above into QuickBooks. "
            "There is no undo. Continue?",
            icon="warning",
        ):
            return
        self.clear_output()
        self._run_in_background(self._commit_worker)

    def _run_in_background(self, target) -> None:
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

    # -- Background workers (must never touch tkinter widgets directly) --
    def _dry_run_worker(self) -> None:
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
        skip_ids = load_processed_line_ids(DEFAULT_LOG_PATH)

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
            self.emit("Looks good. Click \"Import into QuickBooks\" to proceed.")
            status = "Dry run OK. Review the report, then click Import."

        self._signal_done(ok, status)

    def _commit_worker(self) -> None:
        skip_ids = load_processed_line_ids(DEFAULT_LOG_PATH)
        try:
            result_code = run_commit(
                self.batch,
                company_file="",
                log_path=DEFAULT_LOG_PATH,
                skip_ids=skip_ids,
                force=False,
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
