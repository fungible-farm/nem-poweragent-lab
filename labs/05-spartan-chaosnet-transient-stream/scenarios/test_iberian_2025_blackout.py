"""pytest wrapper for `iberian_2025_blackout.py`
(docs/prd/0003-iberian-2025-blackout-scenario.md), following
`sa_2016_black_system.py`'s own test wrapper pattern exactly.

**Skipped by default, same convention as `test_sa_2016_black_system.py`**
(AGENTS.md "sandbox stand-ins must be named, not hidden" applies just as
much to a skipped-by-default test as to a code stand-in). This scenario
simulates ~70s of grid time at Lab 5's 200us EMT timestep -- confirmed in
this sandbox to take over 1280s (~21 minutes) of real wall-clock time (see
this implementation's own commit message for the measured figure; notably
slower per simulated second than `sa_2016_black_system.py`'s own ~43s run,
attributable to `ProtectionTripGenerator`'s `SustainTriggerCondition`
re-scanning its full accumulated measurement history every evaluation tick
-- an O(n^2)-ish cost that grows across the run, a real platform scaling
finding worth a future fix, not addressed here). Gated on the same
`RUN_SLOW_SCENARIOS` environment variable:

    RUN_SLOW_SCENARIOS=1 uv run python -m pytest \
        labs/05-spartan-chaosnet-transient-stream/scenarios/test_iberian_2025_blackout.py -v

or run the scenario script directly (same underlying command this test
wraps):

    uv run labs/05-spartan-chaosnet-transient-stream/scenarios/iberian_2025_blackout.py --step check
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
        f"iberian_2025_blackout.py's --step check solves ~70s of grid time "
        f"(over 1280s wall-clock, confirmed) -- opt in with "
        f"{_SLOW_TEST_ENV_VAR}=1 (see this file's own module docstring)"
    ),
)
def test_iberian_2025_blackout_matches_fixture():
    result = subprocess.run(
        [sys.executable, str(SCENARIOS_DIR / "iberian_2025_blackout.py"), "--step", "check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout
