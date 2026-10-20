"""Command-line entry point: wires loader -> core -> ranking -> (optional)
AI layer -> output. No business logic lives here; it only orchestrates
and formats.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from stall_alert import ai_actions
from stall_alert.core import Verdict, evaluate_candidate, load_config
from stall_alert.loader import RowWarning, load_rows
from stall_alert.ranking import RankedCandidate, rank

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="stall-alert")
    parser.add_argument("board_csv", help="Path to the hiring-board CSV export")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument(
        "--today",
        default=None,
        help="Reference date (YYYY-MM-DD) for reproducible results; defaults to the real current date",
    )
    parser.add_argument(
        "--no-ai", action="store_true", help="Skip the AI layer; use rule-based actions only"
    )
    parser.add_argument(
        "--top", type=int, default=None, help="Show only the top N stalled candidates"
    )
    parser.add_argument(
        "--format", choices=["table", "json", "md"], default="table", help="Output format"
    )
    parser.add_argument(
        "--directive", default="directive.md", help="Path to the AI directive file"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print an AI fallback-rate summary (stalled/ai/fallback counts, "
        "fallback rate, and fallback reasons grouped by cause)",
    )
    parser.add_argument(
        "--encoding",
        default=None,
        help="Encoding to read the CSV as (e.g. cp1252). Default: try UTF-8, "
        "falling back to cp1252 with a warning if that fails.",
    )
    return parser.parse_args(argv)


def resolve_today(today_arg: Optional[str]) -> date:
    if today_arg is None:
        return date.today()
    return datetime.strptime(today_arg, "%Y-%m-%d").date()


@dataclass(frozen=True)
class CombinedBadRow:
    row_number: int
    reason: str


def run(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    today = resolve_today(args.today)
    try:
        config = load_config(args.config)
        load_result = load_rows(args.board_csv, today, encoding=args.encoding)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if load_result.encoding_warning:
        print(f"Warning: {load_result.encoding_warning}")

    bad_rows: list[CombinedBadRow] = [
        CombinedBadRow(e.row_number, e.reason) for e in load_result.errors
    ]
    warnings: list[RowWarning] = load_result.warnings
    on_hold: list = []
    stalled: list = []

    for row in load_result.rows:
        status = evaluate_candidate(row, config, today)
        if status.verdict == Verdict.BAD_ROW:
            bad_rows.append(CombinedBadRow(row.row_number, status.bad_row_reason))
        elif status.verdict == Verdict.ON_HOLD:
            on_hold.append(status)
        elif status.verdict == Verdict.STALLED:
            stalled.append(status)

    bad_rows.sort(key=lambda b: b.row_number)
    ranked = rank(stalled, config)
    if args.top is not None:
        ranked = ranked[: args.top]

    directive_text = ai_actions.load_directive(args.directive) if not args.no_ai else None
    client = None if args.no_ai else _build_client()
    model = os.environ.get("STALL_ALERT_MODEL", DEFAULT_MODEL)

    actions: dict[str, ai_actions.ActionResult] = {}
    for rc in ranked:
        row = rc.status.row
        if args.no_ai:
            actions[row.candidate_id] = ai_actions.rule_based_action(
                row, "AI disabled via --no-ai flag"
            )
        else:
            ctx = ai_actions.ModelContext(
                row=row,
                today=today,
                days_in_stage=rc.status.days_in_stage,
                threshold=rc.status.threshold,
                days_over_threshold=rc.status.days_over_threshold,
            )
            actions[row.candidate_id] = ai_actions.suggest_action(
                client, model, directive_text, ctx
            )

    if args.report:
        print(render_report(ranked, actions))
        print("")

    output = render(args.format, today, bad_rows, warnings, on_hold, ranked, actions)
    print(output)
    return 0


_FALLBACK_CAUSES = [
    ("invalid_json", "invalid JSON"),
    ("api_error", "API error"),
    ("flagged_number", "invented number"),
    ("flagged_date", "invented date"),
    ("flagged_duration", "invented duration"),
    ("flagged_name", "possible invented name"),
    ("overlong_action", "more than"),
    ("invalid_waiting_on", "'waiting_on' must be"),
    ("invalid_deadline", "deadline not allowed"),
    ("missing_or_invalid_field", "missing or invalid"),
    ("ai_disabled", "--no-ai"),
]


def classify_fallback_causes(reason: str) -> list[str]:
    """Substring-match the fallback_reason text into cause buckets.
    Not mutually exclusive - one reason can hit more than one bucket.
    Diagnostic only, not a stable API."""
    causes = [label for label, needle in _FALLBACK_CAUSES if needle in reason]
    return causes or ["other"]


def render_report(ranked: list[RankedCandidate], actions: dict) -> str:
    stalled_count = len(ranked)
    ai_count = sum(1 for rc in ranked if actions[rc.status.row.candidate_id].source == "ai")
    fallback_count = stalled_count - ai_count
    rate = (fallback_count / stalled_count * 100) if stalled_count else 0.0

    cause_counts: dict[str, int] = {}
    for rc in ranked:
        action = actions[rc.status.row.candidate_id]
        if action.source != "fallback":
            continue
        for cause in classify_fallback_causes(action.fallback_reason or ""):
            cause_counts[cause] = cause_counts.get(cause, 0) + 1

    lines = [
        "=== AI fallback report ===",
        f"stalled: {stalled_count}  ai: {ai_count}  fallback: {fallback_count}  "
        f"fallback_rate: {rate:.1f}%",
        "fallback reasons by cause (not mutually exclusive):",
    ]
    if cause_counts:
        for cause, count in sorted(cause_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"  {cause}: {count}")
    else:
        lines.append("  (none)")
    return "\n".join(lines)


def _build_client():
    import openai

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Set it in your environment, or "
            "pass --no-ai to skip the AI layer."
        )
    return openai.OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)


def render(
    fmt: str,
    today: date,
    bad_rows: list[CombinedBadRow],
    warnings: list[RowWarning],
    on_hold: list,
    ranked: list[RankedCandidate],
    actions: dict[str, ai_actions.ActionResult],
) -> str:
    if fmt == "json":
        return _render_json(today, bad_rows, warnings, on_hold, ranked, actions)
    if fmt == "md":
        return _render_md(today, bad_rows, warnings, on_hold, ranked, actions)
    return _render_table(today, bad_rows, warnings, on_hold, ranked, actions)


def _render_json(today, bad_rows, warnings, on_hold, ranked, actions) -> str:
    payload = {
        "today": today.isoformat(),
        "bad_rows": [{"row": b.row_number, "reason": b.reason} for b in bad_rows],
        "warnings": [{"row": w.row_number, "reason": w.reason} for w in warnings],
        "on_hold": [
            {
                "candidate_id": s.row.candidate_id,
                "candidate_name": s.row.candidate_name,
                "stage": s.row.stage,
            }
            for s in on_hold
        ],
        "stalled": [_ranked_to_dict(rc, actions) for rc in ranked],
    }
    return json.dumps(payload, indent=2)


def _ranked_to_dict(rc: RankedCandidate, actions: dict) -> dict:
    row = rc.status.row
    action = actions.get(row.candidate_id)
    return {
        "candidate_id": row.candidate_id,
        "candidate_name": row.candidate_name,
        "role": row.role,
        "stage": row.stage,
        "owner": row.owner,
        "days_in_stage": rc.status.days_in_stage,
        "threshold": rc.status.threshold,
        "days_over_threshold": rc.status.days_over_threshold,
        "stage_weight": rc.stage_weight,
        "priority_weight": rc.priority_weight,
        "score": rc.score,
        "score_breakdown": (
            f"{rc.status.days_over_threshold} x {rc.stage_weight} x "
            f"{rc.priority_weight} = {rc.score}"
        ),
        "action": action.action if action else None,
        "waiting_on": action.waiting_on if action else None,
        "action_source": action.source if action else None,
        "fallback_reason": action.fallback_reason if action else None,
        "raw_response": action.raw_response if action else None,
    }


def _truncate(text: Optional[str], limit: int = 500) -> str:
    if text is None:
        return "(none)"
    return text if len(text) <= limit else text[:limit] + "..."


def _render_table(today, bad_rows, warnings, on_hold, ranked, actions) -> str:
    lines = [f"stall-alert report (today = {today.isoformat()})", ""]

    lines.append(f"Bad rows excluded: {len(bad_rows)}")
    for b in bad_rows:
        lines.append(f"  row {b.row_number}: {b.reason}")

    lines.append(f"Warnings: {len(warnings)}")
    for w in warnings:
        lines.append(f"  row {w.row_number}: {w.reason}")

    lines.append(f"On hold (not flagged): {len(on_hold)}")
    for s in on_hold:
        lines.append(f"  {s.row.candidate_id} {s.row.candidate_name} ({s.row.stage})")

    lines.append("")
    lines.append(f"Stalled candidates, ranked ({len(ranked)}):")
    for i, rc in enumerate(ranked, start=1):
        d = _ranked_to_dict(rc, actions)
        lines.append(
            f"{i}. [{d['score']}] {d['candidate_name']} ({d['candidate_id']}) - "
            f"{d['role']} / {d['stage']}, {d['days_in_stage']}d in stage "
            f"(threshold {d['threshold']})"
        )
        lines.append(f"   breakdown: {d['score_breakdown']}")
        action_line = f"   action [{d['action_source']}] -> waiting_on={d['waiting_on']}: {d['action']}"
        if d["fallback_reason"]:
            action_line += f" (fallback reason: {d['fallback_reason']})"
        lines.append(action_line)
        lines.append(f"   raw_response: {_truncate(d['raw_response'])}")
    return "\n".join(lines)


def _render_md(today, bad_rows, warnings, on_hold, ranked, actions) -> str:
    lines = [f"# stall-alert report (today = {today.isoformat()})", ""]

    lines.append(f"## Bad rows excluded ({len(bad_rows)})")
    for b in bad_rows:
        lines.append(f"- row {b.row_number}: {b.reason}")
    lines.append("")

    lines.append(f"## Warnings ({len(warnings)})")
    for w in warnings:
        lines.append(f"- row {w.row_number}: {w.reason}")
    lines.append("")

    lines.append(f"## On hold - not flagged ({len(on_hold)})")
    for s in on_hold:
        lines.append(f"- {s.row.candidate_id} {s.row.candidate_name} ({s.row.stage})")
    lines.append("")

    lines.append(f"## Stalled candidates, ranked ({len(ranked)})")
    lines.append(
        "| Rank | Candidate | Role / Stage | Days in stage | Threshold | "
        "Breakdown | Score | Action | Waiting on | Source | Fallback reason | Raw response |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, rc in enumerate(ranked, start=1):
        d = _ranked_to_dict(rc, actions)
        raw = _truncate(d["raw_response"]).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {i} | {d['candidate_name']} ({d['candidate_id']}) | "
            f"{d['role']} / {d['stage']} | {d['days_in_stage']} | {d['threshold']} | "
            f"{d['score_breakdown']} | {d['score']} | {d['action']} | {d['waiting_on']} | "
            f"{d['action_source']} | {d['fallback_reason'] or ''} | {raw} |"
        )
    return "\n".join(lines)


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
