"""pytest wrapper for `iberian_2025_blackout.py --phase precursor`
(docs/prd/0003-iberian-2025-blackout-scenario.md's precursor phase),
following `test_iberian_2025_blackout.py`'s own subprocess pattern.

**NOT gated behind RUN_SLOW_SCENARIOS**, unlike the fast-collapse phase's
own test: the precursor phase drives `pandapower.runpp()` quasi-static
snapshots (1740 of them, at a 1.0s cadence over the real ~29-minute report
window), not a 200us-step DPsim EMT solve. Confirmed in this sandbox: a
real `--phase precursor --step check` run takes ~40s wall-clock -- two
orders of magnitude faster than the fast-collapse phase's own ~21-minute
EMT solve, and well inside this suite's own "run it often" fast-regression
budget (AGENTS.md), so it runs unconditionally.
"""
import subprocess
import sys
from pathlib import Path

SCENARIOS_DIR = Path(__file__).resolve().parent


def test_iberian_2025_precursor_matches_fixture():
    result = subprocess.run(
        [
            sys.executable,
            str(SCENARIOS_DIR / "iberian_2025_blackout.py"),
            "--phase", "precursor",
            "--step", "check",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout
