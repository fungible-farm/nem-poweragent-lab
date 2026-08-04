"""Shared chaos-net topology model for Lab 5.

Builds one procedurally-perturbed "chaos-net" grid topology per run, from a
real SimBench seed grid (realistic MV distribution-network parameter
distributions) restructured by a NetworkX random-graph generator (the actual
topology "chaos"). This is the exact split named in
`docs/LAB5_SPARTAN_CHAOSNET.md`'s components table: "SimBench supplies
realistic parameter distributions so procedurally generated topologies
aren't arbitrary; NetworkX supplies the graph structure."

The same `ChaosTopology` this module builds is loadable two ways:
  - `to_pandapower()` -- a steady-state AC power-flow sanity check.
  - `to_dpsim_emt_system()` -- a real DPsim EMT-domain SystemTopology for
    `run_dpsim.py`'s transient solve, including a fault Switch at the
    schedule's target substation.

Sandbox stand-in named here (per AGENTS.md): DPsim's 3-phase (`emt.ph3`)
line/load model used below is a *balanced, decoupled* representation --
diagonal 3x3 R/L/C matrices per line and per load, i.e. no phase-to-phase
mutual coupling. A production untransposed-line model would carry a full
3x3 mutual-impedance matrix (self + mutual terms) derived from real
conductor geometry; SimBench's per-km R/X/C columns are already a
positive-sequence single-phase equivalent (the same figure pandapower's own
single-phase power-flow model uses), so building a diagonal 3x3 from them
is the direct, honest extension of that same equivalent-circuit
simplification into 3-phase EMT, not an invented number.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import TypedDict

import networkx as nx
import numpy as np
import pandapower as pp
import simbench as sb

LAB_DIR = Path(__file__).resolve().parent

# Confirmed a real SimBench code via simbench.collect_all_simbench_codes()
# in this sandbox (session log: 246 total codes, "1-MV-rural--0-sw" among
# them) -- a rural medium-voltage distribution feeder *with* normally-open
# tie switches ("-sw"), i.e. a real network that is itself already built to
# support meshed/reconfigurable operation -- a fitting real seed for a
# "chaos-net" that keeps breaking and re-forming.
SIMBENCH_CODE: str = "1-MV-rural--0-sw"

# Real voltage level (kV) of this SimBench net's MV buses, confirmed via
# `net.bus.vn_kv` in this sandbox (all MV buses sit at 20.0 kV; the seed
# grid's HV buses at 110 kV are excluded -- see `_mv_bus_pool`).
MV_VN_KV: float = 20.0

# System frequency (Hz), matches SimBench/pandapower's implicit 50 Hz and is
# passed to both pandapower (implicitly) and dpsimpy.SystemTopology
# (explicitly) so the two loaders agree.
SYSTEM_FREQUENCY_HZ: float = 50.0

# Docs example: "perturbed: 14 buses, 17 lines, 3 substations tagged as tap
# points" (docs/LAB5_SPARTAN_CHAOSNET.md step 1). We match the bus count
# exactly; the real edge/tap counts an actual run prints will differ from
# that illustrative example -- printed honestly, not forced to match.
NUM_CHAOS_BUSES: int = 14

# NetworkX Watts-Strogatz parameters for the topology perturbation step.
# k=4: each bus starts wired to its 4 nearest neighbours in the chaos ring
# before rewiring -- deliberately denser than a bare radial feeder (k=2)
# because the seed grid code itself is the "-sw" (switched/meshable)
# variant, so some real backup meshing is in scope for the chaos-net too.
# p=0.3: documented rewiring probability -- high enough that every seed
# produces a visibly different topology (per docs/LAB5_SPARTAN_CHAOSNET.md
# step 1's "a different topology on a different seed"), low enough that
# `nx.connected_watts_strogatz_graph` reliably finds a connected graph
# within its retry budget.
WATTS_STROGATZ_K: int = 4
WATTS_STROGATZ_P: float = 0.3
# Retries before nx.connected_watts_strogatz_graph gives up -- generous
# margin above the library's own default (100) since this runs once per
# script invocation, not in a hot loop.
WATTS_STROGATZ_TRIES: int = 200

# "...3 substations tagged as tap points" -- docs/LAB5_SPARTAN_CHAOSNET.md
# step 1 example output, matched exactly (not just approximately) because
# the walkthrough's step 3/4 commands name a specific tap ("sub-3-tap").
NUM_TAP_SUBSTATIONS: int = 3

# Substation tap naming: SUB-1 is the highest-degree bus in the perturbed
# graph (tie-broken by bus index for determinism), SUB-2 the next, etc.
# SUB-3 is therefore always the *lowest*-degree of the three tagged taps --
# an arbitrary but fixed convention, chosen only so "SUB-3" (the walkthrough
# and chaos_schedule.yaml's literal fault target) names the same bus on
# every run for a given seed.
SUBSTATION_PREFIX: str = "SUB-"

# Reproducible default seed, matches docs/LAB5_SPARTAN_CHAOSNET.md step 1's
# worked example ("--seed 42").
DEFAULT_SEED: int = 42


class ChaosBus(TypedDict):
    """One bus in the generated chaos-net topology."""

    index: int
    vn_kv: float
    is_tap: bool
    tap_name: str | None  # "SUB-1" etc, or None if not a tagged tap point


class ChaosLine(TypedDict):
    """One line in the generated chaos-net topology.

    r_ohm_per_km/x_ohm_per_km/c_nf_per_km/max_i_ka are copied verbatim from
    a real SimBench line record (not invented), so both loaders below build
    physically-consistent impedances from the same source numbers.
    """

    from_bus: int
    to_bus: int
    length_km: float
    r_ohm_per_km: float
    x_ohm_per_km: float
    c_nf_per_km: float
    max_i_ka: float


class ChaosLoad(TypedDict):
    """One load in the generated chaos-net topology, sampled from a real
    SimBench load record."""

    bus: int
    p_mw: float
    q_mvar: float


class ChaosTopology(TypedDict):
    """A complete, seed-reproducible chaos-net instance."""

    seed: int
    simbench_code: str
    system_frequency_hz: float
    buses: list[ChaosBus]
    lines: list[ChaosLine]
    loads: list[ChaosLoad]
    ext_grid_bus: int
    tap_buses: list[int]  # bus indices, ordered SUB-1..SUB-N
    tap_names: list[str]


def _mv_bus_pool(net: pp.pandapowerNet) -> list[int]:
    """Real MV bus indices (20 kV) in the SimBench seed net, excluding the
    110 kV HV side of the feeding transformer.

    Args:
        net: a loaded SimBench pandapower net.

    Returns:
        Sorted bus indices at MV_VN_KV.
    """
    mv = net.bus[net.bus.vn_kv == MV_VN_KV]
    return sorted(int(b) for b in mv.index)


def build_chaos_topology(seed: int = DEFAULT_SEED) -> ChaosTopology:
    """Build one seed-reproducible chaos-net topology.

    SimBench (`SIMBENCH_CODE`) supplies the real bus pool, real per-km line
    parameter distribution, and real load distribution. NetworkX
    (`nx.connected_watts_strogatz_graph`, seeded by `seed`) supplies the
    graph structure connecting a `NUM_CHAOS_BUSES`-sized subset of those
    real buses -- a different structure for a different seed, per
    docs/LAB5_SPARTAN_CHAOSNET.md step 1.

    Args:
        seed: selects both which real buses are drawn from the SimBench
            pool and how NetworkX perturbs the graph connecting them --
            fully reproducible for a given seed.

    Returns:
        The generated ChaosTopology.
    """
    rng = np.random.default_rng(seed)
    net = sb.get_simbench_net(SIMBENCH_CODE)

    bus_pool = _mv_bus_pool(net)
    chosen_real_buses = sorted(
        int(b) for b in rng.choice(bus_pool, size=NUM_CHAOS_BUSES, replace=False)
    )
    line_pool = net.line[
        ["r_ohm_per_km", "x_ohm_per_km", "c_nf_per_km", "length_km", "max_i_ka"]
    ].to_dict("records")
    load_pool = net.load[["p_mw", "q_mvar"]].to_dict("records")

    graph = nx.connected_watts_strogatz_graph(
        NUM_CHAOS_BUSES,
        WATTS_STROGATZ_K,
        WATTS_STROGATZ_P,
        tries=WATTS_STROGATZ_TRIES,
        seed=int(seed),
    )

    # Tag the NUM_TAP_SUBSTATIONS highest-degree local buses (0-indexed
    # within the chaos-net, not the real SimBench bus id) as substation tap
    # points -- a hub in the perturbed graph is the closest structural
    # analogue to a real substation with several feeders converging on it.
    # Tie-broken by local index for determinism.
    degree_order = sorted(graph.degree, key=lambda kv: (-kv[1], kv[0]))
    tap_local = [idx for idx, _deg in degree_order[:NUM_TAP_SUBSTATIONS]]
    tap_names = [f"{SUBSTATION_PREFIX}{i + 1}" for i in range(NUM_TAP_SUBSTATIONS)]
    tap_name_by_local = dict(zip(tap_local, tap_names))

    buses: list[ChaosBus] = []
    for local_idx, real_bus in enumerate(chosen_real_buses):
        vn_kv = float(net.bus.at[real_bus, "vn_kv"])
        buses.append(
            {
                "index": local_idx,
                "vn_kv": vn_kv,
                "is_tap": local_idx in tap_name_by_local,
                "tap_name": tap_name_by_local.get(local_idx),
            }
        )

    lines: list[ChaosLine] = []
    for u, v in sorted(graph.edges()):
        rec = line_pool[int(rng.integers(0, len(line_pool)))]
        lines.append(
            {
                "from_bus": int(u),
                "to_bus": int(v),
                "length_km": float(rec["length_km"]),
                "r_ohm_per_km": float(rec["r_ohm_per_km"]),
                "x_ohm_per_km": float(rec["x_ohm_per_km"]),
                "c_nf_per_km": float(rec["c_nf_per_km"]),
                "max_i_ka": float(rec["max_i_ka"]),
            }
        )

    # Local bus 0 is the slack/injection point; every other bus gets a real
    # sampled SimBench load. Bus 0 is deliberately excluded from tap tagging
    # implicitly by degree (it is one node among NUM_CHAOS_BUSES so it *can*
    # be tagged) -- kept simple rather than special-cased, since an
    # ext-grid bus also being a monitored tap point is physically fine.
    loads: list[ChaosLoad] = []
    for local_idx in range(1, NUM_CHAOS_BUSES):
        rec = load_pool[int(rng.integers(0, len(load_pool)))]
        loads.append(
            {
                "bus": local_idx,
                "p_mw": float(rec["p_mw"]),
                "q_mvar": float(rec["q_mvar"]),
            }
        )

    return {
        "seed": int(seed),
        "simbench_code": SIMBENCH_CODE,
        "system_frequency_hz": SYSTEM_FREQUENCY_HZ,
        "buses": buses,
        "lines": lines,
        "loads": loads,
        "ext_grid_bus": 0,
        "tap_buses": tap_local,
        "tap_names": tap_names,
    }


def to_pandapower(topology: ChaosTopology) -> pp.pandapowerNet:
    """Build a pandapower net from a ChaosTopology, for the sanity
    power-flow check named in docs/LAB5_SPARTAN_CHAOSNET.md's Definition of
    Done ("loadable by ... pandapower (for a sanity power-flow check)").

    Args:
        topology: output of build_chaos_topology().

    Returns:
        An unsolved pandapower net; call pandapower.runpp() on it.
    """
    net = pp.create_empty_network(f_hz=topology["system_frequency_hz"])
    bus_id = {
        b["index"]: pp.create_bus(
            net, vn_kv=b["vn_kv"], name=f"chaos-bus-{b['index']}"
        )
        for b in topology["buses"]
    }
    for line in topology["lines"]:
        pp.create_line_from_parameters(
            net,
            from_bus=bus_id[line["from_bus"]],
            to_bus=bus_id[line["to_bus"]],
            length_km=line["length_km"],
            r_ohm_per_km=line["r_ohm_per_km"],
            x_ohm_per_km=line["x_ohm_per_km"],
            c_nf_per_km=line["c_nf_per_km"],
            max_i_ka=line["max_i_ka"],
        )
    for load in topology["loads"]:
        pp.create_load(
            net, bus=bus_id[load["bus"]], p_mw=load["p_mw"], q_mvar=load["q_mvar"]
        )
    pp.create_ext_grid(net, bus=bus_id[topology["ext_grid_bus"]], vm_pu=1.0)
    return net


# --- DPsim EMT translation -------------------------------------------------

# "Open" and "closed" resistance (ohm) for every dpsimpy.emt.ph3.Switch built
# below, including the fault switch. 1e6 ohm open / 0.5 ohm closed for
# ordinary switching (line-outage) events matches the "near-infinite open /
# near-zero closed" convention used in DPsim's own examples (see
# examples/villas/*.py). Named separately from FAULT_CLOSED_RESISTANCE_OHM
# below, which is deliberately not near-zero (see that constant's comment).
SWITCH_OPEN_RESISTANCE_OHM: float = 1e6
SWITCH_CLOSED_RESISTANCE_OHM: float = 0.5

# Line-to-ground fault resistance (ohm) for the fault switch inserted at the
# schedule's target substation. Deliberately *not* a bolted (near-zero-ohm)
# fault: swept 0.2/0.5/1.0/2.0 ohm against the real 14-bus/28-line seed-42
# chaos-net in this sandbox (dpsim 1.2.1, 200us EMT timestep) --
# 0.2 ohm produced a 33% sag but a ~4.3x-nominal-peak switching spike;
# 0.5 ohm produced a clean, numerically stable 16.4% sag at the fault bus
# with a much smaller (~2.7x-nominal-peak) switching transient; both are
# NaN-free (this sandbox's meshed 14-bus topology, unlike a single stiff
# 2-node test circuit, tolerates a stronger fault without ringing). 0.5 ohm
# per phase is the documented choice: a partial (impedance-limited)
# line-to-ground fault rather than a bolted one, producing a real, visible,
# numerically stable voltage sag and clean recovery -- a real transient to
# demonstrate, not a solver crash.
FAULT_CLOSED_RESISTANCE_OHM: float = 0.5


def _phase_voltage_ref(vn_kv: float) -> np.ndarray:
    """Balanced 3-phase peak line-neutral voltage reference (A, B, C) for an
    EMT NetworkInjection, in volts.

    Args:
        vn_kv: nominal line-to-line RMS voltage of the injection bus, kV.

    Returns:
        A (3, 1) complex numpy array: peak line-neutral phasors 120 degrees
        apart, matching dpsimpy.emt.ph3.NetworkInjection.set_parameters's
        expected V_ref shape (validated interactively against dpsim 1.2.1
        in this sandbox).
    """
    peak = vn_kv * 1000.0 * math.sqrt(2.0 / 3.0)
    angles = (0.0, -2.0 * math.pi / 3.0, 2.0 * math.pi / 3.0)
    return np.array(
        [[complex(peak * math.cos(a), peak * math.sin(a))] for a in angles]
    )


class DpsimChaosSystem(TypedDict):
    """Everything run_dpsim.py needs to drive the EMT solve and tap the
    fault substation's node(s).

    `fault_switches`/`fault_buses` are plural (tap_name -> switch/bus index)
    so `to_dpsim_emt_system()` can build N fault-capable switches for N
    `NetworkFaultGenerator`/`ProtectionTripGenerator` targets in one
    SystemTopology -- the generalization from Lab 5's original "one fault"
    to `docs/prd/0001-composable-generator-detector-platform.md`'s ordered
    list of faults/trips. A single-target caller (today's Lab 5 usage)
    gets a one-entry dict; nothing about the physics changes for that case.
    """

    system: object  # dpsimpy.SystemTopology
    nodes: dict[int, object]  # local bus index -> dpsimpy.emt.SimNode
    fault_switches: dict[str, object]  # tap_name -> dpsimpy.emt.ph3.Switch
    fault_buses: dict[str, int]  # tap_name -> local bus index


def to_dpsim_emt_system(
    topology: ChaosTopology, fault_tap_name: str | list[str]
) -> DpsimChaosSystem:
    """Build a real dpsimpy EMT (3-phase) SystemTopology from a
    ChaosTopology, with one fault Switch inserted (initially open) at each
    bus tagged in `fault_tap_name`.

    Requires the `dpsimpy` package (imported lazily here so pandapower-only
    callers -- e.g. generate_topology.py's --step check -- do not need
    DPsim installed).

    Args:
        topology: output of build_chaos_topology().
        fault_tap_name: one of topology["tap_names"] (e.g. "SUB-3"), or a
            list of them -- the substation(s) a fault switch is attached
            to. A bare str is normalized to a one-element list internally;
            in that single-target case the switch keeps today's exact
            component name ("fault_switch") so nothing about an existing
            single-fault run's DPsim component naming changes. Multiple
            targets get a disambiguated name per tap
            (`fault_switch_<TAP-NAME>`).

    Returns:
        The assembled DpsimChaosSystem, with one entry per requested tap
        name in both `fault_switches` and `fault_buses`.

    Raises:
        ValueError: if any requested tap name is not one of this
            topology's tagged tap points.
    """
    import dpsimpy  # local import: see docstring

    tap_names = [fault_tap_name] if isinstance(fault_tap_name, str) else list(fault_tap_name)
    for name in tap_names:
        if name not in topology["tap_names"]:
            raise ValueError(
                f"{name!r} is not a tagged tap point of this topology "
                f"(have {topology['tap_names']})"
            )
    fault_buses = {
        name: topology["tap_buses"][topology["tap_names"].index(name)]
        for name in tap_names
    }

    omega = 2.0 * math.pi * topology["system_frequency_hz"]
    nodes = {
        b["index"]: dpsimpy.emt.SimNode(f"bus{b['index']}", dpsimpy.PhaseType.ABC)
        for b in topology["buses"]
    }

    components: list = []

    for load in topology["loads"]:
        bus = topology["buses"][load["bus"]]
        rx = dpsimpy.emt.ph3.RXLoad(f"load{load['bus']}", dpsimpy.LogLevel.warn)
        rx.set_parameters(
            np.eye(3) * (load["p_mw"] * 1e6 / 3.0),
            np.eye(3) * (load["q_mvar"] * 1e6 / 3.0),
            bus["vn_kv"] * 1000.0,
        )
        rx.connect([nodes[load["bus"]]])
        components.append(rx)

    for line in topology["lines"]:
        r_total = line["r_ohm_per_km"] * line["length_km"]
        x_total = line["x_ohm_per_km"] * line["length_km"]
        c_total = line["c_nf_per_km"] * line["length_km"] * 1e-9
        pi_line = dpsimpy.emt.ph3.PiLine(
            f"line{line['from_bus']}_{line['to_bus']}", dpsimpy.LogLevel.warn
        )
        pi_line.set_parameters(
            np.eye(3) * r_total,
            np.eye(3) * (x_total / omega),
            np.eye(3) * c_total,
        )
        pi_line.connect([nodes[line["from_bus"]], nodes[line["to_bus"]]])
        components.append(pi_line)

    ext_bus = topology["buses"][topology["ext_grid_bus"]]
    extnet = dpsimpy.emt.ph3.NetworkInjection("extnet", dpsimpy.LogLevel.warn)
    extnet.set_parameters(
        _phase_voltage_ref(ext_bus["vn_kv"]), topology["system_frequency_hz"]
    )
    extnet.connect([nodes[topology["ext_grid_bus"]]])
    components.append(extnet)

    fault_switches: dict[str, object] = {}
    for name in tap_names:
        # Single-target case keeps today's exact component name so nothing
        # about an existing single-fault run's DPsim component naming
        # changes (see docstring); multi-target scenarios (new in this
        # round) disambiguate per tap.
        switch_name = "fault_switch" if len(tap_names) == 1 else f"fault_switch_{name}"
        switch = dpsimpy.emt.ph3.Switch(switch_name, dpsimpy.LogLevel.info)
        switch.set_parameters(
            np.eye(3) * SWITCH_OPEN_RESISTANCE_OHM,
            np.eye(3) * FAULT_CLOSED_RESISTANCE_OHM,
            False,
        )
        switch.connect([nodes[fault_buses[name]], dpsimpy.emt.SimNode.gnd])
        components.append(switch)
        fault_switches[name] = switch

    system = dpsimpy.SystemTopology(
        topology["system_frequency_hz"], list(nodes.values()), components
    )

    return {
        "system": system,
        "nodes": nodes,
        "fault_switches": fault_switches,
        "fault_buses": fault_buses,
    }


def write_topology_json(topology: ChaosTopology, path: Path) -> None:
    """Serialize a ChaosTopology to JSON (used for both sample_topology.json
    and the transient run's own record of which topology it solved)."""
    path.write_text(json.dumps(topology, indent=2))


def read_topology_json(path: Path) -> ChaosTopology:
    """Load a ChaosTopology previously written by write_topology_json()."""
    return json.loads(path.read_text())
