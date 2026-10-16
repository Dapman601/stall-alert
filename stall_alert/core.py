"""Deterministic stall-detection logic: business-day math, stage matching
against config, and terminal/on-hold/stalled classification.

No AI, no network calls. Everything here is pure and fully testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Optional

import yaml

from stall_alert.loader import Row


@dataclass(frozen=True)
class Config:
    thresholds: dict[str, int]
    terminal_stages: set[str]
    stage_weights: dict[str, float]
    priority_weights: dict[str, float]


def load_config(path: str) -> Config:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Config(
        thresholds={normalize_stage(k): v for k, v in raw["thresholds"].items()},
        terminal_stages={normalize_stage(s) for s in raw["terminal_stages"]},
        stage_weights={normalize_stage(k): v for k, v in raw["stage_weights"].items()},
        priority_weights=dict(raw["priority_weights"]),
    )


def normalize_stage(stage: str) -> str:
    """Lowercase and treat spaces/hyphens as underscores, e.g.
    'Final Interview' / 'final-interview' -> 'final_interview'."""
    return stage.strip().lower().replace("-", "_").replace(" ", "_")


def is_on_hold(notes: str) -> bool:
    return "on hold" in notes.lower()


def _roll_to_business_day(d: date) -> date:
    """If d falls on a weekend, advance to the following Monday."""
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d += timedelta(days=1)
    return d


def business_days_between(start: date, end: date) -> int:
    """Business days (Mon-Fri) strictly after `start` up to and including
    `end`. Exclusive of start, inclusive of end: e.g. entered Mon, today
    Tue -> 1. If `start` is itself a weekend date, counting begins from
    the next business day. Returns 0 if end is before the (rolled) start.
    """
    start = _roll_to_business_day(start)
    if end < start:
        return 0
    count = 0
    current = start + timedelta(days=1)
    while current <= end:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


class Verdict(Enum):
    STALLED = "stalled"
    NOT_STALLED = "not_stalled"
    TERMINAL = "terminal"
    ON_HOLD = "on_hold"
    BAD_ROW = "bad_row"


@dataclass(frozen=True)
class CandidateStatus:
    row: Row
    verdict: Verdict
    normalized_stage: str
    days_in_stage: Optional[int] = None
    threshold: Optional[int] = None
    days_over_threshold: Optional[int] = None
    bad_row_reason: Optional[str] = None


def evaluate_candidate(row: Row, config: Config, today: date) -> CandidateStatus:
    """Classify a single structurally-valid row.

    Stalled means days_in_stage > threshold (strictly greater; exactly at
    threshold is NOT stalled). Terminal stages are never flagged. A stage
    that normalizes to something absent from both config.thresholds and
    config.terminal_stages is a bad row, not a crash.
    """
    stage = normalize_stage(row.stage)

    if stage in config.terminal_stages:
        return CandidateStatus(row=row, verdict=Verdict.TERMINAL, normalized_stage=stage)

    if stage not in config.thresholds:
        return CandidateStatus(
            row=row,
            verdict=Verdict.BAD_ROW,
            normalized_stage=stage,
            bad_row_reason=(
                f"stage '{row.stage}' (normalized '{stage}') is not listed in "
                f"config thresholds or terminal_stages"
            ),
        )

    days_in_stage = business_days_between(row.stage_entered_date, today)

    if is_on_hold(row.notes):
        return CandidateStatus(
            row=row,
            verdict=Verdict.ON_HOLD,
            normalized_stage=stage,
            days_in_stage=days_in_stage,
        )

    threshold = config.thresholds[stage]
    days_over = days_in_stage - threshold
    verdict = Verdict.STALLED if days_in_stage > threshold else Verdict.NOT_STALLED

    return CandidateStatus(
        row=row,
        verdict=verdict,
        normalized_stage=stage,
        days_in_stage=days_in_stage,
        threshold=threshold,
        days_over_threshold=days_over,
    )
