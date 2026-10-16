from datetime import date

from stall_alert.core import CandidateStatus, Config, Verdict
from stall_alert.loader import Row
from stall_alert.ranking import rank, score

CONFIG = Config(
    thresholds={"applied": 3, "screening": 3, "interview": 5, "final_interview": 4, "offer": 2},
    terminal_stages={"hired", "rejected", "withdrawn"},
    stage_weights={"applied": 1, "screening": 1.5, "interview": 2, "final_interview": 3, "offer": 4},
    priority_weights={"high": 3, "medium": 2, "low": 1},
)


def make_row(candidate_id, role_priority) -> Row:
    return Row(
        row_number=2,
        candidate_id=candidate_id,
        candidate_name=f"Name {candidate_id}",
        role="Engineer",
        stage="applied",
        stage_entered_date=date(2026, 10, 12),
        owner="Sam",
        role_priority=role_priority,
        last_contact_date=None,
        notes="",
    )


def make_status(candidate_id, role_priority, normalized_stage, days_over) -> CandidateStatus:
    row = make_row(candidate_id, role_priority)
    return CandidateStatus(
        row=row,
        verdict=Verdict.STALLED,
        normalized_stage=normalized_stage,
        days_in_stage=CONFIG.thresholds[normalized_stage] + days_over,
        threshold=CONFIG.thresholds[normalized_stage],
        days_over_threshold=days_over,
    )


def test_score_formula():
    assert score(days_over_threshold=2, stage_weight=3, priority_weight=3) == 18


def test_rank_order_hand_verified_fixture():
    # A: applied(w=1)   * high(3)   * over1 = 3
    # B: screening(1.5) * medium(2) * over1 = 3   (tie with A on score)
    # C: final_interview(3) * high(3) * over4 = 36  (highest)
    # D: interview(2) * low(1) * over2 = 4
    a = make_status("C001", "high", "applied", 1)
    b = make_status("C002", "medium", "screening", 1)
    c = make_status("C003", "high", "final_interview", 4)
    d = make_status("C004", "low", "interview", 2)

    ranked = rank([a, b, c, d], CONFIG)
    order = [rc.status.row.candidate_id for rc in ranked]

    # C (36) > D (4) > A/B tied at 3, tie broken by candidate_id ascending
    assert order == ["C003", "C004", "C001", "C002"]
    assert ranked[0].score == 36
    assert ranked[1].score == 4
    assert ranked[2].score == ranked[3].score == 3


def test_ranked_candidate_carries_full_breakdown():
    a = make_status("C001", "high", "applied", 1)
    ranked = rank([a], CONFIG)[0]
    assert ranked.stage_weight == 1
    assert ranked.priority_weight == 3
    assert ranked.score == 1 * 1 * 3
