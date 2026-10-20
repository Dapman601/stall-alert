from datetime import date
from pathlib import Path

from stall_alert.loader import load_rows

HEADER = (
    "candidate_id,candidate_name,role,stage,stage_entered_date,owner,"
    "last_contact_date,role_priority,notes\n"
)


def _write_csv(tmp_path, body: str):
    path = tmp_path / "board.csv"
    path.write_text(HEADER + body, encoding="utf-8")
    return str(path)


def test_valid_row_loads_cleanly(tmp_path):
    path = _write_csv(
        tmp_path,
        "C001,Alice Johnson,Engineer,applied,2026-10-12,Sam,2026-10-13,high,\n",
    )
    result = load_rows(path, today=date(2026, 10, 16))
    assert result.errors == []
    assert result.warnings == []
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.candidate_id == "C001"
    assert row.stage_entered_date == date(2026, 10, 12)
    assert row.last_contact_date == date(2026, 10, 13)
    assert row.role_priority == "high"
    assert row.row_number == 2  # header is row 1


def test_missing_required_field_is_bad_row(tmp_path):
    path = _write_csv(
        tmp_path,
        "C001,Alice Johnson,Engineer,applied,,Sam,2026-10-13,high,\n",
    )
    result = load_rows(path, today=date(2026, 10, 16))
    assert result.rows == []
    assert len(result.errors) == 1
    assert result.errors[0].row_number == 2
    assert "stage_entered_date" in result.errors[0].reason


def test_malformed_stage_entered_date_is_bad_row(tmp_path):
    path = _write_csv(
        tmp_path,
        "C001,Alice Johnson,Engineer,applied,2026/10/12,Sam,2026-10-13,high,\n",
    )
    result = load_rows(path, today=date(2026, 10, 16))
    assert result.rows == []
    assert len(result.errors) == 1
    assert result.errors[0].row_number == 2
    assert "not a valid" in result.errors[0].reason


def test_stage_entered_date_after_today_is_bad_row(tmp_path):
    path = _write_csv(
        tmp_path,
        "C001,Alice Johnson,Engineer,applied,2026-10-20,Sam,2026-10-13,high,\n",
    )
    result = load_rows(path, today=date(2026, 10, 16))
    assert result.rows == []
    assert len(result.errors) == 1
    assert "after --today" in result.errors[0].reason


def test_invalid_role_priority_is_bad_row(tmp_path):
    path = _write_csv(
        tmp_path,
        "C001,Alice Johnson,Engineer,applied,2026-10-12,Sam,2026-10-13,urgent,\n",
    )
    result = load_rows(path, today=date(2026, 10, 16))
    assert result.rows == []
    assert len(result.errors) == 1
    assert "role_priority" in result.errors[0].reason


def test_unparseable_last_contact_date_is_warning_not_bad_row(tmp_path):
    path = _write_csv(
        tmp_path,
        "C001,Alice Johnson,Engineer,applied,2026-10-12,Sam,15th Oct,high,\n",
    )
    result = load_rows(path, today=date(2026, 10, 16))
    assert result.errors == []
    assert len(result.warnings) == 1
    assert result.warnings[0].row_number == 2
    assert len(result.rows) == 1
    assert result.rows[0].last_contact_date is None


def test_missing_last_contact_date_is_not_a_warning(tmp_path):
    path = _write_csv(
        tmp_path,
        "C001,Alice Johnson,Engineer,applied,2026-10-12,Sam,,high,\n",
    )
    result = load_rows(path, today=date(2026, 10, 16))
    assert result.errors == []
    assert result.warnings == []
    assert len(result.rows) == 1
    assert result.rows[0].last_contact_date is None


def test_missing_required_column_in_header_raises(tmp_path):
    path = tmp_path / "board.csv"
    path.write_text("candidate_id,candidate_name,role,stage\nC001,Alice,Eng,applied\n")
    try:
        load_rows(str(path), today=date(2026, 10, 16))
        assert False, "expected ValueError for missing required columns"
    except ValueError as e:
        assert "stage_entered_date" in str(e)


def test_bad_rows_do_not_block_good_rows(tmp_path):
    body = (
        "C001,Alice Johnson,Engineer,applied,2026-10-12,Sam,2026-10-13,high,\n"
        "C002,Bob Lee,Engineer,applied,,Priya,2026-10-13,high,\n"
    )
    path = _write_csv(tmp_path, body)
    result = load_rows(path, today=date(2026, 10, 16))
    assert len(result.rows) == 1
    assert result.rows[0].candidate_id == "C001"
    assert len(result.errors) == 1
    assert result.errors[0].row_number == 3


# --- Day 4 fix: encoding fallback (Day 3 found loader.py crashed with an
# uncaught UnicodeDecodeError on any non-UTF-8 file) ---

def test_utf8_file_has_no_encoding_warning(tmp_path):
    path = _write_csv(tmp_path, "C001,Alice Johnson,Engineer,applied,2026-10-12,Sam,2026-10-13,high,\n")
    result = load_rows(path, today=date(2026, 10, 16))
    assert result.encoding_used == "utf-8-sig"
    assert result.encoding_warning is None


def test_cp1252_file_falls_back_with_warning(tmp_path):
    path = tmp_path / "board.csv"
    body = (
        HEADER
        + "C001,Jos\xe9 Garc\xeda,Engineer,applied,2026-10-12,Sam,2026-10-13,high,\n"
    )
    path.write_bytes(body.encode("cp1252"))
    result = load_rows(str(path), today=date(2026, 10, 16))
    assert result.encoding_used == "cp1252"
    assert result.encoding_warning is not None
    assert "cp1252" in result.encoding_warning
    assert "--encoding" in result.encoding_warning
    assert result.rows[0].candidate_name == "Jos\xe9 Garc\xeda"


def test_explicit_encoding_overrides_detection_no_warning(tmp_path):
    path = tmp_path / "board.csv"
    body = (
        HEADER
        + "C001,Jos\xe9 Garc\xeda,Engineer,applied,2026-10-12,Sam,2026-10-13,high,\n"
    )
    path.write_bytes(body.encode("cp1252"))
    result = load_rows(str(path), today=date(2026, 10, 16), encoding="cp1252")
    assert result.encoding_used == "cp1252"
    assert result.encoding_warning is None  # explicit encoding - no fallback, no warning


def test_explicit_wrong_encoding_raises_clear_value_error(tmp_path):
    path = tmp_path / "board.csv"
    body = (
        HEADER
        + "C001,Jos\xe9 Garc\xeda,Engineer,applied,2026-10-12,Sam,2026-10-13,high,\n"
    )
    path.write_bytes(body.encode("cp1252"))
    try:
        load_rows(str(path), today=date(2026, 10, 16), encoding="ascii")
        assert False, "expected ValueError for undecodable --encoding"
    except ValueError as e:
        assert "ascii" in str(e)
        assert "--encoding" in str(e)


def test_regression_day3_messy_board_cp1252_now_loads():
    """Built from the actual Day 3 finding: data/messy_board_cp1252.csv
    (the real file generated and tested in reports/day3_breaks.md)
    crashed the loader with an uncaught UnicodeDecodeError. It must now
    load successfully, with a visible encoding-fallback warning."""
    path = str(Path(__file__).resolve().parent.parent / "data" / "messy_board_cp1252.csv")
    result = load_rows(path, today=date(2026, 10, 20))
    assert result.encoding_used == "cp1252"
    assert result.encoding_warning is not None
    assert len(result.rows) + len(result.errors) == 5000


# --- Day 4 fix: rows with more fields than the header (an unescaped
# comma inside notes) are kept, with the extra fields rejoined into
# notes, plus a warning naming the row - Day 3 found this silently
# truncated notes with no trace at all. ---

def test_unescaped_comma_in_notes_is_rejoined_not_truncated(tmp_path):
    # Mirrors the exact shape planted in Day 3's messy_board.csv
    # (defect "unquoted_comma_in_notes"): a raw, unquoted comma inside
    # the last column, written without CSV escaping.
    path = tmp_path / "board.csv"
    body = HEADER + "C001,Alice Johnson,Engineer,applied,2026-10-12,Sam,2026-10-13,high,left,right\n"
    path.write_text(body, encoding="utf-8")
    result = load_rows(str(path), today=date(2026, 10, 16))
    assert len(result.rows) == 1
    assert result.rows[0].notes == "left,right"
    assert len(result.warnings) == 1
    assert result.warnings[0].row_number == 2
    assert "rejoined into 'notes'" in result.warnings[0].reason


def test_unescaped_comma_with_on_hold_text_still_detected_as_on_hold(tmp_path):
    # Day 3's dataset never happened to combine the unquoted-comma
    # defect with on-hold text in the same row (checked: 0 such rows
    # exist in data/messy_manifest.csv), so this specific interaction
    # is a new test, not a replay of planted data - added because the
    # instruction asked to verify it works, not just the comma fix
    # alone.
    path = tmp_path / "board.csv"
    body = HEADER + "C001,Alice Johnson,Engineer,applied,2026-10-12,Sam,2026-10-13,high,on hold,waiting for budget\n"
    path.write_text(body, encoding="utf-8")
    result = load_rows(str(path), today=date(2026, 10, 16))
    assert len(result.rows) == 1
    assert result.rows[0].notes == "on hold,waiting for budget"
    from stall_alert.core import is_on_hold
    assert is_on_hold(result.rows[0].notes)


# --- Day 4 fix: missing-column errors are clear messages (listing what
# was found and close matches), not a bare "missing column(s)" with a
# raw traceback bubbling up to the user. Built from the actual Day 3
# header-variant files. ---

def test_regression_day3_header_capitalized_suggests_close_match():
    path = str(Path(__file__).resolve().parent.parent / "data" / "header_capitalized.csv")
    try:
        load_rows(path, today=date(2026, 10, 20))
        assert False, "expected ValueError for the capitalized header"
    except ValueError as e:
        msg = str(e)
        assert "stage" in msg
        assert "Columns found in the file" in msg
        assert "'Stage'" in msg  # close match suggestion


def test_regression_day3_header_spaces_suggests_close_match():
    path = str(Path(__file__).resolve().parent.parent / "data" / "header_spaces.csv")
    try:
        load_rows(path, today=date(2026, 10, 20))
        assert False, "expected ValueError for the whitespace-padded header"
    except ValueError as e:
        msg = str(e)
        assert "stage_entered_date" in msg
        assert "Columns found in the file" in msg
        assert "stage_entered_date" in msg.split("did you mean")[-1]


def test_regression_day3_realistic_export_lists_all_missing_and_found():
    path = str(Path(__file__).resolve().parent.parent / "data" / "realistic_export.csv")
    try:
        load_rows(path, today=date(2026, 10, 20))
        assert False, "expected ValueError for the incompatible ATS export"
    except ValueError as e:
        msg = str(e)
        assert "candidate_id" in msg
        assert "Columns found in the file" in msg
        assert "Candidate Name" in msg  # actual header column named, not hidden
