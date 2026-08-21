"""Derive Track B's seed data (`schema/grid_instances.yaml`) from the real CSIRO Synthetic-NEM
`data/snemSA.m` case -- not a hand-authored snapshot. Every bus/generator/line value in the emitted
file is read directly from that case via `labs/_shared/gridfit.load_case()`; this script only picks
which small, connected, legible subset to include and writes it out, the same "reshape real data
into a committed fixture" role `build_k8s_fixture.py` plays for Track A's k8s snapshot.

Selection algorithm, deterministic and documented (not "walked by hand until it looked right"):
breadth-first search over the real line+trafo graph, starting at `ANCHOR_BUS_INDEX` (a real
generator bus with non-trivial output -- among this case's generators it isn't the largest, just a
representative one chosen to anchor the walk). At each frontier step, real transmission-line
neighbours are visited before real transformer neighbours (both groups sorted by pandapower bus
index for a fully deterministic tie-break) -- transmission is the network's primary connective
layer, generator step-up transformers are secondary attachments. The walk stops as soon as
`TARGET_CLUSTER_SIZE` buses have been visited, keeping the result small enough to stay legible on
one diagram (this lab's own "as many options de-risked as feasible, buying knowledge" sprint framing
does not extend to dumping the whole 2000-bus case into one SysML view).

Real quirk, surfaced automatically from the case data below, not hidden: this cluster's generator
step-up transformers carry an `sn_mva` two orders of magnitude above a real unit's typical
100-500 MVA rating -- a synthetic-case artifact, not a transcription error (see the emitted file's
own header, generated from the real value read here).
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path
from typing import Any, Final

import networkx as nx
import pandapower as pp

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "labs" / "_shared"))
from gridfit import load_case  # noqa: E402

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CASE_PATH: Final[Path] = REPO_ROOT / "data" / "snemSA.m"
OUTPUT_PATH: Final[Path] = Path(__file__).resolve().parent / "schema" / "grid_instances.yaml"

# The real generator bus this walk starts from -- see module docstring for why this one, not the
# case's single largest generator. Named explicitly, not left as an implicit "whatever the search
# happens to land on" (AGENTS.md "no undocumented magic numbers").
ANCHOR_BUS_INDEX: Final[int] = 1683
# Bumped from the original 5 to stress-test the Cassowary layout's generalized forest logic
# (translate_iso_ir.py's `_anchor_forest`/`_level_x_positions`) against a real, denser topology --
# the same anchor's walk reaches several real multi-degree substations at this size (bus 1740,
# degree 11; bus 1728, degree 9), not just the single hub the original 5-bus cluster had.
TARGET_CLUSTER_SIZE: Final[int] = 15


def _build_graph(net: pp.pandapowerNet) -> nx.Graph:
    """Undirected graph over real line+trafo branches, each edge tagged with which table it came
    from (`via`) so the BFS below can prefer transmission lines at each frontier step."""
    g = nx.Graph()
    for _, row in net.line.iterrows():
        g.add_edge(int(row.from_bus), int(row.to_bus), via="line", length_km=float(row.length_km))
    for _, row in net.trafo.iterrows():
        g.add_edge(int(row.hv_bus), int(row.lv_bus), via="trafo", sn_mva=float(row.sn_mva))
    return g


def _select_cluster(g: nx.Graph, anchor: int, target_size: int) -> list[int]:
    """Breadth-first walk from `anchor`, line-neighbours before trafo-neighbours at each frontier
    step (both sorted by bus index), stopping once `target_size` buses have been visited. Returns
    bus indices in discovery order."""
    visited: list[int] = [anchor]
    visited_set: set[int] = {anchor}
    queue: deque[int] = deque([anchor])
    while queue and len(visited) < target_size:
        current = queue.popleft()
        neighbours = [n for n in g.neighbors(current) if n not in visited_set]
        line_neighbours = sorted(n for n in neighbours if g[current][n]["via"] == "line")
        trafo_neighbours = sorted(n for n in neighbours if g[current][n]["via"] == "trafo")
        for n in line_neighbours + trafo_neighbours:
            if len(visited) >= target_size:
                break
            if n in visited_set:
                continue
            visited.append(n)
            visited_set.add(n)
            queue.append(n)
    return visited


def _bus_name(net: pp.pandapowerNet, idx: int) -> str:
    return str(net.bus.loc[idx, "name"])


def _dedupe_names(branches: list[dict[str, Any]]) -> None:
    """Real substations sometimes carry parallel branches between the same bus pair for N-1
    redundancy -- confirmed in this case: two real, distinct transformers between bus_4125/
    bus_4238 (`net.trafo` rows 41/42) and two real, distinct lines between bus_4112/bus_4129, both
    genuinely separate equipment, not a selection-walk duplicate. Naming every branch from just its
    endpoint buses (`line_<from>_<to>` / `xfmr_<hv>_<lv>`) collapses parallel branches onto one
    name, which would emit two YAML entries with the same `name` -- an invalid, ambiguous SysML
    part identifier. In-place, mutates `branches`: the first branch on a given bus pair keeps its
    plain name; each subsequent one gets a `_2`, `_3`, ... suffix, in the same real table row order
    everything else here is read in (deterministic, not re-sorted)."""
    seen: dict[str, int] = {}
    for branch in branches:
        base = branch["name"]
        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            branch["name"] = f"{base}_{seen[base]}"


def build_instances() -> dict[str, Any]:
    net, _warnings = load_case(CASE_PATH)
    g = _build_graph(net)
    cluster_order = _select_cluster(g, ANCHOR_BUS_INDEX, TARGET_CLUSTER_SIZE)
    cluster_set = set(cluster_order)

    buses = [
        {
            "name": _bus_name(net, idx),
            "source": f"data/snemSA.m (pandapower bus index {idx})",
            "voltage_kv": float(net.bus.loc[idx, "vn_kv"]),
        }
        for idx in cluster_order
    ]

    # net.gen's own `name` column is unset (None) in this case -- a generator's real identity here
    # is its bus, so its instance name is derived from the bus it's attached to (`gen_<suffix>`),
    # matching this schema's existing naming convention -- not net.gen's own (empty) name field.
    generators = [
        {
            "name": f"gen_{_bus_name(net, int(row['bus'])).removeprefix('bus_')}",
            "source": f"data/snemSA.m (pandapower gen table, bus {int(row['bus'])})",
            "bus": _bus_name(net, int(row["bus"])),
            "rated_mw": round(float(row["p_mw"]), 1),
        }
        for _, row in net.gen.iterrows()
        if int(row["bus"]) in cluster_set
    ]

    # Read directly from the real line/trafo tables (not via graph-edge iteration, which doesn't
    # preserve a source table's own from/to direction or row order) -- both tables' own row order
    # already matches this walk's discovery order for this cluster, confirmed by inspection.
    transmission = [
        {
            "name": f"line_{_bus_name(net, int(row.from_bus)).removeprefix('bus_')}_{_bus_name(net, int(row.to_bus)).removeprefix('bus_')}",
            "source": f"data/snemSA.m (pandapower line table, {int(row.from_bus)}-{int(row.to_bus)})",
            "from_bus": _bus_name(net, int(row.from_bus)),
            "to_bus": _bus_name(net, int(row.to_bus)),
            "kind": "transmission",
            "length_km": float(row.length_km),
        }
        for _, row in net.line.iterrows()
        if int(row.from_bus) in cluster_set and int(row.to_bus) in cluster_set
    ]
    transformers = [
        {
            "name": f"xfmr_{_bus_name(net, int(row.hv_bus)).removeprefix('bus_')}_{_bus_name(net, int(row.lv_bus)).removeprefix('bus_')}",
            "source": f"data/snemSA.m (pandapower trafo table, {int(row.hv_bus)}-{int(row.lv_bus)})",
            "from_bus": _bus_name(net, int(row.hv_bus)),
            "to_bus": _bus_name(net, int(row.lv_bus)),
            "kind": "transformer",
        }
        for _, row in net.trafo.iterrows()
        if int(row.hv_bus) in cluster_set and int(row.lv_bus) in cluster_set
    ]
    _dedupe_names(transmission)
    _dedupe_names(transformers)

    return {"buses": buses, "generators": generators, "lines": transmission + transformers}


def _fmt_number(x: float) -> str:
    """Whole numbers keep one decimal place (275.0, 1.0 -- matching this file's original
    hand-authored style); genuinely fractional values use Python's own minimal repr (15.75, 127.3).
    """
    return f"{x:.1f}" if float(x) == int(x) else repr(float(x))


def _parallel_branch_note(instances: dict[str, Any]) -> str:
    """Derived, not hand-listed: groups this cluster's real lines/transformers by (kind, from_bus,
    to_bus) and names whichever bus pairs actually came back with more than one real branch (see
    `_dedupe_names`'s own docstring for why that can happen). Empty string if this cluster/anchor
    combination happens to have none -- the header simply omits the paragraph rather than claiming
    a quirk that isn't in the data this run."""
    pair_kind_names: dict[tuple[str, str, str], list[str]] = {}
    for entry in instances["lines"]:
        key = (entry["kind"], entry["from_bus"], entry["to_bus"])
        pair_kind_names.setdefault(key, []).append(entry["name"])
    dupes = [(kind, a, b) for (kind, a, b), names in pair_kind_names.items() if len(names) > 1]
    if not dupes:
        return ""
    lines_pairs = ", ".join(f"`{a}`/`{b}`" for kind, a, b in dupes if kind == "transmission")
    xfmr_pairs = ", ".join(f"`{a}`/`{b}`" for kind, a, b in dupes if kind == "transformer")
    parts = []
    if xfmr_pairs:
        parts.append(f"bus pair(s) {xfmr_pairs} are joined by two parallel transformers each")
    if lines_pairs:
        parts.append(f"bus pair(s) {lines_pairs} by two parallel lines")
    return (
        "#\n# Also real, also carried through as-is: "
        + ", and ".join(parts)
        + " -- genuine N-1-redundant real equipment, not a selection-walk duplicate (see "
        "`_dedupe_names`'s own docstring for how their names stay unique).\n"
    )


def _header(instances: dict[str, Any], anchor_name: str, anchor_mw: float, sn_mva: float) -> str:
    xfmr_entries = [x for x in instances["lines"] if x["kind"] == "transformer"]
    xfmr_names = ", ".join(f"`{x['name']}`" for x in xfmr_entries)
    # "each carry" reads correctly whether this cluster has one transformer or a dozen -- "both"
    # (the original 2-transformer wording) silently became wrong once the cluster grew and stopped
    # being exactly two.
    return f"""# Track B seed data: a real, small, connected cluster from CSIRO's Synthetic-NEM-2000-Bus
# `data/snemSA.m` (the same case Lab 1 loads) -- regenerated by build_grid_instances.py
# (`--step run`), not hand-authored. Every value below is read directly from that case; see that
# script's own module docstring for the exact deterministic selection algorithm (a breadth-first
# walk of the real line+trafo graph, starting at real generator bus `{anchor_name}`
# (p_mw={_fmt_number(anchor_mw)}), preferring transmission-line neighbours over transformer
# neighbours at each frontier step, stopping once a {TARGET_CLUSTER_SIZE}-bus cluster is reached).
#
# Real quirk, reported honestly rather than smoothed over (same convention as Lab 2's bus-1126
# pre-existing-condition note): {xfmr_names} each carry `sn_mva: {_fmt_number(sn_mva)}` in the
# source case -- two orders of magnitude above a real generator step-up transformer's typical
# 100-500 MVA rating. This is a synthetic-case artifact (CSIRO's case appears to use an
# effectively-unconstrained rating for this internal generator-to-bus connection, not a modelled
# equipment limit), not a transcription error -- carried through as-is because the point of this
# track is showing SysML v2 modelling real case data faithfully, quirks included, not curating it.
{_parallel_branch_note(instances).rstrip()}
"""


def _render_yaml(instances: dict[str, Any], header: str) -> str:
    lines: list[str] = [header, "buses:"]
    for i, b in enumerate(instances["buses"]):
        lines += [
            f"  - name: {b['name']}",
            f'    source: "{b["source"]}"',
            f"    voltage_kv: {_fmt_number(b['voltage_kv'])}",
        ]
        if i != len(instances["buses"]) - 1:
            lines.append("")
    lines += ["", "generators:"]
    for i, gen in enumerate(instances["generators"]):
        lines += [
            f"  - name: {gen['name']}",
            f'    source: "{gen["source"]}"',
            f"    bus: {gen['bus']}",
            f"    rated_mw: {_fmt_number(gen['rated_mw'])}",
        ]
        if i != len(instances["generators"]) - 1:
            lines.append("")
    lines += ["", "lines:"]
    for i, ln in enumerate(instances["lines"]):
        lines += [
            f"  - name: {ln['name']}",
            f'    source: "{ln["source"]}"',
            f"    from_bus: {ln['from_bus']}",
            f"    to_bus: {ln['to_bus']}",
            f"    kind: {ln['kind']}",
        ]
        if "length_km" in ln:
            lines.append(f"    length_km: {_fmt_number(ln['length_km'])}")
        if i != len(instances["lines"]) - 1:
            lines.append("")
    return "\n".join(lines) + "\n"


def generate() -> str:
    net, _warnings = load_case(CASE_PATH)
    instances = build_instances()
    anchor_row = net.gen[net.gen.bus == ANCHOR_BUS_INDEX].iloc[0]
    anchor_name = _bus_name(net, ANCHOR_BUS_INDEX)
    cluster_set = set(_select_cluster(_build_graph(net), ANCHOR_BUS_INDEX, TARGET_CLUSTER_SIZE))
    xfmr_row = net.trafo[net.trafo.hv_bus.isin(cluster_set) & net.trafo.lv_bus.isin(cluster_set)].iloc[0]
    header = _header(instances, anchor_name, round(float(anchor_row["p_mw"]), 1), float(xfmr_row["sn_mva"]))
    return _render_yaml(instances, header)


def check_step() -> bool:
    fresh = generate()
    if not OUTPUT_PATH.exists():
        print(f"FAIL: {OUTPUT_PATH} does not exist -- run --step run first")
        return False
    committed = OUTPUT_PATH.read_text()
    if fresh == committed:
        print(f"MATCH: {OUTPUT_PATH.name} vs a fresh re-derivation from {CASE_PATH.relative_to(REPO_ROOT)}")
        return True
    print(f"FAIL: {OUTPUT_PATH.name} is stale -- source data/snemSA.m or the selection algorithm changed, re-run --step run")
    return False


def main() -> None:
    step = sys.argv[sys.argv.index("--step") + 1] if "--step" in sys.argv else "run"
    if step == "check":
        sys.exit(0 if check_step() else 1)
    text = generate()
    OUTPUT_PATH.write_text(text)
    instances = build_instances()
    print(
        f"wrote {OUTPUT_PATH} ({len(instances['buses'])} buses, {len(instances['generators'])} generators, "
        f"{len(instances['lines'])} lines, derived from {CASE_PATH.relative_to(REPO_ROOT)})"
    )


if __name__ == "__main__":
    main()
