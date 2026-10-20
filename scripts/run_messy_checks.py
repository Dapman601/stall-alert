"""Day 3: run stall-alert's core (--no-ai) against every messy/adversarial
data file, time each run, and compare results against data/messy_manifest.csv.

Read-only with respect to stall_alert/ - only imports and calls existing
functions, never modifies them. Each file's checks are wrapped so one
file crashing doesn't stop the rest from running.
"""
from __future__ import annotations

import csv
import subprocess
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
TODAY = "2026-10-20"
CONFIG = str(ROOT / "config.yaml")

sys.path.insert(0, str(ROOT))

SUBPROCESS_FILES = [
    "messy_board.csv",
    "messy_board_cp1252.csv",
    "header_capitalized.csv",
    "header_spaces.csv",
    "header_reordered.csv",
    "realistic_export.csv",
]


def run_cli_subprocess(csv_name: str) -> dict:
    csv_path = DATA_DIR / csv_name
    cmd = [
        sys.executable, "-m", "stall_alert", str(csv_path),
        "--config", CONFIG, "--today", TODAY, "--no-ai", "--format", "json",
    ]
    start = time.perf_counter()
    try:
        result = subprocess.run(
            cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=120
        )
        elapsed = time.perf_counter() - start
        return {
            "file": csv_name, "elapsed_s": elapsed, "returncode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr, "timed_out": False,
        }
    except subprocess.TimeoutExpired as e:
        elapsed = time.perf_counter() - start
        return {
            "file": csv_name, "elapsed_s": elapsed, "returncode": None,
            "stdout": e.stdout or "", "stderr": (e.stderr or "") + "\nTIMED OUT after 120s",
            "timed_out": True,
        }


def load_manifest(path: Path) -> dict[int, dict]:
    by_row = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by_row[int(row["logical_row_number"])] = row
    return by_row


def direct_import_check(csv_name: str) -> dict:
    """Uses stall_alert.loader/core directly (read-only) to get the full
    verdict for every row - including terminal/not_stalled, which the
    CLI's JSON output never surfaces - and compares against the manifest."""
    from datetime import date
    from stall_alert.core import Verdict, evaluate_candidate, load_config
    from stall_alert.loader import load_rows

    csv_path = DATA_DIR / csv_name
    manifest = load_manifest(DATA_DIR / "messy_manifest.csv")
    config = load_config(CONFIG)
    today = date(2026, 10, 20)

    result = {
        "file": csv_name, "crash": None, "total_manifest_rows": len(manifest),
        "missing_rows": [], "mismatches": defaultdict(list), "mismatch_counts": defaultdict(int),
        "truncated_notes": [], "duplicate_id_findings": [], "loaded_row_count": 0,
        "error_row_count": 0,
    }

    try:
        load_result = load_rows(str(csv_path), today)
    except Exception as e:
        result["crash"] = {
            "stage": "load_rows", "exception": repr(e),
            "traceback": traceback.format_exc(),
        }
        return result

    actual_by_row: dict[int, dict] = {}
    for err in load_result.errors:
        actual_by_row[err.row_number] = {"verdict": "bad_row", "reason": err.reason}
    result["error_row_count"] = len(load_result.errors)

    verdict_map = {
        Verdict.STALLED: "stalled", Verdict.NOT_STALLED: "not_stalled",
        Verdict.TERMINAL: "terminal", Verdict.ON_HOLD: "on_hold", Verdict.BAD_ROW: "bad_row",
    }
    for row in load_result.rows:
        try:
            status = evaluate_candidate(row, config, today)
        except Exception as e:
            result.setdefault("per_row_crashes", []).append({
                "row_number": row.row_number, "candidate_id": row.candidate_id,
                "exception": repr(e), "traceback": traceback.format_exc(),
            })
            continue
        actual_by_row[row.row_number] = {
            "verdict": verdict_map[status.verdict], "reason": status.bad_row_reason,
            "notes": row.notes, "candidate_id": row.candidate_id,
        }
    result["loaded_row_count"] = len(load_result.rows)

    for row_num, manifest_row in manifest.items():
        defect = manifest_row["defects"]
        expected = manifest_row["expected_outcome"]
        candidate_id = manifest_row["candidate_id"]
        actual = actual_by_row.get(row_num)
        if actual is None:
            result["missing_rows"].append({
                "row_number": row_num, "candidate_id": candidate_id, "defect": defect,
            })
            continue
        if actual["verdict"] != expected:
            example = {
                "row_number": row_num, "candidate_id": candidate_id,
                "expected": expected, "actual": actual["verdict"],
                "reason": actual.get("reason"),
            }
            result["mismatches"][defect].append(example)
            result["mismatch_counts"][defect] += 1
        if defect == "unquoted_comma_in_notes" and actual.get("notes") is not None:
            if actual["notes"] != "left,right":
                result["truncated_notes"].append({
                    "row_number": row_num, "candidate_id": candidate_id,
                    "actual_notes": actual["notes"],
                })

    # duplicate-id check: for each shared id, confirm both logical rows
    # independently appear with their own row numbers (no merge/overwrite)
    id_to_rows = defaultdict(list)
    for row_num, manifest_row in manifest.items():
        if manifest_row["defects"].startswith("duplicate_id"):
            id_to_rows[manifest_row["candidate_id"]].append(row_num)
    for cid, row_nums in id_to_rows.items():
        present = [rn for rn in row_nums if rn in actual_by_row]
        if len(present) != len(row_nums):
            result["duplicate_id_findings"].append({
                "candidate_id": cid, "expected_rows": row_nums, "present_rows": present,
            })

    return result


def main():
    REPORTS_DIR.mkdir(exist_ok=True)
    subprocess_results = []
    for fname in SUBPROCESS_FILES:
        print(f"Running CLI subprocess on {fname} ...")
        try:
            r = run_cli_subprocess(fname)
        except Exception:
            r = {"file": fname, "elapsed_s": None, "returncode": "HARNESS_EXCEPTION",
                 "stdout": "", "stderr": traceback.format_exc(), "timed_out": False}
        subprocess_results.append(r)
        out_path = REPORTS_DIR / f"day3_noai_{fname.replace('.csv','')}.txt"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"=== {fname} ===\n")
            f.write(f"elapsed_s: {r['elapsed_s']}\n")
            f.write(f"returncode: {r['returncode']}\n")
            f.write(f"timed_out: {r['timed_out']}\n")
            f.write("--- stdout ---\n")
            f.write(r["stdout"][:200000])
            f.write("\n--- stderr ---\n")
            f.write(r["stderr"][:200000])
        status = "CRASH" if r["returncode"] not in (0,) else "ok"
        print(f"  {fname}: returncode={r['returncode']} elapsed={r['elapsed_s']:.2f}s -> {status}" if r['elapsed_s'] else f"  {fname}: HARNESS ERROR")

    print()
    direct_results = {}
    for fname in ["messy_board.csv", "messy_board_cp1252.csv"]:
        print(f"Direct-import manifest check on {fname} ...")
        try:
            dr = direct_import_check(fname)
        except Exception:
            dr = {"file": fname, "crash": {"stage": "harness", "traceback": traceback.format_exc()}}
        direct_results[fname] = dr
        out_path = REPORTS_DIR / f"day3_direct_check_{fname.replace('.csv','')}.txt"
        with open(out_path, "w", encoding="utf-8") as f:
            import json
            def default(o):
                return str(o)
            f.write(json.dumps(dr, indent=2, default=default))
        if dr.get("crash"):
            print(f"  {fname}: CRASH at {dr['crash']['stage']}")
        else:
            print(f"  {fname}: loaded={dr['loaded_row_count']} errors={dr['error_row_count']} "
                  f"missing={len(dr['missing_rows'])} mismatch_types={len(dr['mismatch_counts'])}")

    return subprocess_results, direct_results


if __name__ == "__main__":
    main()
