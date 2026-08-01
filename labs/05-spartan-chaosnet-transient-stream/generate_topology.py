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

import pandapower as pp

import chaosnet

LAB_DIR = Path(__file__).resolve().parent
SAMPLE_TOPOLOGY_FILE = LAB_DIR / "sample_topology.json"
EXPECTED_FILE = LAB_DIR / "expected_topology.json"

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

    return summary


def check_step() -> bool:
    """Re-run generate_step(FIXTURE_SEED) (without touching the committed
    fixtures) and diff it against expected_topology.json.

    Returns:
        True if bus/line/tap counts, tap names, and convergence match
        exactly, and mean_vm_pu matches within FIXTURE_VM_ATOL; False
        otherwise.
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
