"""Scenario schedule loading and the condition-triggered-generator solve
driver (docs/prd/0001-composable-generator-detector-platform.md Goal 3).

Extends `chaos_schedule.yaml`'s flat `events:` list into a small DAG: each
entry keeps `target/type/trigger_time_s/clearing_duration_s` for
time-triggered events (unchanged), and gains an optional
`trigger_condition` block for condition-triggered ones (protection trips,
islanding trips) -- backward compatible by construction: a schedule with
only time-triggered entries (today's `chaos_schedule.yaml`) is a one-node
degenerate case of this format, not a breaking change.

Evaluation cadence (a judgment call against PRD-0001's own "Open
questions" entry on this exact point): condition-triggered generators are
evaluated once per phasor frame (`phase_model.PHASOR_RATE_HZ` = 100 Hz),
not every raw EMT sample (5 kHz @ 200 us step). Real protection relays
trip off an RMS/phasor-magnitude estimate, never an instantaneous 50 Hz
sample (which crosses zero every half-cycle and would make any "sustained"
condition meaningless); `phase_model.py`'s `phasor_frames()`/
`positive_sequence()` is already this repo's one source of truth for that
estimate, so reusing its own rate keeps the two modules' notion of
"measurement" identical instead of inventing a second cadence, and is
cheaper -- directly addressing the Open Questions entry's own concern
about per-step evaluation cost across a longer scenario.

`MeasurementState.values`/`.history` key convention this module populates:
`f"{tap_name}_voltage_v"` -> the tap's positive-sequence voltage magnitude
(volts), for every tap named in a `run_scenario()`/`step_generators()`
call's `monitored_taps`. `f"{tap_name}_angle_deg"` -> that tap's
positive-sequence phase angle (degrees, unsigned/absolute value)
*relative to the first tap listed in `monitored_taps`* (dict iteration
order -- the caller's own choice of which bus is the fixed angle
reference; the reference tap's own `angle_deg` is always 0), added by
docs/prd/0002-sa-2016-black-system-cascade-scenario.md (the Heywood trip
is an impedance-trajectory/loss-of-synchronism mechanism, not a magnitude
threshold, so a `SustainTriggerCondition` on an `IslandingProtectionGenerator`
needs a live angle measurement).

Two real, sandbox-discovered pitfalls shaped this design (more than the
originally-anticipated "two-line, not new DSP work" addition
docs/prd/0002-...md's implementation plan expected -- both are genuine
platform-behaviour discoveries from this implementation round, reported
here rather than silently worked around):

1. A naive single-tap, single-frame `np.angle(v1[0])` read is *not* usable
   directly: confirmed empirically that the most-recent phasor frame's own
   absolute angle alternates by ~180 degrees every consecutive
   `_build_measurement_state()` call, entirely independent of any real
   physical event (the same two values recur every other tick in steady
   state -- a stable artifact, not noise). This is the *same* documented
   mechanism `detectors.ROCOF_FRAME_LAG`'s own docstring names for why
   `RoCoFDetector` compares frames 2 apart rather than consecutive ones
   (`PHASOR_RATE_HZ` = 2x `FUNDAMENTAL_HZ`, so consecutive frames sit
   exactly half a nominal cycle apart -- the pi-radian phase-wrap
   ambiguity boundary), just surfacing here in the absolute single-frame
   angle instead of a frame-to-frame RoCoF estimate.
2. An earlier draft of this fix (this same implementation session) instead
   accumulated a running "total phase rotation since t=0" via
   `ROCOF_FRAME_LAG`-apart delta differencing (matching RoCoFDetector's
   own technique). That approach is alias-free but was confirmed, by
   direct measurement, to pick up a small, *permanent, irreversible*
   residual bias from every switching transient (the fault
   open/close events themselves), each leaving the running sum offset by
   roughly half a degree that never decayed back out even long after the
   fault itself had fully cleared -- contaminating any later measurement
   with the accumulated "memory" of unrelated, long-past transients. The
   design here instead uses a *direct, non-cumulative, same-tick*
   comparison against a fixed reference tap's own current-frame phasor
   (`angle(v1_tap[0] * conj(v1_reference[0]))`): since both phasors share
   the identical window-alignment artifact at the same tick, it cancels in
   the product/conjugate exactly as it already does in
   `detectors.AngleSeparationDetector`'s own (already-validated,
   already-working) cross-waveform comparison -- reusing that same
   platform-proven technique live, rather than a second, independently-
   invented (and, as measured, flawed) accumulation scheme.

A future scenario adding a further measurement should extend
`_build_measurement_state()` and document the new key names here, not
invent a second, undocumented convention.

Cross-lab dependency note (see `detectors.py`'s own docstring for the full
rationale): this module imports Lab 5's `phase_model.py` directly.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TypedDict

import numpy as np
import yaml

from .generators import GeneratorEvent, MeasurementState

_LAB5_DIR = Path(__file__).resolve().parent.parent.parent / "05-spartan-chaosnet-transient-stream"
if str(_LAB5_DIR) not in sys.path:
    sys.path.insert(0, str(_LAB5_DIR))

from phase_model import (  # noqa: E402  (see sys.path bootstrap above)
    PHASOR_RATE_HZ,
    ThreePhaseWaveform,
    phasor_frames,
    positive_sequence,
)


class TimeTriggeredEventConfig(TypedDict):
    """A time-triggered schedule entry -- `chaos_schedule.yaml`'s existing
    shape, unchanged (PRD-0001 Goal 3: backward compatible)."""

    target: str
    type: str
    trigger_time_s: float
    clearing_duration_s: float


class ConditionTriggeredEventConfig(TypedDict):
    """A condition-triggered schedule entry -- PRD-0001 Goal 3's extension
    to the flat `events:` list: fires the instant `trigger_condition` is
    met instead of at a fixed time.

    Attributes:
        generator_id: unique id for the resulting `ProtectionTripGenerator`.
        target: asset/substation this trip acts on.
        action: `{asset, effect}` -- see `generators.TripAction`.
        trigger_condition: the tagged-union condition -- see
            `generators.TriggerCondition`.
    """

    generator_id: str
    target: str
    action: dict
    trigger_condition: dict


def is_condition_triggered(entry: dict) -> bool:
    """True if a raw parsed schedule dict is the condition-triggered shape
    (has a `trigger_condition` block) rather than the time-triggered
    shape.

    Args:
        entry: one raw entry from `load_scenario_schedule()`'s returned
            list.

    Returns:
        True if `entry` should be driven by a condition-triggered
        generator.
    """
    return "trigger_condition" in entry


def load_scenario_schedule(path: Path) -> list[dict]:
    """Parse a scenario schedule YAML (chaos_schedule.yaml's schema,
    extended per PRD-0001 Goal 3) into its raw `events` list.

    Does no field validation itself (matches `chaos_schedule.yaml`'s own
    `load_schedule()` in run_dpsim.py, which is equally permissive) --
    callers dispatch each entry via `is_condition_triggered()`.

    Args:
        path: path to the schedule YAML file.

    Returns:
        The parsed `events` list (a mix of raw
        TimeTriggeredEventConfig/ConditionTriggeredEventConfig-shaped
        dicts).
    """
    doc = yaml.safe_load(path.read_text())
    return doc["events"]


def eval_stride_steps(time_step_s: float) -> int:
    """Number of raw solve steps between condition-triggered-generator
    evaluations, derived from `phase_model.PHASOR_RATE_HZ` so the same
    cadence `phase_model.py` already uses for its own phasor view is
    reused here (see module docstring "Evaluation cadence").

    Args:
        time_step_s: the solve's raw timestep (s).

    Returns:
        `max(1, round(1 / (time_step_s * PHASOR_RATE_HZ)))`.
    """
    return max(1, round(1.0 / (time_step_s * PHASOR_RATE_HZ)))


def _build_measurement_state(
    t_s: float,
    raw: dict[str, dict[str, list[float]]],
    times: list[float],
    history: dict[str, list[tuple[float, float]]],
    monitored_taps: dict[str, int],
) -> MeasurementState:
    """Build one `MeasurementState` tick from the raw per-tap sample
    buffers collected so far, using `phase_model.py`'s own
    `phasor_frames()`/`positive_sequence()` for the voltage-magnitude
    estimate (see module docstring "Evaluation cadence" -- no independent
    phasor math here).

    Mutates and returns `history` in place (appends this tick's value per
    tap) so callers keep one running `MeasurementState.history` across
    ticks without rebuilding it from scratch.

    Args:
        t_s: current simulated time (s).
        raw: tap_name -> {"va": [...], "vb": [...], "vc": [...]} sample
            buffers collected so far (same length as `times`, for every
            tap in `monitored_taps`).
        times: sample times collected so far (s), shared across all taps.
        history: the running `MeasurementState.history` dict, mutated in
            place.
        monitored_taps: tap_name -> local bus index, naming which taps to
            compute a measurement for this tick.

    Returns:
        The `MeasurementState` for this tick.
    """
    values: dict[str, float] = {}
    times_arr = np.asarray(times)
    v1_by_tap: dict[str, complex] = {}
    for tap in monitored_taps:
        if len(raw[tap]["va"]) < 2:
            continue
        wave = ThreePhaseWaveform(
            times_arr,
            np.asarray(raw[tap]["va"]),
            np.asarray(raw[tap]["vb"]),
            np.asarray(raw[tap]["vc"]),
        )
        frame_times, pa, pb, pc = phasor_frames(wave)
        if len(frame_times) == 0:
            continue
        v1 = positive_sequence(pa[-1:], pb[-1:], pc[-1:])
        mag = float(abs(v1[0]))
        key = f"{tap}_voltage_v"
        values[key] = mag
        history.setdefault(key, []).append((t_s, mag))
        v1_by_tap[tap] = v1[0]

    # angle_deg: each tap's phase angle relative to the *first* tap in
    # monitored_taps (dict iteration order) -- see module docstring
    # "MeasurementState.values/.history key convention" for the full
    # rationale (a direct, same-tick, cross-tap comparison, not a
    # single-tap read or a cumulative accumulation -- both confirmed,
    # empirically, to be unusable).
    if v1_by_tap:
        reference_tap = next(iter(monitored_taps))
        ref_v1 = v1_by_tap.get(reference_tap)
        if ref_v1 is not None:
            for tap, v1_val in v1_by_tap.items():
                angle_key = f"{tap}_angle_deg"
                # Same-tick comparison against the fixed reference tap's own
                # current-frame phasor -- the shared window-alignment
                # artifact cancels in this product/conjugate (see docstring
                # point 2), exactly as detectors.AngleSeparationDetector's
                # own cross-waveform comparison already relies on.
                angle_deg = float(
                    abs(np.degrees(np.angle(v1_val * np.conj(ref_v1))))
                )
                values[angle_key] = angle_deg
                history.setdefault(angle_key, []).append((t_s, angle_deg))
    return {"t_s": t_s, "values": values, "history": history}


def step_generators(
    t_s: float,
    pending: list,
    monitored_taps: dict[str, int],
    raw: dict[str, dict[str, list[float]]],
    times: list[float],
    history: dict[str, list[tuple[float, float]]],
) -> tuple[list[GeneratorEvent], list]:
    """Evaluate and fire every still-pending generator against one
    measurement-cadence tick.

    The shared per-step primitive both `run_scenario()` (this module's own
    full driver, used by `demo_scenario.py`) and `run_dpsim.py`'s minimal
    `trigger_condition` extension call, so there is one implementation of
    "what a measurement tick looks like" for condition-triggered
    generators, not two.

    Args:
        t_s: current simulated time (s).
        pending: generators (any `generators.Generator`-shaped object) not
            yet fully fired.
        monitored_taps: tap_name -> local bus index for every bus this
            tick's `MeasurementState` should expose.
        raw: tap_name -> {"va": [...], "vb": [...], "vc": [...]} sample
            buffers collected so far (same length as `times`).
        times: sample times collected so far (s).
        history: the running `MeasurementState.history`, mutated in place.

    Returns:
        `(events_fired_this_tick, still_pending)`. `still_pending` is the
        same list of generators passed in -- a generator's own `ready()`
        is expected to return False permanently once it has nothing left
        to do (see e.g. `NetworkFaultGenerator`), so no generator is ever
        dropped from `still_pending` here; a "one-shot" generator simply
        stops firing.
    """
    state = _build_measurement_state(t_s, raw, times, history, monitored_taps)
    fired: list[GeneratorEvent] = []
    for gen in pending:
        if gen.ready(t_s, state):
            fired.append(gen.fire(None, t_s))
    return fired, pending


class ScenarioRunResult(TypedDict):
    """Everything a scenario's own `--step run`/`--step check` needs: the
    raw per-tap transient waveform samples plus the committed generator
    event log.

    Attributes:
        times: sample times (s), shared across every monitored tap.
        node_waveforms: tap_name -> {"va": [...], "vb": [...], "vc": [...]}
            (same shape as run_dpsim.py's `dpsim_transient_log.json`, one
            entry per monitored tap).
        events: the committed `GeneratorEvent` log, in fire order.
    """

    times: list[float]
    node_waveforms: dict[str, dict[str, list[float]]]
    events: list[GeneratorEvent]


def run_scenario(
    dsys: dict,
    monitored_taps: dict[str, int],
    time_step_s: float,
    final_time_s: float,
    generators: list,
    verbose: bool = False,
    init_powerflow_system: object | None = None,
) -> ScenarioRunResult:
    """Drive one full DPsim EMT solve with a mix of time- and
    condition-triggered generators.

    Every generator in `generators` is polled (`ready()`/`fire()`) at the
    phasor-frame cadence (see `eval_stride_steps()`) against a
    `MeasurementState` built from each monitored tap's own
    positive-sequence voltage magnitude. `NetworkFaultGenerator` instances
    fire (open/close a real `dpsimpy.emt.ph3.Switch`) exactly like any
    other generator here -- unlike Lab 5's own `run_dpsim.py`, which keeps
    pre-registering its single time-triggered fault via
    `dpsimpy.event.SwitchEvent3Ph` directly (see that script's own
    docstring) for its zero-behaviour-change regression path. This driver
    is what `demo_scenario.py` (and future 0002/0003 scenarios) use
    instead, since they have no pre-existing byte-identical-output bar to
    protect.

    Args:
        dsys: a `chaosnet.DpsimChaosSystem` (system/nodes/fault_switches/
            fault_buses).
        monitored_taps: tap_name -> local bus index for every bus whose
            voltage is both recorded in the output waveform and available
            to generators' `MeasurementState` (must be a superset of every
            generator's own measurement target).
        time_step_s: solve timestep (s).
        final_time_s: solve end time (s).
        generators: the scenario's Generator list, evaluated in list order
            each cadence tick.
        verbose: print progress lines (matches run_dpsim.py's own
            convention).
        init_powerflow_system: if given, a solved SP-domain
            `dpsimpy.SystemTopology` applied via `dsys["system"]
            .init_with_powerflow(init_powerflow_system, dpsimpy.Domain.EMT)`
            instead of the default `sim.do_steady_state_init(True)` --
            the two-stage init `renewable_source.py`'s own module docstring
            documents as the real DPsim mechanism for seeding an EMT solve
            from an externally-computed power-flow state (docs/prd/0003's
            precursor->collapse handoff: a real reactive-power injection
            carried forward from another phase's own final state, applied
            here as this solve's own EMT initial condition). None (default)
            reproduces every existing caller's exact prior behaviour --
            nothing about the default path changes.

    Returns:
        A `ScenarioRunResult` with the full per-tap transient waveform and
        the committed `GeneratorEvent` log (in fire order).
    """
    import dpsimpy  # local import, mirrors run_dpsim.py's own convention

    sim = dpsimpy.Simulation("scenario_engine_run", dpsimpy.LogLevel.warn)
    sim.set_system(dsys["system"])
    sim.set_domain(dpsimpy.Domain.EMT)
    sim.set_time_step(time_step_s)
    sim.set_final_time(final_time_s)
    if init_powerflow_system is not None:
        # Two-stage PF init (see docstring above) -- mutates dsys["system"]'s
        # own internal node state in place, same DPsim API shape
        # renewable_source.initialize_with_powerflow() already established;
        # must NOT be combined with do_steady_state_init on the same run.
        dsys["system"].init_with_powerflow(init_powerflow_system, dpsimpy.Domain.EMT)
    else:
        sim.do_steady_state_init(True)

    phase_attrs: dict[str, list] = {}
    for tap, bus in monitored_taps.items():
        node = dsys["nodes"][bus]
        v_attr = node.attr("v")
        phase_attrs[tap] = [v_attr.derive_coeff(p, 0) for p in range(3)]

    num_samples = int(round(final_time_s / time_step_s))
    stride = eval_stride_steps(time_step_s)

    times: list[float] = []
    raw: dict[str, dict[str, list[float]]] = {
        tap: {"va": [], "vb": [], "vc": []} for tap in monitored_taps
    }
    history: dict[str, list[tuple[float, float]]] = {}
    events: list[GeneratorEvent] = []
    pending = list(generators)

    sim.start()
    for step in range(num_samples):
        t = sim.next()
        times.append(t)
        for tap, attrs in phase_attrs.items():
            va, vb, vc = (a.get() for a in attrs)
            raw[tap]["va"].append(va)
            raw[tap]["vb"].append(vb)
            raw[tap]["vc"].append(vc)

        if pending and step > 0 and step % stride == 0:
            fired, pending = step_generators(t, pending, monitored_taps, raw, times, history)
            events.extend(fired)
            if verbose:
                for ev in fired:
                    print(f"[{t:.4f}s] fired {ev['generator_id']} ({ev['kind']})")
    sim.stop()

    return {"times": times, "node_waveforms": raw, "events": events}
