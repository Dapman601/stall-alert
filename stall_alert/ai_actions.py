"""Thin, optional AI layer: one next-action suggestion per stalled
candidate, validated against the candidate's own row data, with a
rule-based fallback when the model's response can't be trusted.

Nothing here is required for the core tool to work (--no-ai skips it
entirely), and every network call is isolated behind `call_model` so
tests can mock it without ever hitting the real API.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from stall_alert.loader import Row

ALLOWED_WHO = {"recruiter", "hiring_manager", "owner"}
MAX_ACTION_WORDS = 25
MAX_REASON_WORDS = 20  # matches directive.md's stated limit for 'reason'

_NUMBER_PATTERN = re.compile(r"\d+")
_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}")
_CAPITALIZED_WORD_PATTERN = re.compile(r"\b[A-Z][a-zA-Z]+\b")

_MONTH_NAMES = {
    1: "january", 2: "february", 3: "march", 4: "april", 5: "may",
    6: "june", 7: "july", 8: "august", 9: "september", 10: "october",
    11: "november", 12: "december",
}
_MONTH_ABBR = {
    1: "jan", 2: "feb", 3: "mar", 4: "apr", 5: "may", 6: "jun",
    7: "jul", 8: "aug", 9: "sep", 10: "oct", 11: "nov", 12: "dec",
}
_MONTH_NAME_TO_NUM = {name: num for num, name in _MONTH_NAMES.items()}
_MONTH_NAME_TO_NUM.update({abbr: num for num, abbr in _MONTH_ABBR.items()})
_MONTH_ALTERNATION = "|".join(sorted(_MONTH_NAME_TO_NUM, key=len, reverse=True))

# Fix 2: a row/context date may appear in model text as ISO
# ("2026-10-05"), "Oct 5", "October 5", "5 October", or a bare "5th".
_MONTH_DAY_PATTERN = re.compile(
    rf"\b(?P<month>{_MONTH_ALTERNATION})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)
_DAY_MONTH_PATTERN = re.compile(
    rf"\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month>{_MONTH_ALTERNATION})\b",
    re.IGNORECASE,
)
_BARE_ORDINAL_PATTERN = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\b")

# Fix 5: number words should be treated like digits in the number
# check. Vague quantities ("a couple", "several") have no real value,
# but only matter when they're describing a duration (see below) -
# ordinary use ("answer some questions") is not a claim about elapsed
# time and must not be flagged.
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "dozen": 12,
}
_VAGUE_QUANTITY_WORDS = {"a couple", "couple", "a few", "few", "several", "some"}

_NUMBER_WORD_ALTERNATION = "|".join(
    re.escape(w) for w in sorted(_NUMBER_WORDS, key=len, reverse=True)
)
_QUANTITY_PATTERN = re.compile(rf"\b(?:{_NUMBER_WORD_ALTERNATION})\b", re.IGNORECASE)

# Fix 5: a number (digit or word) immediately describing a duration in
# months/weeks/days/hours is checked only against the bare numeric
# value already allowed (days_in_stage/threshold/days_over_threshold/
# etc.) - there is no unit conversion, so a value that coincidentally
# matches a day-based context number in face value (not meaning) can
# still slip through. This is a known, documented gap - see
# test_meaning_mismatch_* (xfail). Vague quantities ("a couple",
# "several") are only recognized as a duration quantity here - they
# have no numeric value, so they always fail when used this way.
_DURATION_QTY_ALTERNATION = "|".join(
    re.escape(w)
    for w in sorted(set(_NUMBER_WORDS) | _VAGUE_QUANTITY_WORDS, key=len, reverse=True)
)
_DURATION_PATTERN = re.compile(
    rf"\b(?P<qty>\d+|{_DURATION_QTY_ALTERNATION})\+?\s+(?:of\s+)?"
    rf"(?P<unit>months?|weeks?|days?|hours?)\b",
    re.IGNORECASE,
)

# Day 2 wrap-up, deadline rule: in the ACTION field only, "within N
# days", "within N business days", or "within N hours" is allowed as
# a suggested deadline, independent of context, as long as N (digit or
# number word - not a vague quantity) is within a sane bound. Anything
# outside this exact shape or bound still goes through the normal
# checks above. Never applied to 'reason' - every number there must
# still come from the row/context.
_DEADLINE_MAX = {"day": 5, "hour": 48}
_DEADLINE_PATTERN = re.compile(
    rf"\bwithin\s+(?P<qty>\d+|{_NUMBER_WORD_ALTERNATION})\s+(?:business\s+)?"
    rf"(?P<unit>days?|hours?)\b",
    re.IGNORECASE,
)


def _exempt_deadlines(text: str) -> str:
    def replace(m: re.Match) -> str:
        qty_text = m.group("qty").lower()
        qty_val = int(qty_text) if qty_text.isdigit() else _NUMBER_WORDS[qty_text]
        unit = m.group("unit").lower().rstrip("s")
        if qty_val <= _DEADLINE_MAX[unit]:
            return _mask(m.group(0))
        return m.group(0)  # out of bound: leave as-is for the normal checks

    return _DEADLINE_PATTERN.sub(replace, text)

# Heuristic stoplist: common words that are capitalized for reasons other
# than being a person's name (sentence-initial words, domain vocabulary).
# This is a deliberately simple heuristic for a thin AI layer, not an NLP
# name detector - see README Assumptions.
_COMMON_ACTION_WORDS = {
    "schedule", "email", "call", "ask", "send", "follow", "up", "confirm",
    "review", "reach", "out", "set", "next", "this", "the", "a", "an",
    "recruiter", "hiring", "manager", "owner", "candidate", "interview",
    "stage", "today", "week", "days", "update", "check", "contact",
    "notify", "escalate", "offer", "final", "screening", "applied",
    "with", "for", "and", "or", "to", "on", "in", "of", "their", "status",
    "please", "now", "soon", "immediately", "directly", "feedback",
    "decision", "move", "forward", "role", "position", "team",
    "complete", "no", "high", "medium", "low", "overdue", "exceeded",
    "applicant", "application", "phone", "technical", "within",
}


class ValidationError(Exception):
    pass


@dataclass(frozen=True)
class ModelContext:
    """Everything sent to the model and checked against by the
    validator: the candidate's row, plus the computed stall facts
    (Fix 1 - grounding the model so it doesn't have to guess/invent
    elapsed time)."""

    row: Row
    today: date
    days_in_stage: int
    threshold: int
    days_over_threshold: int


@dataclass(frozen=True)
class ActionResult:
    action: str
    who: str
    reason: str
    source: str  # "ai" or "fallback"
    fallback_reason: Optional[str] = None  # None when source == "ai"
    raw_response: Optional[str] = None  # exact model text; None if no call was made/returned


def load_directive(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def row_to_dict(ctx: ModelContext) -> dict[str, Any]:
    row = ctx.row
    return {
        "candidate_id": row.candidate_id,
        "candidate_name": row.candidate_name,
        "role": row.role,
        "stage": row.stage,
        "stage_entered_date": row.stage_entered_date.isoformat(),
        "owner": row.owner,
        "role_priority": row.role_priority,
        "last_contact_date": row.last_contact_date.isoformat()
        if row.last_contact_date
        else None,
        "notes": row.notes,
        "today": ctx.today.isoformat(),
        "days_in_stage": ctx.days_in_stage,
        "threshold": ctx.threshold,
        "days_over_threshold": ctx.days_over_threshold,
    }


def _allowed_text(ctx: ModelContext) -> str:
    row = ctx.row
    parts = [
        row.candidate_id,
        row.candidate_name,
        row.role,
        row.stage,
        row.owner,
        row.role_priority,
        row.notes,
        row.stage_entered_date.isoformat(),
        ctx.today.isoformat(),
        str(ctx.days_in_stage),
        str(ctx.threshold),
        str(ctx.days_over_threshold),
    ]
    if row.last_contact_date:
        parts.append(row.last_contact_date.isoformat())
    return " ".join(parts)


def _allowed_name_tokens(row: Row) -> set[str]:
    """Words drawn from the row itself that should never be flagged as
    an invented name - person names, but also role/stage words (e.g.
    'Engineer', 'Recruiter Ops'), since those are equally part of the
    candidate's own data, not something the model made up."""
    tokens: set[str] = set()
    for field in (row.candidate_name, row.owner, row.role, row.stage):
        for word in re.findall(r"[A-Za-z]+", field):
            tokens.add(word.lower())
    return tokens


def _context_dates(ctx: ModelContext) -> list[date]:
    dates = [ctx.today, ctx.row.stage_entered_date]
    if ctx.row.last_contact_date:
        dates.append(ctx.row.last_contact_date)
    return dates


def _allowed_month_day_pairs(ctx: ModelContext) -> set[tuple[int, int]]:
    return {(d.month, d.day) for d in _context_dates(ctx)}


def _allowed_month_words(ctx: ModelContext) -> set[str]:
    """Month names/abbreviations for any date in the row or context are
    not invented names - a candidate stalled since October has every
    right to be described that way, not just via the ISO date."""
    words: set[str] = set()
    for d in _context_dates(ctx):
        words.add(_MONTH_NAMES[d.month])
        words.add(_MONTH_ABBR[d.month])
    return words


def _mask(span: str) -> str:
    return " " * len(span)


def _date_phrase_violations(text: str, ctx: ModelContext) -> tuple[list[str], str]:
    """Fix 2: recognize 'Oct 5', 'October 5', '5 October', and a bare
    '5th' as the same date if the (month, day) - or just the day, for a
    bare ordinal - matches a row/context date. Masks every recognized
    span (allowed or not) so the later number/name scans don't also
    flag the same digits/month-word."""
    violations: list[str] = []
    allowed_pairs = _allowed_month_day_pairs(ctx)
    allowed_days = {day for _, day in allowed_pairs}

    def replace_month_day(m: re.Match) -> str:
        month_num = _MONTH_NAME_TO_NUM[m.group("month").lower()]
        day_num = int(m.group("day"))
        if (month_num, day_num) not in allowed_pairs:
            violations.append(f"invented date '{m.group(0)}'")
        return _mask(m.group(0))

    working = _MONTH_DAY_PATTERN.sub(replace_month_day, text)
    working = _DAY_MONTH_PATTERN.sub(replace_month_day, working)

    def replace_bare_ordinal(m: re.Match) -> str:
        day_num = int(m.group(1))
        if day_num not in allowed_days:
            violations.append(f"invented date '{m.group(0)}'")
        return _mask(m.group(0))

    working = _BARE_ORDINAL_PATTERN.sub(replace_bare_ordinal, working)
    return violations, working


def _duration_violations(text: str, allowed_numbers: set[str]) -> tuple[list[str], str]:
    """Fix 5: '<quantity> months/weeks/days/hours' is checked against
    the same allowed-numbers set as any other number - no unit
    conversion. A vague quantity ('a couple', 'several') has no real
    value and always fails whenever it's used as a duration (e.g.
    'a few weeks', 'several months', 'a few days', 'within several
    hours'); days/hours are included alongside months/weeks so a vague
    day/hour count doesn't slip through unchecked. NOTE: because
    there's no unit conversion, a quantity that coincidentally equals
    a day-based context number (e.g. threshold=2 and the text says '2
    months') can still pass - that's a known, deliberately unfixed
    gap; see the xfail test."""
    violations: list[str] = []

    def replace_duration(m: re.Match) -> str:
        qty_text = m.group("qty").lower()
        if qty_text in _VAGUE_QUANTITY_WORDS:
            violations.append(f"invented duration '{m.group(0)}'")
            return _mask(m.group(0))
        qty_str = str(_NUMBER_WORDS[qty_text]) if qty_text in _NUMBER_WORDS else qty_text
        if qty_str not in allowed_numbers:
            violations.append(f"invented duration '{m.group(0)}'")
        return _mask(m.group(0))

    working = _DURATION_PATTERN.sub(replace_duration, text)
    return violations, working


def _quantity_word_violations(text: str, allowed_numbers: set[str]) -> tuple[list[str], str]:
    """Fix 5: standalone number words ('four days') not already
    consumed by a duration phrase, treated the same as digits in the
    number check. Vague quantities ('some', 'a few') are intentionally
    NOT matched here - outside a month/week/day/hour duration phrase
    they're ordinary words ('answer some questions'), not a claim
    about elapsed time, so they must not be flagged."""
    violations: list[str] = []

    def replace_quantity(m: re.Match) -> str:
        word_text = m.group(0).lower()
        qty_str = str(_NUMBER_WORDS[word_text])
        if qty_str not in allowed_numbers:
            violations.append(f"invented number '{m.group(0)}'")
        return _mask(m.group(0))

    working = _QUANTITY_PATTERN.sub(replace_quantity, text)
    return violations, working


def _content_violations(
    text: str, ctx: ModelContext, allow_deadline: bool = False
) -> list[str]:
    """Flag only invented person names, dates, and numbers - not ordinary
    words absent from the row/context. Ordinary vocabulary must always
    pass. The allowed sets include the computed stall context (Fix 1),
    not just the raw row, so correct day-counts/dates the model echoes
    back are not flagged. `allow_deadline=True` (action field only)
    exempts "within N days/business days/hours" within bound - see
    _exempt_deadlines."""
    if allow_deadline:
        text = _exempt_deadlines(text)

    violations, working = _date_phrase_violations(text, ctx)

    allowed_text = _allowed_text(ctx)
    allowed_numbers = set(_NUMBER_PATTERN.findall(allowed_text))
    allowed_dates = set(_DATE_PATTERN.findall(allowed_text))
    allowed_names = _allowed_name_tokens(ctx.row) | _allowed_month_words(ctx)

    for full_date in _DATE_PATTERN.findall(working):
        if full_date not in allowed_dates:
            violations.append(f"invented date '{full_date}'")
    working = _DATE_PATTERN.sub(lambda m: _mask(m.group(0)), working)

    duration_violations, working = _duration_violations(working, allowed_numbers)
    violations.extend(duration_violations)

    for number in _NUMBER_PATTERN.findall(working):
        if number not in allowed_numbers:
            violations.append(f"invented number '{number}'")
    working = _NUMBER_PATTERN.sub(lambda m: _mask(m.group(0)), working)

    quantity_violations, working = _quantity_word_violations(working, allowed_numbers)
    violations.extend(quantity_violations)

    # Fix 3: no blanket exemption for the first word - a genuinely
    # invented name at the start of the sentence must still be caught.
    # Common sentence-starting verbs/words pass via _COMMON_ACTION_WORDS.
    for raw_word in working.split():
        for word in _CAPITALIZED_WORD_PATTERN.findall(raw_word):
            if word.lower() in _COMMON_ACTION_WORDS:
                continue
            if word.lower() in allowed_names:
                continue
            violations.append(f"possible invented name '{word}'")

    return violations


def validate_ai_response(
    parsed: Any, ctx: ModelContext, raw_response: Optional[str] = None
) -> ActionResult:
    if not isinstance(parsed, dict):
        raise ValidationError("response is not a JSON object")

    action = parsed.get("action")
    who = parsed.get("who")
    reason = parsed.get("reason")

    if not isinstance(action, str) or not action.strip():
        raise ValidationError("missing or invalid 'action'")
    if not isinstance(who, str) or who not in ALLOWED_WHO:
        raise ValidationError(f"'who' must be one of {sorted(ALLOWED_WHO)}")
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError("missing or invalid 'reason'")

    if len(action.split()) > MAX_ACTION_WORDS:
        raise ValidationError(
            f"'action' has more than {MAX_ACTION_WORDS} words"
        )
    if len(reason.split()) > MAX_REASON_WORDS:
        raise ValidationError(
            f"'reason' has more than {MAX_REASON_WORDS} words"
        )

    violations = _content_violations(
        action, ctx, allow_deadline=True
    ) + _content_violations(reason, ctx, allow_deadline=False)
    if violations:
        raise ValidationError("; ".join(violations))

    return ActionResult(
        action=action.strip(),
        who=who,
        reason=reason.strip(),
        source="ai",
        raw_response=raw_response,
    )


_CODE_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def _strip_code_fence(text: str) -> str:
    """Models often wrap JSON in markdown fences despite being told not
    to. Strip a single surrounding ```/```json fence if present; leave
    everything else untouched."""
    match = _CODE_FENCE_PATTERN.match(text.strip())
    return match.group(1) if match else text


def parse_and_validate(raw_text: str, ctx: ModelContext) -> ActionResult:
    try:
        parsed = json.loads(_strip_code_fence(raw_text))
    except json.JSONDecodeError as e:
        raise ValidationError(f"invalid JSON: {e}") from e
    return validate_ai_response(parsed, ctx, raw_response=raw_text)


def rule_based_action(
    row: Row, fallback_reason: str, raw_response: Optional[str] = None
) -> ActionResult:
    """Deterministic fallback used when the AI response is missing,
    unparseable, or fails validation (or when --no-ai is set). Built
    only from the row's own fields, so it never needs content
    validation itself. `fallback_reason` records why we're here;
    `raw_response` is the model's exact text when one was received
    (None for API errors or --no-ai, where no response text exists)."""
    return ActionResult(
        action=f"{row.owner} should contact {row.candidate_name} for a status update.",
        who="owner",
        reason="Fallback action: no valid AI suggestion was available.",
        source="fallback",
        fallback_reason=fallback_reason,
        raw_response=raw_response,
    )


def call_model(client: Any, model: str, directive_text: str, ctx: ModelContext) -> str:
    """Isolated network call, OpenAI-compatible shape (used for OpenRouter).
    Tests mock `client`, never the network."""
    response = client.chat.completions.create(
        model=model,
        max_tokens=200,
        messages=[
            {"role": "system", "content": directive_text},
            {"role": "user", "content": json.dumps(row_to_dict(ctx))},
        ],
    )
    return response.choices[0].message.content


def suggest_action(
    client: Any, model: str, directive_text: str, ctx: ModelContext
) -> ActionResult:
    try:
        raw_text = call_model(client, model, directive_text, ctx)
    except Exception as e:
        return rule_based_action(ctx.row, f"API error: {e}")

    try:
        return parse_and_validate(raw_text, ctx)
    except ValidationError as e:
        return rule_based_action(ctx.row, f"validation failed: {e}", raw_response=raw_text)
