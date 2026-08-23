"""pytest wrapper for `iberian_2025_blackout.py --phase combined`
(docs/prd/0003-iberian-2025-blackout-scenario.md's precursor->collapse
handoff), following `test_iberian_2025_blackout.py`'s own subprocess pattern.

**Skipped by default, same convention as `test_iberian_2025_blackout.py`**
(AGENTS.md "sandbox stand-ins must be named, not hidden" applies just as
much to a skipped-by-default test): `--phase combined --step check` runs the
precursor phase (fast, ~40s) followed by the full fast-collapse phase's own
~70s-of-grid-time DPsim EMT solve (the same ~21-minute-class solve
`test_iberian_2025_blackout.py` already gates), so the combined run's own
wall-clock is dominated by that collapse-phase solve, not the handoff itself.
Gated on the same `RUN_SLOW_SCENARIOS` environment variable:

    RUN_SLOW_SCENARIOS=1 uv run python -m pytest \
        labs/05-spartan-chaosnet-transient-stream/scenarios/test_iberian_2025_combined.py -v

or run the scenario script directly (same underlying command this test
wraps):

    uv run labs/05-spartan-chaosnet-transient-stream/scenarios/iberian_2025_blackout.py \
        --phase combined --step check
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCENARIOS_DIR = Path(__file__).resolve().parent

_SLOW_TEST_ENV_VAR = "RUN_SLOW_SCENARIOS"


@pytest.mark.skipif(
    not os.environ.get(_SLOW_TEST_ENV_VAR),
    reason=(
        f"iberian_2025_blackout.py's --phase combined --step check runs the precursor "
        f"phase (~40s) then the collapse phase's own ~70s-of-grid-time EMT solve (the "
        f"same ~21-minute-class solve test_iberian_2025_blackout.py already gates) -- "
        f"opt in with {_SLOW_TEST_ENV_VAR}=1 (see this file's own module docstring)"
    ),
)
def test_iberian_2025_combined_matches_fixture():
    result = subprocess.run(
        [
            sys.executable,
            str(SCENARIOS_DIR / "iberian_2025_blackout.py"),
            "--phase", "combined",
            "--step", "check",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout
