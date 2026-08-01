"""pytest wrapper around Lab 3's orchestrator, for scripts/run_labs_1_3.sh."""
import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent


def test_lab3_scorecard_matches_fixture():
    result = subprocess.run(
        [sys.executable, str(LAB_DIR / "orchestrator.py"), "--step", "check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout
