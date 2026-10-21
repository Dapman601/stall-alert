"""Runs scripts/demo.md's commands in order, for the demo video.

Post-freeze addition for demo rehearsal/recording; does not change any
stall_alert/ behavior. Prints a heading, the command, then its output for
each step, pausing for Enter between steps (use --no-pause to run through
without stopping). The one AI step reads OPENROUTER_API_KEY from the
environment and never prints it; if the key isn't set, that step is
skipped with a message instead of being run.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

STEPS = [
    {
        "heading": "STEP 1: tests",
        "display": "pytest",
        "argv": [sys.executable, "-m", "pytest"],
        "needs_api_key": False,
    },
    {
        "heading": "STEP 2: sample board without AI",
        "display": "python -m stall_alert data/sample_board.csv --today 2026-10-16 --no-ai --format table --top 3",
        "argv": [
            sys.executable, "-m", "stall_alert",
            "data/sample_board.csv", "--today", "2026-10-16",
            "--no-ai", "--format", "table", "--top", "3",
        ],
        "needs_api_key": False,
    },
    {
        "heading": "STEP 3: with AI, --report",
        "display": "python -m stall_alert data/sample_board.csv --today 2026-10-16 --report --format table --top 3",
        "argv": [
            sys.executable, "-m", "stall_alert",
            "data/sample_board.csv", "--today", "2026-10-16",
            "--report", "--format", "table", "--top", "3",
        ],
        "needs_api_key": True,
    },
    {
        "heading": "STEP 4: one deliberate failure, handled cleanly",
        "display": "python -m stall_alert data/header_capitalized.csv --today 2026-10-20 --no-ai",
        "argv": [
            sys.executable, "-m", "stall_alert",
            "data/header_capitalized.csv", "--today", "2026-10-20", "--no-ai",
        ],
        "needs_api_key": False,
    },
    {
        "heading": "STEP 5: one honest limitation",
        "display": "python -m stall_alert data/realistic_export.csv --today 2026-10-20 --no-ai",
        "argv": [
            sys.executable, "-m", "stall_alert",
            "data/realistic_export.csv", "--today", "2026-10-20", "--no-ai",
        ],
        "needs_api_key": False,
    },
]


def run_step(step: dict, pause: bool) -> None:
    print(f"\n{'=' * 60}")
    print(step["heading"])
    print("=" * 60)

    if step["needs_api_key"] and not os.environ.get("OPENROUTER_API_KEY"):
        print("Skipping: OPENROUTER_API_KEY is not set in the environment.")
        return

    print(f"$ {step['display']}")
    result = subprocess.run(step["argv"], cwd=REPO_ROOT, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    print(f"(exit code: {result.returncode})")

    if pause:
        input("\nPress Enter to continue...")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-pause", action="store_true", help="Run all steps without pausing for Enter"
    )
    args = parser.parse_args()

    for step in STEPS:
        run_step(step, pause=not args.no_pause)


if __name__ == "__main__":
    main()
