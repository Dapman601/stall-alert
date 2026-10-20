"""CSV loading and structural row validation for stall-alert.

This module does NOT know about config.yaml or stages/thresholds. It only
checks that each row is well-formed: required fields present, dates parse,
and stage_entered_date is not in the future. Anything that depends on
config (e.g. "is this stage known?") is checked later in core.py.
"""
from __future__ import annotations

import csv
import difflib
import io
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

DEFAULT_ENCODING = "utf-8-sig"
FALLBACK_ENCODING = "cp1252"

REQUIRED_FIELDS = [
    "candidate_id",
    "candidate_name",
    "role",
    "stage",
    "stage_entered_date",
    "owner",
    "role_priority",
]

VALID_PRIORITIES = {"high", "medium", "low"}

DATE_FORMAT = "%Y-%m-%d"


@dataclass(frozen=True)
class Row:
    row_number: int  # 1-indexed, counting the header as row 1 (matches a spreadsheet view)
    candidate_id: str
    candidate_name: str
    role: str
    stage: str
    stage_entered_date: date
    owner: str
    role_priority: str
    last_contact_date: Optional[date]
    notes: str


@dataclass(frozen=True)
class RowError:
    row_number: int
    reason: str


@dataclass(frozen=True)
class RowWarning:
    row_number: int
    reason: str


@dataclass(frozen=True)
class LoadResult:
    rows: list[Row]
    errors: list[RowError]
    warnings: list[RowWarning]
    encoding_used: str = DEFAULT_ENCODING
    encoding_warning: Optional[str] = None


def _parse_date(value: str) -> Optional[date]:
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        return None


def _missing_columns_message(missing: list[str], found_columns: list[str]) -> str:
    """Builds a clear, actionable error message for a missing-column
    failure - naming what's missing, what was actually found, and any
    close matches (e.g. 'Stage' for 'stage', or a whitespace-padded
    name) so the fix is obvious without a traceback."""
    lines = [f"CSV is missing required column(s): {', '.join(missing)}"]
    lines.append(
        f"Columns found in the file: {', '.join(found_columns) if found_columns else '(none)'}"
    )
    normalized_found = {c.strip().lower(): c for c in found_columns}
    for col in missing:
        close = difflib.get_close_matches(col, normalized_found.keys(), n=2, cutoff=0.6)
        if close:
            suggestions = ", ".join(repr(normalized_found[c]) for c in close)
            lines.append(f"  '{col}' not found - did you mean {suggestions}?")
    return "\n".join(lines)


def _decode_csv_bytes(raw_bytes: bytes, encoding: Optional[str]) -> tuple[str, str, Optional[str]]:
    """Returns (text, encoding_used, encoding_warning).

    If `encoding` is given explicitly (--encoding), it's used as-is - a
    decode failure there is the user's to fix, so it's a clear error,
    not a silent fallback. Otherwise: try UTF-8 first; if that fails,
    fall back to cp1252 (which can decode any byte, so it never raises)
    and report the fallback via `encoding_warning` rather than silently.
    """
    if encoding:
        try:
            return raw_bytes.decode(encoding), encoding, None
        except (UnicodeDecodeError, LookupError) as e:
            raise ValueError(
                f"Could not decode the file using encoding '{encoding}': {e}. "
                f"Try a different --encoding value."
            ) from e

    try:
        return raw_bytes.decode(DEFAULT_ENCODING), DEFAULT_ENCODING, None
    except UnicodeDecodeError:
        text = raw_bytes.decode(FALLBACK_ENCODING, errors="replace")
        warning = (
            f"File isn't UTF-8; read as {FALLBACK_ENCODING}. If names look "
            f"wrong, rerun with --encoding <name>."
        )
        return text, FALLBACK_ENCODING, warning


def load_rows(path: str, today: date, encoding: Optional[str] = None) -> LoadResult:
    """Load and structurally validate a hiring-board CSV.

    Bad rows are never silently dropped: every excluded row is reported
    in `errors` with its row number and reason. Rows with a non-fatal
    issue (currently: an unparseable last_contact_date) are kept and
    reported in `warnings` instead.
    """
    with open(path, "rb") as f:
        raw_bytes = f.read()
    text, encoding_used, encoding_warning = _decode_csv_bytes(raw_bytes, encoding)

    reader = csv.DictReader(io.StringIO(text))
    found_columns = reader.fieldnames or []
    missing = [c for c in REQUIRED_FIELDS if c not in found_columns]
    if missing:
        raise ValueError(_missing_columns_message(missing, found_columns))

    rows: list[Row] = []
    errors: list[RowError] = []
    warnings: list[RowWarning] = []

    for i, raw in enumerate(reader, start=2):  # header is row 1
        extra_fields = raw.pop(None, None)  # csv.DictReader's restkey
        if extra_fields:
            # More comma-separated values than header columns - almost
            # always an unescaped comma inside notes (the last column).
            # Day 3 found this silently truncated notes; rejoin instead
            # of losing data, and say so rather than hiding it.
            raw["notes"] = ",".join([raw.get("notes") or "", *extra_fields])
            warnings.append(
                RowWarning(
                    i,
                    "row has more fields than the header (likely an "
                    "unescaped comma in notes); extra fields were "
                    "rejoined into 'notes'",
                )
            )

        reason = _validate_required_fields(raw)
        if reason:
            errors.append(RowError(i, reason))
            continue

        stage_entered = _parse_date(raw["stage_entered_date"].strip())
        if stage_entered is None:
            errors.append(
                RowError(
                    i,
                    f"stage_entered_date '{raw['stage_entered_date']}' is not "
                    f"a valid {DATE_FORMAT} date",
                )
            )
            continue
        if stage_entered > today:
            errors.append(
                RowError(
                    i,
                    f"stage_entered_date {stage_entered.isoformat()} is after "
                    f"--today {today.isoformat()}",
                )
            )
            continue

        priority = raw["role_priority"].strip().lower()
        if priority not in VALID_PRIORITIES:
            errors.append(
                RowError(
                    i,
                    f"role_priority '{raw['role_priority']}' is not one of "
                    f"{sorted(VALID_PRIORITIES)}",
                )
            )
            continue

        last_contact_raw = (raw.get("last_contact_date") or "").strip()
        last_contact: Optional[date] = None
        if last_contact_raw:
            last_contact = _parse_date(last_contact_raw)
            if last_contact is None:
                warnings.append(
                    RowWarning(
                        i,
                        f"last_contact_date '{last_contact_raw}' is not a "
                        f"valid {DATE_FORMAT} date; ignoring it",
                    )
                )

        rows.append(
            Row(
                row_number=i,
                candidate_id=raw["candidate_id"].strip(),
                candidate_name=raw["candidate_name"].strip(),
                role=raw["role"].strip(),
                stage=raw["stage"].strip(),
                stage_entered_date=stage_entered,
                owner=raw["owner"].strip(),
                role_priority=priority,
                last_contact_date=last_contact,
                notes=(raw.get("notes") or "").strip(),
            )
        )

    return LoadResult(
        rows=rows, errors=errors, warnings=warnings,
        encoding_used=encoding_used, encoding_warning=encoding_warning,
    )


def _validate_required_fields(raw: dict) -> Optional[str]:
    for field in REQUIRED_FIELDS:
        value = (raw.get(field) or "").strip()
        if not value:
            return f"missing required field '{field}'"
    return None
