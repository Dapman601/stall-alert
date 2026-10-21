"""End-to-end tests: run the real CLI as a subprocess against real data files.

Added after the Day 5 freeze for demo-video confidence; no stall_alert/
behavior change. No API calls anywhere here - every invocation uses
--no-ai, so these never touch the network and never need OPENROUTER_API_KEY.
"""
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = REPO_ROOT / "data"


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "stall_alert", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_sample_board_no_ai_matches_known_counts_and_top_candidate():
    result = run_cli(
        str(DATA / "sample_board.csv"), "--no-ai", "--today", "2026-10-16"
    )
    assert result.returncode == 0
    out = result.stdout
    assert "Bad rows excluded: 4" in out
    assert "Warnings: 1" in out
    assert "On hold (not flagged): 1" in out
    assert "Stalled candidates, ranked (11):" in out
    assert "1. [63] Yara Singh (C025)" in out
    assert "7 x 3 x 3 = 63" in out


def test_messy_board_cp1252_warns_and_exits_clean():
    result = run_cli(
        str(DATA / "messy_board_cp1252.csv"), "--no-ai", "--today", "2026-10-20"
    )
    assert result.returncode == 0
    assert "Warning: File isn't UTF-8; read as cp1252." in result.stdout


def test_header_capitalized_gives_clear_error_no_traceback():
    result = run_cli(
        str(DATA / "header_capitalized.csv"), "--no-ai", "--today", "2026-10-20"
    )
    assert result.returncode == 1
    assert "Stage" in result.stderr
    assert "Error:" in result.stderr
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_realistic_export_gives_clear_error_and_processes_zero_rows():
    result = run_cli(
        str(DATA / "realistic_export.csv"), "--no-ai", "--today", "2026-10-20"
    )
    assert result.returncode == 1
    assert "Error:" in result.stderr
    assert "Traceback" not in result.stderr
    # Known limitation: an entirely different schema reads zero rows, by
    # design, rather than being auto-mapped - see README Known Limitations.
    assert "Stalled candidates" not in result.stdout


@pytest.mark.xfail(
    reason="config validation not built (known limitation)", strict=True
)
def test_broken_config_missing_stage_weight_is_not_a_clean_error(tmp_path):
    with open(REPO_ROOT / "config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    del config["stage_weights"]["interview"]
    broken_config = tmp_path / "broken_config.yaml"
    with open(broken_config, "w", encoding="utf-8") as f:
        yaml.dump(config, f)

    result = run_cli(
        str(DATA / "sample_board.csv"),
        "--no-ai",
        "--today",
        "2026-10-16",
        "--config",
        str(broken_config),
    )
    # This SHOULD be a clean `Error:` message (like the header-mismatch
    # cases above), but config.yaml validation was never built, so it
    # currently crashes with a raw KeyError traceback instead.
    assert result.returncode == 1
    assert "Error:" in result.stderr
    assert "Traceback" not in result.stderr
