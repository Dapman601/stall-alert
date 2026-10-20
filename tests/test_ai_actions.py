import json
from datetime import date
from types import SimpleNamespace

import pytest

from stall_alert import ai_actions
from stall_alert.loader import Row


def make_row(**overrides) -> Row:
    defaults = dict(
        row_number=2,
        candidate_id="C001",
        candidate_name="Alice Johnson",
        role="Engineer",
        stage="applied",
        stage_entered_date=date(2026, 10, 12),
        owner="Sam Reed",
        role_priority="high",
        last_contact_date=date(2026, 10, 13),
        notes="",
    )
    defaults.update(overrides)
    return Row(**defaults)


def make_ctx(row: Row = None, **overrides) -> ai_actions.ModelContext:
    defaults = dict(
        row=row if row is not None else make_row(),
        today=date(2026, 10, 16),
        days_in_stage=4,
        threshold=3,
        days_over_threshold=1,
    )
    defaults.update(overrides)
    return ai_actions.ModelContext(**defaults)


class FakeClient:
    """Mocks the OpenAI-compatible client shape used by
    ai_actions.call_model (OpenRouter). Never makes a network call."""

    def __init__(self, text: str = None, exception: Exception = None):
        self._text = text
        self._exception = exception
        self.calls = []

    class _Completions:
        def __init__(self, outer):
            self._outer = outer

        def create(self, **kwargs):
            self._outer.calls.append(kwargs)
            if self._outer._exception:
                raise self._outer._exception
            message = SimpleNamespace(content=self._outer._text)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class _Chat:
        def __init__(self, outer):
            self.completions = FakeClient._Completions(outer)

    @property
    def chat(self):
        return FakeClient._Chat(self)


def _respond(action, who, reason):
    return json.dumps({"action": action, "who": who, "reason": reason})


# --- the happy path: ordinary words must always pass ---

def test_valid_ordinary_response_passes_validation():
    ctx = make_ctx()
    text = _respond(
        action="Schedule a quick check-in call this week to confirm next steps.",
        who="recruiter",
        reason="Candidate has been in the applied stage longer than expected.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"
    assert result.fallback_reason is None
    assert result.who == "recruiter"


# --- role/stage words from the row itself are not invented names ---

def test_role_word_in_action_is_not_flagged_as_invented_name():
    ctx = make_ctx(row=make_row(role="Engineer"))
    text = _respond(
        action="Ask the Engineer candidate to confirm interest in the role.",
        who="recruiter",
        reason="Confirm interest to keep the applied stage moving.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"
    assert result.fallback_reason is None


# --- markdown-fenced JSON still parses (models often fence despite instructions) ---

def test_markdown_fenced_json_is_still_parsed():
    ctx = make_ctx()
    inner = _respond(
        action="Schedule a quick check-in call this week to confirm next steps.",
        who="recruiter",
        reason="Candidate has been in the applied stage longer than expected.",
    )
    text = f"```json\n{inner}\n```"
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"
    assert result.fallback_reason is None


# --- invalid JSON falls back ---

def test_invalid_json_falls_back():
    ctx = make_ctx()
    client = FakeClient(text="this is not json")
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "invalid JSON" in result.fallback_reason


# --- overlong action falls back ---

def test_overlong_action_falls_back():
    ctx = make_ctx()
    long_action = " ".join(["word"] * 30)
    text = _respond(action=long_action, who="recruiter", reason="too long test")
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "25 words" in result.fallback_reason


# --- Fix 4: enforce the 20-word reason limit (matching directive.md) ---

def test_overlong_reason_falls_back():
    ctx = make_ctx()
    long_reason = " ".join(["word"] * 25)
    text = _respond(
        action="Follow up with the candidate about the applied role.",
        who="recruiter",
        reason=long_reason,
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "20 words" in result.fallback_reason


def test_reason_at_exactly_20_words_passes():
    ctx = make_ctx()
    reason = " ".join(["word"] * 20)
    text = _respond(
        action="Follow up with the candidate about the applied role.",
        who="recruiter",
        reason=reason,
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"


# --- invented name falls back ---

def test_invented_person_name_falls_back():
    ctx = make_ctx()
    text = _respond(
        action="Email Jennifer Walsh to confirm interview availability this week.",
        who="recruiter",
        reason="Need a faster response from the candidate.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "invented name" in result.fallback_reason


# --- invented number falls back ---

def test_invented_number_falls_back():
    ctx = make_ctx()
    text = _respond(
        action="Offer a 15% signing bonus to close the candidate quickly.",
        who="recruiter",
        reason="Faster close increases the chance of acceptance.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "invented number" in result.fallback_reason


# --- invented date falls back ---

def test_invented_date_falls_back():
    ctx = make_ctx()
    text = _respond(
        action="Schedule the next interview for 2026-12-01 at the latest.",
        who="recruiter",
        reason="Candidate should not wait longer than that.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "invented date" in result.fallback_reason


# --- Fix 2: date-aware matching (Oct 5 / October 5 / 5 October / 5th) ---

def test_month_day_format_of_a_real_row_date_passes():
    # row.stage_entered_date = 2026-10-12
    ctx = make_ctx()
    text = _respond(
        action="Follow up with the candidate about the role this week.",
        who="recruiter",
        reason="Candidate entered the applied stage on Oct 12.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"


def test_full_month_name_day_first_format_of_a_real_row_date_passes():
    # row.last_contact_date = 2026-10-13
    ctx = make_ctx()
    text = _respond(
        action="Follow up with the candidate about the role this week.",
        who="recruiter",
        reason="No contact since 13 October.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"


def test_bare_ordinal_matching_a_real_row_day_passes():
    # row.stage_entered_date day = 12
    ctx = make_ctx()
    text = _respond(
        action="Follow up with the candidate about the role this week.",
        who="recruiter",
        reason="Candidate entered the stage on the 12th.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"


def test_month_day_not_matching_any_row_date_still_falls_back():
    ctx = make_ctx()
    text = _respond(
        action="Follow up with the candidate about the role this week.",
        who="recruiter",
        reason="No contact since October 25.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "invented date" in result.fallback_reason


# --- regression test built from a real Day 2 fallback (C022 Victor
# Hugo): "No contact since Oct 5" where last_contact_date=2026-10-05 -
# previously flagged as invented number '5' + invented name 'Oct'. ---

def test_real_fallback_oct5_now_passes():
    row = make_row(
        candidate_id="C022",
        candidate_name="Victor Hugo",
        role="Engineer",
        stage="screening",
        stage_entered_date=date(2026, 10, 2),
        owner="Jon Ortiz",
        role_priority="low",
        last_contact_date=date(2026, 10, 5),
    )
    ctx = make_ctx(row=row, days_in_stage=10, threshold=3, days_over_threshold=7)
    text = _respond(
        action="Contact Victor Hugo to schedule technical screening or next step.",
        who="recruiter",
        reason="7 days overdue, no recent contact since Oct 5.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"
    assert result.fallback_reason is None


# --- Fix 3: an invented name at the very start of action/reason must
# still be caught (previously blanket-exempted via "i == 0: continue") ---

def test_invented_name_as_first_word_of_action_falls_back():
    ctx = make_ctx()
    text = _respond(
        action="Jennifer should follow up with the candidate this week.",
        who="recruiter",
        reason="Candidate has been stalled too long in the applied stage.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "invented name" in result.fallback_reason


def test_invented_name_as_first_word_of_reason_falls_back():
    # "Marcus should" matches the should/needs/to pattern. Plain
    # "Marcus flagged..." (no trigger word after it) is the documented
    # gap - see test_single_invented_name_without_trigger_not_caught.
    ctx = make_ctx()
    text = _respond(
        action="Follow up with the candidate about the applied role.",
        who="recruiter",
        reason="Marcus should flag this candidate as a priority.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "invented name" in result.fallback_reason


# --- regression: real sentence-starters observed in live runs must
# still pass now that the first word is no longer exempt ---

def test_real_sentence_starter_complete_still_passes():
    row = make_row(
        candidate_id="C004", candidate_name="David Kim", role="Product Manager",
        stage="screening", stage_entered_date=date(2026, 10, 12), owner="Jon Ortiz",
        role_priority="medium",
    )
    ctx = make_ctx(row=row, days_in_stage=4, threshold=3, days_over_threshold=1)
    text = _respond(
        action="Complete screening call with David Kim today or tomorrow.",
        who="recruiter",
        reason="1 day past threshold in screening stage.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"


def test_real_sentence_starter_high_priority_still_passes():
    row = make_row(
        candidate_id="C001", candidate_name="Alice Johnson", role="Software Engineer",
        stage="applied", stage_entered_date=date(2026, 10, 12), owner="Sam Reed",
        role_priority="high",
    )
    ctx = make_ctx(row=row, days_in_stage=4, threshold=3, days_over_threshold=1)
    text = _respond(
        action="Review Alice Johnson's application and advance to phone screen or reject.",
        who="recruiter",
        reason="High priority role, exceeded 3-day applied stage threshold.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"


# --- invalid 'who' enum falls back ---

def test_invalid_who_enum_falls_back():
    ctx = make_ctx()
    text = _respond(
        action="Follow up with the candidate about the applied role.",
        who="hr_team",
        reason="Keep the process moving.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "who" in result.fallback_reason


# --- API error falls back and is distinguished from validation errors ---

def test_api_error_falls_back_with_distinct_reason():
    ctx = make_ctx()
    client = FakeClient(exception=ConnectionError("network unreachable"))
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert result.fallback_reason.startswith("API error")
    assert "network unreachable" in result.fallback_reason


def test_rule_based_action_has_no_content_violations():
    ctx = make_ctx()
    result = ai_actions.rule_based_action(ctx.row, "AI disabled via --no-ai flag")
    assert result.source == "fallback"
    assert result.fallback_reason == "AI disabled via --no-ai flag"
    assert ai_actions._content_violations(result.action, ctx) == []


# --- Fix 1: computed context (today/days_in_stage/threshold/days_over_threshold)
# is sent to the model and added to the validator's allowed set ---

def test_row_to_dict_includes_computed_context():
    ctx = make_ctx()
    payload = ai_actions.row_to_dict(ctx)
    assert payload["today"] == "2026-10-16"
    assert payload["days_in_stage"] == 4
    assert payload["threshold"] == 3
    assert payload["days_over_threshold"] == 1


def test_response_citing_real_days_over_threshold_passes():
    # Day 1/Step 0 baseline: the model had no way to know elapsed time,
    # so it guessed (usually wrong). Now that days_over_threshold=7 is
    # sent, a response that correctly cites it should pass.
    row = make_row(
        candidate_id="C025",
        candidate_name="Yara Singh",
        role="Engineer",
        stage="final_interview",
        stage_entered_date=date(2026, 10, 1),
        owner="Jon Ortiz",
        role_priority="high",
    )
    ctx = make_ctx(row=row, days_in_stage=11, threshold=4, days_over_threshold=7)
    text = _respond(
        action="Schedule the final interview with Yara Singh this week.",
        who="recruiter",
        reason="Candidate is 7 days over the final_interview threshold of 4.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"
    assert result.fallback_reason is None


# --- regression test built from a real Day 1/Step 0 fallback (C011 Karen
# White): "waiting at final stage for 2+ months" - fabricated, unrelated
# to any row or computed-context number (real days_over_threshold=4).
# Fix 1 grounds correct numbers; it must NOT make fabricated ones pass. ---

def test_real_fallback_with_fabricated_duration_still_falls_back():
    row = make_row(
        candidate_id="C011",
        candidate_name="Karen White",
        role="Recruiter Ops",
        stage="final-interview",
        stage_entered_date=date(2026, 10, 6),
        owner="Sam Reed",
        role_priority="high",
    )
    ctx = make_ctx(row=row, days_in_stage=8, threshold=4, days_over_threshold=4)
    text = _respond(
        action="Schedule final interview immediately with Sam Reed to close "
        "high-priority Recruiter Ops role.",
        who="recruiter",
        reason="Candidate waiting at final stage for 2+ months on high-priority role.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    # Fix 5 now recognizes "2+ months" as a duration phrase (distinct
    # message), rather than a bare "invented number '2'".
    assert "invented duration" in result.fallback_reason


# --- Fix 5: number words treated like digits; vague quantities always fail ---

def test_number_word_matching_context_passes():
    # days_over_threshold=1 in make_ctx() defaults
    ctx = make_ctx()
    text = _respond(
        action="Follow up with the candidate about the applied role.",
        who="recruiter",
        reason="Candidate is one day over the applied stage threshold.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"


def test_number_word_not_matching_context_falls_back():
    # "fifteen applicants" is realistic phrasing that isolates the
    # standalone number-word check: the quantity isn't adjacent to a
    # days/weeks/months/hours unit, so it's checked as an ordinary
    # number, not a duration (see the next test for that path).
    ctx = make_ctx()
    text = _respond(
        action="Follow up with the candidate about the applied role.",
        who="recruiter",
        reason="Candidate is one of fifteen applicants under review for this role.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "invented number" in result.fallback_reason


def test_number_word_days_duration_not_matching_context_falls_back():
    # "fifteen days" is realistic, but now routes through the
    # duration-phrase check (days is a recognized duration unit), so
    # the message is "invented duration", not "invented number".
    ctx = make_ctx()
    text = _respond(
        action="Follow up with the candidate about the applied role.",
        who="recruiter",
        reason="Candidate has been stalled for fifteen days without contact.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "invented duration" in result.fallback_reason


def test_vague_quantity_word_in_duration_always_falls_back():
    # A vague quantity used as a duration ("a couple of weeks") has no
    # fixed value and always fails - unlike ordinary, non-duration use
    # (see test_vague_quantity_some_outside_duration_* below, which
    # must PASS).
    ctx = make_ctx()
    text = _respond(
        action="Follow up with the candidate about the applied role.",
        who="recruiter",
        reason="Candidate has been waiting a couple of weeks for a response.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "invented duration" in result.fallback_reason


def test_month_duration_not_matching_context_falls_back():
    # None of days_in_stage/threshold/days_over_threshold equal 3, so
    # "three months" has no coincidental match (see the xfail test for
    # the case where it would).
    ctx = make_ctx(days_in_stage=6, threshold=5, days_over_threshold=1)
    text = _respond(
        action="Follow up with the candidate about the applied role.",
        who="recruiter",
        reason="Candidate has been waiting three months for a response.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "invented duration" in result.fallback_reason


# --- documents a known, un-fixed hole: a duration's bare number can
# coincidentally equal a day-based context field even though the UNITS
# don't match (months vs. days). Fix 5 does no unit conversion, so this
# slips through. Left as xfail per instruction - not to be fixed today. ---

@pytest.mark.xfail(
    reason="Known gap: '2 months in stage' coincidentally matches "
    "threshold=2 (a day-based value) because duration checking compares "
    "bare numbers only, with no month/week-to-day conversion. The "
    "mismatch in units (months vs. days) is not detected. Intentionally "
    "left unfixed per Day 2 instructions.",
    strict=True,
)
def test_meaning_mismatch_months_vs_day_based_threshold_not_caught():
    row = make_row(stage="offer")
    ctx = make_ctx(row=row, days_in_stage=5, threshold=2, days_over_threshold=3)
    text = _respond(
        action="Follow up with the candidate about the offer status.",
        who="recruiter",
        reason="Candidate has been 2 months in stage, significantly delayed.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    # This SHOULD fall back (months != days; threshold=2 is unrelated to
    # "2 months"), but the naive face-value check lets it through as "ai".
    assert result.source == "fallback"


# --- vague-quantity flagging is now scoped to duration phrases only -
# ordinary use of "some"/"a few" outside a month/week/day/hour duration
# is not a claim about elapsed time and must PASS. ---

def test_vague_quantity_some_outside_duration_passes():
    ctx = make_ctx()
    text = _respond(
        action="Follow up and answer some of the candidate's questions.",
        who="recruiter",
        reason="Candidate raised questions during the applied stage.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"


def test_vague_quantity_a_few_outside_duration_passes():
    ctx = make_ctx()
    text = _respond(
        action="Follow up and address a few concerns before the next interview.",
        who="recruiter",
        reason="Candidate raised concerns during the applied stage.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"


# --- vague quantities INSIDE a duration phrase must still fail - no
# fixed value, so there's nothing to check them against. ---

def test_vague_quantity_a_few_weeks_duration_falls_back():
    ctx = make_ctx()
    text = _respond(
        action="Follow up with the candidate about the applied role.",
        who="recruiter",
        reason="Candidate has stalled for a few weeks with no response.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "invented duration" in result.fallback_reason


def test_vague_quantity_several_months_duration_falls_back():
    ctx = make_ctx()
    text = _respond(
        action="Follow up with the candidate about the applied role.",
        who="recruiter",
        reason="Candidate has been several months in stage with no update.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "invented duration" in result.fallback_reason


# --- days/hours are included in the duration pattern too, so a vague
# day/hour count doesn't slip through unchecked. ---

def test_vague_quantity_a_few_days_duration_falls_back():
    ctx = make_ctx()
    text = _respond(
        action="Follow up with the candidate about the applied role.",
        who="recruiter",
        reason="Candidate has been overdue for a few days with no contact.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "invented duration" in result.fallback_reason


def test_vague_quantity_several_hours_duration_falls_back():
    ctx = make_ctx()
    text = _respond(
        action="Follow up with the candidate within several hours.",
        who="recruiter",
        reason="Candidate is high priority and needs a prompt response.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "invented duration" in result.fallback_reason


# --- Day 2 wrap-up, deadline rule: "within N days/business days/hours"
# is allowed in ACTION only, within bound. Day 4 part 2 adds a gate on
# top: the bound only matters when deadline_allowed is True
# (days_over_threshold >= threshold) - see the dedicated
# deadline_allowed tests further below. These tests all use an
# explicit days_over_threshold >= threshold context so they're testing
# the bound logic, not the gate. ---

def test_deadline_within_2_days_in_action_passes():
    # Real Day 2 case: Alice Johnson's action from an actual live run,
    # with days_over_threshold bumped to >= threshold so
    # deadline_allowed is True (isolating the bound check from the gate).
    row = make_row(
        candidate_id="C001", candidate_name="Alice Johnson", role="Software Engineer",
        stage="applied", stage_entered_date=date(2026, 10, 12), owner="Sam Reed",
        role_priority="high",
    )
    ctx = make_ctx(row=row, days_in_stage=6, threshold=3, days_over_threshold=3)
    text = _respond(
        action="Review Alice Johnson's application and schedule phone screen within 2 days.",
        who="recruiter",
        reason="High priority role, 3 days over threshold at applied stage.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"


def test_deadline_within_10_days_in_action_falls_back():
    # Default make_ctx() uses an October stage_entered_date, whose "10"
    # month digit would coincidentally land in allowed_numbers - pick
    # a November date here so "10" has no legitimate source at all.
    row = make_row(
        stage_entered_date=date(2026, 11, 5), last_contact_date=date(2026, 11, 6)
    )
    ctx = make_ctx(
        row=row, today=date(2026, 11, 20), days_in_stage=6, threshold=3,
        days_over_threshold=3,
    )
    text = _respond(
        action="Follow up with the candidate within 10 days.",
        who="recruiter",
        reason="Candidate is high priority for the applied role.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "invented duration" in result.fallback_reason


def test_deadline_within_2_days_in_reason_falls_back():
    # The exemption never applies to 'reason' - every number there
    # must still come from the row/context (ctx has no "2" anywhere).
    # deadline_allowed=True here too, to isolate "never applies to
    # reason" from the separate deadline_allowed gate.
    ctx = make_ctx(days_in_stage=6, threshold=3, days_over_threshold=3)
    text = _respond(
        action="Follow up with the candidate about the applied role.",
        who="recruiter",
        reason="Candidate should respond within 2 days or be deprioritized.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "invented duration" in result.fallback_reason


def test_deadline_within_two_days_number_word_in_action_passes():
    ctx = make_ctx(days_in_stage=6, threshold=3, days_over_threshold=3)
    text = _respond(
        action="Follow up with the candidate within two days.",
        who="recruiter",
        reason="Candidate is high priority for the applied role.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"


def test_deadline_within_3_business_days_in_action_passes():
    ctx = make_ctx(days_in_stage=6, threshold=3, days_over_threshold=3)
    text = _respond(
        action="Follow up with the candidate within 3 business days.",
        who="recruiter",
        reason="Candidate is high priority for the applied role.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"


def test_deadline_within_48_hours_in_action_passes():
    ctx = make_ctx(days_in_stage=6, threshold=3, days_over_threshold=3)
    text = _respond(
        action="Contact the candidate within 48 hours.",
        who="recruiter",
        reason="Candidate is high priority for the applied role.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"


def test_deadline_within_60_hours_in_action_falls_back():
    ctx = make_ctx(days_in_stage=6, threshold=3, days_over_threshold=3)
    text = _respond(
        action="Contact the candidate within 60 hours.",
        who="recruiter",
        reason="Candidate is high priority for the applied role.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "invented duration" in result.fallback_reason


# --- Day 4 part 2: deadline_allowed is decided in code
# (days_over_threshold >= threshold), not by the model. When False, ANY
# "within N ..." phrase is a violation, regardless of N's bound. ---

def test_deadline_allowed_property_true_at_and_above_threshold():
    ctx = make_ctx(days_in_stage=6, threshold=3, days_over_threshold=3)
    assert ctx.deadline_allowed is True


def test_deadline_allowed_property_false_below_threshold():
    ctx = make_ctx(days_in_stage=4, threshold=3, days_over_threshold=1)
    assert ctx.deadline_allowed is False


def test_deadline_in_bound_rejected_when_deadline_not_allowed():
    # "within 2 days" would normally pass (2 <= 5) - but
    # days_over_threshold=1 < threshold=3, so deadline_allowed is False
    # and it must be rejected regardless of being in-bound.
    ctx = make_ctx(days_in_stage=4, threshold=3, days_over_threshold=1)
    text = _respond(
        action="Follow up with the candidate within 2 days.",
        who="recruiter",
        reason="Candidate is high priority for the applied role.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "deadline not allowed" in result.fallback_reason


def test_deadline_included_in_payload_sent_to_model():
    ctx = make_ctx(days_in_stage=6, threshold=3, days_over_threshold=3)
    payload = ai_actions.row_to_dict(ctx)
    assert payload["deadline_allowed"] is True


# --- Day 2 close-out, name check: sentence-initial words no longer
# depend on a stoplist - only flagged if the shape looks like a
# person's name (two consecutive capitalized words, or a capitalized
# word followed by should/needs/to). Real model verbs the stoplist
# never anticipated (the "Collect" regression) now pass automatically. ---

def test_sentence_initial_unknown_verb_collect_passes():
    row = make_row(
        candidate_id="C008", candidate_name="Henry Cho", role="Designer",
        stage="Final Interview", stage_entered_date=date(2026, 10, 7), owner="Priya Nair",
        role_priority="medium",
    )
    ctx = make_ctx(row=row, days_in_stage=7, threshold=4, days_over_threshold=3)
    text = _respond(
        action="Collect final interview feedback and make a hiring decision.",
        who="hiring_manager",
        reason="Three business days over threshold at final interview stage.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"


def test_sentence_initial_unknown_verb_gather_passes():
    ctx = make_ctx()
    text = _respond(
        action="Gather feedback from the hiring manager about this candidate.",
        who="hiring_manager",
        reason="Candidate is past the applied stage threshold.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"


def test_sentence_initial_unknown_verb_escalate_passes():
    ctx = make_ctx()
    text = _respond(
        action="Escalate this candidate's feedback to the hiring manager.",
        who="hiring_manager",
        reason="Candidate is past the applied stage threshold.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"


def test_two_word_invented_name_at_sentence_start_falls_back():
    ctx = make_ctx()
    text = _respond(
        action="Tunde Bello should email the candidate about next steps.",
        who="recruiter",
        reason="Candidate is past the applied stage threshold.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "invented name" in result.fallback_reason


def test_single_invented_name_followed_by_should_falls_back():
    ctx = make_ctx()
    text = _respond(
        action="Tunde should email the candidate about next steps.",
        who="recruiter",
        reason="Candidate is past the applied stage threshold.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "fallback"
    assert "invented name" in result.fallback_reason


def test_real_candidate_name_right_after_sentence_initial_verb_passes():
    # "Review Alice Johnson's..." is "Verb FirstName" (two capitalized
    # words), but Alice Johnson is the real candidate - must not be
    # mistaken for an invented two-word name.
    row = make_row(candidate_id="C001", candidate_name="Alice Johnson")
    ctx = make_ctx(row=row)
    text = _respond(
        action="Review Alice Johnson's application and advance or reject.",
        who="recruiter",
        reason="Candidate is past the applied stage threshold.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    assert result.source == "ai"


@pytest.mark.xfail(
    reason="Known gap: a single invented name at the start of a "
    "sentence, NOT followed by should/needs/to and not paired with a "
    "second capitalized word (e.g. 'Marcus flagged...'), no longer "
    "matches either name-shape heuristic and is not caught. Narrowing "
    "the sentence-initial check to avoid stoplist false positives "
    "(the 'Collect' regression) reopened this narrower gap.",
    strict=True,
)
def test_single_invented_name_without_trigger_word_not_caught():
    ctx = make_ctx()
    text = _respond(
        action="Follow up with the candidate about the applied role.",
        who="recruiter",
        reason="Marcus flagged this candidate as a priority last week.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", ctx)
    # This SHOULD fall back ("Marcus" is invented), but the narrowed
    # heuristic has no trigger here, so it incorrectly passes as "ai".
    assert result.source == "fallback"
