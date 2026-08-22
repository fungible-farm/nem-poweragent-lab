#!/usr/bin/env python3
"""Lab 9 -- reproduce the README's N-1 outage sweep for real, from a clean
checkout, per this repo's own rule (AGENTS.md: "the proof scripts are the
proof, not a transcript"). Trips each of Lab 6's 19 cluster branches, one at
a time, from a fresh env.reset(), and reports the resulting cluster-wide
maximum rho -- the same real computation that grounds `RHO_LIMIT = 0.030` in
generate_fixture.py and the "Design notes" table in README.md. This is a
*read-only* diagnostic: it does not write any committed fixture (Phase 1/3's
fixtures come from generate_fixture.py's scripted 5-step episode instead),
it only re-derives the numbers the README quotes so they're independently
checkable, not asserted from an ad hoc session transcript.

    uv run --with grid2op --no-binary-package grid2op python \\
        labs/09-cim-gridy-phase1-3-vertical-slice/sweep_outages.py
"""
from __future__ import annotations

import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB_DIR))

from grid2op_bridge import (  # noqa: E402
    DATASET_DIR,
    build_action,
    cluster_line_map,
    load_cluster_names,
)


def main() -> None:
    if not DATASET_DIR.exists():
        print(f"[FAIL] {DATASET_DIR} not found -- run build_dataset.py first", file=sys.stderr)
        sys.exit(1)

    import pandapower as pp
    import grid2op

    net = pp.from_json(str(DATASET_DIR / "grid.json"))
    _, line_names = load_cluster_names()
    line_map = cluster_line_map(net, line_names)

    env = grid2op.make(str(DATASET_DIR), test=True)

    base_obs = env.reset()
    base_rho = max(base_obs.rho[i] for i in line_map.values())
    print(f"base case (nothing tripped)              rho_max={base_rho:.6f}")

    results: list[tuple[str, float | None]] = []
    for name in line_names:
        env.reset()
        obs, _reward, done, info = env.step(
            build_action(env, {"action": "set_line_status", "line": name, "status": -1}, line_map)
        )
        if done or info.get("exception"):
            print(f"{name:28s} power flow DIVERGES (done={done})")
            results.append((name, None))
            continue
        rho_max = max(obs.rho[i] for i in line_map.values())
        print(f"{name:28s} rho_max={rho_max:.6f}")
        results.append((name, rho_max))

    env.close()

    converged = [(n, r) for n, r in results if r is not None]
    diverged = [n for n, r in results if r is None]
    converged.sort(key=lambda nr: nr[1], reverse=True)

    print()
    print(f"{len(converged)} convergent outages, {len(diverged)} divergent, "
          f"{len(line_names)} total")
    print(f"largest real cluster-wide loading increase: "
          f"{converged[0][0]} ({converged[0][1]:.6f})")
    print(f"diverged (islanding, not modelled): {', '.join(diverged)}")


if __name__ == "__main__":
    main()
