from pathlib import Path

from import_batch import log_safely, print_dry_run_report
from schema import Batch


def make_batch():
    return Batch.model_validate(
        {
            "batch_id": "b1",
            "transactions": [
                {
                    "line_id": "l1",
                    "date": "2026-07-01",
                    "lines": [
                        {"account": "Bank", "credit": 100},
                        {"account": "Expenses", "debit": 100},
                    ],
                }
            ],
        }
    )


def test_print_dry_run_report_uses_custom_emit_not_stdout():
    # This is the exact seam the GUI depends on: it must be possible to
    # capture the report without printing to stdout, so it can be routed
    # into a Tkinter widget instead.
    lines = []
    print_dry_run_report(make_batch(), skip_ids=set(), missing=[], emit=lines.append)
    text = "\n".join(lines)
    assert "b1" in text
    assert "Bank" in text
    assert "CR 100.00" in text


def test_print_dry_run_report_shows_missing_accounts_via_emit():
    lines = []
    print_dry_run_report(make_batch(), skip_ids=set(), missing=["Ghost Account"], emit=lines.append)
    text = "\n".join(lines)
    assert "PREFLIGHT FAILED" in text
    assert "Ghost Account" in text


def test_log_safely_reports_write_failure_via_emit_not_stdout(tmp_path):
    # Point the log at a path whose parent doesn't exist as a directory
    # (it's a file), so append_log's mkdir/open fails and log_safely has
    # to route the warning through emit instead of raising.
    blocking_file = tmp_path / "not_a_directory"
    blocking_file.write_text("x")
    bad_log_path = blocking_file / "import_log.jsonl"

    lines = []
    log_safely(bad_log_path, {"line_id": "l1"}, emit=lines.append)
    assert any("WARNING" in line for line in lines)
    assert any("l1" in line for line in lines)
