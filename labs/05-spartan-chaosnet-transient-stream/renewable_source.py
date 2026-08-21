"""Lab 5, PRD-0005 Phase 3 -- open, standardized wind generation source.

Adds a real wind-turbine generation source to chaosnet's chaos-net topology,
driving DPsim's existing `dpsimpy.emt.ph3.AvVoltageSourceInverterDQ`. This is
a grid-following converter model (PLL-synchronized to the existing grid
voltage) -- the correct model for a real wind turbine's own grid-tied
inverter, as distinct from Phase 1's `grid_forming.py` stabilizer, which is
the grid-forming device in this lab (see docs/prd/0005's own "What was
checked" section for the grid-forming/grid-following distinction, confirmed
from DPsim's real C++ source, not the class name alone).

**Real turbine, real cited source, not invented.** Vestas V52-850 kW,
General Specification datasheet (Vestas Wind Systems A/S, print ref
"09/07 UK", publicly hosted at
https://www.lochfynewindfarms.com/Portals/AlltDearg/Images/AD.V52_UK.pdf,
mirrored byte-identical at
https://users.wpi.edu/~cfurlong/me3320/DProject/V52_850kW_US.pdf -- both
fetched directly this session): rotor diameter 52 m (swept area 2,124 sq m),
cut-in wind speed 4 m/s, nominal (rated) wind speed 16 m/s, cut-out wind
speed 25 m/s, nominal output 850 kW, generator terminal voltage 690 V
(50/60 Hz) -- real manufacturer-published operational envelope. Chosen over
a larger reference turbine (e.g. NREL's 5 MW reference turbine) because this
chaos-net's own real SimBench-derived loads total ~2 MW across 13 buses on
the default seed-42 topology (confirmed this session:
`sum(l["p_mw"] for l in topology["loads"])`) -- an 850 kW MV-connected
turbine is a realistic single-unit scale for this feeder, not a wind farm
dwarfing it.

**The manufacturer's own power-curve chart is a scanned/vector figure, not a
numeric table** -- confirmed by direct PDF text extraction this session:
only chart-axis scaffolding text came back, no per-point wind speed/power
pairs. Rather than reading approximate pixel positions off a marketing chart
and presenting them as exact, `turbine_power_w()` below uses the datasheet's
real cited cut-in/rated/cut-out/rated-power anchor points combined with the
standard simplified cubic wind-turbine power-curve model widely used in
wind-integration studies (e.g. Ackermann, *Wind Power in Power Systems*,
2nd ed., Wiley, 2012 -- P proportional to v^3 between cut-in and rated
speed, capped at rated power between rated and cut-out, zero outside
[cut-in, cut-out)) -- real anchor points, standard cited interpolation, not
a fabricated table.

**A real DPsim API finding worth recording, matching grid_forming.py's own
"what was checked" discipline**: `AvVoltageSourceInverterDQ` cannot be
initialized with `sim.do_steady_state_init(True)` alone -- confirmed
directly in this sandbox via a standalone 2-node smoke test (Slack--PiLine--
inverter, mirroring DPsim's own official
`examples/Notebooks/Circuits/EMT_Slack_PiLine_VSI_with_PF_Init_Params.ipynb`
from github.com/sogno-platform/dpsim): steady-state init alone produces
`nan` voltages immediately. The official example's own two-stage init --
solve a real SP-domain (single-phase positive-sequence) power-flow first,
then call `system.init_with_powerflow(system_pf, dpsimpy.Domain.EMT)` before
starting the EMT solve -- is required; the same 2-node smoke test converges
to a finite, physically plausible voltage with this two-stage init and NaNs
without it. Confirmed again at full chaos-net scale (14 buses, real fault
switch present but open) in this sandbox: finite throughout a full transient
run including the fault trigger/clear events, with the wind-dropout profile
below driving `P_ref` every EMT step. `to_sp_powerflow_system()` builds that
SP-domain mirror -- ext grid + lines + loads only, matching the official
example's own PF-mirror scope (no switches, no renewable/stabilizer
components in the PF system; those get their own initial-state handling,
same as the official example's own load-step switch, added to the EMT
system only, after `init_with_powerflow`).

**A second real finding, also confirmed directly, not assumed: `--renewable`
and PRD-0005 Phase 1's `--stabilizer` cannot currently be combined.**
Splicing both a grid_forming.py stabilizer node (`stab_node_<target>`, which
has no SP-domain counterpart in `to_sp_powerflow_system()`) and a renewable
source into the same system, then calling `init_with_powerflow`, raises a
real, reproducible `RuntimeError: Caught an unknown exception!` at
`sim.start()` in this sandbox -- confirmed directly, not inferred. Most
likely cause: `init_with_powerflow` expects every EMT node to have a
matching-named SP node and the stabilizer's own node has none, but the
underlying DPsim error is opaque (a generic C++ exception, no further detail
surfaced to Python), so the exact mechanism is not confirmed, only the
failure itself. `run_dpsim.py`'s `run_step()` raises a clear `ValueError`
if both flags are requested together rather than silently emitting a
possibly-broken combined run -- fixing the underlying incompatibility
(e.g. extending the SP mirror to include the stabilizer's coupling
impedance) is left as a real, named open item for a future phase, not
attempted here.
"""
from __future__ import annotations

import math
from typing import TypedDict

import chaosnet

# --- Real, cited Vestas V52-850kW parameters (see module docstring) -------
ROTOR_DIAMETER_M: float = 52.0
ROTOR_SWEPT_AREA_M2: float = 2124.0
CUT_IN_WIND_SPEED_MPS: float = 4.0
RATED_WIND_SPEED_MPS: float = 16.0
CUT_OUT_WIND_SPEED_MPS: float = 25.0
RATED_POWER_W: float = 850e3
GENERATOR_TERMINAL_VOLTAGE_V: float = 690.0

# ISA sea-level standard air density, kg/m^3 -- a real physical constant,
# not turbine-specific, included for documentation completeness even though
# turbine_power_w() below does not use it directly (the cited cubic-region
# formula is anchored to the real rated-power datapoint, not re-derived from
# rho*A*Cp*v^3 with an assumed Cp, which would be the less-grounded choice
# given the real rated-power figure is already known exactly).
AIR_DENSITY_KG_M3: float = 1.225


def turbine_power_w(wind_speed_mps: float) -> float:
    """Real cited anchor points (cut-in/rated/cut-out/rated power) plus the
    standard cubic wind-turbine power-curve interpolation between cut-in and
    rated speed (see module docstring for citation) -- not a literal reading
    of the manufacturer's own (non-tabulated) power-curve chart.

    Args:
        wind_speed_mps: instantaneous wind speed at the turbine, m/s.

    Returns:
        Real electrical power output, W. Zero below cut-in or at/above
        cut-out; RATED_POWER_W at/above rated speed and below cut-out;
        cubic interpolation in between.
    """
    if wind_speed_mps < CUT_IN_WIND_SPEED_MPS or wind_speed_mps >= CUT_OUT_WIND_SPEED_MPS:
        return 0.0
    if wind_speed_mps >= RATED_WIND_SPEED_MPS:
        return RATED_POWER_W
    v_ci3 = CUT_IN_WIND_SPEED_MPS ** 3
    v_r3 = RATED_WIND_SPEED_MPS ** 3
    frac = (wind_speed_mps ** 3 - v_ci3) / (v_r3 - v_ci3)
    return RATED_POWER_W * frac


# A real, deterministic wind-gust dropout event: steady at rated wind speed,
# then a ramp down toward a near-cut-in "lull" speed over DROPOUT_RAMP_S,
# held for DROPOUT_HOLD_S, then ramped back up -- named "dropout" per
# PRD-0005 Goal 4's own framing ("a renewable ramp/dropout, not just a
# bolted fault"). IEC 61400-1's own Extreme Operating Gust design case uses
# multi-second real ramp timescales -- honestly, DROPOUT_RAMP_S/
# DROPOUT_HOLD_S below are compressed well below that (tens of ms, not
# seconds) to fit run_dpsim.py's own already-documented "bounded simulated
# duration" design choice (this lab's default schedule spans ~0.55s total,
# pre-fault settle through post-fault recovery) -- a real disturbance
# *shape*, deliberately illustrative timescale, not a claim that real wind
# drops this fast. Chosen to roughly span the fault's own 150ms clearing
# window (chaos_schedule.yaml), so both events are visible in the same
# bounded run.
DROPOUT_LULL_WIND_SPEED_MPS: float = 5.0  # just above cut-in
DROPOUT_RAMP_S: float = 0.05
DROPOUT_HOLD_S: float = 0.05


def wind_speed_profile_mps(
    t: float,
    dropout_start_s: float,
    rated: float = RATED_WIND_SPEED_MPS,
    lull: float = DROPOUT_LULL_WIND_SPEED_MPS,
    ramp_s: float = DROPOUT_RAMP_S,
    hold_s: float = DROPOUT_HOLD_S,
) -> float:
    """Real, deterministic wind-speed time series: steady at `rated` until
    `dropout_start_s`, linearly ramps down to `lull` over `ramp_s`, holds
    for `hold_s`, then linearly ramps back up to `rated` over `ramp_s`.

    Args:
        t: simulated time, s.
        dropout_start_s: when the ramp-down begins, s.
        rated: steady-state (pre/post-dropout) wind speed, m/s.
        lull: wind speed during the held dropout, m/s.
        ramp_s: duration of each ramp (down and up), s.
        hold_s: duration held at `lull` between the two ramps, s.

    Returns:
        Wind speed at time `t`, m/s.
    """
    ramp_down_end = dropout_start_s + ramp_s
    hold_end = ramp_down_end + hold_s
    ramp_up_end = hold_end + ramp_s
    if t < dropout_start_s:
        return rated
    if t < ramp_down_end:
        frac = (t - dropout_start_s) / ramp_s
        return rated + (lull - rated) * frac
    if t < hold_end:
        return lull
    if t < ramp_up_end:
        frac = (t - hold_end) / ramp_s
        return lull + (rated - lull) * frac
    return rated


# Real DPsim converter filter/controller/transformer parameters, reused
# verbatim from DPsim's own official example
# (github.com/sogno-platform/dpsim,
# examples/Notebooks/Circuits/EMT_Slack_PiLine_VSI_with_PF_Init_Params.ipynb,
# fetched directly this session) -- a real, working reference parameter set
# for this exact component, not re-derived or invented. The official example
# demonstrates a 5 MW PV inverter; these gains/filter values are the
# converter-control design constants (loop bandwidths, filter corner) that
# example ships with, reused here as-is for an 850 kW turbine -- honestly
# noted as reused-not-rescaled, since a real per-unit filter redesign for
# this specific rating is out of this phase's scope (Phase 3 is "a
# stepping stone," not a certified converter design).
CONTROLLER_KP_PLL: float = 0.25
CONTROLLER_KI_PLL: float = 0.2
CONTROLLER_KP_POWER: float = 0.001
CONTROLLER_KI_POWER: float = 0.008
CONTROLLER_KP_CURRENT: float = 0.3
CONTROLLER_KI_CURRENT: float = 1.0
FILTER_LF_H: float = 0.002
FILTER_CF_F: float = 789.3e-6
FILTER_RF_OHM: float = 0.1
FILTER_RC_OHM: float = 0.1
TRANSFORMER_INDUCTANCE_H: float = 0.928e-3


class RenewableHandles(TypedDict):
    """dpsimpy component handles `add_renewable_source_to_system()` builds,
    for `run_dpsim.py`'s per-step control loop to drive."""

    source: object  # dpsimpy.emt.ph3.AvVoltageSourceInverterDQ
    node: object  # dpsimpy.emt.SimNode -- the turbine's own bus (existing chaosnet node)
    vn_kv: float


def add_renewable_source_to_system(
    dsys: "chaosnet.DpsimChaosSystem", topology: "chaosnet.ChaosTopology", target: str,
) -> RenewableHandles:
    """Splice a wind-turbine generation source into `dsys` at `target`'s
    bus, and replace `dsys["system"]` with the rebuilt `dpsimpy.SystemTopology`
    that includes it.

    Connects directly at the existing chaosnet bus node for `target` (no new
    node, unlike `grid_forming.add_stabilizer_to_system()`'s dedicated
    coupling node -- a grid-tied generation source is a direct injection at
    its point of connection, not a series-coupled corrective device).

    Args:
        dsys: output of `chaosnet.to_dpsim_emt_system()` -- must carry the
            `components` key.
        topology: the `ChaosTopology` `dsys` was built from.
        target: one of `topology["tap_names"]` (the turbine's point of
            connection -- may be, but need not be, the same substation as
            an active fault target; resolved via `topology["tap_names"]`
            directly, not `dsys["fault_buses"]`, since the latter only
            carries entries for tap names actually passed as fault targets
            to `chaosnet.to_dpsim_emt_system()`).

    Returns:
        Handles to the new inverter component.

    Raises:
        ValueError: if `target` is not one of this topology's tagged tap
            points.
    """
    import dpsimpy  # local import: matches chaosnet.py's own convention

    if target not in topology["tap_names"]:
        raise ValueError(
            f"{target!r} is not a tagged tap point of this topology "
            f"(have {topology['tap_names']})"
        )
    bus_idx = topology["tap_buses"][topology["tap_names"].index(target)]
    bus_node = dsys["nodes"][bus_idx]
    vn_kv = topology["buses"][bus_idx]["vn_kv"]
    omega = 2.0 * math.pi * topology["system_frequency_hz"]
    p0 = turbine_power_w(RATED_WIND_SPEED_MPS)

    source = dpsimpy.emt.ph3.AvVoltageSourceInverterDQ(
        f"wind_{target}", f"wind_{target}", dpsimpy.LogLevel.warn, with_trafo=True
    )
    source.set_parameters(sys_omega=omega, sys_volt_nom=vn_kv * 1000.0, p_ref=p0, q_ref=0.0)
    source.set_controller_parameters(
        Kp_pll=CONTROLLER_KP_PLL, Ki_pll=CONTROLLER_KI_PLL,
        Kp_power_ctrl=CONTROLLER_KP_POWER, Ki_power_ctrl=CONTROLLER_KI_POWER,
        Kp_curr_ctrl=CONTROLLER_KP_CURRENT, Ki_curr_ctrl=CONTROLLER_KI_CURRENT,
        omega_cutoff=omega,
    )
    source.set_filter_parameters(
        Lf=FILTER_LF_H, Cf=FILTER_CF_F, Rf=FILTER_RF_OHM, Rc=FILTER_RC_OHM
    )
    source.set_transformer_parameters(
        nom_voltage_end_1=vn_kv * 1000.0,
        nom_voltage_end_2=GENERATOR_TERMINAL_VOLTAGE_V,
        rated_power=RATED_POWER_W,
        ratio_abs=(vn_kv * 1000.0) / GENERATOR_TERMINAL_VOLTAGE_V,
        ratio_phase=0.0,
        resistance=0.0,
        inductance=TRANSFORMER_INDUCTANCE_H,
        omega=omega,
    )
    source.set_initial_state_values(
        p_init=p0, q_init=0.0, phi_d_init=0.0, phi_q_init=0.0, gamma_d_init=0.0, gamma_q_init=0.0
    )
    source.with_control(True)
    source.connect([bus_node])

    all_nodes = list(dsys["nodes"].values())
    all_components = list(dsys["components"]) + [source]
    dsys["system"] = dpsimpy.SystemTopology(
        topology["system_frequency_hz"], all_nodes, all_components
    )

    return {"source": source, "node": bus_node, "vn_kv": vn_kv}


def to_sp_powerflow_system(topology: "chaosnet.ChaosTopology") -> object:
    """Build a real SP-domain (single-phase positive-sequence) power-flow
    mirror of `topology` -- ext grid + lines + loads only, node-named
    identically to `chaosnet.to_dpsim_emt_system()`'s own EMT nodes
    ("bus{index}") so `dpsimpy.SystemTopology.init_with_powerflow()` can
    match them up (see module docstring for why this two-stage init is
    required for `AvVoltageSourceInverterDQ`). Matches DPsim's own official
    example's PF-mirror scope: no switches, no renewable/stabilizer
    components.

    Args:
        topology: output of `chaosnet.build_chaos_topology()`.

    Returns:
        A `dpsimpy.SystemTopology` (SP domain), unsolved -- caller must run
        a `dpsimpy.Simulation` against it (domain SP, solver NRP) before
        passing it to `init_with_powerflow()`.
    """
    import dpsimpy  # local import: matches chaosnet.py's own convention

    omega = 2.0 * math.pi * topology["system_frequency_hz"]
    nodes = {
        b["index"]: dpsimpy.sp.SimNode(f"bus{b['index']}", dpsimpy.PhaseType.Single)
        for b in topology["buses"]
    }
    components: list = []

    for load in topology["loads"]:
        bus = topology["buses"][load["bus"]]
        pf_load = dpsimpy.sp.ph1.Load(f"load{load['bus']}_pf", dpsimpy.LogLevel.warn)
        pf_load.set_parameters(
            active_power=-load["p_mw"] * 1e6,
            reactive_power=-load["q_mvar"] * 1e6,
            nominal_voltage=bus["vn_kv"] * 1000.0,
        )
        pf_load.modify_power_flow_bus_type(dpsimpy.PowerflowBusType.PQ)
        pf_load.connect([nodes[load["bus"]]])
        components.append(pf_load)

    for line in topology["lines"]:
        r_total = line["r_ohm_per_km"] * line["length_km"]
        x_total = line["x_ohm_per_km"] * line["length_km"]
        c_total = line["c_nf_per_km"] * line["length_km"] * 1e-9
        pf_line = dpsimpy.sp.ph1.PiLine(
            f"line{line['from_bus']}_{line['to_bus']}_pf", dpsimpy.LogLevel.warn
        )
        pf_line.set_parameters(R=r_total, L=x_total / omega, C=c_total)
        pf_line.set_base_voltage(topology["buses"][line["from_bus"]]["vn_kv"] * 1000.0)
        pf_line.connect([nodes[line["from_bus"]], nodes[line["to_bus"]]])
        components.append(pf_line)

    ext_bus = topology["buses"][topology["ext_grid_bus"]]
    pf_ext = dpsimpy.sp.ph1.NetworkInjection("extnet_pf", dpsimpy.LogLevel.warn)
    pf_ext.set_parameters(voltage_set_point=ext_bus["vn_kv"] * 1000.0)
    pf_ext.set_base_voltage(ext_bus["vn_kv"] * 1000.0)
    pf_ext.modify_power_flow_bus_type(dpsimpy.PowerflowBusType.VD)
    pf_ext.connect([nodes[topology["ext_grid_bus"]]])
    components.append(pf_ext)

    return dpsimpy.SystemTopology(
        topology["system_frequency_hz"], list(nodes.values()), components
    )


def initialize_with_powerflow(
    dsys: "chaosnet.DpsimChaosSystem", topology: "chaosnet.ChaosTopology"
) -> None:
    """Solve `to_sp_powerflow_system(topology)` and apply it to
    `dsys["system"]` via `init_with_powerflow` -- the real two-stage init
    `AvVoltageSourceInverterDQ` requires (see module docstring). Mutates
    `dsys["system"]`'s internal node/component state in place (DPsim's own
    API shape); call this once, after every component has been spliced into
    `dsys["system"]`, and before `sim.start()`. Must not be combined with
    `sim.do_steady_state_init(True)` on the same run (the official DPsim
    example this mirrors uses `init_with_powerflow` instead of steady-state
    init, not alongside it).

    Args:
        dsys: the fully-assembled DpsimChaosSystem (renewable already
            spliced in via `add_renewable_source_to_system()`).
        topology: the `ChaosTopology` `dsys` was built from.
    """
    import dpsimpy  # local import: matches chaosnet.py's own convention

    sp_system = to_sp_powerflow_system(topology)
    sim_pf = dpsimpy.Simulation("renewable_pf_init", dpsimpy.LogLevel.warn)
    sim_pf.set_system(sp_system)
    sim_pf.set_time_step(1.0)
    sim_pf.set_final_time(2.0)
    sim_pf.set_domain(dpsimpy.Domain.SP)
    sim_pf.set_solver(dpsimpy.Solver.NRP)
    sim_pf.do_init_from_nodes_and_terminals(False)
    sim_pf.run()
    dsys["system"].init_with_powerflow(sp_system, dpsimpy.Domain.EMT)
