"""pytest wrapper around Lab 4's reconcile.py -- Part A only, see reconcile.py's
module docstring for why Parts B/C aren't implemented (or tested) here."""
import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent


def test_lab4_reconciliation_matches_fixture():
    result = subprocess.run(
        [sys.executable, str(LAB_DIR / "reconcile.py"), "--step", "check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout
