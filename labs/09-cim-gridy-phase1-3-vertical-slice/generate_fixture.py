#!/usr/bin/env python3
"""Lab 9 Phase 1/3 -- run the real Grid2Op episode and write the committed
fixtures the Rust `mission-engine` tests read.

    uv run --with grid2op --no-binary-package grid2op python \\
        labs/09-cim-gridy-phase1-3-vertical-slice/generate_fixture.py

Writes:
  fixtures/episode_observations.jsonl  -- Phase 1: 5 real steps, including one
      real line trip and one real reclose, in the same wire format
      grid2op_bridge.py emits live.
  fixtures/contingency_candidates.json -- Phase 3: the fixed contingency plus
      three candidate remedial actions, each scored from its OWN real grid2op
      what-if run (no fabricated post-action numbers).

Before writing anything it calls `grid2op_bridge.verify_line_ordering()`,
which asserts grid2op's flattened line/rho ordering against the pandapower
net's own branch tables across the entire 698-branch line space, and
cross-checks every Lab 6 cluster branch against the bus pair
`grid_instances.yaml` records for it. That correlation was not confirmed
anywhere in this repo before this lab, so it is verified, not assumed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB_DIR))

from grid2op_bridge import (  # noqa: E402
    DATASET_DIR,
    build_action,
    cluster_bus_map,
    cluster_line_map,
    load_cluster_names,
    observation_payload,
    verify_line_ordering,
)

FIXTURES_DIR = LAB_DIR / "fixtures"
EPISODE_FIXTURE = FIXTURES_DIR / "episode_observations.jsonl"
CANDIDATES_FIXTURE = FIXTURES_DIR / "contingency_candidates.json"

# The mission's single, fixed, named contingency: a real single-circuit 275 kV
# transmission line inside Lab 6's cluster. Chosen by measuring every one of
# the cluster's 19 N-1 branch outages for real (`sweep_outages.py`, see
# README "Design notes"): one of the two largest real cluster-wide loading
# increases of any outage whose power flow still converges (line_4128_4148
# measures marginally higher, 0.037629 vs 0.037622 -- this line was picked
# for being the more centrally-connected branch of the two).
CONTINGENCY_LINE = "line_4125_4128"

# The mission's security threshold. NOT 1.0 -- see README "Design notes: the
# rho limit is 0.030, not 1.0". snemSA.m's branch ratings are effectively
# unconstrained (Lab 6 already documents `sn_mva: 10000.0` as a synthetic-case
# artifact), so grid2op derives a uniform ~20,995 A thermal limit for every
# cluster branch and rho never exceeds 0.038 under ANY single cluster outage.
# 0.030 sits above the real base-case cluster maximum (0.026554) and below the
# real post-contingency maximum (0.037622), so the threshold crossing this lab
# scores is a real measured change in the real grid state, not a fabricated
# overload.
RHO_LIMIT = 0.030

# Phase 1's scripted 5-step episode.
EPISODE_ACTIONS = [
    {"action": "do_nothing"},
    {"action": "set_line_status", "line": CONTINGENCY_LINE, "status": -1},
    {"action": "do_nothing"},
    {"action": "set_line_status", "line": CONTINGENCY_LINE, "status": 1},
]

# Phase 3's candidate remedial actions, each applied to the SAME real
# post-contingency state and measured with a real grid2op step.
CANDIDATES = [
    {
        "name": "reclose_line_4125_4128",
        "description": "Reclose the tripped 275 kV circuit bus_4125-bus_4128.",
        "action": {"action": "set_line_status", "line": CONTINGENCY_LINE, "status": 1},
    },
    {
        "name": "open_line_4117_4131",
        "description": "Open bus_4117-bus_4131 to redistribute flow around the outage.",
        "action": {"action": "set_line_status", "line": "line_4117_4131", "status": -1},
    },
    {
        "name": "do_nothing",
        "description": "Accept the post-contingency state and continue monitoring.",
        "action": {"action": "do_nothing"},
    },
]


def main() -> None:
    if not DATASET_DIR.exists():
        print(f"[FAIL] {DATASET_DIR} not found -- run build_dataset.py first", file=sys.stderr)
        sys.exit(1)

    import pandapower as pp
    import grid2op

    net = pp.from_json(str(DATASET_DIR / "grid.json"))
    bus_names, line_names = load_cluster_names()
    line_map = cluster_line_map(net, line_names)
    bus_map = cluster_bus_map(net, bus_names)

    env = grid2op.make(str(DATASET_DIR), test=True)
    for note in verify_line_ordering(env, net, line_map):
        print(f"[verify] {note}")

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    # ---- Phase 1 episode -------------------------------------------------
    obs = env.reset()
    records = [observation_payload(obs, 0, False, 0.0, line_map, bus_map)]
    for step, request in enumerate(EPISODE_ACTIONS, start=1):
        obs, reward, done, info = env.step(build_action(env, request, line_map))
        if info.get("exception"):
            raise RuntimeError(f"step {step} raised: {info['exception']}")
        records.append(observation_payload(obs, step, done, reward, line_map, bus_map))

    with EPISODE_FIXTURE.open("w") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    print(f"Wrote {EPISODE_FIXTURE} ({len(records)} steps)")
    for rec in records:
        rho_max = max(l["rho"] for l in rec["lines"])
        worst = max(rec["lines"], key=lambda l: l["rho"])["name"]
        over = sum(1 for l in rec["lines"] if l["rho"] > RHO_LIMIT)
        print(f"  step {rec['step']}: rho_max={rho_max:.6f} ({worst}) "
              f"over_limit={over}/{len(rec['lines'])} done={rec['done']}")

    # ---- Phase 3 candidates ----------------------------------------------
    # Each candidate starts from the same real post-contingency state: a fresh
    # reset followed by the real trip of CONTINGENCY_LINE.
    candidates_out = []
    contingency_state = None
    for cand in CANDIDATES:
        env.reset()
        obs, _, done, info = env.step(
            build_action(env, {"action": "set_line_status",
                               "line": CONTINGENCY_LINE, "status": -1}, line_map)
        )
        if done or info.get("exception"):
            raise RuntimeError(f"contingency step failed: {info.get('exception')}")
        if contingency_state is None:
            contingency_state = observation_payload(obs, 0, False, 0.0, line_map, bus_map)

        obs2, reward, done2, info2 = env.step(build_action(env, cand["action"], line_map))
        if done2 or info2.get("exception"):
            raise RuntimeError(f"candidate {cand['name']} failed: {info2.get('exception')}")
        payload = observation_payload(obs2, 1, done2, reward, line_map, bus_map)
        candidates_out.append({
            "name": cand["name"],
            "description": cand["description"],
            "post_action_rho": [[l["name"], l["rho"]] for l in payload["lines"]],
        })

    doc = {
        "contingency": {
            "name": f"n1_{CONTINGENCY_LINE}",
            "tripped_line": CONTINGENCY_LINE,
            "description": (
                "N-1 outage of the real 275 kV circuit bus_4125-bus_4128 in Lab 6's "
                "15-bus cluster of CSIRO snemSA.m."
            ),
        },
        "rho_limit": RHO_LIMIT,
        "post_contingency_rho": [
            [l["name"], l["rho"]] for l in (contingency_state or {}).get("lines", [])
        ],
        "candidates": candidates_out,
    }
    CANDIDATES_FIXTURE.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"Wrote {CANDIDATES_FIXTURE} ({len(candidates_out)} candidates)")
    for cand in candidates_out:
        rho_max = max(r for _, r in cand["post_action_rho"])
        over = sum(1 for _, r in cand["post_action_rho"] if r > RHO_LIMIT)
        print(f"  {cand['name']:26s} rho_max={rho_max:.6f} over_limit={over}"
              f"/{len(cand['post_action_rho'])}")

    env.close()


if __name__ == "__main__":
    main()
