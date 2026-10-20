"""Ranking of stalled candidates.

score = days_over_threshold * stage_weight * priority_weight

Later stages and higher-priority roles weigh more because stage_weights
and priority_weights both increase with seniority/urgency (see
config.yaml). Every ranked row keeps its breakdown so a human can see
exactly why it scored the way it did.
"""
from __future__ import annotations

from dataclasses import dataclass

from stall_alert.core import CandidateStatus, Config


@dataclass(frozen=True)
class RankedCandidate:
    status: CandidateStatus
    stage_weight: float
    priority_weight: float
    score: float


def score(days_over_threshold: int, stage_weight: float, priority_weight: float) -> float:
    """days_over_threshold * stage_weight * priority_weight."""
    return days_over_threshold * stage_weight * priority_weight


def rank(stalled: list[CandidateStatus], config: Config) -> list[RankedCandidate]:
    """Rank already-filtered STALLED candidates, highest score first.

    Ties are broken by days_over_threshold (desc), then candidate_id
    (asc) so output order is deterministic.
    """
    ranked = []
    for status in stalled:
        stage_weight = config.stage_weights[status.normalized_stage]
        priority_weight = config.priority_weights[status.row.role_priority]
        s = score(status.days_over_threshold, stage_weight, priority_weight)
        ranked.append(
            RankedCandidate(
                status=status,
                stage_weight=stage_weight,
                priority_weight=priority_weight,
                score=s,
            )
        )

    ranked.sort(
        key=lambda rc: (
            -rc.score,
            -rc.status.days_over_threshold,
            rc.status.row.candidate_id,
        )
    )
    return ranked
