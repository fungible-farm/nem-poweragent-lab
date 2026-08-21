#!/usr/bin/env python3
"""Lab 5, step 2 -- DPsim EMT Transient Solve with a Scheduled Fault.

See README.md in this directory for the full walkthrough. Two steps:

    uv run labs/05-spartan-chaosnet-transient-stream/run_dpsim.py --schedule chaos_schedule.yaml
    uv run labs/05-spartan-chaosnet-transient-stream/run_dpsim.py --step check

Loads the chaos-net topology (chaosnet.py), builds a real dpsimpy EMT
(3-phase) SystemTopology, and runs a real electromagnetic-transient solve at
a 4kHz-class (<=250us) timestep -- 200us here, matching
docs/LAB5_SPARTAN_CHAOSNET.md step 2's worked example -- with one real
dpsimpy.event.SwitchEvent3Ph-driven fault at the schedule's target
substation, verified in this sandbox (dpsim 1.2.1) to fire exactly at its
scheduled simulated time via `sim.add_event()`.

Two named, deliberate design choices (not sandbox limitations -- DPsim
itself is real and fully available here):

1. **Bounded simulated duration.** The Definition of Done asks for "at
   least one scheduled fault/switching event firing mid-run" with a
   countdown before it fires, not an open-ended stream. This script
   simulates roughly half a second of grid time (trigger_time_s +
   clearing_duration_s + POST_FAULT_SETTLE_S) -- pre-fault steady state,
   the fault, and post-fault recovery -- rather than running indefinitely.
   A real 4kHz-class stream for SPARTAN's data recorder would keep
   running; this lab demonstrates the mechanism end-to-end within a bounded
   demo run, per the task's own scoping guidance.
2. **Real wall-clock countdown, not simulated-time countdown.** The
   simulated pre-fault settle period (chaos_schedule.yaml's
   trigger_time_s=0.2s of grid time) is far shorter than the "8s... 7...
   6..." countdown docs/LAB5_SPARTAN_CHAOSNET.md's example shows. The
   countdown printed below is therefore real wall-clock time (via
   `time.sleep`), presentational narration counting down to the moment
   this script calls into DPsim's solve -- DPsim's own event system then
   fires the fault at the scheduled *simulated* time inside that solve,
   for real. Both clocks are real; they are just different clocks, named
   here so nobody mistakes one for the other.

dpsim_transient_log.json key convention (extended by docs/backlog/0006
option 2 -- see chaosnet.fault_adjacent_line_name()/_fault_adjacent_line()):

- `times` -- simulated time (s) per sample.
- `va`/`vb`/`vc` -- the fault substation's own three phase instantaneous
  voltages (V), i.e. `v_intf` of the fault bus's SimNode.
- `ia_line`/`ib_line`/`ic_line` -- three phase instantaneous currents (A),
  i.e. `i_intf` of the *fault-adjacent* `PiLine` (chaosnet.py's
  `fault_adjacent_lines[target]`) -- the same tap pattern as `v_intf`,
  applied to a line's current instead of a node's voltage. Together with
  va/vb/vc this is what `view_rx_trajectory.py` divides to get the R-X
  apparent-impedance trajectory Z(t) = V(t)/I(t).
- `fault_adjacent_line` -- the tapped PiLine's dpsimpy component name
  (e.g. "line0_12"), so a reader of the log can identify which line
  ia_line/ib_line/ic_line actually came from.
- `bus_voltages` -- (docs/backlog/0006 option 4) every bus's own three phase
  instantaneous voltages (V), i.e. `v_intf` of *every* SimNode in
  `dsys["nodes"]`, not just the fault bus -- the same `derive_coeff(p, 0)`
  tap pattern as va/vb/vc above, looped over every bus instead of hard-picked
  at one. Keyed by local bus index as a JSON string (e.g. "0".."13" for
  seed 42's 14-bus topology), each value `{"va": [...], "vb": [...], "vc":
  [...]}` -- the fault bus's own entry here is numerically identical to the
  top-level va/vb/vc arrays (same v_intf attribute, tapped twice), kept
  as a convenience for callers that want one uniform bus_voltages dict
  instead of special-casing the fault bus. `animate_sag_propagation.py`
  reduces each bus's three phases to a single |V1(t)| positive-sequence
  magnitude (via phase_model.py's existing DFT machinery) to animate
  network-wide sag propagation over `generate_topology.py`'s topology
  layout.
- `trigger_time_s`/`clear_time_s` -- fault close/open simulated times (s).
- `target` -- the fault substation name (e.g. "SUB-3").
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import TypedDict

import numpy as np
import yaml

import chaosnet

LAB_DIR = Path(__file__).resolve().parent
DEFAULT_SCHEDULE_FILE = LAB_DIR / "chaos_schedule.yaml"
EXPECTED_FILE = LAB_DIR / "expected_dpsim_run.json"
VILLAS_DATA_DIR = LAB_DIR / "villas"
VILLAS_STREAM_CSV = VILLAS_DATA_DIR / "chaos_stream.csv"
TRANSIENT_LOG_JSON = LAB_DIR / "dpsim_transient_log.json"
# PRD-0005 Phase 3: written only when --renewable is active (see run_step()).
RENEWABLE_LOG_JSON = LAB_DIR / "renewable_generation.json"

# "EMT solve running at 200us timestep" -- docs/LAB5_SPARTAN_CHAOSNET.md
# step 2 worked example, verbatim. Well inside the Definition of Done's
# 4kHz-class (<=250us) requirement and DPsim's own documented real-time
# floor (50us, per github.com/sogno-platform/dpsim's README).
TIME_STEP_S: float = 200e-6

# Post-fault settle margin (s) appended after the schedule's own
# trigger_time_s + clearing_duration_s, so the printed/plotted transient
# shows a clean post-fault recovery, not a solve that stops mid-transient.
POST_FAULT_SETTLE_S: float = 0.2

# Real wall-clock countdown length (s) before the solve starts, matching
# "...in 8s... 7... 6..." in docs/LAB5_SPARTAN_CHAOSNET.md step 2's worked
# example verbatim. See module docstring point 2 for why this is a
# *wall-clock* countdown, separate from the schedule's simulated
# trigger_time_s.
FAULT_COUNTDOWN_SECONDS: int = 8

# check_step() passes this instead of FAULT_COUNTDOWN_SECONDS so the
# self-check gate (run via pytest / scripts/run_labs_1_3.sh-style proof
# runs) doesn't spend 8 real seconds sleeping on every invocation. Still a
# real, honestly-labelled shortcut for the *non-interactive* path only --
# the interactive walkthrough command always gets the full countdown.
FAST_COUNTDOWN_SECONDS: int = 0

DEFAULT_SEED: int = chaosnet.DEFAULT_SEED

# Float tolerance for expected_dpsim_run.json's RMS/peak voltage
# comparisons -- looser than JSON print precision, tight enough to catch a
# real regression in the fault physics. Same rationale as Lab 1/2's
# FIXTURE_FLOAT_ATOL.
FIXTURE_VOLTAGE_ATOL: float = 5.0


class ScheduleEvent(TypedDict):
    target: str
    type: str
    trigger_time_s: float
    clearing_duration_s: float


def load_schedule(path: Path) -> list[ScheduleEvent]:
    """Parse chaos_schedule.yaml into a list of ScheduleEvent.

    Args:
        path: path to the schedule YAML file.

    Returns:
        The parsed `events` list.
    """
    doc = yaml.safe_load(path.read_text())
    return doc["events"]


def _is_condition_triggered(event: dict) -> bool:
    """True if a raw parsed schedule dict is the condition-triggered shape
    (carries a `trigger_condition` block) added by
    `_shared.scenario_engine.scenario`'s schedule extension
    (docs/prd/0001-composable-generator-detector-platform.md Goal 3),
    rather than today's plain time-triggered shape
    (`target/type/trigger_time_s/clearing_duration_s`).

    Args:
        event: one raw entry from `load_schedule()`'s returned list.

    Returns:
        True if `event` should be driven by a condition-triggered
        generator instead of a pre-registered `SwitchEvent3Ph` pair.
    """
    return "trigger_condition" in event


class DpsimRunSummary(TypedDict):
    """Diffable summary of one run_step() solve, written to
    expected_dpsim_run.json and re-derived by check_step()."""

    seed: int
    fault_target: str
    fault_type: str
    time_step_s: float
    trigger_time_s: float
    clearing_duration_s: float
    final_time_s: float
    num_samples: int
    pre_fault_rms_v: float
    during_fault_rms_v: float
    post_fault_rms_v: float
    sag_percent: float
    max_abs_v: float
    converged: bool
    stabilizer_active: bool
    delay_compensation_active: bool  # PRD-0005 Phase 2
    propagation_delay_s: float  # PRD-0005 Phase 2 (0.0 when stabilizer inactive)
    renewable_active: bool  # PRD-0005 Phase 3
    renewable_target: str | None  # PRD-0005 Phase 3 (None when renewable inactive)


def _rms(values: list[float]) -> float:
    """Root-mean-square of a real-valued sample window."""
    arr = np.asarray(values, dtype=float)
    return float(np.sqrt(np.mean(arr * arr)))


def _write_villas_csv(
    times: list[float], channels: dict[str, list[float]], path: Path
) -> None:
    """Write a per-timestep sample stream in VILLASnode's own native `file`
    node-type CSV format.

    Format confirmed by direct experiment against
    registry.git.rwth-aachen.de/acs/public/villas/node:latest (1.1.0) in
    this sandbox: `villas-node` writing a `signal` node's output to a
    `type = "file", format = "csv"` node produces
    `# secs,nsecs,offset,sequence,<names>` followed by rows of
    `secs,nsecs,offset,sequence,<values>` -- reproduced here exactly so
    `kube/villasnode-tap-pod.yaml`'s `file` input node can read DPsim's
    real transient output directly, no format guessing.

    Args:
        times: simulated time (s) since solve start, one per sample.
        channels: channel name -> one value per sample (same length as
            `times`), e.g. {"va": [...], "vb": [...], "vc": [...]}.
        path: output CSV path.
    """
    names = list(channels.keys())
    base_epoch = time.time()
    lines = ["# secs,nsecs,offset,sequence," + ",".join(names)]
    for seq, t in enumerate(times):
        ts = base_epoch + t
        secs = int(ts)
        nsecs = int(round((ts - secs) * 1e9))
        vals = ",".join(f"{channels[name][seq]:.6f}" for name in names)
        lines.append(f"{secs},{nsecs},0.0,{seq},{vals}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def _resolve_schedule_path(schedule_path: Path) -> Path:
    """Resolve --schedule against either the current working directory or
    this lab's own directory.

    docs/LAB5_SPARTAN_CHAOSNET.md step 2's worked example
    (`--schedule chaos_schedule.yaml`) is written assuming the file sits
    next to run_dpsim.py, and is the exact command this lab's own README
    documents -- but `uv run labs/.../run_dpsim.py` is normally invoked
    from the repo root, where a bare `chaos_schedule.yaml` does not exist
    as a relative path. Falling back to LAB_DIR keeps that literal
    documented command working regardless of the caller's cwd, without
    silently accepting a typo'd filename elsewhere (only LAB_DIR is tried,
    not an unbounded search).

    Args:
        schedule_path: the --schedule value as given.

    Returns:
        An existing path: `schedule_path` unchanged if it resolves from
        the current working directory, otherwise `LAB_DIR / schedule_path.name`.

    Raises:
        FileNotFoundError: if neither location has the file.
    """
    if schedule_path.exists():
        return schedule_path
    fallback = LAB_DIR / schedule_path.name
    if fallback.exists():
        return fallback
    raise FileNotFoundError(
        f"schedule file not found at {schedule_path} or {fallback}"
    )


def run_step(
    schedule_path: Path,
    seed: int = DEFAULT_SEED,
    countdown_seconds: int = FAULT_COUNTDOWN_SECONDS,
    verbose: bool = True,
    stabilizer: bool = False,
    delay_compensation: bool = False,
    renewable: bool = False,
    renewable_target: str = "SUB-1",
    output_log_path: Path = TRANSIENT_LOG_JSON,
    write_villas_csv: bool = True,
) -> DpsimRunSummary:
    """Run the real DPsim EMT solve against chaos_schedule.yaml's scheduled
    events.

    `stabilizer` (PRD-0005 Phase 1) wires `grid_forming.py`'s grid-forming
    stabilizer into the *primary* fault target's bus before the solve
    starts (`grid_forming.add_stabilizer_to_system()` rebuilds
    `dsys["system"]` to include it -- see that module's docstring for why a
    fresh SystemTopology is required), then drives its `V_ref` every EMT
    timestep from the same fault-bus voltage tap this function already
    reads for `dpsim_transient_log.json`, plus the stabilizer's own
    coupling-branch current. False (default) reproduces today's exact
    baseline physics/output -- nothing about the non-stabilizer path
    changes.

    Every time-triggered event in the schedule is now fired (looped, not
    hard-picked at index 0) -- the generalization
    docs/prd/0001-composable-generator-detector-platform.md Goal 1 asks
    for ("an ordered list of faults" instead of Lab 5's original single
    fault). This summary's own top-level fields (`fault_target`,
    `fault_type`, etc.) still describe the *first* time-triggered event
    specifically, matching exactly what today's one-event
    `chaos_schedule.yaml` has always reported -- for that schedule, "first
    time-triggered event" and "the only event" are the same thing, so this
    is a zero-behaviour-change regression bar, not a schema change.

    A schedule entry may also carry an optional `trigger_condition` block
    (PRD-0001 Goal 3's DAG extension) instead of a fixed `trigger_time_s`;
    such entries are driven by a `_shared.scenario_engine.generators`
    condition-triggered generator, evaluated every
    `_shared.scenario_engine.scenario` measurement-cadence tick against
    the live solve, rather than pre-registered as a
    `dpsimpy.event.SwitchEvent3Ph`. Today's `chaos_schedule.yaml` has no
    such entries, so this path is exercised only by schedules that add one
    (see `labs/_shared/scenario_engine/demo_scenario.py` for a worked
    example) -- for the regression schedule it is inert.

    Args:
        schedule_path: path to a YAML file matching chaos_schedule.yaml's
            shape.
        seed: chaos-net topology seed (chaosnet.build_chaos_topology).
        countdown_seconds: real wall-clock countdown length; pass
            FAST_COUNTDOWN_SECONDS from check_step() to skip it.
        verbose: if True, print the walkthrough's documented progress
            lines.
        stabilizer: if True, activate the PRD-0005 Phase 1 grid-forming
            stabilizer at the primary fault target's bus.
        delay_compensation: if True (and `stabilizer` is True), activate
            PRD-0005 Phase 2's deadtime/Smith-predictor compensation term
            on top of the stabilizer (see `grid_forming.propagation_delay_s()`
            and `GridFormingStabilizer.delay_compensation_enabled`). Has no
            effect when `stabilizer` is False. Default False reproduces
            Phase 1's exact stabilizer behavior.
        renewable: if True, activate the PRD-0005 Phase 3 wind-turbine
            generation source at `renewable_target`'s bus (see
            `renewable_source.py`), driven by a real deterministic
            wind-dropout profile each EMT step. Cannot currently be
            combined with `stabilizer=True` -- raises ValueError if both
            are requested (see `renewable_source.py`'s module docstring
            for the confirmed, real DPsim incompatibility). Default False
            reproduces today's exact baseline physics/output.
        renewable_target: tap name for the renewable source's point of
            connection (default "SUB-1", distinct from the default
            schedule's own fault target "SUB-3"). Unused when `renewable`
            is False.
        output_log_path: where to write the per-timestep transient log
            (default TRANSIENT_LOG_JSON, today's exact baseline path).
            `grid_forming.run_comparison()` passes a distinct path for the
            stabilized run so it never clobbers the baseline log/fixture.
        write_villas_csv: if True, also write the VILLASnode-format CSV
            (default True, matching today's behaviour). Skipped for
            non-default comparison runs that don't need a VILLASnode tap.

    Returns:
        A DpsimRunSummary of this run.

    Raises:
        ValueError: if the schedule has zero time-triggered events (at
            least one is required to anchor this summary's own fields), or
            if both `stabilizer` and `renewable` are True (see `renewable`
            docstring above -- a real, confirmed DPsim incompatibility, not
            an arbitrary restriction).
    """
    import dpsimpy  # local import: keeps generate_topology.py runnable
    # without dpsim installed (chaosnet.to_pandapower doesn't need it).

    if stabilizer and renewable:
        raise ValueError(
            "--stabilizer and --renewable cannot currently be combined: "
            "splicing both into one SystemTopology and calling "
            "init_with_powerflow raises a real, reproducible "
            "RuntimeError at sim.start() in this sandbox (see "
            "renewable_source.py's module docstring)"
        )

    schedule_path = _resolve_schedule_path(schedule_path)
    events = load_schedule(schedule_path)
    time_triggered = [e for e in events if not _is_condition_triggered(e)]
    condition_triggered = [e for e in events if _is_condition_triggered(e)]
    if not time_triggered:
        raise ValueError(
            f"{schedule_path} has no time-triggered events -- at least one "
            "is required to anchor this run's summary fields"
        )

    # Backward-compat summary anchor: today's schedule has exactly one
    # event, so "first time-triggered event" and "the schedule's event"
    # are identical -- see docstring.
    primary = time_triggered[0]
    target, fault_type = primary["target"], primary["type"]
    trigger_s = float(primary["trigger_time_s"])
    clear_s = trigger_s + float(primary["clearing_duration_s"])

    final_time_s = max(
        float(e["trigger_time_s"]) + float(e["clearing_duration_s"])
        for e in time_triggered
    ) + POST_FAULT_SETTLE_S

    topology = chaosnet.build_chaos_topology(seed)
    # Union of every time- and condition-triggered target, in first-seen
    # order, deduplicated -- one fault switch per distinct substation
    # (chaosnet.to_dpsim_emt_system's own plural extension). For today's
    # one-event schedule this is exactly `[target]`, matching the original
    # single-target call exactly (same switch name, same physics).
    fault_targets = list(
        dict.fromkeys(
            [e["target"] for e in time_triggered]
            + [e["target"] for e in condition_triggered]
        )
    )
    dsys = chaosnet.to_dpsim_emt_system(topology, fault_targets)

    # PRD-0005 Phase 1: splice the grid-forming stabilizer into `dsys` at
    # the primary target's bus *before* building the Simulation, so
    # sim.set_system() below picks up the rebuilt SystemTopology
    # (grid_forming.add_stabilizer_to_system() mutates dsys["system"] in
    # place -- see that module's docstring for why a full rebuild, not an
    # incremental add, is required).
    stab_handles = None
    stabilizer_ctrl = None
    delay_s = 0.0
    if stabilizer:
        import grid_forming

        stab_handles = grid_forming.add_stabilizer_to_system(dsys, topology, target)
        # PRD-0005 Phase 2: the real computed propagation delay for this
        # target's fault-adjacent line, always computed (cheap, no dpsim
        # call) so it's available to log/report even when
        # delay_compensation=False -- only its *use* inside the controller
        # is gated by delay_compensation below, per
        # GridFormingStabilizer.delay_compensation_enabled's own docstring.
        delay_s = grid_forming.propagation_delay_s(topology, dsys["fault_buses"][target])
        stabilizer_ctrl = grid_forming.GridFormingStabilizer(
            nominal_peak_v=stab_handles["peak_v"], time_step_s=TIME_STEP_S,
            delay_compensation_enabled=delay_compensation, delay_s=delay_s,
        )
        if verbose:
            print(
                f"[stabilizer] active at {target}'s bus: rating="
                f"{grid_forming.STABILIZER_RATING_MVA:.1f} MVA, coupling="
                f"{stab_handles['r_ohm']:.3f}+j{stab_handles['x_ohm']:.3f} ohm, "
                f"delay_compensation={delay_compensation} "
                f"(propagation delay={delay_s * 1e6:.3f}us)"
            )

    # PRD-0005 Phase 3: splice the wind-turbine renewable source into `dsys`
    # at renewable_target's bus before building the Simulation, same
    # rebuild-the-SystemTopology requirement as the stabilizer above.
    renewable_handles = None
    if renewable:
        import renewable_source

        renewable_handles = renewable_source.add_renewable_source_to_system(
            dsys, topology, renewable_target
        )
        if verbose:
            print(
                f"[renewable] Vestas V52-850kW active at {renewable_target}'s bus "
                f"({renewable_handles['vn_kv']:.1f} kV): rated="
                f"{renewable_source.RATED_POWER_W / 1e3:.0f} kW, real wind-dropout "
                "profile driving P_ref each EMT step"
            )

    if verbose:
        print(f"EMT solve running at {TIME_STEP_S * 1e6:.0f}us timestep")

    start_wall = time.time()

    def _tag() -> str:
        elapsed = int(time.time() - start_wall)
        return f"[T+{elapsed // 60:02d}:{elapsed % 60:02d}]"

    if verbose:
        print(
            f"{_tag()} fault scheduled at substation {target} in "
            f"{countdown_seconds}s..."
        )
        for remaining in range(countdown_seconds - 1, 0, -1):
            time.sleep(1)
            print(f"... {remaining}...")
        if countdown_seconds > 0:
            time.sleep(1)
        elif countdown_seconds == 0:
            print(
                "(countdown_seconds=0: non-interactive self-check path, "
                "see FAST_COUNTDOWN_SECONDS docstring -- skipping the "
                "real-time sleep, not the fault itself)"
            )

    if renewable:
        # PRD-0005 Phase 3: AvVoltageSourceInverterDQ requires the real
        # two-stage power-flow init, not do_steady_state_init -- see
        # renewable_source.py's module docstring for the confirmed finding.
        # Applied to dsys["system"] *before* sim.set_system() below, matching
        # the exact order confirmed working in this sandbox (untested, and
        # not assumed safe, the other way around).
        renewable_source.initialize_with_powerflow(dsys, topology)

    sim = dpsimpy.Simulation(f"lab5_seed{seed}", dpsimpy.LogLevel.warn)
    sim.set_system(dsys["system"])
    sim.set_domain(dpsimpy.Domain.EMT)
    sim.set_time_step(TIME_STEP_S)
    sim.set_final_time(final_time_s)
    if not renewable:
        sim.do_steady_state_init(True)
    # Loop sim.add_event() over every time-triggered schedule entry instead
    # of assuming exactly one (PRD-0001 Goal 1) -- each against its own
    # fault switch from chaosnet's plural fault_switches dict.
    for e in time_triggered:
        e_trigger_s = float(e["trigger_time_s"])
        e_clear_s = e_trigger_s + float(e["clearing_duration_s"])
        e_switch = dsys["fault_switches"][e["target"]]
        sim.add_event(dpsimpy.event.SwitchEvent3Ph(e_trigger_s, e_switch, True))
        sim.add_event(dpsimpy.event.SwitchEvent3Ph(e_clear_s, e_switch, False))

    fault_node = dsys["nodes"][dsys["fault_buses"][target]]
    v_attr = fault_node.attr("v")
    phase_attrs = [v_attr.derive_coeff(p, 0) for p in range(3)]

    # docs/backlog/0006 option 2: second tap, i_intf on the fault-adjacent
    # PiLine (chaosnet._fault_adjacent_line()'s deterministic pick), mirroring
    # the v_intf voltage tap above exactly -- same derive_coeff(p, 0) pattern,
    # applied to a line's current attribute instead of a node's voltage
    # attribute. See module docstring's "key convention" section.
    fault_adjacent_line = dsys["fault_adjacent_lines"][target]
    fault_adjacent_line_name = chaosnet.fault_adjacent_line_name(
        topology, dsys["fault_buses"][target]
    )
    i_attr = fault_adjacent_line.attr("i_intf")
    line_phase_attrs = [i_attr.derive_coeff(p, 0) for p in range(3)]

    # docs/backlog/0006 option 4: one v_intf tap per bus in dsys["nodes"],
    # the same derive_coeff(p, 0) pattern as the fault-bus tap above, looped
    # over every bus instead of hard-picked at one -- chaosnet.py's own
    # DpsimChaosSystem docstring already named this exact gap ("run_dpsim.py
    # picks out exactly one... and discards the rest of the solve's per-step
    # state"). Only NUM_CHAOS_BUSES=14 buses exist for this lab's topology
    # (chaosnet.NUM_CHAOS_BUSES), so capturing literally every bus (not a
    # scoped-down subset) is cheap -- see module docstring's `bus_voltages`
    # key convention entry and README's measured capture-overhead numbers.
    all_bus_phase_attrs: dict[int, list] = {
        bus_idx: [node.attr("v").derive_coeff(p, 0) for p in range(3)]
        for bus_idx, node in dsys["nodes"].items()
    }

    # PRD-0005 Phase 1: the stabilizer's own coupling-branch current tap,
    # same derive_coeff(p, 0) pattern as every other current tap above --
    # what GridFormingStabilizer.step() reads each timestep to measure the
    # active power flowing into the bus it's supporting.
    stab_current_phase_attrs: list | None = None
    if stabilizer:
        stab_i_attr = stab_handles["coupling"].attr("i_intf")
        stab_current_phase_attrs = [stab_i_attr.derive_coeff(p, 0) for p in range(3)]

    # Optional condition-triggered generators (PRD-0001 Goal 3). Empty for
    # today's chaos_schedule.yaml, so every block gated on
    # `pending_generators`/`condition_triggered` below is a no-op on the
    # regression path -- see run_step()'s own docstring.
    pending_generators: list = []
    monitored_taps: dict[str, int] = {}
    cond_phase_attrs: dict[str, list] = {}
    cond_raw: dict[str, dict[str, list[float]]] = {}
    cond_history: dict[str, list[tuple[float, float]]] = {}
    eval_stride = 1
    if condition_triggered:
        sys.path.insert(0, str(LAB_DIR.parent))  # for the `_shared` package
        from _shared.scenario_engine import generators as scenario_generators
        from _shared.scenario_engine.scenario import eval_stride_steps, step_generators

        eval_stride = eval_stride_steps(TIME_STEP_S)
        for ce in condition_triggered:
            ce_target = ce["target"]
            bus = dsys["fault_buses"][ce_target]
            monitored_taps[ce_target] = bus
            node = dsys["nodes"][bus]
            v_attr_ce = node.attr("v")
            cond_phase_attrs[ce_target] = [v_attr_ce.derive_coeff(p, 0) for p in range(3)]
            cond_raw[ce_target] = {"va": [], "vb": [], "vc": []}
            cond_history[f"{ce_target}_voltage_v"] = []
            pending_generators.append(
                scenario_generators.ProtectionTripGenerator(
                    id=ce["generator_id"],
                    target=ce_target,
                    action=ce["action"],
                    trigger_condition=ce["trigger_condition"],
                    switch=dsys["fault_switches"][ce_target],
                )
            )

    num_samples = int(round(final_time_s / TIME_STEP_S))
    times: list[float] = []
    va_series: list[float] = []
    vb_series: list[float] = []
    vc_series: list[float] = []
    ia_line_series: list[float] = []
    ib_line_series: list[float] = []
    ic_line_series: list[float] = []
    # docs/backlog/0006 option 4: one {"va": [...], "vb": [...], "vc": [...]}
    # accumulator per bus, keyed the same way as all_bus_phase_attrs above.
    bus_voltage_series: dict[int, dict[str, list[float]]] = {
        bus_idx: {"va": [], "vb": [], "vc": []} for bus_idx in all_bus_phase_attrs
    }
    scenario_events: list = []

    # PRD-0005 Phase 3: real wind-speed/power-output series, accumulated
    # only when renewable is active.
    wind_speed_series: list[float] = []
    renewable_power_series: list[float] = []

    injected_printed = False
    cleared_printed = False

    sim.start()
    for step in range(num_samples):
        t = sim.next()
        va, vb, vc = (a.get() for a in phase_attrs)
        ia_l, ib_l, ic_l = (a.get() for a in line_phase_attrs)
        times.append(t)
        va_series.append(va)
        vb_series.append(vb)
        vc_series.append(vc)
        ia_line_series.append(ia_l)
        ib_line_series.append(ib_l)
        ic_line_series.append(ic_l)
        for bus_idx, attrs in all_bus_phase_attrs.items():
            ba, bb, bc = (a.get() for a in attrs)
            series = bus_voltage_series[bus_idx]
            series["va"].append(ba)
            series["vb"].append(bb)
            series["vc"].append(bc)

        # PRD-0005 Phase 1: drive the stabilizer's V_ref from this step's
        # own fault-bus voltage tap (va/vb/vc above) and its coupling
        # branch current -- the write here takes effect on the *next*
        # sim.next() call, an honest one-EMT-step (200us) digital-control
        # actuation delay, not an instantaneous/ideal correction.
        if stabilizer:
            ia_s, ib_s, ic_s = (a.get() for a in stab_current_phase_attrs)
            v_ref = stabilizer_ctrl.step(t, va, vb, vc, ia_s, ib_s, ic_s)
            stab_handles["source"].attr("V_ref").set(v_ref)

        # PRD-0005 Phase 3: drive the wind turbine's real-time power
        # reference from the wind-dropout profile, timed to start at the
        # same moment the schedule's own fault triggers (trigger_s) -- a
        # real, honestly-scheduled compound disturbance (wind dropout +
        # electrical fault together), not an assumed-independent event.
        if renewable:
            wind_mps = renewable_source.wind_speed_profile_mps(t, dropout_start_s=trigger_s)
            power_w = renewable_source.turbine_power_w(wind_mps)
            renewable_handles["source"].attr("P_ref").set(power_w)
            wind_speed_series.append(wind_mps)
            renewable_power_series.append(power_w)

        if pending_generators:
            for tgt, attrs in cond_phase_attrs.items():
                ca, cb, cc = (a.get() for a in attrs)
                cond_raw[tgt]["va"].append(ca)
                cond_raw[tgt]["vb"].append(cb)
                cond_raw[tgt]["vc"].append(cc)
            if step % eval_stride == 0:
                fired, pending_generators = step_generators(
                    t, pending_generators, monitored_taps, cond_raw, times, cond_history
                )
                scenario_events.extend(fired)
                if verbose:
                    for ev in fired:
                        print(
                            f"[scenario] fired {ev['generator_id']} "
                            f"({ev['kind']}) at t={ev['time_s']:.4f}s"
                        )

        if verbose and not injected_printed and t >= trigger_s:
            injected_printed = True
            print(
                f"FAULT INJECTED: {target} {fault_type}, clearing in "
                f"{primary['clearing_duration_s'] * 1000:.0f}ms"
            )
        if verbose and not cleared_printed and t >= clear_s:
            cleared_printed = True
            print(f"FAULT CLEARED: {target} restored to pre-fault topology")
    sim.stop()

    def _window(center: float, half: float = 0.02) -> list[float]:
        return [v for t, v in zip(times, va_series) if abs(t - center) < half]

    pre_fault = _window(trigger_s - 0.05)
    during_fault = _window((trigger_s + clear_s) / 2.0)
    post_fault = _window(final_time_s - 0.05)
    all_abs = np.abs(np.array(va_series + vb_series + vc_series))

    summary: DpsimRunSummary = {
        "seed": seed,
        "fault_target": target,
        "fault_type": fault_type,
        "time_step_s": TIME_STEP_S,
        "trigger_time_s": trigger_s,
        "clearing_duration_s": float(primary["clearing_duration_s"]),
        "final_time_s": final_time_s,
        "num_samples": num_samples,
        "pre_fault_rms_v": round(_rms(pre_fault), 3),
        "during_fault_rms_v": round(_rms(during_fault), 3),
        "post_fault_rms_v": round(_rms(post_fault), 3),
        "sag_percent": round(
            100.0 * (1.0 - _rms(during_fault) / _rms(pre_fault)), 2
        ),
        "max_abs_v": round(float(all_abs.max()), 3),
        "converged": bool(np.isfinite(all_abs).all()),
        "stabilizer_active": stabilizer,
        "delay_compensation_active": stabilizer and delay_compensation,
        "propagation_delay_s": delay_s,
        "renewable_active": renewable,
        "renewable_target": renewable_target if renewable else None,
    }

    if verbose:
        print(
            f"Pre-fault {summary['pre_fault_rms_v']:.0f} V -> during-fault "
            f"{summary['during_fault_rms_v']:.0f} V "
            f"({summary['sag_percent']:.1f}% sag) -> post-fault "
            f"{summary['post_fault_rms_v']:.0f} V, {num_samples} samples, "
            f"finite={summary['converged']}"
        )

    if write_villas_csv:
        _write_villas_csv(
            times, {"va": va_series, "vb": vb_series, "vc": vc_series}, VILLAS_STREAM_CSV
        )
    output_log_path.write_text(
        json.dumps(
            {
                "times": times,
                "va": va_series,
                "vb": vb_series,
                "vc": vc_series,
                "ia_line": ia_line_series,
                "ib_line": ib_line_series,
                "ic_line": ic_line_series,
                "fault_adjacent_line": fault_adjacent_line_name,
                "bus_voltages": {
                    str(bus_idx): series
                    for bus_idx, series in bus_voltage_series.items()
                },
                "trigger_time_s": trigger_s,
                "clear_time_s": clear_s,
                "target": target,
                "stabilizer_active": stabilizer,
                "delay_compensation_active": stabilizer and delay_compensation,
                "propagation_delay_s": delay_s,
            }
        )
    )
    if verbose:
        stream_msg = (
            f"[stream] wrote {output_log_path.name} "
            f"({len(bus_voltage_series)} buses x 3 phases x {num_samples} "
            "samples in bus_voltages, docs/backlog/0006 option 4)"
        )
        if write_villas_csv:
            stream_msg = (
                f"[stream] wrote {VILLAS_STREAM_CSV.relative_to(LAB_DIR)} "
                f"(VILLASnode file-node format, {num_samples} samples) and "
                f"{output_log_path.name} "
                f"({len(bus_voltage_series)} buses x 3 phases x {num_samples} "
                "samples in bus_voltages, docs/backlog/0006 option 4)"
            )
        print(stream_msg)

    # Only overwrite the committed fixture for the exact baseline case this
    # fixture describes: default schedule/seed, stabilizer off, renewable
    # off -- a stabilized or renewable-active comparison run must never
    # clobber expected_dpsim_run.json.
    if (
        schedule_path.resolve() == DEFAULT_SCHEDULE_FILE.resolve()
        and seed == DEFAULT_SEED
        and not stabilizer
        and not renewable
    ):
        EXPECTED_FILE.write_text(json.dumps(summary, indent=2))

    # PRD-0005 Phase 3: real wind-speed/power-output series, written only
    # when renewable is active -- never touches any other committed fixture.
    if renewable:
        RENEWABLE_LOG_JSON.write_text(
            json.dumps(
                {
                    "target": renewable_target,
                    "vn_kv": renewable_handles["vn_kv"],
                    "rated_power_w": renewable_source.RATED_POWER_W,
                    "times": times,
                    "wind_speed_mps": wind_speed_series,
                    "p_ref_w": renewable_power_series,
                },
                indent=2,
            )
        )
        if verbose:
            print(
                f"[renewable] wrote {RENEWABLE_LOG_JSON.name} "
                f"({len(wind_speed_series)} samples: rated "
                f"{max(renewable_power_series) / 1e3:.0f} kW -> lull "
                f"{min(renewable_power_series) / 1e3:.1f} kW -> recovered)"
            )

    return summary


def check_step() -> bool:
    """Re-run run_step() with the default schedule/seed and a fast
    (non-interactive) countdown, and diff the result against
    expected_dpsim_run.json.

    Returns:
        True if the fault fired at the right time against the right
        substation and every RMS/peak voltage figure matches within
        FIXTURE_VOLTAGE_ATOL; False otherwise.
    """
    if not EXPECTED_FILE.exists():
        print(f"[FAIL] no fixture at {EXPECTED_FILE}", file=sys.stderr)
        return False
    expected = json.loads(EXPECTED_FILE.read_text())

    actual = run_step(
        DEFAULT_SCHEDULE_FILE,
        seed=DEFAULT_SEED,
        countdown_seconds=FAST_COUNTDOWN_SECONDS,
        verbose=False,
    )
    # run_step() just rewrote expected_dpsim_run.json with `actual`
    # (deterministic re-derivation); restore the pre-run copy so a genuine
    # regression stays detectable on the next run.
    EXPECTED_FILE.write_text(json.dumps(expected, indent=2))

    ok = True
    for key in ("fault_target", "fault_type", "trigger_time_s", "num_samples", "converged"):
        if expected[key] != actual[key]:
            print(f"FAIL: {key}: expected={expected[key]} actual={actual[key]}")
            ok = False
    for key in ("pre_fault_rms_v", "during_fault_rms_v", "post_fault_rms_v", "max_abs_v"):
        if abs(expected[key] - actual[key]) > FIXTURE_VOLTAGE_ATOL:
            print(f"FAIL: {key}: expected={expected[key]} actual={actual[key]}")
            ok = False

    if ok:
        print(
            f"MATCH: DPsim EMT run matches expected_dpsim_run.json "
            f"(sag {actual['sag_percent']:.1f}%, {actual['num_samples']} samples)"
        )
    return ok


def main() -> None:
    """CLI entry point. --step run (default) executes the full solve with
    the interactive countdown; --step check re-derives it fast and diffs
    against expected_dpsim_run.json, exiting non-zero on mismatch."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--schedule", type=Path, default=DEFAULT_SCHEDULE_FILE
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--step", choices=["run", "check"], default="run")
    parser.add_argument(
        "--stabilizer", action="store_true",
        help="activate the PRD-0005 Phase 1 grid-forming stabilizer (see grid_forming.py)",
    )
    parser.add_argument(
        "--delay-compensation", action="store_true",
        help=(
            "activate the PRD-0005 Phase 2 deadtime/Smith-predictor "
            "compensation term on top of --stabilizer (see grid_forming."
            "propagation_delay_s()); has no effect without --stabilizer"
        ),
    )
    parser.add_argument(
        "--renewable", action="store_true",
        help=(
            "activate the PRD-0005 Phase 3 wind-turbine generation source "
            "(see renewable_source.py); cannot be combined with "
            "--stabilizer (raises ValueError -- see renewable_source.py's "
            "module docstring)"
        ),
    )
    parser.add_argument(
        "--renewable-target", type=str, default="SUB-1",
        help="tap name for --renewable's point of connection (default SUB-1)",
    )
    args = parser.parse_args()

    if args.step == "run":
        run_step(
            args.schedule, seed=args.seed, stabilizer=args.stabilizer,
            delay_compensation=args.delay_compensation,
            renewable=args.renewable, renewable_target=args.renewable_target,
        )
    elif args.step == "check":
        ok = check_step()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
