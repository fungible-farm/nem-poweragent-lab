#!/usr/bin/env python3
"""Lab 9 Phase 1 -- the live Grid2Op subprocess bridge.

Speaks one JSON object per line on stdout (an observation) and reads one JSON
object per line on stdin (an action), which is what
`rust/mission-engine/src/grid2op_bridge.rs` drives when run with
`--grid2op-live`. The Rust side follows the `bevy_rapier` pattern PRD-0009
names: a `Plugin` spawns this process on `Startup`, a `std::thread` pumps its
stdout into an `mpsc::Receiver`, and an `Update` `System` drains that into a
Bevy `Resource`.

grid2op is NOT a dependency of this repo's pyproject.toml/uv.lock, and
`--no-binary-package grid2op` is REQUIRED (grid2op 1.12.5's published PyPI
wheel is missing `grid2op/typing_variables.py` -- diagnosed in full in
`labs/08-cim-gridy-phase0-spikes/0a-grid2op/README.md`):

    uv run --with grid2op --no-binary-package grid2op python \\
        labs/09-cim-gridy-phase1-3-vertical-slice/grid2op_bridge.py

Protocol
--------
stdout, one object per line:

    {"step": 0, "done": false, "reward": 1.0,
     "lines": [{"grid2op_line_id": 290, "name": "line_4125_4128", "rho": 0.011116}, ...],
     "buses": [{"grid2op_sub_id": 1741, "name": "bus_4125", "v_kv": 275.4}, ...]}

stdin, one object per line:

    {"action": "do_nothing"}
    {"action": "set_line_status", "line": "line_4125_4128", "status": -1}

`{"action": "do_nothing"}` maps to grid2op's own `env.action_space({})` no-op,
exactly as Lab 8 0a's `run_episode.py` already proved.

Scope, stated honestly
----------------------
The episode runs the real, full ~503-bus/698-branch snemSA.m network. Only the
19 branches and 15 buses of Lab 6's already-modelled cluster
(`labs/06-sysml-digital-thread/schema/grid_instances.yaml`) are reported on the
wire and given Bevy entities -- full-grid modelling is explicitly out of scope
for this lab.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LAB_DIR = Path(__file__).resolve().parent
DATASET_DIR = LAB_DIR / "dataset_snemSA"
GRID_INSTANCES = REPO_ROOT / "labs" / "06-sysml-digital-thread" / "schema" / "grid_instances.yaml"


# --------------------------------------------------------------------------
# Lab 6 cluster <-> grid2op index correlation
#
# grid2op's PandaPowerBackend flattens pandapower's two branch tables into one
# line-index space: ids 0..len(net.line)-1 are net.line rows in table order,
# then len(net.line)..len(net.line)+len(net.trafo)-1 are net.trafo rows in
# table order. This is NOT documented anywhere in this repo and was NOT
# assumed -- `verify_line_ordering()` below asserts it directly against
# grid2op's own `line_or_to_subid`/`line_ex_to_subid` arrays, and
# `generate_fixture.py` calls it before writing any fixture.
#
# Lab 6's own branch names are derived, not read from the net (net.line["name"]
# and net.trafo["name"] are all None in this case) -- see
# labs/06-sysml-digital-thread/build_grid_instances.py: a line is
# `line_<from_bus_name>_<to_bus_name>` (with the "bus_" prefix stripped), a
# transformer is `xfmr_<hv_bus_name>_<lv_bus_name>`, and parallel branches
# between the same pair get `_2`, `_3`, ... suffixes in table-row order. Bus
# NAMES (bus_4052, ...) survive create_continuous_bus_index untouched, so the
# same derivation reproduces Lab 6's names exactly on the reindexed net.
# --------------------------------------------------------------------------

def load_cluster_names() -> tuple[list[str], list[str]]:
    """Lab 6's cluster bus + branch names, read from its committed schema."""
    import yaml

    inst = yaml.safe_load(GRID_INSTANCES.read_text())
    return (
        [b["name"] for b in inst["buses"]],
        [ln["name"] for ln in inst["lines"]],
    )


def derive_branch_names(net: Any) -> list[str]:
    """Lab 6's naming rule applied to every branch of the net, in grid2op's
    own flattened line-index order (net.line rows, then net.trafo rows)."""
    busname = net.bus["name"].to_dict()

    def short(bus_id: int) -> str:
        return str(busname[int(bus_id)]).removeprefix("bus_")

    names = [
        f"line_{short(row.from_bus)}_{short(row.to_bus)}"
        for row in net.line.itertuples()
    ]
    names += [
        f"xfmr_{short(row.hv_bus)}_{short(row.lv_bus)}"
        for row in net.trafo.itertuples()
    ]
    return names


def cluster_line_map(net: Any, cluster_line_names: list[str]) -> dict[str, int]:
    """Lab 6 branch name -> grid2op line id, reproducing Lab 6's `_2` suffix
    dedupe over the cluster subset in table-row order."""
    bases = set()
    for name in cluster_line_names:
        head, _, tail = name.rpartition("_")
        # `line_4112_4129_2` -> base `line_4112_4129`; `line_4112_4129` -> itself.
        bases.add(head if tail.isdigit() and head.count("_") >= 2 else name)

    mapping: dict[str, int] = {}
    seen: dict[str, int] = {}
    for idx, base in enumerate(derive_branch_names(net)):
        if base not in bases:
            continue
        seen[base] = seen.get(base, 0) + 1
        mapping[base if seen[base] == 1 else f"{base}_{seen[base]}"] = idx

    missing = [n for n in cluster_line_names if n not in mapping]
    if missing:
        raise AssertionError(
            f"Lab 6 cluster branches not found in the grid2op line space: {missing}"
        )
    return mapping


def cluster_bus_map(net: Any, cluster_bus_names: list[str]) -> dict[str, int]:
    """Lab 6 bus name -> grid2op substation id (== the dense pandapower bus
    index, since PandaPowerBackend models one substation per bus)."""
    by_name = {str(v): int(k) for k, v in net.bus["name"].to_dict().items()}
    return {name: by_name[name] for name in cluster_bus_names}


def verify_line_ordering(env: Any, net: Any, line_map: dict[str, int]) -> list[str]:
    """Assert -- do not assume -- that grid2op's line/rho ordering really is
    net.line rows followed by net.trafo rows, and that every Lab 6 cluster
    branch's grid2op endpoints are the bus pair Lab 6 says they are.

    Returns human-readable evidence lines for the caller to print.
    """
    import yaml

    n_line_pp = len(net.line)
    evidence: list[str] = []

    if int(env.n_line) != n_line_pp + len(net.trafo):
        raise AssertionError(
            f"env.n_line={env.n_line} != len(net.line)+len(net.trafo)="
            f"{n_line_pp + len(net.trafo)}"
        )

    # Endpoint check across the WHOLE line space, not a sample.
    for i in range(int(env.n_line)):
        if i < n_line_pp:
            row = net.line.iloc[i]
            exp_or, exp_ex = int(row.from_bus), int(row.to_bus)
        else:
            row = net.trafo.iloc[i - n_line_pp]
            exp_or, exp_ex = int(row.hv_bus), int(row.lv_bus)
        if (int(env.line_or_to_subid[i]), int(env.line_ex_to_subid[i])) != (exp_or, exp_ex):
            raise AssertionError(
                f"grid2op line {i} endpoints "
                f"({env.line_or_to_subid[i]},{env.line_ex_to_subid[i]}) != pandapower "
                f"row endpoints ({exp_or},{exp_ex}) -- the flattened "
                f"net.line-then-net.trafo ordering assumption is WRONG"
            )
    evidence.append(
        f"line ordering verified: all {int(env.n_line)} grid2op line endpoints match "
        f"net.line rows 0..{n_line_pp - 1} then net.trafo rows 0..{len(net.trafo) - 1}"
    )

    # Named cross-check: each Lab 6 branch's grid2op endpoints must be the bus
    # names Lab 6's own YAML records for it.
    inst = yaml.safe_load(GRID_INSTANCES.read_text())
    by_name = {ln["name"]: ln for ln in inst["lines"]}
    busname = net.bus["name"].to_dict()
    for name, i in sorted(line_map.items(), key=lambda kv: kv[1]):
        want = by_name[name]
        got = (str(busname[int(env.line_or_to_subid[i])]),
               str(busname[int(env.line_ex_to_subid[i])]))
        if got != (want["from_bus"], want["to_bus"]):
            raise AssertionError(
                f"{name} (grid2op line {i}) connects {got}, but Lab 6 says "
                f"({want['from_bus']}, {want['to_bus']})"
            )
    evidence.append(
        f"Lab 6 cluster cross-check: all {len(line_map)} cluster branches connect the "
        f"exact bus pair grid_instances.yaml records for them"
    )
    return evidence


# --------------------------------------------------------------------------
# Observation payload
# --------------------------------------------------------------------------

def observation_payload(
    obs: Any,
    step: int,
    done: bool,
    reward: float,
    line_map: dict[str, int],
    bus_map: dict[str, int],
) -> dict[str, Any]:
    lines = [
        {"grid2op_line_id": int(i), "name": name, "rho": round(float(obs.rho[i]), 9)}
        for name, i in sorted(line_map.items(), key=lambda kv: kv[1])
    ]

    # A cluster bus's real measured voltage: the origin-side voltage of the
    # first cluster branch that starts there, else the extremity-side voltage
    # of the first that ends there. Real grid2op observation data, not a
    # placeholder.
    buses = []
    for name, sub in sorted(bus_map.items(), key=lambda kv: kv[1]):
        v = None
        for i in line_map.values():
            if int(obs.line_or_to_subid[i]) == sub:
                v = float(obs.v_or[i])
                break
            if int(obs.line_ex_to_subid[i]) == sub:
                v = float(obs.v_ex[i])
                break
        buses.append({
            "grid2op_sub_id": int(sub),
            "name": name,
            "v_kv": round(v, 6) if v is not None else None,
        })

    return {
        "step": step,
        "done": bool(done),
        "reward": round(float(reward), 6),
        "lines": lines,
        "buses": buses,
    }


def build_action(env: Any, request: dict[str, Any], line_map: dict[str, int]) -> Any:
    kind = request.get("action", "do_nothing")
    if kind == "do_nothing":
        # grid2op's own canonical no-op (Lab 8 0a proved this exact call).
        return env.action_space({})
    if kind == "set_line_status":
        line_id = line_map[request["line"]]
        return env.action_space({"set_line_status": [(line_id, int(request["status"]))]})
    raise ValueError(f"unsupported action: {kind!r}")


def main() -> None:
    if not DATASET_DIR.exists():
        print(
            f"[FAIL] {DATASET_DIR} not found -- run build_dataset.py first",
            file=sys.stderr,
        )
        sys.exit(1)

    import pandapower as pp
    import grid2op

    net = pp.from_json(str(DATASET_DIR / "grid.json"))
    bus_names, line_names = load_cluster_names()
    line_map = cluster_line_map(net, line_names)
    bus_map = cluster_bus_map(net, bus_names)

    env = grid2op.make(str(DATASET_DIR), test=True)
    for note in verify_line_ordering(env, net, line_map):
        print(f"[bridge] {note}", file=sys.stderr)

    obs = env.reset()
    step = 0
    sys.stdout.write(
        json.dumps(observation_payload(obs, step, False, 0.0, line_map, bus_map)) + "\n"
    )
    sys.stdout.flush()

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            request = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"[bridge] bad action line {raw!r}: {exc}", file=sys.stderr)
            continue
        if request.get("action") == "quit":
            break
        obs, reward, done, _info = env.step(build_action(env, request, line_map))
        step += 1
        sys.stdout.write(
            json.dumps(
                observation_payload(obs, step, done, reward, line_map, bus_map)
            ) + "\n"
        )
        sys.stdout.flush()
        if done:
            break

    env.close()


if __name__ == "__main__":
    main()
