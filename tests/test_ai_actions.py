import json
from datetime import date
from types import SimpleNamespace

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
    row = make_row()
    text = _respond(
        action="Schedule a quick check-in call this week to confirm next steps.",
        who="recruiter",
        reason="Candidate has been in the applied stage longer than expected.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", row)
    assert result.source == "ai"
    assert result.fallback_reason is None
    assert result.who == "recruiter"


# --- role/stage words from the row itself are not invented names ---

def test_role_word_in_action_is_not_flagged_as_invented_name():
    row = make_row(role="Engineer")
    text = _respond(
        action="Ask the Engineer candidate to confirm interest in the role.",
        who="recruiter",
        reason="Confirming interest keeps the applied stage moving.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", row)
    assert result.source == "ai"
    assert result.fallback_reason is None


# --- markdown-fenced JSON still parses (models often fence despite instructions) ---

def test_markdown_fenced_json_is_still_parsed():
    row = make_row()
    inner = _respond(
        action="Schedule a quick check-in call this week to confirm next steps.",
        who="recruiter",
        reason="Candidate has been in the applied stage longer than expected.",
    )
    text = f"```json\n{inner}\n```"
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", row)
    assert result.source == "ai"
    assert result.fallback_reason is None


# --- invalid JSON falls back ---

def test_invalid_json_falls_back():
    row = make_row()
    client = FakeClient(text="this is not json")
    result = ai_actions.suggest_action(client, "test-model", "directive", row)
    assert result.source == "fallback"
    assert "invalid JSON" in result.fallback_reason


# --- overlong action falls back ---

def test_overlong_action_falls_back():
    row = make_row()
    long_action = " ".join(["word"] * 30)
    text = _respond(action=long_action, who="recruiter", reason="too long test")
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", row)
    assert result.source == "fallback"
    assert "25 words" in result.fallback_reason


# --- invented name falls back ---

def test_invented_person_name_falls_back():
    row = make_row()
    text = _respond(
        action="Email Jennifer Walsh to confirm interview availability this week.",
        who="recruiter",
        reason="Need a faster response from the candidate.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", row)
    assert result.source == "fallback"
    assert "invented name" in result.fallback_reason


# --- invented number falls back ---

def test_invented_number_falls_back():
    row = make_row()
    text = _respond(
        action="Offer a 15% signing bonus to close the candidate quickly.",
        who="recruiter",
        reason="Faster close increases the chance of acceptance.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", row)
    assert result.source == "fallback"
    assert "invented number" in result.fallback_reason


# --- invented date falls back ---

def test_invented_date_falls_back():
    row = make_row()
    text = _respond(
        action="Schedule the next interview for 2026-12-01 at the latest.",
        who="recruiter",
        reason="Candidate should not wait longer than that.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", row)
    assert result.source == "fallback"
    assert "invented date" in result.fallback_reason


# --- invalid 'who' enum falls back ---

def test_invalid_who_enum_falls_back():
    row = make_row()
    text = _respond(
        action="Follow up with the candidate about the applied role.",
        who="hr_team",
        reason="Keep the process moving.",
    )
    client = FakeClient(text=text)
    result = ai_actions.suggest_action(client, "test-model", "directive", row)
    assert result.source == "fallback"
    assert "who" in result.fallback_reason


# --- API error falls back and is distinguished from validation errors ---

def test_api_error_falls_back_with_distinct_reason():
    row = make_row()
    client = FakeClient(exception=ConnectionError("network unreachable"))
    result = ai_actions.suggest_action(client, "test-model", "directive", row)
    assert result.source == "fallback"
    assert result.fallback_reason.startswith("API error")
    assert "network unreachable" in result.fallback_reason


def test_rule_based_action_has_no_content_violations():
    row = make_row()
    result = ai_actions.rule_based_action(row, "AI disabled via --no-ai flag")
    assert result.source == "fallback"
    assert result.fallback_reason == "AI disabled via --no-ai flag"
    assert ai_actions._content_violations(result.action, row) == []
