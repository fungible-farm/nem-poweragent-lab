"""Procedural load-scale fit tasks across networks, for G3's first RL pilot (backlog 0017).

0017's cheapest first step: "a GRPO pilot on the r6 Qwen student over generated load-scale fits
drawn from two networks, scored on calls to reach tolerance against bisection". Today's training
and evaluation fits all come from one network (0008). This draws fits from snem-sa-2000 and
snem-1803 (solvable since the flat-start retry, 0008), with elements *discovered* per network:

- a load-scale fit scales every load and observes one bus voltage, so the bracketing needs the
  voltage to move monotonically in scale. Discovery solves at ``DISCOVERY_SCALES`` and keeps
  buses whose voltage is strictly monotone across them with at least ``MIN_SPAN_PU`` between
  the interval ends;
- task targets, tolerances and references then come from ``generate._gen_fit_example``, the same
  real-bisection reference the benchmark uses.

Seeds are this module's own (``PROCEDURAL_SEED``). A pool is audited against every evaluation
suite before training (``audit_rows``), so a training fit can never be an evaluated one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandapower as pp

from powercoder.datasets import generate
from powercoder.inference import powermcp as pm

PROCEDURAL_SEED: int = 20261024
NETWORKS: tuple[str, ...] = ("snem-sa-2000", "snem-1803")
# The tool's interval ends (studies.SCALE_MIN/MAX) and three interior points.
DISCOVERY_SCALES: tuple[float, ...] = (0.9, 0.95, 1.0, 1.05, 1.1)
# A span this small would need a tolerance below the solver's own noise to be a real fit.
MIN_SPAN_PU: float = 1e-3
# Elements kept per network, the most responsive first.
ELEMENTS_PER_NETWORK: int = 40
PER_NETWORK: int = 50


def discover_load_scale_buses(case: str) -> list[dict[str, Any]]:
    """Buses whose voltage is strictly monotone in load scale with a usable span, as generate expects.

    Returns:
        ``[{"bus", "vm_lo", "vm_hi"}]``, most responsive first, at most ELEMENTS_PER_NETWORK.
    """
    curves: dict[int, list[float]] = {}
    for scale in DISCOVERY_SCALES:
        net, _ = pm._load_network_object(case)
        net.load.loc[:, ["p_mw", "q_mvar"]] *= scale
        pm._runpp_counted(net, numba=True)
        for bus in net.bus.index:
            curves.setdefault(int(bus), []).append(float(net.res_bus.vm_pu[bus]))
    kept = []
    for bus, values in curves.items():
        steps = [b - a for a, b in zip(values, values[1:])]
        monotone = all(s > 0 for s in steps) or all(s < 0 for s in steps)
        if monotone and abs(values[-1] - values[0]) >= MIN_SPAN_PU:
            kept.append({"bus": bus, "vm_lo": values[0], "vm_hi": values[-1]})
    kept.sort(key=lambda e: abs(e["vm_hi"] - e["vm_lo"]), reverse=True)
    return kept[:ELEMENTS_PER_NETWORK]


def build(per_network: int = PER_NETWORK) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Verified load-scale fits from every network, and the discovered element count per network."""
    rows, discovered = [], {}
    cache = generate.EndpointCache()
    for case in NETWORKS:
        elements = discover_load_scale_buses(case)
        discovered[case] = len(elements)
        made = 0
        for i in range(per_network * 2):
            row = generate._gen_fit_example("pf-load-scale-fit", case, elements, i, PROCEDURAL_SEED, cache)
            if row["lifecycle"]["status"] == "verified":
                row["lifecycle"]["split"] = "train"
                rows.append(row)
                made += 1
            if made == per_network:
                break
    return rows, discovered


def main() -> int:
    """Write a frozen pool with its manifest."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--per-network", type=int, default=PER_NETWORK)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise ValueError("Refusing to overwrite a frozen pool")
    rows, discovered = build(args.per_network)
    args.out_dir.mkdir(parents=True)
    examples = args.out_dir / "examples.jsonl"
    with examples.open("x") as stream:
        for row in rows:
            stream.write(json.dumps(row, allow_nan=False) + "\n")
    by_network = {case: sum(r["topology"] == case for r in rows) for case in NETWORKS}
    (args.out_dir / "manifest.json").write_text(json.dumps({
        "pool": "procedural-load-scale-v1", "seed": PROCEDURAL_SEED, "n_tasks": len(rows), "by_network": by_network,
        "discovered_elements": discovered, "examples_sha256": hashlib.sha256(examples.read_bytes()).hexdigest()},
        indent=2) + "\n")
    print(json.dumps({"tasks": len(rows), "by_network": by_network, "discovered_elements": discovered}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
