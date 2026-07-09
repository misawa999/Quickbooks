"""Append-only import log, used as the source of truth for dedupe/resume."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Set


def load_processed_line_ids(log_path: Path) -> Set[str]:
    if not log_path.exists():
        return set()
    processed: Set[str] = set()
    with log_path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            record = json.loads(raw_line)
            if record.get("status") == "ok":
                processed.add(record["line_id"])
    return processed


def append_log(log_path: Path, record: dict) -> None:
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
