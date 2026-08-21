#!/usr/bin/env python3
"""Iberian Peninsula 2025 blackout: a structurally-faithful (not literal-
topology) reproduction of the 28 April 2025 Spain/Portugal grid incident's
**fast-collapse phase only** (12:32:00-12:33:23.960 CEST), on
`_shared.scenario_engine`'s composable Generator/Detector platform
(docs/prd/0003-iberian-2025-blackout-scenario.md).

**Not a claim of reproducing the real Spanish/Portuguese network's exact
topology, generator fleet, or protection settings** -- the report itself
states most underlying data was anonymised/aggregated by asset group for
confidentiality, so no public source could ground-truth that level of
detail even in principle (PRD-0003's own acceptance criteria). Every
timestamp/kV/MW figure cited to ENTSO-E's real "Grid Incident in Spain and
Portugal on 28 April 2025" Final Report (20 March 2026) is a grounded fact;
every other constant is this implementation's own engineering choice,
documented as such.

**Scope decision, made and recorded honestly (not silently) before writing
any code**: this implementation covers only the ~84-second fast-collapse
phase, using this chaos-net topology's existing DPsim EMT machinery
(matching `sa_2016_black_system.py`'s proven single-phase pattern) --
**not** PRD-0003's own "Two-phase simulation approach" (a quasi-static
`pandapower` precursor phase, 12:03-12:32, producing the two named
oscillation modes). Building a genuine precursor-phase stepper that
produces a real (not synthetically-injected) 0.63 Hz/0.2 Hz oscillation is
a substantial, novel sub-project with no precedent anywhere in this repo --
this chaos-net topology has no rotor/converter-control dynamics that could
emergently produce such a mode, so any precursor-phase "oscillation" this
platform could show today would necessarily be an explicitly-synthetic
injected sinusoid, not a recovered one, which would make
`OscillationDetector`'s acceptance criterion circular (inject a 0.63 Hz
signal, then detect a 0.63 Hz signal). Left as a real, named future-phase
gap here, matching `docs/prd/0005-...md` Phase 4's own precedent for
honestly gating out a large sub-scope rather than half-implementing it --
see "Acceptance criteria" in the PRD for exactly which criteria this
implementation satisfies and which stay open.

**New platform finding this session: a live-drivable RES/plant-behaviour
component.** `chaosnet.py`'s only load component, `dpsimpy.emt.ph3.RXLoad`,
was confirmed EMPIRICALLY in this sandbox to **not** respond to a live
`.attr("Q").set(...)` call mid-simulation -- a windowed-RMS before/after
comparison showed a -0.02% "change," indistinguishable from solver noise,
despite the attribute's own stored value genuinely updating (confirmed via
`print_attribute`). RXLoad's P/Q appear to be baked into a fixed admittance
at `sim.start()`, not re-read per step, unlike a source component's
"_ref"-suffixed live control attributes. `dpsimpy.emt.ph3.CurrentSource`'s
`I_ref` attribute, by contrast, IS live: the same before/after test with a
500A-per-phase step showed a real +0.20% voltage response at the driven
bus. This is the mechanism `PlantBehaviourGenerator`'s `apply_setpoint`
callback below drives, instead of RXLoad.

**A second new finding, the same class of bug `grid_forming.py`'s own
`stab_source`/`ControlledVoltageSource` splice already discovered and
documented for a different component**: `CurrentSource.connect([node])`
(one terminal) does not raise, but the resulting `SystemTopology(...)`
constructor call segfaults (confirmed reproducibly, exit code 139, isolated
via a staged print-and-flush script). `CurrentSource.connect([node,
dpsimpy.emt.SimNode.gnd])` (two terminals, matching `chaosnet.py`'s own
`Switch` convention) fixes it. Recorded here since this is the first time
this exact failure mode has been confirmed for `CurrentSource` specifically
(not just `ControlledVoltageSource`), reinforcing it as a general dpsimpy
ph3-component convention, not a one-off.

Tap-role mapping (a modelling choice, reusing `sa_2016_black_system.py`'s
own established roles for this same seed-42 topology, not new/unverified
locations):

- `SUB-1` is the network's own fixed slack/reference phase (same role,
  same empirical justification, as `sa_2016_black_system.py`).
- `SUB-2` is the RES/cascade bus: hosts the new live `CurrentSource`
  (driven by all `PlantBehaviourGenerator`/`OperatorActionGenerator`
  firings below), all three overvoltage `ProtectionTripGenerator`s, and
  doubles as the `IslandingProtectionGenerator`'s angle-separation
  measurement point relative to `SUB-1` -- the same "double duty forced by
  only 2 non-reference tap points" simplification `sa_2016_black_system.py`
  already names and uses, not a new one.

CLI (matches every other `scenario_engine` script's convention):
    uv run labs/05-spartan-chaosnet-transient-stream/scenarios/iberian_2025_blackout.py --step run
    uv run labs/05-spartan-chaosnet-transient-stream/scenarios/iberian_2025_blackout.py --step check
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import TypedDict

import numpy as np

SCENARIOS_DIR = Path(__file__).resolve().parent
LAB5_DIR = SCENARIOS_DIR.parent
SHARED_PARENT_DIR = LAB5_DIR.parent  # labs/
for _p in (str(SHARED_PARENT_DIR), str(LAB5_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import dpsimpy  # noqa: E402
import chaosnet  # noqa: E402  (from labs/05-spartan-chaosnet-transient-stream)
import run_dpsim  # noqa: E402  (reuse its TIME_STEP_S, not a second literal)
from phase_model import ThreePhaseWaveform  # noqa: E402

from _shared.scenario_engine.detectors import (  # noqa: E402
    AngleSeparationDetector,
    CascadingFailureClassifier,
    Finding,
    RoCoFDetector,
)
from _shared.scenario_engine.generators import (  # noqa: E402
    GeneratorEvent,
    IslandingProtectionGenerator,
    OperatorActionGenerator,
    PlantBehaviourGenerator,
    ProtectionTripGenerator,
    SustainTriggerCondition,
)
from _shared.scenario_engine.scenario import run_scenario  # noqa: E402
from _shared.scenario_engine.scoring import print_score_report, score_run  # noqa: E402


class _NoOpTripActuator:
    """Named sandbox stand-in (AGENTS.md "sandbox stand-ins must be named,
    not hidden"), same class of stand-in as `sa_2016_black_system.py`'s own
    `_NoOpTripActuator`: overvoltage-trip waves 1 and 2 below do not
    actuate a real dpsimpy switch, since chaosnet.py has no independent
    per-generator breaker component and this bus's one real fault switch
    is reserved for wave 3 (the final, physically-disturbing trip -- see
    module docstring "Tap-role mapping" and WAVE_3 constants below).
    """

    def open(self) -> None:
        return None

    def close(self) -> None:
        return None


class _CurrentAccumulator:
    """Live-drivable aggregate RES/plant-behaviour current injection at
    SUB-2, backing every `PlantBehaviourGenerator`/`OperatorActionGenerator`
    firing below via `dpsimpy.emt.ph3.CurrentSource.attr("I_ref").set(...)`
    (see module docstring "New platform finding this session").

    All 6 factor-generators (5 `PlantBehaviourGenerator` + 1
    `OperatorActionGenerator`) share ONE real `CurrentSource` and
    additively nudge its net `I_ref`, rather than each getting an
    independently-attributable live component -- an explicit, named
    simplification (matching `docs/prd/0002-...md`'s own precedent of not
    scoring generator-loss MW per-unit): this platform's DPsim solve has
    no way to separate "how much of the resulting voltage rise came from
    factor 1 vs factor 5" once their currents are summed at one bus, so
    this implementation does not claim to, and each `GeneratorEvent`'s own
    `detail` records only that generator's own nudge, not an attributed
    voltage outcome.

    Attributes:
        source: the live `dpsimpy.emt.ph3.CurrentSource`.
        _total_a: running net per-phase current magnitude (A), real-valued
            (in-phase with the bus's own reference angle -- a genuine
            engineering simplification, not a claim about the real
            event's actual reactive/active current split).
    """

    def __init__(self, source: object) -> None:
        self.source = source
        self._total_a: float = 0.0

    def nudge(self, delta_a: float) -> float:
        """Add delta_a to the net current and push it live. Returns the
        new total for the firing GeneratorEvent's own detail."""
        self._total_a += delta_a
        matrix = np.eye(3, dtype=complex) * self._total_a
        self.source.attr("I_ref").set(matrix)
        return self._total_a


EXPECTED_FILE = SCENARIOS_DIR / "expected_iberian_2025_run.json"

DEFAULT_SEED: int = chaosnet.DEFAULT_SEED
TIME_STEP_S: float = run_dpsim.TIME_STEP_S

# --- Tap-role assignment (see module docstring "Tap-role mapping") --------
REFERENCE_TAP: str = "SUB-1"   # fixed slack/reference phase
RES_TAP: str = "SUB-2"         # RES/cascade bus AND islanding-analog measurement point

# --- Scenario timeline -----------------------------------------------------
# NOT literal ENTSO-E relative-second offsets from 12:32:00 -- unlike
# sa_2016_black_system.py's fault sequence (which could reuse AEMO's own
# real inter-fault gaps directly), this scenario's disturbance mechanism
# (a live current injection, not a switched fault) has no natural
# real-world time constant to inherit, so its own fire times are this
# scenario's real, measured DPsim solve times, calibrated (see FACTOR_*
# constants below) so all 6 factor-generators and the 3 overvoltage waves
# fire in the SAME RELATIVE ORDER the report gives -- same "scored against
# this scenario's own real times, not fabricated to match the source
# report's absolute timestamps" precedent sa_2016_black_system.py's own
# module docstring already states for its fixture.
AFRR_RAMP_START_S: float = 20.0        # "steep local voltage rise" (factor 5), biggest single step
POST_WAVE_3_SETTLE_S: float = 3.0      # room for RoCoF/angle/classifier to develop after wave 3
FINAL_TIME_S: float = 70.0             # see this file's own dev-calibration notes (PR/commit)

# --- PlantBehaviourGenerator/OperatorActionGenerator current-nudge
# magnitudes (A, per-phase, real-valued) -- see module docstring for the
# live-CurrentSource mechanism. Confirmed empirically in this sandbox
# (seed 42, SUB-2, real `phase_model.positive_sequence()` magnitude, not
# the earlier smoke test's crude windowed-RMS-of-instantaneous-samples
# proxy): the response is linear across the tested 100A-5000A range, at
# ~0.00045%/A relative to SUB-2's own real confirmed baseline of 13327.3V
# positive-sequence magnitude (the SAME baseline sa_2016_black_system.py's
# own DIP_THRESHOLD_V comment already establishes for this seed/topology --
# reused, not re-derived independently). A step settles to steady state
# within ~20-30ms with only modest overshoot (confirmed: a 5000A step
# settles to a clean +2.2-2.3% plateau, not a large multi-cycle ring), so
# TRIP_SUSTAIN_S below only needs to be long enough to clear that settling
# window, not to suppress large transient ringing.
FACTOR_1_RES_FIXED_PF_A: float = 2500.0     # RES fixed power factor (report factor 1)
FACTOR_2_CONVENTIONAL_Q_SAT_A: float = 2500.0   # conventional gen Q-sat (factor 2)
FACTOR_4_LOCAL_VC_MISALIGN_A: float = 2500.0    # local voltage-control misalignment (factor 4)
FACTOR_5_AFRR_RAMP_A: float = 3500.0        # aFRR-driven ramp loss of Q absorption (factor 5)
FACTOR_6_PSS_ABSENCE_A: float = 3000.0      # absent/insufficient PSS action (factor 6)
OPERATOR_ACTION_NUDGE_A: float = 4500.0     # late, near-miss operator intervention (factor 3)

# Real report latency framing ("typically less than 5 minutes," and in the
# final episode NOT completed in time): compressed to this scenario's own
# bounded window (same class of honest timescale compression
# docs/prd/0005-...md Phase 3's wind-dropout profile already used, not a
# literal claim of a 5-minute delay inside a ~70s scenario). Chosen so the
# action's real fire time (ready_at_s + latency_s = 65s) lands well after
# wave 1's own real fire time (~20s, see calibration notes) -- reproducing
# the report's own near-miss/failure framing directly: the operator's
# attempted mitigation arrives too late to prevent the first overvoltage
# trip, and in fact (in this scenario's own calibration) directly
# contributes to crossing the final, most severe threshold instead.
OPERATOR_ACTION_READY_S: float = 0.0
OPERATOR_ACTION_LATENCY_S: float = 65.0

# --- Overvoltage protection thresholds -----------------------------------
# Real report figures: wave 1 pre-trip voltage 417.9kV (400kV base, +4.48%);
# wave 2 ~432.4kV (+8.1%); wave 3 is the report's own later, cumulative
# wave reaching >2.5GW total loss, modelled here as a third, still-higher
# proportional threshold (+8.33%) so it stages distinctly after wave 2
# rather than co-firing with it. This topology has no bus at a literal
# 400kV base, so thresholds are set proportionally against SUB-2's own
# real confirmed baseline (13327.3V, see FACTOR_* constants' own comment)
# -- same "scored proportionally against this scenario's own smaller
# synthetic topology" precedent sa_2016_black_system.py already applies to
# its own angle threshold, not a literal kV match.
_BASELINE_V1_V: float = 13327.3
WAVE_1_VOLTAGE_LIMIT_V: float = _BASELINE_V1_V * 1.045   # +4.5%, matches 417.9kV/400kV ratio
WAVE_2_VOLTAGE_LIMIT_V: float = _BASELINE_V1_V * 1.063   # +6.3%, staged between wave 1 and 3
WAVE_3_VOLTAGE_LIMIT_V: float = _BASELINE_V1_V * 1.081   # +8.1%, matches 432.4kV/400kV ratio
TRIP_SUSTAIN_S: float = 0.03   # clears the confirmed ~20-30ms step-settling window

# --- Islanding (ES-FR loss-of-synchronism analog) -------------------------
# Same class of proportionally-scaled stand-in as sa_2016_black_system.py's
# own ISLANDING_ANGLE_LIMIT_DEG (see that module's docstring point 2 for
# the full "no rotor-dynamics component" justification, which applies
# identically here -- this chaos-net topology is structurally incapable of
# reaching AEMO's/ENTSO-E's real ~90-degree class of loss-of-synchronism
# angle regardless of which historical event is being modelled).
ISLANDING_ANGLE_LIMIT_DEG: float = 2.0
ISLANDING_SUSTAIN_S: float = 0.05
ANGLE_SEPARATION_THRESHOLD_DEG: float = ISLANDING_ANGLE_LIMIT_DEG

CLASSIFIER_WEIGHTS: dict[str, float] = {
    "rocof": 0.4,
    "angle_separation": 0.4,
    "oscillation": 0.1,
    "voltage_cascade": 0.1,
}

FIXTURE_TIME_TOLERANCE_S: float = 1.0 / 100.0  # 1 phasor frame @ 100 Hz
FIXTURE_MIN_CONFIDENCE: float = 0.1


class IberianScenarioSummary(TypedDict):
    """Diffable summary of one iberian_2025_blackout run, printed for
    humans and used to build/re-derive expected_iberian_2025_run.json."""

    seed: int
    events: list[GeneratorEvent]
    findings: list[Finding]


def _build_generators(
    dsys: chaosnet.DpsimChaosSystem, accumulator: _CurrentAccumulator
) -> list:
    """Construct this scenario's 5 PlantBehaviourGenerators, 1
    OperatorActionGenerator, 3 ProtectionTripGenerators (overvoltage waves
    1-3), and 1 IslandingProtectionGenerator (ES-FR LOS analog).

    Args:
        dsys: output of chaosnet.to_dpsim_emt_system() for
            [REFERENCE_TAP, RES_TAP].
        accumulator: shared live-CurrentSource driver (see
            _CurrentAccumulator's own docstring).

    Returns:
        The 10 generators in evaluation order.
    """

    def _make_setpoint(delta_a: float, label: str):
        def _apply(_ignored_q_var: float) -> None:
            accumulator.nudge(delta_a)

        return _apply

    plant_behaviours = [
        PlantBehaviourGenerator(
            id="plant-res-fixed-pf",
            target=RES_TAP,
            ready_at_s=0.0,
            power_factor=1.0,  # unused by _make_setpoint's callback; kept for the dataclass shape
            active_power_w=0.0,
            apply_setpoint=_make_setpoint(FACTOR_1_RES_FIXED_PF_A, "factor-1-res-fixed-pf"),
        ),
        PlantBehaviourGenerator(
            id="plant-conventional-q-sat",
            target=RES_TAP,
            ready_at_s=2.0,
            power_factor=1.0,
            active_power_w=0.0,
            apply_setpoint=_make_setpoint(
                FACTOR_2_CONVENTIONAL_Q_SAT_A, "factor-2-conventional-q-sat"
            ),
        ),
        PlantBehaviourGenerator(
            id="plant-local-vc-misalign",
            target=RES_TAP,
            ready_at_s=5.0,
            power_factor=1.0,
            active_power_w=0.0,
            apply_setpoint=_make_setpoint(
                FACTOR_4_LOCAL_VC_MISALIGN_A, "factor-4-local-vc-misalign"
            ),
        ),
        PlantBehaviourGenerator(
            id="plant-afrr-ramp",
            target=RES_TAP,
            ready_at_s=AFRR_RAMP_START_S,
            power_factor=1.0,
            active_power_w=0.0,
            apply_setpoint=_make_setpoint(FACTOR_5_AFRR_RAMP_A, "factor-5-afrr-ramp"),
        ),
        PlantBehaviourGenerator(
            id="plant-pss-absence",
            target=RES_TAP,
            ready_at_s=45.0,
            power_factor=1.0,
            active_power_w=0.0,
            apply_setpoint=_make_setpoint(FACTOR_6_PSS_ABSENCE_A, "factor-6-pss-absence"),
        ),
    ]

    def _apply_operator_action() -> None:
        accumulator.nudge(OPERATOR_ACTION_NUDGE_A)

    operator_action = OperatorActionGenerator(
        id="operator-late-mitigation",
        target=RES_TAP,
        action_label="shunt reactor / export reduction (factor 3, real report framing: "
        "typically <5 minutes, NOT completed in time in the final episode)",
        ready_at_s=OPERATOR_ACTION_READY_S,
        latency_s=OPERATOR_ACTION_LATENCY_S,
        apply_action=_apply_operator_action,
    )

    wind_switch = _NoOpTripActuator()
    wave_1_condition: SustainTriggerCondition = {
        "kind": "sustain",
        "measurement": f"{RES_TAP}_voltage_v",
        "comparator": ">",
        "limit": WAVE_1_VOLTAGE_LIMIT_V,
        "sustain_s": TRIP_SUSTAIN_S,
    }
    wave_2_condition: SustainTriggerCondition = {
        "kind": "sustain",
        "measurement": f"{RES_TAP}_voltage_v",
        "comparator": ">",
        "limit": WAVE_2_VOLTAGE_LIMIT_V,
        "sustain_s": TRIP_SUSTAIN_S,
    }
    trip_wave_1 = ProtectionTripGenerator(
        id="trip-wave-1",
        target=RES_TAP,
        action={"asset": RES_TAP, "effect": "close"},
        trigger_condition=wave_1_condition,
        switch=wind_switch,
    )
    trip_wave_2 = ProtectionTripGenerator(
        id="trip-wave-2",
        target=RES_TAP,
        action={"asset": RES_TAP, "effect": "close"},
        trigger_condition=wave_2_condition,
        switch=wind_switch,
    )

    # Wave 3 reuses the topology's own real fault switch at RES_TAP as its
    # actuator (matching demo_scenario.py's own established "reuse
    # chaosnet's fault-switch primitive as a real physical trip actuator"
    # precedent) -- a genuine to-ground disturbance at RES_TAP, deliberate
    # so RoCoF/angle-separation have a real transient to detect near the
    # end of the run, not just the accumulator's own smooth current ramp.
    real_fault_switch = dsys["fault_switches"][RES_TAP]
    wave_3_condition: SustainTriggerCondition = {
        "kind": "sustain",
        "measurement": f"{RES_TAP}_voltage_v",
        "comparator": ">",
        "limit": WAVE_3_VOLTAGE_LIMIT_V,
        "sustain_s": TRIP_SUSTAIN_S,
    }
    trip_wave_3 = ProtectionTripGenerator(
        id="trip-wave-3",
        target=RES_TAP,
        action={"asset": RES_TAP, "effect": "close"},
        trigger_condition=wave_3_condition,
        switch=real_fault_switch,
    )

    island_condition: SustainTriggerCondition = {
        "kind": "sustain",
        "measurement": f"{RES_TAP}_angle_deg",
        "comparator": ">",
        "limit": ISLANDING_ANGLE_LIMIT_DEG,
        "sustain_s": ISLANDING_SUSTAIN_S,
    }
    island_trip = IslandingProtectionGenerator(
        id="island-es-fr",
        target=RES_TAP,
        action={"asset": RES_TAP, "effect": "close"},
        trigger_condition=island_condition,
        switch=_NoOpTripActuator(),
    )

    return [
        *plant_behaviours,
        operator_action,
        trip_wave_1,
        trip_wave_2,
        trip_wave_3,
        island_trip,
    ]


def _run_detectors(waves: dict[str, ThreePhaseWaveform], up_to_s: float) -> list[Finding]:
    """Run RoCoFDetector + AngleSeparationDetector + CascadingFailureClassifier
    against this run's real waveforms. OscillationDetector/VoltageCascadeDetector
    are NOT run here -- see module docstring "Scope decision."

    Args:
        waves: tap_name -> ThreePhaseWaveform for every monitored tap.
        up_to_s: consume every detector up to and including this time.

    Returns:
        The concatenated Finding log.
    """
    findings: list[Finding] = []

    rocof = RoCoFDetector(id="rocof-res")
    findings.extend(rocof.consume(waves[RES_TAP], up_to_s))

    angle_sep = AngleSeparationDetector(
        id="angle-res-vs-ref",
        region_b_wave=waves[REFERENCE_TAP],
        threshold_deg=ANGLE_SEPARATION_THRESHOLD_DEG,
    )
    findings.extend(angle_sep.consume(waves[RES_TAP], up_to_s))

    classifier = CascadingFailureClassifier(
        id="classifier-iberian2025", weight_by_kind=dict(CLASSIFIER_WEIGHTS)
    )
    classifier.set_source_findings(findings)
    findings.extend(classifier.consume(waves[RES_TAP], up_to_s))

    return findings


def run_step(seed: int = DEFAULT_SEED, verbose: bool = True) -> IberianScenarioSummary:
    """Run the real DPsim EMT solve for this scenario's fast-collapse
    phase: 5 PlantBehaviourGenerator nudges + 1 late OperatorActionGenerator
    driving a live CurrentSource at RES_TAP, 3 overvoltage
    ProtectionTripGenerators, 1 ES-FR islanding analog, scored by
    RoCoFDetector/AngleSeparationDetector/CascadingFailureClassifier.

    Args:
        seed: chaos-net topology seed (chaosnet.build_chaos_topology).
        verbose: if True, print progress lines matching every other
            scenario_engine script's own convention.

    Returns:
        An IberianScenarioSummary of this run's events and findings.
    """
    topology = chaosnet.build_chaos_topology(seed)
    dsys = chaosnet.to_dpsim_emt_system(topology, [REFERENCE_TAP, RES_TAP])

    # Splice in the live RES/plant-behaviour CurrentSource at RES_TAP --
    # same "rebuild the whole SystemTopology" pattern grid_forming.py's own
    # stabilizer splice already established (SystemTopology.add() silently
    # no-ops for a genuinely new component -- see chaosnet.DpsimChaosSystem's
    # own docstring). Two-terminal connect (see module docstring "A second
    # new finding") -- one-terminal segfaults.
    res_bus_idx = dsys["fault_buses"][RES_TAP]
    res_node = dsys["nodes"][res_bus_idx]
    res_source = dpsimpy.emt.ph3.CurrentSource(f"res_source_{RES_TAP}", dpsimpy.LogLevel.warn)
    res_source.set_parameters(np.zeros((3, 3), dtype=complex), topology["system_frequency_hz"])
    res_source.connect([res_node, dpsimpy.emt.SimNode.gnd])
    all_components = list(dsys["components"]) + [res_source]
    dsys["system"] = dpsimpy.SystemTopology(
        topology["system_frequency_hz"], list(dsys["nodes"].values()), all_components
    )
    dsys["components"] = all_components
    accumulator = _CurrentAccumulator(res_source)

    monitored_taps = {
        REFERENCE_TAP: dsys["fault_buses"][REFERENCE_TAP],
        RES_TAP: dsys["fault_buses"][RES_TAP],
    }
    generators = _build_generators(dsys, accumulator)

    if verbose:
        print(
            f"[iberian_2025_blackout] seed={seed} solving {FINAL_TIME_S:.2f}s at "
            f"{TIME_STEP_S * 1e6:.0f}us timestep ({int(round(FINAL_TIME_S / TIME_STEP_S))} "
            f"raw steps): 5 plant-behaviour nudges + 1 late operator action @{RES_TAP}, "
            f"3 overvoltage trip waves, island@{RES_TAP} angle>{ISLANDING_ANGLE_LIMIT_DEG}deg "
            f"sustained {ISLANDING_SUSTAIN_S}s"
        )

    wall_start = time.time()
    result = run_scenario(
        dsys, monitored_taps, TIME_STEP_S, FINAL_TIME_S, generators, verbose=verbose
    )
    wall_elapsed = time.time() - wall_start

    if verbose:
        print(f"[iberian_2025_blackout] solve wall-clock: {wall_elapsed:.1f}s")
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

    summary: IberianScenarioSummary = {
        "seed": seed, "events": result["events"], "findings": findings
    }

    if seed == DEFAULT_SEED:
        _write_fixture(summary)

    return summary


def _write_fixture(summary: IberianScenarioSummary) -> None:
    """(Re)write expected_iberian_2025_run.json from a real run's own
    observed events/findings -- same "committed, re-derived from reality,
    never fabricated" discipline as sa_2016_black_system.py's own
    _write_fixture().

    Args:
        summary: this run's own IberianScenarioSummary.
    """
    earliest_by_id: dict[str, float] = {}
    for e in summary["events"]:
        gid = e["generator_id"]
        if gid not in earliest_by_id or e["time_s"] < earliest_by_id[gid]:
            earliest_by_id[gid] = e["time_s"]

    def _earliest_finding(detector_id: str, kind: str) -> float | None:
        matches = [
            f["time_s"]
            for f in summary["findings"]
            if f["detector_id"] == detector_id and f["kind"] == kind
        ]
        return min(matches) if matches else None

    fixture: dict = {
        "generators": {
            gid: {"time_s": t, "tolerance_s": FIXTURE_TIME_TOLERANCE_S}
            for gid, t in earliest_by_id.items()
        },
        "detectors": {},
    }

    for detector_id, kind in (
        ("rocof-res", "rocof"),
        ("angle-res-vs-ref", "angle_separation"),
        ("classifier-iberian2025", "composite"),
    ):
        t = _earliest_finding(detector_id, kind)
        if t is not None:
            fixture["detectors"][f"{detector_id}:{kind}"] = {
                "time_s": t,
                "tolerance_s": FIXTURE_TIME_TOLERANCE_S,
                "min_confidence": FIXTURE_MIN_CONFIDENCE,
            }

    EXPECTED_FILE.write_text(json.dumps(fixture, indent=2))


def check_step() -> bool:
    """Re-run run_step() with the default seed and diff the result against
    expected_iberian_2025_run.json via scoring.score_run().

    Returns:
        True if every generator-realism and detector-performance entry in
        the resulting ScoreReport passed; False otherwise.
    """
    if not EXPECTED_FILE.exists():
        print(f"[FAIL] no fixture at {EXPECTED_FILE}", file=sys.stderr)
        return False
    fixture = json.loads(EXPECTED_FILE.read_text())

    summary = run_step(seed=DEFAULT_SEED, verbose=False)
    EXPECTED_FILE.write_text(json.dumps(fixture, indent=2))

    report = score_run(summary["events"], summary["findings"], fixture)
    print_score_report(report)
    return report["all_passed"]


def main() -> None:
    """CLI entry point. --step run (default) executes the full scenario
    and prints its events/findings; --step check re-derives it and scores
    against expected_iberian_2025_run.json, exiting non-zero on mismatch."""
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
