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
7. **(Day 4)** "on hold" detection matches `on hold`/`on-hold`/`onhold` in
   `notes` (any case, word-boundaries - so it won't match inside a longer
   word), but NOT negated forms: `no longer on hold`, `off hold`, `taken
   off hold`. `hold off` is deliberately **not** treated as on-hold - the
   match is kept narrow on purpose, so that if a note is ambiguous the
   candidate stays visible in the stalled list rather than being silently
   hidden. (Day 3 found the original plain-substring match on `"on hold"`
   missed the hyphen/no-space forms and incorrectly caught `"no longer on
   hold"`; see `reports/day3_breaks.md` and `reports/day4_fix1_onhold_run.txt`.)
8. Terminal-stage matching is case-insensitive and normalized the same
   way stage names are (spaces/hyphens -> underscores) before comparing
   to `hired`/`rejected`/`withdrawn`.
9. Terminal-stage status takes priority over on-hold status: a
   terminal-stage row is reported as terminal even if its notes also
   contain "on hold".
10. CLI default output format is `table`; `--top` with no value shows
    all stalled candidates.
11. The AI layer's "no invented names" check is a heuristic, not an NLP
    name detector: it flags capitalized words that aren't in a small
    built-in list of common action vocabulary and aren't drawn from the
    candidate's own name/role/stage fields or a row/context month name.
    As of Day 2 Fix 3, the first word of the sentence is **not**
    exempt — it's checked the same as any other word (see Day 2 #3
    below). This can occasionally over- or under-flag; it's
    intentionally simple for a thin, iterable AI layer.
12. Both the `action` and `reason` fields from the model are checked for
    invented names/dates/numbers/durations. `action` enforces the
    25-word cap; as of Day 2 Fix 4, `reason` enforces a 20-word cap in
    code too (previously that cap existed only as advisory text in
    `directive.md`).
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

### Day 2: reducing the AI fallback rate

16. **Fix 1 — computed context sent to the model.** The payload to the
    model now includes `today`, `days_in_stage`, `threshold`, and
    `days_over_threshold` (not just raw row fields), and those four
    values are added to the validator's allowed-numbers/dates set.
    Rationale: without them, the model had no way to know elapsed time
    and guessed (usually wrong); this grounds it in facts it can cite
    correctly.
17. **Fix 2 — date-aware matching.** A row/context date may appear in
    model text as ISO (`2026-10-05`), `Oct 5`, `October 5`, `5 October`,
    or a bare `5th`; all are recognized as the same date if the
    (month, day) — or just the day, for a bare ordinal — matches a
    row/context date. Month names/abbreviations derived from any
    row/context date are never flagged as invented names, independent
    of whether they're paired with a matching day in the same phrase.
18. **Fix 3 — no first-word exemption.** The capitalized-word name
    check used to skip word index 0 unconditionally ("sentence-initial
    capitalization, not a name"). It no longer does; an invented name
    at the very start of `action` or `reason` is now caught. This
    required expanding the common-vocabulary stoplist (e.g. `complete`,
    `no`, `high`/`medium`/`low`, `within`) so legitimate sentence
    starters observed in real runs don't newly fail — see Known
    Limitations for the one gap this exposed before Fix 5 closed it.
19. **Fix 4 — 20-word reason limit enforced in code.** `reason` is now
    validated the same way `action` is (strictly more than 20 words
    fails), matching the limit already stated in `directive.md`.
20. **Fix 5 — number words and duration phrases.** Number words
    (`one`–`twenty`, `dozen`) are treated like digits in the number
    check wherever they appear. Vague quantities (`a couple`, `couple`,
    `a few`, `few`, `several`, `some`) have no fixed value, so they
    only matter - and always fail - when describing a duration
    (`month(s)`/`week(s)`/`day(s)`/`hour(s)`); ordinary non-duration
    use ("answer some questions") is not a claim about elapsed time
    and passes untouched. A `<quantity> month(s)/week(s)/day(s)/
    hour(s)` phrase is checked against the same allowed-numbers set as
    any other number, with **no unit conversion** — see Known
    Limitations for why this is intentionally incomplete.
21. **Day 2 wrap-up — deadline rule, action only.** In the `action`
    field only, `"within N days"`, `"within N business days"`, or
    `"within N hours"` (N as a digit or number word, not a vague
    quantity) is allowed as a suggested deadline independent of
    context, as long as N is within a sane bound (≤5 for days/business
    days, ≤48 for hours). Exceeding the bound, or any other phrasing
    (`"by Friday"`, `"in a couple of days"`, a bare `"10 days"` with no
    "within"), is checked exactly as before. This exemption **never**
    applies to `reason` — every number there must still come from the
    row/context, with no exceptions.
22. **(Day 4)** CSV encoding: the loader tries UTF-8 first. If that
    fails, it falls back to `cp1252` automatically and prints a visible
    warning (`Warning: File isn't UTF-8; read as cp1252. If names look
    wrong, rerun with --encoding <name>.`) rather than crashing with a
    raw traceback (Day 3 found the hardcoded `utf-8-sig` decode crashed
    the whole file on any non-UTF-8 byte). `--encoding <name>` overrides
    detection entirely; if decoding still fails with an explicit
    `--encoding`, that's a clear `Error:` message, not a traceback.
    cp1252 can't represent every Unicode character (e.g. Vietnamese/
    Yoruba tone marks, CJK) - those characters are replaced with `?` on
    the fallback path, which is a real, visible data-quality cost of
    the fallback, not a bug.

## Known Limitations

Gaps found and deliberately left unfixed during Day 2, so they're
visible rather than silently absorbed:

- **Duration unit mismatch (documented via an `xfail` test,
  `test_meaning_mismatch_months_vs_day_based_threshold_not_caught`).**
  Fix 5's duration check compares only the bare numeral in a
  `month(s)`/`week(s)` phrase against the allowed-numbers set — it
  never converts "2 months" to its day-equivalent (~60 days) and
  compares that against `days_in_stage`/`threshold`/
  `days_over_threshold`. So if a row's `threshold` happens to equal the
  face-value number in the phrase (e.g. `threshold=2` and the model
  writes "2 months"), the phrase passes even though the units don't
  match and the claim is almost certainly wrong. Fixing this properly
  would mean parsing the unit and doing real conversion with a
  tolerance — a bigger feature than "treat number words like digits,"
  so it's left open rather than built today.
- **Fix 3 exposed, then Fix 5 resolved, a number-words-as-names false
  positive.** Before Fix 5 existed, removing the first-word exemption
  (Fix 3) caused a real model response starting "One day past
  threshold..." to be flagged as `possible invented name 'One'` —
  observed live in a Fix 4 test run. Fix 5's quantity-word pass now
  masks recognized number words (including at the start of a sentence)
  before the name check ever runs, so this specific case is resolved;
  flagged here because it was a real regression introduced by Fix 3
  and fixed by a later, separate fix rather than by Fix 3 itself.
- **What's actually known about Fix 3/4 live-run fallbacks, and what
  isn't.** Only the Fix 4 runs' full output was captured to disk. Of
  those: one fallback (Uma Patel, run 1) was the model citing "within 2
  days," a number with no basis in the row/context — the pre-existing
  generic number check, not a new-check side effect. One fallback
  (Victor Hugo, run 3) was the model citing "11 days" with no match in
  context — same, pre-existing generic check. The third Fix 4 fallback
  (Frank Wright, run 3) is the "One" case described above, which *was*
  caused by a new check (Fix 3). The Fix 3 runs' fallback reasons were
  never captured to a file — only summary counts were shown via `head`
  — so **it is not known** whether either of those two fallbacks was
  caused by Fix 3's new first-word check or was an ordinary cause; that
  data no longer exists and would require a fresh run to find out.
