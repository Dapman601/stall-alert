"""Day 4 part 2: run the stall-alert AI layer against evals/cases.json
and save raw results for later grading.

Read-only with respect to stall_alert/ - just calls the existing
suggest_action() the same way cli.py does. Works against either ActionResult
schema (who or waiting_on) by inspecting whichever field is actually present,
so the same script runs the v3 baseline and the final version without
modification.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, fields
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stall_alert import ai_actions
from stall_alert.core import evaluate_candidate, load_config
from stall_alert.loader import Row

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"


def build_client():
    import openai

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set.")
    return openai.OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)


def build_row(case: dict) -> Row:
    return Row(
        row_number=0,
        candidate_id=case["candidate_id"],
        candidate_name=case["candidate_name"],
        role=case["role"],
        stage=case["stage"],
        stage_entered_date=date.fromisoformat(case["stage_entered_date"]),
        owner=case["owner"],
        role_priority=case["role_priority"],
        last_contact_date=date.fromisoformat(case["last_contact_date"])
        if case.get("last_contact_date")
        else None,
        notes=case.get("notes", ""),
    )


def actor_value(result: ai_actions.ActionResult) -> tuple[str, str]:
    """Returns (field_name, value) for whichever of who/waiting_on the
    current ActionResult schema actually has."""
    field_names = {f.name for f in fields(result)}
    if "waiting_on" in field_names:
        return "waiting_on", result.waiting_on
    if "who" in field_names:
        return "who", result.who
    return "unknown", ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, help="e.g. v3_baseline or final")
    parser.add_argument("--run", type=int, required=True, help="run number, for the output filename")
    parser.add_argument("--cases", default="evals/cases.json")
    parser.add_argument("--directive", default="directive.md")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--out-dir", default="reports")
    args = parser.parse_args()

    cases_data = json.loads((ROOT / args.cases).read_text(encoding="utf-8"))
    today = date.fromisoformat(cases_data["today"])
    config = load_config(str(ROOT / cases_data.get("config", args.config)))
    directive_text = ai_actions.load_directive(str(ROOT / args.directive))
    model = os.environ.get("STALL_ALERT_MODEL", DEFAULT_MODEL)
    client = build_client()

    results = []
    for case in cases_data["cases"]:
        row = build_row(case)
        status = evaluate_candidate(row, config, today)
        ctx = ai_actions.ModelContext(
            row=row,
            today=today,
            days_in_stage=status.days_in_stage,
            threshold=status.threshold,
            days_over_threshold=status.days_over_threshold,
        )
        result = ai_actions.suggest_action(client, model, directive_text, ctx)
        field_name, field_value = actor_value(result)

        results.append({
            "case_id": case["case_id"],
            "stage": case["stage"],
            "days_in_stage": status.days_in_stage,
            "threshold": status.threshold,
            "days_over_threshold": status.days_over_threshold,
            "action": result.action,
            "reason": result.reason,
            "actor_field_name": field_name,
            "actor_field_value": field_value,
            "source": result.source,
            "fallback_reason": result.fallback_reason,
            "raw_response": result.raw_response,
        })
        print(f"{case['case_id']}: source={result.source} {field_name}={field_value!r} action={result.action!r}")

    out_path = ROOT / args.out_dir / f"day4_eval_{args.label}_run{args.run}.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {len(results)} results to {out_path}")


if __name__ == "__main__":
    main()
