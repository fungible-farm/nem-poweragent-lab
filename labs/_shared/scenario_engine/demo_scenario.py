#!/usr/bin/env python3
"""PRD-0001's own synthetic proof scenario
(docs/prd/0001-composable-generator-detector-platform.md "Acceptance
criteria for this PRD").

A platform smoke test, not a historical-accuracy attempt (no SA 2016 /
Iberian 2025 numbers involved -- those are 0002/0003's own, separate,
larger follow-on work). Demonstrates the two capabilities PRD-0001's own
acceptance bar names explicitly, end to end, on Lab 5's existing chaos-net
topology (seed 42):

1. A `NetworkFaultGenerator` line-to-ground fault at substation SUB-3
   (trigger_time_s=0.2, clearing_duration_s=0.15 -- the same real,
   sandbox-verified values `chaos_schedule.yaml` already uses, reused here
   for narrative consistency, not because this scenario depends on that
   file).
2. A `ProtectionTripGenerator` at substation SUB-2 with a *sustain*-kind
   `trigger_condition` (`SUB-2_voltage_v < TRIP_VOLTAGE_LIMIT_V` sustained
   for `TRIP_SUSTAIN_S`), firing once SUB-3's fault has sagged SUB-2's own
   voltage long enough -- a real causal chain (fault -> measured
   consequence -> protective response), not two independent, unrelated
   events.
3. All five concrete detectors consuming the resulting real DPsim
   waveform, with `OscillationDetector` (PRD-0001's own named acceptance-
   bar detector) required to find the real switching-transient ringing at
   the fault/trip instants.

Named stand-in (AGENTS.md "sandbox stand-ins must be named, not hidden"):
`ProtectionTripGenerator`'s trip action here reuses chaosnet.py's
to-ground fault-switch primitive as the trip actuator (closing SUB-2's own
fault switch), since chaosnet.py has no independent line/asset breaker
component yet -- a real, physically simulated action (a second bolted/
impedance-limited disturbance at SUB-2), just not literally "opening a
breaker to disconnect a line." See `generators.TripAction`'s own docstring
for the same note.

Threshold provenance (AGENTS.md "no undocumented magic numbers"):
`TRIP_VOLTAGE_LIMIT_V`/`TRIP_SUSTAIN_S` were derived from a real solve run
in this sandbox (dpsim 1.2.1, seed 42): SUB-2's own positive-sequence
voltage magnitude sits at ~13324 V pre-fault and sags to a steady ~11730 V
throughout SUB-3's fault window (0.2104s-0.35s), a clear, stable ~12%
sag -- 12000 V sits strictly between those two figures, and 0.04s
(~4 phasor frames at the 100 Hz cadence `scenario.py` evaluates at) is
comfortably inside the ~140ms the sag actually holds for, so the trip
fires mid-fault, not at the very last instant before clearing.

CLI (matches every other lab's --step run/--step check convention):
    uv run labs/_shared/scenario_engine/demo_scenario.py --step run
    uv run labs/_shared/scenario_engine/demo_scenario.py --step check
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TypedDict

import numpy as np

SCENARIO_ENGINE_DIR = Path(__file__).resolve().parent
SHARED_PARENT_DIR = SCENARIO_ENGINE_DIR.parent.parent  # labs/
LAB5_DIR = SCENARIO_ENGINE_DIR.parent.parent / "05-spartan-chaosnet-transient-stream"
for _p in (str(SHARED_PARENT_DIR), str(LAB5_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import chaosnet  # noqa: E402  (from labs/05-spartan-chaosnet-transient-stream)
import run_dpsim  # noqa: E402  (reuse its TIME_STEP_S, not a second literal)
from phase_model import ThreePhaseWaveform  # noqa: E402

from _shared.scenario_engine.detectors import (  # noqa: E402
    AngleSeparationDetector,
    CascadingFailureClassifier,
    Finding,
    OscillationDetector,
    RoCoFDetector,
    VoltageCascadeDetector,
)
from _shared.scenario_engine.generators import (  # noqa: E402
    GeneratorEvent,
    NetworkFaultGenerator,
    ProtectionTripGenerator,
)
from _shared.scenario_engine.scenario import run_scenario  # noqa: E402
from _shared.scenario_engine.scoring import print_score_report, score_run  # noqa: E402

EXPECTED_FILE = SCENARIO_ENGINE_DIR.parent / "expected_demo_scenario_run.json"

DEFAULT_SEED: int = chaosnet.DEFAULT_SEED

# Same real EMT timestep Lab 5's own run_dpsim.py uses -- reused directly,
# not a second copy of the same magic number.
TIME_STEP_S: float = run_dpsim.TIME_STEP_S

FAULT_TARGET: str = "SUB-3"
FAULT_TYPE: str = "line-to-ground"
FAULT_TRIGGER_TIME_S: float = 0.2
FAULT_CLEARING_DURATION_S: float = 0.15

TRIP_TARGET: str = "SUB-2"
# See module docstring "Threshold provenance" for the real sandbox sweep
# these two constants were derived from.
TRIP_VOLTAGE_LIMIT_V: float = 12000.0
TRIP_SUSTAIN_S: float = 0.04

# Margin appended after the fault clears so the post-clear/post-trip
# transient (what OscillationDetector needs something real to find) has
# room to ring and settle, matching run_dpsim.py's own
# POST_FAULT_SETTLE_S convention.
POST_SETTLE_S: float = 0.2

FINAL_TIME_S: float = FAULT_TRIGGER_TIME_S + FAULT_CLEARING_DURATION_S + POST_SETTLE_S

# --step check's fixture re-derivation must land within this much of the
# committed ground-truth generator/detector time_s -- the solve is fully
# deterministic (fixed seed, no randomness in the loop itself), so a
# genuine regression should exceed this by orders of magnitude; the value
# itself is one measurement-cadence tick (see scenario.eval_stride_steps())
# at TIME_STEP_S, i.e. the coarsest granularity anything here is actually
# evaluated at.
FIXTURE_TIME_TOLERANCE_S: float = 1.0 / 100.0  # 1 phasor frame @ 100 Hz

# Detector confidence floor recorded into the fixture -- see module
# docstring; set below the actually-observed OscillationDetector
# confidence from this scenario's own real run (not an invented number),
# with headroom so small numerical noise between re-runs can't flip a
# PASS to FAIL.
FIXTURE_MIN_CONFIDENCE: float = 0.1


class DemoScenarioSummary(TypedDict):
    """Diffable summary of one demo_scenario run, printed for humans and
    used to build/re-derive expected_demo_scenario_run.json."""

    seed: int
    events: list[GeneratorEvent]
    findings: list[Finding]


def _build_generators(dsys: chaosnet.DpsimChaosSystem) -> list:
    """Construct this demo's one NetworkFaultGenerator + one
    ProtectionTripGenerator, wired to their real dpsimpy fault switches.

    Args:
        dsys: output of chaosnet.to_dpsim_emt_system() for
            [FAULT_TARGET, TRIP_TARGET].

    Returns:
        [fault_generator, trip_generator] in evaluation order.
    """
    fault_gen = NetworkFaultGenerator(
        id="fault-sub3",
        target=FAULT_TARGET,
        fault_type=FAULT_TYPE,
        trigger_time_s=FAULT_TRIGGER_TIME_S,
        clearing_duration_s=FAULT_CLEARING_DURATION_S,
        switch=dsys["fault_switches"][FAULT_TARGET],
    )
    trip_gen = ProtectionTripGenerator(
        id="trip-sub2",
        target=TRIP_TARGET,
        action={"asset": TRIP_TARGET, "effect": "close"},
        trigger_condition={
            "kind": "sustain",
            "measurement": f"{TRIP_TARGET}_voltage_v",
            "comparator": "<",
            "limit": TRIP_VOLTAGE_LIMIT_V,
            "sustain_s": TRIP_SUSTAIN_S,
        },
        switch=dsys["fault_switches"][TRIP_TARGET],
    )
    return [fault_gen, trip_gen]


def _run_detectors(waves: dict[str, ThreePhaseWaveform], up_to_s: float) -> list[Finding]:
    """Run all five concrete detectors against this run's real waveforms.

    Args:
        waves: tap_name -> ThreePhaseWaveform (FAULT_TARGET and
            TRIP_TARGET's own recorded waveforms).
        up_to_s: consume every detector up to and including this time.

    Returns:
        The concatenated Finding log from every detector, including
        CascadingFailureClassifier's own composite of the other four.
    """
    findings: list[Finding] = []

    osc = OscillationDetector(id="osc-sub2")
    findings.extend(osc.consume(waves[TRIP_TARGET], up_to_s))

    rocof = RoCoFDetector(id="rocof-sub2")
    findings.extend(rocof.consume(waves[TRIP_TARGET], up_to_s))

    voltage_cascade = VoltageCascadeDetector(
        id="vcascade-sub2", rise_threshold_v=200.0, acceleration_threshold_v_per_s2=1.0
    )
    findings.extend(voltage_cascade.consume(waves[TRIP_TARGET], up_to_s))

    angle_sep = AngleSeparationDetector(
        id="angle-sub3-sub2", region_b_wave=waves[FAULT_TARGET], threshold_deg=2.0
    )
    findings.extend(angle_sep.consume(waves[TRIP_TARGET], up_to_s))

    classifier = CascadingFailureClassifier(id="classifier-1")
    classifier.set_source_findings(findings)
    findings.extend(classifier.consume(waves[TRIP_TARGET], up_to_s))

    return findings


def run_step(seed: int = DEFAULT_SEED, verbose: bool = True) -> DemoScenarioSummary:
    """Run the real DPsim EMT solve for this demo scenario: SUB-3 fault,
    SUB-2 sustained-undervoltage trip, all five detectors.

    Args:
        seed: chaos-net topology seed (chaosnet.build_chaos_topology).
        verbose: if True, print progress lines matching run_dpsim.py's own
            convention.

    Returns:
        A DemoScenarioSummary of this run's events and findings.
    """
    topology = chaosnet.build_chaos_topology(seed)
    dsys = chaosnet.to_dpsim_emt_system(topology, [FAULT_TARGET, TRIP_TARGET])
    monitored_taps = {
        FAULT_TARGET: dsys["fault_buses"][FAULT_TARGET],
        TRIP_TARGET: dsys["fault_buses"][TRIP_TARGET],
    }
    generators = _build_generators(dsys)

    if verbose:
        print(
            f"[demo_scenario] seed={seed} solving {FINAL_TIME_S:.3f}s at "
            f"{TIME_STEP_S * 1e6:.0f}us timestep: fault@{FAULT_TARGET} "
            f"t={FAULT_TRIGGER_TIME_S}s, trip@{TRIP_TARGET} once "
            f"|V1|<{TRIP_VOLTAGE_LIMIT_V:.0f}V sustained {TRIP_SUSTAIN_S}s"
        )

    result = run_scenario(
        dsys, monitored_taps, TIME_STEP_S, FINAL_TIME_S, generators, verbose=verbose
    )

    if verbose:
        for ev in result["events"]:
            print(f"  fired: {ev['generator_id']} ({ev['kind']}) at t={ev['time_s']:.4f}s")

    waves = {
        tap: ThreePhaseWaveform(
            np.asarray(result["times"]),
            np.asarray(result["node_waveforms"][tap]["va"]),
            np.asarray(result["node_waveforms"][tap]["vb"]),
            np.asarray(result["node_waveforms"][tap]["vc"]),
        )
        for tap in monitored_taps
    }
    findings = _run_detectors(waves, FINAL_TIME_S)

    if verbose:
        for f in findings:
            print(
                f"  finding: {f['detector_id']} ({f['kind']}) at "
                f"t={f['time_s']:.4f}s confidence={f['confidence']:.2f} {f['detail']}"
            )

    summary: DemoScenarioSummary = {"seed": seed, "events": result["events"], "findings": findings}

    if seed == DEFAULT_SEED:
        _write_fixture(summary)

    return summary


def _write_fixture(summary: DemoScenarioSummary) -> None:
    """(Re)write expected_demo_scenario_run.json from a real run's own
    observed events/findings -- the same "committed, re-derived from
    reality, never fabricated" discipline run_dpsim.py's own
    expected_dpsim_run.json follows.

    Only the two generators/detector entries PRD-0001's acceptance bar
    actually requires (the fault, the trip, and OscillationDetector) are
    scored strictly; the fixture intentionally does not pin every
    detector's output; the platform-smoke-test purpose of this scenario is
    "the required pair works end to end," not "every detector's exact
    numeric output is frozen."

    Args:
        summary: this run's own DemoScenarioSummary.
    """
    earliest_by_id: dict[str, float] = {}
    for e in summary["events"]:
        gid = e["generator_id"]
        if gid not in earliest_by_id or e["time_s"] < earliest_by_id[gid]:
            earliest_by_id[gid] = e["time_s"]

    osc_findings = [
        f for f in summary["findings"] if f["detector_id"] == "osc-sub2" and f["kind"] == "oscillation"
    ]
    osc_time = min((f["time_s"] for f in osc_findings), default=None)

    fixture = {
        "generators": {
            gid: {"time_s": t, "tolerance_s": FIXTURE_TIME_TOLERANCE_S}
            for gid, t in earliest_by_id.items()
        },
        "detectors": {},
    }
    if osc_time is not None:
        fixture["detectors"]["osc-sub2:oscillation"] = {
            "time_s": osc_time,
            "tolerance_s": FIXTURE_TIME_TOLERANCE_S,
            "min_confidence": FIXTURE_MIN_CONFIDENCE,
        }
    EXPECTED_FILE.write_text(json.dumps(fixture, indent=2))


def check_step() -> bool:
    """Re-run run_step() with the default seed and diff the result against
    expected_demo_scenario_run.json via scoring.score_run().

    Returns:
        True if every generator-realism and detector-performance entry in
        the resulting ScoreReport passed; False otherwise.
    """
    if not EXPECTED_FILE.exists():
        print(f"[FAIL] no fixture at {EXPECTED_FILE}", file=sys.stderr)
        return False
    fixture = json.loads(EXPECTED_FILE.read_text())

    summary = run_step(seed=DEFAULT_SEED, verbose=False)
    # run_step() just rewrote the fixture (deterministic re-derivation);
    # restore the pre-run copy so a genuine regression stays detectable.
    EXPECTED_FILE.write_text(json.dumps(fixture, indent=2))

    report = score_run(summary["events"], summary["findings"], fixture)
    print_score_report(report)
    return report["all_passed"]


def main() -> None:
    """CLI entry point. --step run (default) executes the full scenario
    and prints its events/findings; --step check re-derives it and scores
    against expected_demo_scenario_run.json, exiting non-zero on
    mismatch."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--step", choices=["run", "check"], default="run")
    args = parser.parse_args()

    if args.step == "run":
        run_step(seed=args.seed)
    elif args.step == "check":
        ok = check_step()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
