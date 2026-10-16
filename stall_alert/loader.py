"""CSV loading and structural row validation for stall-alert.

This module does NOT know about config.yaml or stages/thresholds. It only
checks that each row is well-formed: required fields present, dates parse,
and stage_entered_date is not in the future. Anything that depends on
config (e.g. "is this stage known?") is checked later in core.py.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

REQUIRED_FIELDS = [
    "candidate_id",
    "candidate_name",
    "role",
    "stage",
    "stage_entered_date",
    "owner",
    "role_priority",
]

ALL_FIELDS = REQUIRED_FIELDS + ["last_contact_date", "notes"]

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


def _parse_date(value: str) -> Optional[date]:
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        return None


def load_rows(path: str, today: date) -> LoadResult:
    """Load and structurally validate a hiring-board CSV.

    Bad rows are never silently dropped: every excluded row is reported
    in `errors` with its row number and reason. Rows with a non-fatal
    issue (currently: an unparseable last_contact_date) are kept and
    reported in `warnings` instead.
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_FIELDS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(
                f"CSV is missing required column(s): {', '.join(missing)}"
            )

        rows: list[Row] = []
        errors: list[RowError] = []
        warnings: list[RowWarning] = []

        for i, raw in enumerate(reader, start=2):  # header is row 1
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

        return LoadResult(rows=rows, errors=errors, warnings=warnings)


def _validate_required_fields(raw: dict) -> Optional[str]:
    for field in REQUIRED_FIELDS:
        value = (raw.get(field) or "").strip()
        if not value:
            return f"missing required field '{field}'"
    return None
