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
from typing import Any, Optional

from stall_alert.loader import Row

ALLOWED_WHO = {"recruiter", "hiring_manager", "owner"}
MAX_ACTION_WORDS = 25

_NUMBER_PATTERN = re.compile(r"\d+")
_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}")
_CAPITALIZED_WORD_PATTERN = re.compile(r"\b[A-Z][a-zA-Z]+\b")

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
}


class ValidationError(Exception):
    pass


@dataclass(frozen=True)
class ActionResult:
    action: str
    who: str
    reason: str
    source: str  # "ai" or "fallback"
    fallback_reason: Optional[str] = None  # None when source == "ai"


def load_directive(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def row_to_dict(row: Row) -> dict[str, Any]:
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
    }


def _allowed_text(row: Row) -> str:
    parts = [
        row.candidate_id,
        row.candidate_name,
        row.role,
        row.stage,
        row.owner,
        row.role_priority,
        row.notes,
        row.stage_entered_date.isoformat(),
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


def _content_violations(text: str, row: Row) -> list[str]:
    """Flag only invented person names, dates, and numbers - not ordinary
    words absent from the row. Ordinary vocabulary must always pass."""
    violations: list[str] = []
    allowed_text = _allowed_text(row)
    allowed_numbers = set(_NUMBER_PATTERN.findall(allowed_text))
    allowed_dates = set(_DATE_PATTERN.findall(allowed_text))
    allowed_names = _allowed_name_tokens(row)

    for full_date in _DATE_PATTERN.findall(text):
        if full_date not in allowed_dates:
            violations.append(f"invented date '{full_date}'")

    for number in _NUMBER_PATTERN.findall(text):
        if number not in allowed_numbers:
            violations.append(f"invented number '{number}'")

    words = text.split()
    for i, raw_word in enumerate(words):
        for word in _CAPITALIZED_WORD_PATTERN.findall(raw_word):
            if i == 0:
                continue  # sentence-initial capitalization, not a name
            if word.lower() in _COMMON_ACTION_WORDS:
                continue
            if word.lower() in allowed_names:
                continue
            violations.append(f"possible invented name '{word}'")

    return violations


def validate_ai_response(parsed: Any, row: Row) -> ActionResult:
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

    violations = _content_violations(action, row) + _content_violations(reason, row)
    if violations:
        raise ValidationError("; ".join(violations))

    return ActionResult(action=action.strip(), who=who, reason=reason.strip(), source="ai")


_CODE_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def _strip_code_fence(text: str) -> str:
    """Models often wrap JSON in markdown fences despite being told not
    to. Strip a single surrounding ```/```json fence if present; leave
    everything else untouched."""
    match = _CODE_FENCE_PATTERN.match(text.strip())
    return match.group(1) if match else text


def parse_and_validate(raw_text: str, row: Row) -> ActionResult:
    try:
        parsed = json.loads(_strip_code_fence(raw_text))
    except json.JSONDecodeError as e:
        raise ValidationError(f"invalid JSON: {e}") from e
    return validate_ai_response(parsed, row)


def rule_based_action(row: Row, fallback_reason: str) -> ActionResult:
    """Deterministic fallback used when the AI response is missing,
    unparseable, or fails validation (or when --no-ai is set). Built
    only from the row's own fields, so it never needs content
    validation itself. `fallback_reason` records why we're here."""
    return ActionResult(
        action=f"{row.owner} should contact {row.candidate_name} for a status update.",
        who="owner",
        reason="Fallback action: no valid AI suggestion was available.",
        source="fallback",
        fallback_reason=fallback_reason,
    )


def call_model(client: Any, model: str, directive_text: str, row: Row) -> str:
    """Isolated network call, OpenAI-compatible shape (used for OpenRouter).
    Tests mock `client`, never the network."""
    response = client.chat.completions.create(
        model=model,
        max_tokens=200,
        messages=[
            {"role": "system", "content": directive_text},
            {"role": "user", "content": json.dumps(row_to_dict(row))},
        ],
    )
    return response.choices[0].message.content


def suggest_action(client: Any, model: str, directive_text: str, row: Row) -> ActionResult:
    try:
        raw_text = call_model(client, model, directive_text, row)
    except Exception as e:
        return rule_based_action(row, f"API error: {e}")

    try:
        return parse_and_validate(raw_text, row)
    except ValidationError as e:
        return rule_based_action(row, f"validation failed: {e}")
