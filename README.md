# stall-alert

Reads a CSV export of a hiring board, finds candidates who have not moved
stage for longer than an allowed number of business days, ranks who to
follow up with first, and suggests one next action per candidate. A
recruiter reads the output; nothing is sent automatically.

## Setup

```
pip install -r requirements.txt
```

Set `OPENROUTER_API_KEY` in your environment if you want the AI layer
(skip it entirely with `--no-ai`). Optionally set `STALL_ALERT_MODEL`
to an OpenRouter model id (default: `anthropic/claude-sonnet-4.5`).
Requests go to OpenRouter's OpenAI-compatible endpoint
(`https://openrouter.ai/api/v1/chat/completions`), not directly to
Anthropic.

## Running it

```
python -m stall_alert data/sample_board.csv --config config.yaml --today 2026-10-16 --no-ai --format table
```

Flags:
- `--config` path to `config.yaml` (default `config.yaml`)
- `--today YYYY-MM-DD` reference date for reproducible results (default: real current date)
- `--no-ai` skip the AI layer; use rule-based actions only
- `--top N` show only the top N stalled candidates
- `--format table|json|md` output format (default `table`)
- `--directive` path to the AI directive file (default `directive.md`)

## Running tests

```
pytest
```

All AI calls are mocked in tests; the suite never makes a network call.

## Architecture

Two strictly separate layers:

- **Core** (`loader.py`, `core.py`, `ranking.py`): pure Python, no AI,
  fully tested. Loads and validates the CSV, computes business days in
  the current stage, applies per-stage thresholds from `config.yaml`,
  and ranks stalled candidates.
- **AI layer** (`ai_actions.py`): thin and optional. For each stalled
  candidate, asks the model (prompt loaded from `directive.md` at
  runtime) for one next action as JSON, validates the response, and
  falls back to a rule-based action (marked `fallback`, with a
  `fallback_reason`) if anything about the response can't be trusted.
  The model is called through OpenRouter's OpenAI-compatible API (not
  the Anthropic SDK directly) — see Assumption 15.

## Scoring formula

```
score = days_over_threshold * stage_weight * priority_weight
```

- `days_over_threshold` = `days_in_stage - threshold` (only computed for
  stalled candidates, i.e. `days_in_stage > threshold`)
- `stage_weight` and `priority_weight` come from `config.yaml`; later
  stages and higher-priority roles weigh more
- Every ranked row in the output shows its breakdown
  (`days_over x stage_weight x priority_weight = score`) so a human can
  see exactly why it ranks where it does
- Ties are broken by `days_over_threshold` (descending), then
  `candidate_id` (ascending), so output order is deterministic

"Stalled" means `days_in_stage > threshold`, strictly greater — a
candidate exactly at the threshold is **not** stalled.

## Business-day counting

Business days (Mon-Fri) are counted **exclusive of the start date,
inclusive of the end date**: entering a stage on Monday and checking on
Tuesday is 1 day in stage; checking the same Monday is 0 days. If
`stage_entered_date` itself falls on a weekend, counting begins from the
following Monday.

## Sample data answer key (`data/sample_board.csv`, all relative to `--today 2026-10-16`)

| candidate_id | case |
|---|---|
| C001 Alice Johnson | stalled, applied, 1 day over |
| C002 Bob Lee | exactly at threshold (applied, 3 days) — not stalled |
| C003 Carol Smith | exactly at threshold (screening, 3 days) — not stalled |
| C004 David Kim | stalled, screening, 1 day over |
| C005 Elena Garcia | exactly at threshold (interview, 5 days) — not stalled |
| C006 Frank Wright | stalled, interview, 1 day over |
| C007 Grace Park | stalled, final_interview, 2 days over |
| C008 Henry Cho | stalled, stage written as "Final Interview" — tests stage-name normalization |
| C009 Irene Novak | exactly at threshold (offer, 2 days) — not stalled |
| C010 Jack Daniels | stalled, offer, 1 day over |
| C011 Karen White | stalled, stage written as "final-interview" — tests stage-name normalization, highest-scoring non-trivial case |
| C012 Leo Martin | terminal (hired) — never flagged despite being very old |
| C013 Mia Chen | terminal (rejected) — never flagged |
| C014 Noah Davis | terminal (withdrawn) — never flagged |
| C015 Olivia Brooks | "on hold" in notes — listed separately, not flagged as stalled |
| C016 Paul Reyes | bad row: missing `stage_entered_date` |
| C017 Quinn Harper | bad row: malformed `stage_entered_date` (`2026/10/10`) |
| C018 Rachel Kim | bad row: `stage_entered_date` after `--today` |
| C019 Steve Young | bad row: stage `onboarding` is not in config thresholds or terminal_stages |
| C020 Tina Brooks | not stalled; `last_contact_date` (`15th Oct`) is unparseable — reported as a **warning**, not a bad row |
| C021 Uma Patel | stalled, `stage_entered_date` on a Saturday — tests weekend roll-forward |
| C022 Victor Hugo | stalled, screening, 7 days over |
| C023 Wendy Alo | stalled, interview, 2 days over |
| C024 Xander Lee | not stalled (applied, 2 days, below threshold) |
| C025 Yara Singh | stalled, final_interview, 7 days over, highest score overall |

## Assumptions

Decisions made that were not explicitly specified, listed here instead
of guessed silently:

1. CSV dates must be ISO `YYYY-MM-DD`; any other format is a bad row.
2. Row numbers in bad-row/warning reports count the header as row 1
   (matching what you'd see opening the file in a spreadsheet).
3. `--today` defaults to the real current date if omitted.
4. Required fields are `candidate_id`, `candidate_name`, `role`, `stage`,
   `stage_entered_date`, `owner`, `role_priority`; `last_contact_date`
   and `notes` may be blank.
5. `role_priority` must be one of `high`/`medium`/`low` (case-insensitive,
   normalized to lowercase); anything else is a bad row.
6. If the CSV header is missing a required column entirely, that's a
   fatal error (the tool exits), not a per-row bad row, since it would
   affect every row identically.
7. "on hold" detection is a case-insensitive substring match on `notes`.
8. Terminal-stage matching is case-insensitive and normalized the same
   way stage names are (spaces/hyphens -> underscores) before comparing
   to `hired`/`rejected`/`withdrawn`.
9. Terminal-stage status takes priority over on-hold status: a
   terminal-stage row is reported as terminal even if its notes also
   contain "on hold".
10. CLI default output format is `table`; `--top` with no value shows
    all stalled candidates.
11. The AI layer's "no invented names" check is a heuristic, not an NLP
    name detector: it flags capitalized words (other than the first
    word of the sentence) that aren't in a small built-in list of common
    action vocabulary and aren't drawn from the candidate's own name or
    owner fields. This can occasionally over- or under-flag; it's
    intentionally simple for a thin, iterable AI layer.
12. Both the `action` and `reason` fields from the model are checked for
    invented names/dates/numbers; only `action` enforces the 25-word cap
    (per `directive.md`, `reason` is capped at 20 words there, but that
    cap is advisory to the model, not re-validated in code).
13. `ActionResult.fallback_reason` is `None` when `source == "ai"`, and
    is populated for every fallback case (API error, invalid JSON,
    failed validation, or `--no-ai`) so the output explains *why* a row
    fell back.
14. Test fixtures are defined inline in each test file rather than in a
    shared fixtures module.
15. The AI layer talks to OpenRouter's OpenAI-compatible
    `/chat/completions` endpoint rather than the Anthropic SDK directly
    (per a Day 1 request, overriding the original Anthropic-API
    design). The directive is sent as the `system` message; the
    candidate row as the `user` message; the response is read from
    `choices[0].message.content`. `STALL_ALERT_MODEL` must be an
    OpenRouter model id (default `anthropic/claude-sonnet-4.5`); the
    key comes from `OPENROUTER_API_KEY`, never hardcoded.
