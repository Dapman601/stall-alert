from datetime import date

from stall_alert.core import (
    Config,
    Verdict,
    business_days_between,
    evaluate_candidate,
    is_on_hold,
    normalize_stage,
)
from stall_alert.loader import Row

CONFIG = Config(
    thresholds={"applied": 3, "screening": 3, "interview": 5, "final_interview": 4, "offer": 2},
    terminal_stages={"hired", "rejected", "withdrawn"},
    stage_weights={"applied": 1, "screening": 1.5, "interview": 2, "final_interview": 3, "offer": 4},
    priority_weights={"high": 3, "medium": 2, "low": 1},
)


def make_row(**overrides) -> Row:
    defaults = dict(
        row_number=2,
        candidate_id="C001",
        candidate_name="Alice Johnson",
        role="Engineer",
        stage="applied",
        stage_entered_date=date(2026, 10, 12),
        owner="Sam",
        role_priority="high",
        last_contact_date=None,
        notes="",
    )
    defaults.update(overrides)
    return Row(**defaults)


# --- business_days_between ---

def test_business_days_exclusive_start_inclusive_end():
    # Mon -> Tue = 1
    assert business_days_between(date(2026, 10, 12), date(2026, 10, 13)) == 1


def test_business_days_same_day_is_zero():
    assert business_days_between(date(2026, 10, 12), date(2026, 10, 12)) == 0


def test_business_days_mon_to_wed_is_two():
    assert business_days_between(date(2026, 10, 12), date(2026, 10, 14)) == 2


def test_business_days_across_weekend_fri_to_mon_is_one():
    # Fri 10-9 -> Mon 10-12, weekend skipped
    assert business_days_between(date(2026, 10, 9), date(2026, 10, 12)) == 1


def test_business_days_weekend_start_rolls_to_next_business_day():
    # Sat 10-10 rolls to Mon 10-12, same result as starting on the Monday
    saturday_start = business_days_between(date(2026, 10, 10), date(2026, 10, 16))
    monday_start = business_days_between(date(2026, 10, 12), date(2026, 10, 16))
    assert saturday_start == monday_start == 4


def test_business_days_sunday_start_rolls_to_next_business_day():
    sunday_start = business_days_between(date(2026, 10, 11), date(2026, 10, 16))
    monday_start = business_days_between(date(2026, 10, 12), date(2026, 10, 16))
    assert sunday_start == monday_start


# --- stage normalization ---

def test_normalize_stage_lowercases_and_converts_spaces_and_hyphens():
    assert normalize_stage("Final Interview") == "final_interview"
    assert normalize_stage("final-interview") == "final_interview"
    assert normalize_stage("FINAL_INTERVIEW") == "final_interview"


# --- on-hold detection ---

def test_is_on_hold_case_insensitive_substring():
    assert is_on_hold("Candidate asked to put things ON HOLD while relocating")
    assert is_on_hold("on hold")
    assert not is_on_hold("holding steady, no issues")


# --- evaluate_candidate: thresholds ---

def test_exactly_at_threshold_is_not_stalled():
    row = make_row(stage="applied", stage_entered_date=date(2026, 10, 13))  # 3 business days
    status = evaluate_candidate(row, CONFIG, today=date(2026, 10, 16))
    assert status.days_in_stage == 3
    assert status.verdict == Verdict.NOT_STALLED


def test_one_day_over_threshold_is_stalled():
    row = make_row(stage="applied", stage_entered_date=date(2026, 10, 12))  # 4 business days
    status = evaluate_candidate(row, CONFIG, today=date(2026, 10, 16))
    assert status.days_in_stage == 4
    assert status.verdict == Verdict.STALLED
    assert status.days_over_threshold == 1


# --- terminal stages ---

def test_terminal_stage_is_never_flagged_even_if_very_old():
    row = make_row(stage="hired", stage_entered_date=date(2020, 1, 1))
    status = evaluate_candidate(row, CONFIG, today=date(2026, 10, 16))
    assert status.verdict == Verdict.TERMINAL


def test_terminal_stage_matching_is_case_and_format_insensitive():
    row = make_row(stage="Rejected", stage_entered_date=date(2020, 1, 1))
    status = evaluate_candidate(row, CONFIG, today=date(2026, 10, 16))
    assert status.verdict == Verdict.TERMINAL


# --- on-hold candidates ---

def test_on_hold_candidate_is_listed_separately_not_flagged():
    row = make_row(
        stage="interview",
        stage_entered_date=date(2026, 9, 1),
        notes="Team agreed to put this on hold for now",
    )
    status = evaluate_candidate(row, CONFIG, today=date(2026, 10, 16))
    assert status.verdict == Verdict.ON_HOLD
    assert status.days_in_stage is not None  # still computed for display


# --- unknown stage ---

def test_unknown_stage_not_in_config_is_bad_row():
    row = make_row(stage="onboarding", stage_entered_date=date(2026, 10, 5))
    status = evaluate_candidate(row, CONFIG, today=date(2026, 10, 16))
    assert status.verdict == Verdict.BAD_ROW
    assert "onboarding" in status.bad_row_reason
