import json

from dedupe import append_log, load_processed_line_ids


def test_load_processed_line_ids_empty_when_missing(tmp_path):
    log_path = tmp_path / "import_log.jsonl"
    assert load_processed_line_ids(log_path) == set()


def test_append_and_load(tmp_path):
    log_path = tmp_path / "import_log.jsonl"
    append_log(log_path, {"line_id": "a", "status": "ok"})
    append_log(log_path, {"line_id": "b", "status": "error"})
    append_log(log_path, {"line_id": "c", "status": "ok"})

    assert load_processed_line_ids(log_path) == {"a", "c"}

    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 3
    assert json.loads(lines[0])["line_id"] == "a"


def test_append_log_creates_missing_parent_directories(tmp_path):
    # The default log path lives under ~/Documents/QuickBooks Importer/,
    # which doesn't exist until the first run creates it.
    log_path = tmp_path / "does" / "not" / "exist" / "import_log.jsonl"
    append_log(log_path, {"line_id": "a", "status": "ok"})
    assert load_processed_line_ids(log_path) == {"a"}
