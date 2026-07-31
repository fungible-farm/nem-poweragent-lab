"""pytest wrapper around Lab 1's --step check, for scripts/run_labs_1_3.sh."""
import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent


def test_lab1_fit_matches_fixture():
    result = subprocess.run(
        [sys.executable, str(LAB_DIR / "run.py"), "--step", "check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout
