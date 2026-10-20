# stall-alert — 5-minute demo script

Run these in order, from the repo root, with a venv activated and
dependencies installed (`pip install -r requirements.txt`). Before
starting, export `OPENROUTER_API_KEY` in your shell **out of camera/screen
view** (e.g. in a terminal tab you don't share) — no command below prints
the key, but don't type it live either.

## 1. Tests passing (~15s)

```
pytest
```

**Show:** `108 passed, 2 xfailed` at the bottom. Mention the 2 `xfailed`
are documented, known gaps (not hidden failures) — see README Known
Limitations.

## 2. Sample board without AI, one score checked by hand (~45s)

```
python -m stall_alert data/sample_board.csv --today 2026-10-16 --no-ai --format table --top 3
```

**Show:** the ranked list, specifically:
```
1. [63] Yara Singh (C025) - Engineer / final_interview, 11d in stage (threshold 4)
   breakdown: 7 x 3 x 3 = 63
```
**Say, while checking by hand:** "11 days in stage, threshold 4, so 7 days
over. `final_interview`'s stage weight is 3, her role priority is high,
weight 3. 7 x 3 x 3 = 63 — matches the output exactly."

## 3. With AI, `--report`, read two actions aloud (~60s)

```
python -m stall_alert data/sample_board.csv --today 2026-10-16 --report --format table --top 3
```

**Show:** the fallback-rate summary line near the top (`stalled: 3  ai: 3
fallback: 0  fallback_rate: 0.0%` — `--top 3` also limits how many
candidates get a live AI call, which is why this says 3, not all 11
stalled candidates) and the per-candidate `action`/`waiting_on` lines
below it. **Read two actions aloud** from the ranked list — point out
each one is specific to that candidate's stage, not a generic "follow
up."

## 4. One deliberate failure, handled cleanly (~20s)

```
python -m stall_alert data/header_capitalized.csv --today 2026-10-20 --no-ai
```

**Show:** the tool exits with a clear `Error:` listing the missing column
(`stage`) and its closest match (`Stage`) — not a raw Python traceback.
**Say:** "this is a renamed column, not a crash — the tool tells you
exactly what's wrong and what it probably means."

## 5. One honest limitation (~20s)

```
python -m stall_alert data/realistic_export.csv --today 2026-10-20 --no-ai
```

**Show:** the same kind of clear `Error:`, but this time listing *seven*
missing columns — an ATS export with completely different header names
(`"Candidate Name"`, `"Current Stage"`, etc.). **Say:** "this reads zero
rows, by design — it's not auto-mapped to a different schema, and I'd
rather it fail loudly here than guess wrong and silently misread data.
That's a real limitation, documented in the README, not a bug."

---

Total: ~3 minutes of commands/output, leaving room for questions within a
5-minute slot.
