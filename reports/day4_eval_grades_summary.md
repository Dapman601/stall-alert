# Day 4 Eval Grades Summary

Grading method: each result object's `action` / `actor_field_value` / `reason` was checked against the case's `good_action_criteria` from `evals/cases.json`. `final_only: true` criteria are graded `N/A` for v3_baseline runs (v3's schema uses `who`, not `waiting_on`, so those criteria cannot apply) and graded normally (PASS/FAIL) for `final` runs. `deadline_allowed` was computed per case as `days_over_threshold >= threshold`. No rows in any of the four files used a fallback (`source` was `"ai"` for all 60 rows), so the fallback-grading rule was not triggered.

**Where final's gain over v3 actually comes from (verified against the raw grades, not just the headline 10/15 vs 14/15).** Every one of v3's 5 failures (E001, E003, E005, E009, E011 - both runs) is a deadline-phrase violation, including E011's failure, which is on a compound criterion ("must not invent an offer detail AND must not include a deadline phrase") - checking the sub-reason confirms it failed specifically on the deadline-phrase clause ("Action contains 'within 3 business days'"), not the invented-detail clause. **On every non-deadline criterion, in both runs, v3 passed all of them** - including the E011 "proposes speeding up / alerting the hiring manager" criterion, which v3 passed ("Action expedites the next interview step explicitly 'given competing offer'") while **final failed it in both runs** ("Follow up on competing offer status and timeline" only asks about the timeline, without explicitly proposing to expedite or alert). So: final's entire 14/15-vs-10/15 edge is the deadline rule working as designed; on the one case where they differ on a non-deadline criterion, v3's phrasing was actually the better one.

## v3_baseline_run1 (10/15 passed)

| case_id | overall | graded_count | na_count | reason |
|---|---|---|---|---|
| E001 | FAIL | 2 | 1 | Action contains 'within 2 business days'; days_over_threshold(1) < threshold(3) so deadline_allowed=False. |
| E002 | PASS | 3 | 0 | all criteria passed |
| E003 | FAIL | 2 | 1 | Contains 'within 2 business days'; days_over_threshold(2) < threshold(3) so deadline_allowed=False. |
| E004 | PASS | 3 | 0 | all criteria passed |
| E005 | FAIL | 2 | 1 | Contains 'within 3 business days'; days_over_threshold(2) < threshold(5) so deadline_allowed=False. |
| E006 | PASS | 3 | 0 | all criteria passed |
| E007 | PASS | 2 | 1 | all criteria passed |
| E008 | PASS | 2 | 1 | all criteria passed |
| E009 | FAIL | 2 | 1 | Contains 'within 2 business days'; days_over_threshold(1) < threshold(2) so deadline_allowed=False. |
| E010 | PASS | 2 | 1 | all criteria passed |
| E011 | FAIL | 3 | 0 | Action contains 'within 3 business days'; deadline_allowed=False (3 over threshold < 5 threshold). |
| E012 | PASS | 3 | 0 | all criteria passed |
| E013 | PASS | 2 | 1 | all criteria passed |
| E014 | PASS | 1 | 2 | all criteria passed |
| E015 | PASS | 2 | 1 | all criteria passed |

## v3_baseline_run2 (10/15 passed)

| case_id | overall | graded_count | na_count | reason |
|---|---|---|---|---|
| E001 | FAIL | 2 | 1 | Action contains 'within 2 business days'; deadline_allowed=False (1<3). |
| E002 | PASS | 3 | 0 | all criteria passed |
| E003 | FAIL | 2 | 1 | Contains 'within 2 business days'; deadline_allowed=False (2<3). |
| E004 | PASS | 3 | 0 | all criteria passed |
| E005 | FAIL | 2 | 1 | Contains 'within 3 business days'; deadline_allowed=False (2<5). |
| E006 | PASS | 3 | 0 | all criteria passed |
| E007 | PASS | 2 | 1 | all criteria passed |
| E008 | PASS | 2 | 1 | all criteria passed |
| E009 | FAIL | 2 | 1 | Contains 'within 2 business days'; deadline_allowed=False (1<2). |
| E010 | PASS | 2 | 1 | all criteria passed |
| E011 | FAIL | 3 | 0 | Action contains 'within 3 business days'; deadline_allowed=False. |
| E012 | PASS | 3 | 0 | all criteria passed |
| E013 | PASS | 2 | 1 | all criteria passed |
| E014 | PASS | 1 | 2 | all criteria passed |
| E015 | PASS | 2 | 1 | all criteria passed |

## final_run1 (14/15 passed)

| case_id | overall | graded_count | na_count | reason |
|---|---|---|---|---|
| E001 | PASS | 3 | 0 | all criteria passed |
| E002 | PASS | 3 | 0 | all criteria passed |
| E003 | PASS | 3 | 0 | all criteria passed |
| E004 | PASS | 3 | 0 | all criteria passed |
| E005 | PASS | 3 | 0 | all criteria passed |
| E006 | PASS | 3 | 0 | all criteria passed |
| E007 | PASS | 3 | 0 | all criteria passed |
| E008 | PASS | 3 | 0 | all criteria passed |
| E009 | PASS | 3 | 0 | all criteria passed |
| E010 | PASS | 3 | 0 | all criteria passed |
| E011 | FAIL | 3 | 0 | Action 'Follow up on competing offer status and timeline' only asks about the offer's status - it neither proposes expediting the next interview step nor alerts the hiring manager. |
| E012 | PASS | 3 | 0 | all criteria passed |
| E013 | PASS | 3 | 0 | all criteria passed |
| E014 | PASS | 3 | 0 | all criteria passed |
| E015 | PASS | 3 | 0 | all criteria passed |

## final_run2 (14/15 passed)

| case_id | overall | graded_count | na_count | reason |
|---|---|---|---|---|
| E001 | PASS | 3 | 0 | all criteria passed |
| E002 | PASS | 3 | 0 | all criteria passed |
| E003 | PASS | 3 | 0 | all criteria passed |
| E004 | PASS | 3 | 0 | all criteria passed |
| E005 | PASS | 3 | 0 | all criteria passed |
| E006 | PASS | 3 | 0 | all criteria passed |
| E007 | PASS | 3 | 0 | all criteria passed |
| E008 | PASS | 3 | 0 | all criteria passed |
| E009 | PASS | 3 | 0 | all criteria passed |
| E010 | PASS | 3 | 0 | all criteria passed |
| E011 | FAIL | 3 | 0 | Action 'Follow up on competing offer status and timeline for decision' only asks about the offer's timeline - it neither proposes expediting the next interview step nor alerts the hiring manager. |
| E012 | PASS | 3 | 0 | all criteria passed |
| E013 | PASS | 3 | 0 | all criteria passed |
| E014 | PASS | 3 | 0 | all criteria passed |
| E015 | PASS | 3 | 0 | all criteria passed |

## Comparison: v3_baseline (avg of 2 runs) vs final (avg of 2 runs)

**Totals:** v3_baseline averaged **10/15** passed per run vs final averaged **14/15** passed per run.

The gap is driven almost entirely by the deadline-phrase rule: v3_baseline has no `deadline_allowed` concept, so it always includes a "within N business days" deadline phrase (per its prompt), which fails the `MUST NOT include a deadline phrase` criterion on every case where `deadline_allowed=False` (E001, E003, E005, E009, E011 — 5 of 15 cases). `final` correctly omits the deadline phrase on those same cases. The one common failure (E011, in both final runs) is a content judgment call, not a deadline violation — see note below.

| case_id | v3_baseline graded_count | final graded_count | note |
|---|---|---|---|
| E001 | 2 | 3 | waiting_on criterion is N/A for v3 (final_only) |
| E002 | 3 | 3 | no final_only criteria on this case |
| E003 | 2 | 3 | waiting_on criterion is N/A for v3 |
| E004 | 3 | 3 | no final_only criteria on this case |
| E005 | 2 | 3 | waiting_on criterion is N/A for v3 |
| E006 | 3 | 3 | no final_only criteria on this case |
| E007 | 2 | 3 | waiting_on criterion is N/A for v3 |
| E008 | 2 | 3 | waiting_on criterion is N/A for v3 |
| E009 | 2 | 3 | waiting_on criterion is N/A for v3 |
| E010 | 2 | 3 | waiting_on criterion is N/A for v3 |
| E011 | 3 | 3 | no final_only criteria on this case |
| E012 | 3 | 3 | no final_only criteria on this case |
| E013 | 2 | 3 | waiting_on criterion is N/A for v3 |
| E014 | 1 | 3 | waiting_on AND "no who key" criteria both N/A for v3 (2 of 3 N/A) |
| E015 | 2 | 3 | waiting_on criterion is N/A for v3 |

v3_baseline was graded on 34 criteria total across its 15 cases (vs. 45 for final); 11 criteria were N/A per run because v3's "who" schema has no `waiting_on` field. This means v3's 10/15 pass rate was earned under a *lighter* grading load than final's 14/15 — the comparison is not entirely apples-to-apples in strictness of grading, only in the criteria that were actually applicable to each schema version.
