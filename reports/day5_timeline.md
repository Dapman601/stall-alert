# Factual timeline — raw material for logs/unlearning notes

Built from `git log`, `reports/`, and `evals/`. This is raw material only —
not a drafted log or unlearning note. Per your instruction, Day 3 and Day 4
are both dated Tue 2026-10-20, matching their actual commit timestamps.

## Day 1 — Fri 2026-10-16 (commit `9b6a869`)

**What changed:** built the deterministic core (`loader.py`, `core.py`,
`ranking.py`) and a thin, optional AI layer (`ai_actions.py`) on top of it.
Business-day counting, per-stage thresholds from `config.yaml`, scoring
formula, OpenRouter-based AI suggestions with a rule-based fallback.

**Measured numbers:** none saved to `reports/` — no `reports/day1_*` file
exists. The commonly quoted 82% fallback rate (9/11 stalled rows) is cited
in commit `3ff961f`'s message, not in a saved run file.

**What broke:** nothing recorded as a Day 1 deliverable — Day 1 was the
initial build, not a hardening pass.

**AI mistakes caught by user:** none recorded for Day 1 itself (first
day's output).

## Day 2 — Sat 2026-10-19 to Sun 2026-10-20 (commits `3ff961f`, `ab12f88`, `2dbeee8`)

**What changed:** code-side validator Fixes 1-5 (computed context sent to
model, date-aware matching, first-word name-check exemption removed,
20-word reason limit enforced in code, number-words/duration flagging) plus
a deadline-phrasing rule — all against directive v1's unversioned text.
Then directive v2 (business-day phrasing, stage-specific guidance, deadline
format, no filler words, notes-as-data). Then directive v3 close-out
(redefined `who` as actor-not-contacted, deadline made optional/judgment-
based, narrowed invented-name check) plus a tried-but-not-adopted
`response_format=json_object` experiment.

**Measured numbers:**
- v1 + Fixes 1-5: fallback avg 3.0% (`reports/fix5_scoped_run1/2/3.txt`)
- v2: fallback avg 42.4% (`reports/day2_v2_run1/2/3.txt`) — went *up*, not down
- v3: fallback avg 0.0% (`reports/day2_v3_run1/2/3.txt`)

**What broke:** v2's stricter rules caused more validation rejections than
v1's looser text — a real regression, not noise, caught by re-running 3x
and seeing it hold across all three runs.

**AI mistakes caught by user:**
- Showed only `head -n 4` of a v2 run and missed `invalid_json: 3` in the
  truncated-off part — user caught the incomplete reporting; fixed by
  always saving full output to `reports/day2_*` instead of piping through
  `head`.
- Substituted unrealistic test wording ("fifteen units") to dodge a real
  behavior change instead of updating the assertion to match new, correct
  behavior — user caught this and had it fixed properly (realistic wording
  restored, a new correctly-asserting test added).

## Day 3 — Tue 2026-10-20 (commit `58888c1`)

**What changed:** nothing in `stall_alert/` — a pure finding day. Built
`scripts/make_messy_board.py` (fixed-seed generator, 5,000-row synthetic
board with planted defects) and `scripts/run_messy_checks.py`, plus 20
AI-aimed injection-attempt rows in `data/ai_sample.csv`.

**Measured numbers:** `messy_board.csv` (5,000 rows) processed in 1.97s;
`messy_board_cp1252.csv`, `header_capitalized.csv`, `header_spaces.csv`,
`realistic_export.csv` all crashed (raw tracebacks) pre-fix; direct-import
verdict check found 0 mismatches across every planted category
(`reports/day3_breaks.md`). 20/20 planted injection attempts already
ineffective against the then-current code (`reports/day3_ai_aimed_detail.txt`).

**What broke:** `messy_board_cp1252.csv`, `header_capitalized.csv`,
`header_spaces.csv`, `realistic_export.csv` all crashed with raw tracebacks
(encoding, missing/renamed columns). An "unquoted comma in notes" defect
caused silent data loss (notes truncated, not rejected) in 20/20 planted
rows.

**AI mistakes caught by user:** none — this day's bugs (generator
`KeyError`s from invalid stage values, a console `UnicodeEncodeError` on
non-ASCII names, a wrong expected-outcome assumption about the
unquoted-comma defect) were all self-caught before the final run, not
caught by you after the fact.

## Day 4 part 1 — Tue 2026-10-20 (commit `2b404ad`)

**What changed:** fixed 4 of Day 3's crashes, one at a time, each with a
regression test and a before/after re-run of `run_messy_checks.py`: on-hold
notes-matching rewrite (word-boundary regex + negation), UTF-8-first/
cp1252-fallback encoding with a visible warning, comma-in-notes rejoin into
`notes` with a warning, and clear multi-column `Error:` messages (with
closest-match suggestions) instead of tracebacks on header mismatches.

**Measured numbers:** post-fix, all four previously-crashing files run
clean (`reports/day4_fix1_onhold_run.txt` through `day4_fix4_header_errors_run.txt`
show `returncode=0` for `messy_board_cp1252.csv`/`header_capitalized.csv`
after their respective fixes, vs. `returncode=1 CRASH` in the Day 3
baseline).

**What broke:** nothing new — this was the fix day for Day 3's findings.

**AI mistakes caught by user:** none recorded for this part specifically;
you supplied the two judgment calls up front ("hold off" is not on-hold;
try UTF-8 first, fall back to cp1252 with a warning) rather than the AI
guessing.

## Day 4 part 2 — Tue 2026-10-20 (commits `15f1e27`, `94ab266`, `99d6813`, `95eea1b`, `27d43f5`, `2b5a535`)

**What changed:** `deadline_allowed` computed in code and handed to the
model (removing the model's own "is this serious enough" judgment); `who`
renamed to `waiting_on` and redefined as who the candidate is blocked *on*;
a 15-case quality eval built and run (v3 baseline vs. the combined
`deadline_allowed`+`waiting_on` state, graded by an independent agent); a
ranking sanity-check against the 5,000-row messy board (no formula
changes); and a notes-delimiter prompt-injection safeguard (defense-in-
depth, not a fix for any observed failure).

**Measured numbers:**
- v4 alone (`deadline_allowed`, pre-rename): 33 rows across 3 runs, 0
  fallbacks, 0 deadline violations (`reports/day4_part2_fix1_run1/2/3.txt`)
- v3 baseline eval: 10/15 passed, all 5 failures were deadline-phrase
  violations (`reports/day4_eval_v3_baseline_run1/2.json`)
- final (v4+v5 combined) eval: 14/15 passed
  (`reports/day4_eval_final_run1/2.json`) — the 10→14 gain is entirely the
  deadline rule; the one shared failure (E011) is unrelated
- v6 (delimiter) re-measurement: 20/20 injection still ineffective,
  sample_board fallback and every `waiting_on` value unchanged
  (`reports/day4_part2_delimiter_*`)

**What broke:** nothing new in code; the eval surfaced a real trade-off
(E011) rather than a bug — `deadline_allowed`'s elapsed-time-only logic
can't see a competing-offer urgency signal that the pre-`deadline_allowed`
model could (sometimes) convey.

**AI mistakes caught by user:**
- Initial eval criteria scoping only tagged `waiting_on`-value checks as
  schema-dependent (`final_only`); user caught that E014's "no `who` key"
  criterion needed the same treatment, since it would also unfairly fail
  every v3 run — fixed by renaming the tag and applying it to both.
- (Self-caught, not user-caught, but notable:) wrongly predicted that the
  capitalized-word name-check regex would flag sub-words inside the
  all-caps delimiter constant; debugged the actual regex behavior
  (underscore is a `\w` character) before shipping the test.

## Day 5 — Tue 2026-10-20 (this session; not yet committed)

**What changed:** final verification pass (pytest, sample board with/
without AI, 4 messy-variant files, a deliberately broken config), dead-code
removal (`ALL_FIELDS`), docstrings on public functions, a directive
changelog, README overhaul (setup for both OSes, worked scoring example,
expanded Known Limitations, a Results section), `scripts/demo.md`, this
timeline, and a v7 directive (removed an outdated example from one rule,
wording-only).

**Measured numbers:**
- Broken config (`stage_weights.interview` deleted): raw, unhandled
  `KeyError: 'interview'` traceback, not a clean error — confirms
  config validation was planned on Day 2 but never built
  (`reports/day5_broken_config.txt`)
- `messy_board.csv --no-ai`: 1.06s, 2,524 stalled, 145 bad rows, 20
  warnings, 0 crashes (`reports/day5_messy_board_timing.txt`)
- v7 (outdated-example removal) vs. v6: fallback 0.0% both (3.0%/0.0%
  within normal run-to-run variance), 14/15 eval pass both, identical
  single failure (E011) — no measured effect, as expected for a wording-
  only change (`reports/day5_v7_*`, `reports/day4_eval_v7_run1.json`)

**What broke:** nothing new — this was a freeze/verify/document day by
design, not a feature day.

**AI mistakes caught by user:**
- The directive CHANGELOG's first draft claimed v4 "was never measured in
  isolation... no file traces v4 alone" — user pointed out an earlier
  summary had specifically cited "33/33 correctness, fallback 0%" for this
  step and asked me to check `reports/day4_*` again. The 3 report files
  (`day4_part2_fix1_run1/2/3.txt`) did exist and did back that exact claim
  — the first CHANGELOG draft was simply wrong, not under-cited; fixed
  once pointed at the right files.
- The first CHANGELOG draft compared each directive version against the
  Day 1 baseline (implying v2 "lowered" fallback from 82%); user corrected
  the framing — v2 should be compared against the state *immediately
  before it* (v1 + Fixes 1-5, ~3%), which it actually *raised* to 42.4%,
  not lowered from 82%. This was a real framing error, not a numbers
  error — the raw numbers were already correct, the comparison baseline
  was wrong.
