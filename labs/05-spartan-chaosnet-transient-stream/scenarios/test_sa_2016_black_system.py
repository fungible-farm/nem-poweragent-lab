"""pytest wrapper for `sa_2016_black_system.py`
(docs/prd/0002-sa-2016-black-system-cascade-scenario.md), following
`labs/_shared/test_scenario_engine.py`'s own `--step check` + subprocess
pattern.

**Skipped by default, unlike every other `--step check` test in this repo**
-- named here, not hidden (AGENTS.md "sandbox stand-ins must be named, not
hidden" applies just as much to a skipped-by-default test as to a code
stand-in). This scenario simulates ~43s of grid time at Lab 5's 200us EMT
timestep (~215,000 raw solve steps, ~78x `demo_scenario.py`'s own
~2,750-step run) -- measured in this sandbox at several hundred seconds of
real wall-clock time (see this implementation's own commit message / PR
notes for the actual measured figure). Collecting this test unconditionally
would make the routine `uv run python -m pytest labs/05-spartan-chaosnet-transient-stream/
labs/_shared/` sweep (documented in AGENTS.md and this PRD's own
verification steps as the fast, "run it often" regression gate, historically
~60s total) balloon to that same several-hundred-second figure -- a real
regression to that convention's whole purpose. This test is therefore
gated on the `RUN_SLOW_SCENARIOS` environment variable, skipped (not
silently passed -- `pytest.skip()` reports as SKIPPED, never PASSED)
unless set:

    RUN_SLOW_SCENARIOS=1 uv run python -m pytest \
        labs/05-spartan-chaosnet-transient-stream/scenarios/test_sa_2016_black_system.py -v

or run the scenario script directly (same underlying command this test
wraps):

    uv run labs/05-spartan-chaosnet-transient-stream/scenarios/sa_2016_black_system.py --step check
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
        f"sa_2016_black_system.py's --step check solves ~43s of grid time "
        f"(several hundred seconds wall-clock) -- opt in with "
        f"{_SLOW_TEST_ENV_VAR}=1 (see this file's own module docstring)"
    ),
)
def test_sa_2016_black_system_matches_fixture():
    result = subprocess.run(
        [sys.executable, str(SCENARIOS_DIR / "sa_2016_black_system.py"), "--step", "check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout
