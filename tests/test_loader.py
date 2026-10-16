from datetime import date

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
