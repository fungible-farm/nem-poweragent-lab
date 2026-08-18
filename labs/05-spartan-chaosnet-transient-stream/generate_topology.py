#!/usr/bin/env python3
"""Lab 5, step 1 -- Chaos-Net Topology Generator.

See README.md in this directory for the full walkthrough. Two steps:

    uv run labs/05-spartan-chaosnet-transient-stream/generate_topology.py --seed 42
    uv run labs/05-spartan-chaosnet-transient-stream/generate_topology.py --step check

Builds one procedurally-perturbed grid topology per run (real SimBench seed
grid + a NetworkX Watts-Strogatz perturbation, see chaosnet.py for the full
split), confirms it is power-flow-convergent via a real
`pandapower.runpp()`, and prints the summary line documented in
docs/LAB5_SPARTAN_CHAOSNET.md step 1.

No sandbox stand-in in this file: SimBench, NetworkX, and pandapower are all
real, installed packages, and pandapower.runpp() is a real AC solve -- see
chaosnet.py's own module docstring for the one named simplification (a
balanced/decoupled 3-phase line model) that lives in the topology builder
itself, not here.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TypedDict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402
import pandapower as pp  # noqa: E402

import chaosnet  # noqa: E402

LAB_DIR = Path(__file__).resolve().parent
SAMPLE_TOPOLOGY_FILE = LAB_DIR / "sample_topology.json"
EXPECTED_FILE = LAB_DIR / "expected_topology.json"
SAMPLE_TOPOLOGY_PLOT_FILE = LAB_DIR / "sample_topology_plot.png"

# nx.spring_layout()'s force-directed node placement is itself randomized;
# this is a fixed, arbitrary seed for *that* placement RNG only -- kept
# separate from chaosnet.build_chaos_topology()'s own `seed` (which selects
# the real buses drawn from SimBench and the Watts-Strogatz perturbation) so
# a plot of a given topology renders identically across repeated runs
# without coupling the layout algorithm's randomness to the topology
# generation's.
TOPOLOGY_LAYOUT_SEED: int = 7

# Node/edge colors for _plot_topology(). Chosen via the dataviz skill's
# `references/palette.md` categorical palette (slot 1 blue / slot 8 red) and
# confirmed colorblind-safe as a pair by that skill's own
# `validate_palette.js "#2a78d6,#e34948" --mode light` (and `--mode dark`)
# tool (not a script in this repo): CVD separation 21.6 (protan),
# normal-vision separation 32.3, both well clear of the skill's floors. Also
# a close match to this
# lab's existing verify_stream.py plot convention (`#3b6fa0`-ish blue for the
# main series, `#c0392b`-ish red for the highlighted/fault element).
TOPOLOGY_BUS_NODE_COLOR: str = "#2a78d6"
TOPOLOGY_TAP_NODE_COLOR: str = "#e34948"
# Muted axis/gridline ink (dataviz skill's palette.md "Muted (axis/labels)"
# role) so edges read as structure without competing with the two node
# colors above.
TOPOLOGY_EDGE_COLOR: str = "#898781"

# Ordinary-bus vs tap-substation marker size (nx.draw node_size units,
# points^2). Taps are drawn 2x larger -- deliberate visual emphasis so the
# NUM_TAP_SUBSTATIONS=3 tagged substations (one of which,
# chaos_schedule.yaml's SUB-3, is this lab's actual fault target) are
# obviously distinguishable from the other buses at a glance, not just by
# color.
TOPOLOGY_BUS_NODE_SIZE: int = 260
TOPOLOGY_TAP_NODE_SIZE: int = 520

# spring_layout's output coordinates sit roughly in [-1, 1] per axis
# (NetworkX's own documented convention for its force-directed layouts);
# this nudges a tap's text label just above its node so the label doesn't
# sit on top of (and obscure) the marker it names.
TOPOLOGY_LABEL_Y_OFFSET: float = 0.08

# Matches verify_stream.py's SAMPLE_PLOT_FILE figure/dpi convention, sized
# slightly more square (8x6 vs 9x4) since this is a graph layout, not a
# wide time-series plot.
TOPOLOGY_PLOT_FIGSIZE: tuple[float, float] = (8.0, 6.0)
TOPOLOGY_PLOT_DPI: int = 130

# Only --seed 42's output overwrites the committed sample_topology.json /
# expected_topology.json fixtures (docs/LAB5_SPARTAN_CHAOSNET.md step 1's
# own worked example uses --seed 42) -- running with a different seed prints
# and exits without touching the committed fixtures, so exploring other
# seeds can't accidentally cause fixture drift.
FIXTURE_SEED: int = chaosnet.DEFAULT_SEED


class TopologyCheckSummary(TypedDict):
    """Diffable summary of one generate_step() run, written to
    expected_topology.json and re-derived by check_step()."""

    seed: int
    simbench_code: str
    num_buses: int
    num_lines: int
    num_taps: int
    tap_names: list[str]
    pandapower_converged: bool
    mean_vm_pu: float


def _build_topology_graph(topology: chaosnet.ChaosTopology) -> nx.Graph:
    """Reconstruct a small nx.Graph directly from a ChaosTopology's
    buses/lines lists -- shared by `_plot_topology()` and
    `animate_sag_propagation.py` (docs/backlog/0006 option 4) so both draw
    the *identical* graph structure rather than each rebuilding their own.

    Deliberately does not thread through build_chaos_topology()'s internal
    nx.connected_watts_strogatz_graph object -- keeps this decoupled from
    that internal graph-building state, so it can plot any ChaosTopology,
    including one read back from sample_topology.json, not just a
    freshly-built one.

    Args:
        topology: output of chaosnet.build_chaos_topology() (or
            chaosnet.read_topology_json()).

    Returns:
        An undirected nx.Graph with one node per bus index, one edge per
        line.
    """
    graph = nx.Graph()
    for bus in topology["buses"]:
        graph.add_node(bus["index"])
    for line in topology["lines"]:
        graph.add_edge(line["from_bus"], line["to_bus"])
    return graph


def _topology_layout(graph: nx.Graph) -> dict[int, tuple[float, float]]:
    """The one fixed node layout for a chaos-net graph -- `nx.spring_layout()`
    seeded by `TOPOLOGY_LAYOUT_SEED`, factored out so every renderer of this
    lab's topology (the static plot below and `animate_sag_propagation.py`'s
    animation, docs/backlog/0006 option 4) places each bus at the identical
    (x, y) position -- a reader can overlay or compare the two artifacts by
    eye.

    Args:
        graph: output of `_build_topology_graph()`.

    Returns:
        bus index -> (x, y) position, per nx.spring_layout()'s convention.
    """
    return nx.spring_layout(graph, seed=TOPOLOGY_LAYOUT_SEED)


def _plot_topology(topology: chaosnet.ChaosTopology, path: Path) -> None:
    """Render the generated chaos-net graph structure -- until now this lab's
    entire premise ("a new topology each run") was only ever visible as a
    bus/line count printed as text (docs/backlog/0004-lab4-lab5-
    visualization-options.md, Lab 5 item 1 / docs/backlog/0001-topology-and-
    results-visualization-gap.md item 1).

    Tap-point buses (chaos_schedule.yaml's fault target, SUB-3, is one of
    them) are drawn larger, in a different color, and labelled with their
    tap_name so a reader can immediately spot the fault target on the
    picture; ordinary buses are smaller, unlabelled dots.

    Args:
        topology: output of chaosnet.build_chaos_topology() (or
            chaosnet.read_topology_json()).
        path: output PNG path.
    """
    graph = _build_topology_graph(topology)
    pos = _topology_layout(graph)

    is_tap_by_index = {bus["index"]: bus["is_tap"] for bus in topology["buses"]}
    nodelist = list(graph.nodes())
    node_color = [
        TOPOLOGY_TAP_NODE_COLOR if is_tap_by_index[n] else TOPOLOGY_BUS_NODE_COLOR
        for n in nodelist
    ]
    node_size = [
        TOPOLOGY_TAP_NODE_SIZE if is_tap_by_index[n] else TOPOLOGY_BUS_NODE_SIZE
        for n in nodelist
    ]

    fig, ax = plt.subplots(figsize=TOPOLOGY_PLOT_FIGSIZE)
    nx.draw(
        graph,
        pos=pos,
        ax=ax,
        nodelist=nodelist,
        node_color=node_color,
        node_size=node_size,
        edge_color=TOPOLOGY_EDGE_COLOR,
        width=1.0,
        with_labels=False,
    )

    tap_labels = {
        bus["index"]: bus["tap_name"]
        for bus in topology["buses"]
        if bus["tap_name"] is not None
    }
    label_pos = {
        n: (x, y + TOPOLOGY_LABEL_Y_OFFSET) for n, (x, y) in pos.items() if n in tap_labels
    }
    nx.draw_networkx_labels(
        graph,
        label_pos,
        ax=ax,
        labels=tap_labels,
        font_size=9,
        font_weight="bold",
        font_color=TOPOLOGY_TAP_NODE_COLOR,
    )

    ax.set_title(
        f"Lab 5 chaos-net topology -- seed {topology['seed']}, "
        f"{topology['simbench_code']}"
    )
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=TOPOLOGY_PLOT_DPI)
    plt.close(fig)


def generate_step(
    seed: int, verbose: bool = True, refresh_fixtures: bool = True
) -> TopologyCheckSummary:
    """Build one chaos-net topology and sanity-check it with a real AC
    power flow.

    Args:
        seed: --seed value.
        verbose: if True, print the walkthrough's documented summary line.
        refresh_fixtures: if True and seed == FIXTURE_SEED, (re)write the
            committed sample_topology.json / expected_topology.json
            fixtures from this run's real output. check_step() passes
            False so a self-check re-derivation never mutates the fixture
            it is about to diff against.

    Returns:
        A TopologyCheckSummary of this run.
    """
    topology = chaosnet.build_chaos_topology(seed)
    net = chaosnet.to_pandapower(topology)
    pp.runpp(net)

    summary: TopologyCheckSummary = {
        "seed": seed,
        "simbench_code": topology["simbench_code"],
        "num_buses": len(topology["buses"]),
        "num_lines": len(topology["lines"]),
        "num_taps": len(topology["tap_names"]),
        "tap_names": topology["tap_names"],
        "pandapower_converged": bool(net.converged),
        "mean_vm_pu": round(float(net.res_bus.vm_pu.mean()), 6),
    }

    if verbose:
        print(
            f"Seeded from simbench code {topology['simbench_code']}, "
            f"perturbed: {summary['num_buses']} buses, {summary['num_lines']} "
            f"lines, {summary['num_taps']} substations tagged as tap points "
            f"({', '.join(summary['tap_names'])})"
        )
        print(
            f"pandapower.runpp() converged: {summary['pandapower_converged']} "
            f"(mean bus voltage {summary['mean_vm_pu']:.4f} pu)"
        )

    if seed == FIXTURE_SEED and refresh_fixtures:
        chaosnet.write_topology_json(topology, SAMPLE_TOPOLOGY_FILE)
        EXPECTED_FILE.write_text(json.dumps(summary, indent=2))
        if verbose:
            print(
                f"[fixtures] wrote {SAMPLE_TOPOLOGY_FILE.name} and "
                f"{EXPECTED_FILE.name} (seed == FIXTURE_SEED={FIXTURE_SEED})"
            )
        _plot_topology(topology, SAMPLE_TOPOLOGY_PLOT_FILE)
        if verbose:
            print(
                f"[fixtures] wrote {SAMPLE_TOPOLOGY_PLOT_FILE.name} "
                f"(seed == FIXTURE_SEED={FIXTURE_SEED})"
            )

    return summary


def check_step() -> bool:
    """Re-run generate_step(FIXTURE_SEED) (without touching the committed
    fixtures) and diff it against expected_topology.json.

    Also asserts the committed sample_topology_plot.png artifact exists
    (mirroring verify_stream.py's own SAMPLE_PLOT_FILE.exists() check) so
    the self-check gate actually covers the topology plot per AGENTS.md's
    "every lab is self-checking" convention, not just the JSON fixtures.

    Returns:
        True if bus/line/tap counts, tap names, and convergence match
        exactly, mean_vm_pu matches within FIXTURE_VM_ATOL, and the
        committed topology plot PNG exists; False otherwise.
    """
    if not EXPECTED_FILE.exists():
        print(f"[FAIL] no fixture at {EXPECTED_FILE}", file=sys.stderr)
        return False
    expected = json.loads(EXPECTED_FILE.read_text())
    actual = generate_step(FIXTURE_SEED, verbose=False, refresh_fixtures=False)

    ok = True
    for key in ("num_buses", "num_lines", "num_taps", "tap_names", "pandapower_converged"):
        if expected[key] != actual[key]:
            print(f"FAIL: {key}: expected={expected[key]} actual={actual[key]}")
            ok = False
    if abs(expected["mean_vm_pu"] - actual["mean_vm_pu"]) > FIXTURE_VM_ATOL:
        print(
            f"FAIL: mean_vm_pu: expected={expected['mean_vm_pu']} "
            f"actual={actual['mean_vm_pu']}"
        )
        ok = False
    if not SAMPLE_TOPOLOGY_PLOT_FILE.exists():
        print(f"FAIL: no plot at {SAMPLE_TOPOLOGY_PLOT_FILE}")
        ok = False

    if ok:
        print(
            f"MATCH: seed {FIXTURE_SEED} topology matches "
            f"expected_topology.json ({actual['num_buses']} buses, "
            f"{actual['num_lines']} lines, taps={actual['tap_names']})"
        )
    return ok


# Float-equality slack for mean_vm_pu, same rationale as Lab 1/2's
# FIXTURE_FLOAT_ATOL/FIXTURE_VOLTAGE_ATOL: looser than print precision to
# absorb solver last-bit noise across numpy/BLAS versions.
FIXTURE_VM_ATOL: float = 1e-4


def main() -> None:
    """CLI entry point. --seed selects the topology (default
    chaosnet.DEFAULT_SEED); --step check re-derives FIXTURE_SEED's topology
    and diffs it against expected_topology.json, exiting non-zero on
    mismatch (CI/pytest-friendly gate, matching Lab 1/2's pattern)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=chaosnet.DEFAULT_SEED)
    parser.add_argument("--step", choices=["generate", "check"], default="generate")
    args = parser.parse_args()

    if args.step == "generate":
        generate_step(args.seed)
    elif args.step == "check":
        ok = check_step()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
