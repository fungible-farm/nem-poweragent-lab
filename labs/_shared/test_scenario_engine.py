"""pytest wrapper for `labs/_shared/scenario_engine`
(docs/prd/0001-composable-generator-detector-platform.md), following
`labs/05-spartan-chaosnet-transient-stream/test_lab5.py`'s own
`--step check` + subprocess pattern.

Two things are checked here, per the implementation plan:

1. This package's own synthetic proof scenario (`demo_scenario.py`)
   self-checks against its committed `expected_demo_scenario_run.json`
   fixture -- PRD-0001's own acceptance bar (a condition-triggered
   generator and a detector, demonstrated end to end).
2. A **direct** re-run of Lab 5's own `test_lab5.py` tests, so this
   package's test suite proves -- every time it runs, not just once at
   review time -- that extending `chaosnet.py`/`run_dpsim.py` for this
   platform caused zero behaviour change to Lab 5's existing single fault
   (the plan's own explicit, non-negotiable regression bar).

Plus a handful of direct unit tests of `generators.ProtectionTripGenerator`'s
tagged-union `trigger_condition` (`SustainTriggerCondition` |
`CountTriggerCondition`) against a stub switch -- the specific gap
`docs/prd/0002-sa-2016-black-system-cascade-scenario.md`'s own "Composable
capability mapping" names in PRD-0001's original sketch and instructs be
backported "now," per this implementation's own plan. These do not need a
live DPsim solve: `ready()`/`fire()` only need a `MeasurementState` and an
object with `.open()`/`.close()` methods, so a plain stub is enough to
prove the dispatch logic itself is correct, independent of any real
solve's numeric behaviour (that end-to-end proof is `demo_scenario.py`'s
own job, checked separately above).
"""
import subprocess
import sys
from pathlib import Path

SHARED_DIR = Path(__file__).resolve().parent
LAB5_DIR = SHARED_DIR.parent / "05-spartan-chaosnet-transient-stream"
SCENARIO_ENGINE_DIR = SHARED_DIR / "scenario_engine"

sys.path.insert(0, str(SHARED_DIR.parent))
from _shared.scenario_engine.generators import (  # noqa: E402
    ProtectionTripGenerator,
)


class _StubSwitch:
    """A minimal `.open()`/`.close()` stand-in for a dpsimpy
    `emt.ph3.Switch`, so `ProtectionTripGenerator`'s trigger-condition
    dispatch logic can be unit-tested without a live DPsim solve."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def open(self) -> None:
        self.calls.append("open")

    def close(self) -> None:
        self.calls.append("close")


def _run_check(directory: Path, script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(directory / script), "--step", "check"],
        capture_output=True,
        text=True,
    )


# --- 1. This package's own synthetic proof scenario -------------------------


def test_demo_scenario_matches_fixture():
    result = _run_check(SCENARIO_ENGINE_DIR, "demo_scenario.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


# --- 2. Direct regression: Lab 5's own tests still pass unmodified ---------


def test_lab5_topology_matches_fixture_unmodified():
    result = _run_check(LAB5_DIR, "generate_topology.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


def test_lab5_dpsim_run_matches_fixture_unmodified():
    result = _run_check(LAB5_DIR, "run_dpsim.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


def test_lab5_stream_summary_matches_fixture_unmodified():
    result = _run_check(LAB5_DIR, "verify_stream.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


# --- 3. Direct unit tests of the tagged-union trigger_condition -------------


def _state(t_s: float, measurement: str, history: list[tuple[float, float]]) -> dict:
    values = {measurement: history[-1][1]} if history else {}
    return {"t_s": t_s, "values": values, "history": {measurement: history}}


def test_sustain_trigger_condition_fires_once_window_is_fully_below_limit():
    """SustainTriggerCondition: must NOT fire on a single qualifying
    sample, and must fire only once the trailing sustain_s window is both
    full and entirely below the limit."""
    switch = _StubSwitch()
    gen = ProtectionTripGenerator(
        id="trip-test",
        target="SUB-X",
        action={"asset": "SUB-X", "effect": "close"},
        trigger_condition={
            "kind": "sustain",
            "measurement": "SUB-X_voltage_v",
            "comparator": "<",
            "limit": 100.0,
            "sustain_s": 0.05,
        },
        switch=switch,
    )
    # Below-limit for only 0.02s so far -- window not yet full: must not fire.
    history = [(0.0, 50.0), (0.01, 50.0), (0.02, 50.0)]
    assert gen.ready(0.02, _state(0.02, "SUB-X_voltage_v", history)) is False

    # Below-limit continuously from t=0.0 to t=0.06 (>= 0.05s sustain_s): must fire.
    history = [(0.0, 50.0), (0.01, 50.0), (0.02, 50.0), (0.03, 50.0), (0.04, 50.0), (0.05, 50.0), (0.06, 50.0)]
    assert gen.ready(0.06, _state(0.06, "SUB-X_voltage_v", history)) is True
    event = gen.fire(None, 0.06)
    assert event["kind"] == "trip"
    assert event["generator_id"] == "trip-test"
    assert switch.calls == ["close"]
    # Once fired, ready() must never fire again.
    assert gen.ready(0.10, _state(0.10, "SUB-X_voltage_v", history)) is False


def test_sustain_trigger_condition_does_not_fire_if_window_briefly_recovers():
    """A value back above the limit anywhere in the trailing window must
    block firing -- "sustained" means the *entire* window qualifies."""
    switch = _StubSwitch()
    gen = ProtectionTripGenerator(
        id="trip-test",
        target="SUB-X",
        action={"asset": "SUB-X", "effect": "close"},
        trigger_condition={
            "kind": "sustain",
            "measurement": "SUB-X_voltage_v",
            "comparator": "<",
            "limit": 100.0,
            "sustain_s": 0.05,
        },
        switch=switch,
    )
    history = [(0.0, 50.0), (0.02, 150.0), (0.04, 50.0), (0.06, 50.0)]
    assert gen.ready(0.06, _state(0.06, "SUB-X_voltage_v", history)) is False


def test_count_trigger_condition_fires_once_enough_dips_in_window():
    """CountTriggerCondition (PRD-0002's backported gap): fires once
    `count` qualifying dips have occurred within the trailing `window_s`,
    regardless of whether the measurement is continuously below
    threshold."""
    switch = _StubSwitch()
    gen = ProtectionTripGenerator(
        id="trip-test-count",
        target="SUB-Y",
        action={"asset": "SUB-Y", "effect": "close"},
        trigger_condition={
            "kind": "count",
            "measurement": "SUB-Y_voltage_v",
            "dip_threshold": 100.0,
            "count": 3,
            "window_s": 1.0,
        },
        switch=switch,
    )
    # Two dips (below 100) interleaved with recoveries (above 100) -- not
    # enough yet.
    history = [(0.0, 50.0), (0.1, 150.0), (0.2, 50.0), (0.3, 150.0)]
    assert gen.ready(0.3, _state(0.3, "SUB-Y_voltage_v", history)) is False

    # A third dip within the same 1.0s window: now fires.
    history = history + [(0.4, 150.0), (0.5, 50.0)]
    assert gen.ready(0.5, _state(0.5, "SUB-Y_voltage_v", history)) is True
    event = gen.fire(None, 0.5)
    assert event["kind"] == "trip"
    assert switch.calls == ["close"]


def test_count_trigger_condition_only_counts_dips_within_the_rolling_window():
    """A dip that has aged out of the trailing window_s must not count."""
    switch = _StubSwitch()
    gen = ProtectionTripGenerator(
        id="trip-test-count-2",
        target="SUB-Y",
        action={"asset": "SUB-Y", "effect": "close"},
        trigger_condition={
            "kind": "count",
            "measurement": "SUB-Y_voltage_v",
            "dip_threshold": 100.0,
            "count": 2,
            "window_s": 0.5,
        },
        switch=switch,
    )
    # First dip at t=0.0 is 0.6s in the past by t=0.6 -- outside the 0.5s
    # window -- so only the t=0.5 dip counts, not enough for count=2.
    history = [(0.0, 50.0), (0.5, 50.0), (0.6, 150.0)]
    assert gen.ready(0.6, _state(0.6, "SUB-Y_voltage_v", history)) is False
