"""Walk the generated `.sysml` text's `part` usages (Part/containment only, matching this MVP's
scope) into an isometric-diagram intermediate representation (iso-IR) JSON -- deliberately shaped
to match the real `DaanV2/isometric-diagrams` (MIT-licensed) project's own `DiagramSpec` schema
(`title`/`type`/`nodes[].{id,label,type,position:{x,y}}`), confirmed by reading that project's
`src/lib/types/diagram.ts` directly and by driving its real app headlessly (Playwright, via a
`npx playwright install chromium` + `nvm use 22` container of its own devDependency) to render this
lab's actual Track A instance data on 2026-08-18 -- confirmed real, correct, 7/7 nodes rendered
with correct labels and type icons via its `#d=<base64url-yaml>` permalink mechanism.

That real render is NOT wired into this lab's own pipeline: it needs Node >=20.19/22.13 (this
repo's toolchain is Python/uv-only; the working host `nvm` versions were a session-local finding,
not something this repo can assume) plus a ~290MB headless-Chromium download, and its own SVG
export (`src/lib/export.ts`) is DOM-dependent (`getComputedStyle`, `XMLSerializer` inside a live
browser page) -- there is no pure-function/server-side render path in that project, confirmed by
reading its source. Vendoring a second-language (Node/Svelte) app plus a browser automation
toolchain into this Python power-systems repo is real, disproportionate infrastructure for this
MVP -- a genuine finding worth revisiting as a dedicated follow-up phase, not a same-sprint
integration. `render_diagram.py` instead renders this module's iso-IR JSON with a small, pure,
deterministic, in-repo isometric SVG writer -- see that module's own docstring.

Because the iso-IR JSON's field names match DaanV2's real `DiagramSpec` 1:1, dumping it to YAML and
opening `https://<a running instance of DaanV2/isometric-diagrams>#d=<base64url(that yaml)>` is a
real, working way to view this lab's data in the real tool by hand, right now -- proven, not just
plausible.

Two Lab-6-specific extensions beyond DaanV2's own DiagramSpec (extra JSON fields/values, inert to
DaanV2 itself if the same file were opened there): edges carry an optional `kind` field
(`transmission`/`transformer`, read from each Line part's own `kind` attribute) so the renderer can
draw the two real branch types differently, and Generator parts now also emit an `attachment` edge
back to their own `bus` attribute -- Track B's generators previously had no visual link to the bus
they're actually connected to, an omission fixed here, not just a rendering-order issue.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import deque
from pathlib import Path
from typing import Any, Final

import kiwisolver as kiwi

import generate_sysml

LAB_DIR: Final[Path] = Path(__file__).resolve().parent
OUTPUT_DIR: Final[Path] = LAB_DIR / "output"
FIXTURES_DIR: Final[Path] = LAB_DIR / "fixtures"

# DaanV2 DiagramSpec's real NodeType enum (src/lib/types/diagram.ts) -- only the ones this
# translator actually assigns are listed with their mapping rationale below.
TYPE_BY_PART_TYPE: Final[dict[str, str]] = {
    "Agent": "generic",
    "MCPServer": "server",
    "DataSource": "database",
    "Bus": "router",  # a real grid connection point -- "router" is the closest real DaanV2 node icon
    "Generator": "warehouse",  # a real generating unit -- "warehouse" reads as a large physical asset
    "Line": "generic",  # rendered as an edge below, not a node -- see PART_RE handling
    "Phase": "generic",  # a real pipeline stage -- no closer real DaanV2 icon exists, kept honest
}

# render_diagram.py's shape dispatch, keyed by DaanV2 NodeType string above (not the SysML part
# type) -- a Lab-6-specific rendering hint, not part of DaanV2's own DiagramSpec vocabulary. Buses
# render as a flat bar (a real single-line-diagram bus bar convention), generators as a circle
# ("G" glyph), everything else as the original isometric box.
SHAPE_BY_TYPE: Final[dict[str, str]] = {
    "router": "bar",
    "warehouse": "circle",
}
DEFAULT_SHAPE: Final[str] = "box"

TRACKS: Final[dict[str, dict[str, str]]] = {
    "digital-thread": {
        "title": "Lab 6 Track A -- Digital Thread",
        "output": "digital_thread_iso_ir.json",
        "expected": "expected_digital_thread_iso_ir.json",
    },
    "grid": {
        "title": "Lab 6 Track B -- Grid Topology",
        "output": "grid_topology_iso_ir.json",
        "expected": "expected_grid_topology_iso_ir.json",
    },
    "pipeline": {
        "title": "Lab 6 Track C -- Pipeline Phases",
        "output": "pipeline_phases_iso_ir.json",
        "expected": "expected_pipeline_phases_iso_ir.json",
    },
}

# Matches `        part <name> : <Type> {` -- the exact shape generate_sysml.py emits for each
# instance usage (4-space-indented, inside the root container part). Deliberately does not match
# `part def` lines or the root container part itself.
PART_RE: Final[re.Pattern[str]] = re.compile(r"^        part (\w+) : (\w+) \{$")
FROM_BUS_RE: Final[re.Pattern[str]] = re.compile(r'^            attribute fromBus = "(\w+)";$')
TO_BUS_RE: Final[re.Pattern[str]] = re.compile(r'^            attribute toBus = "(\w+)";$')
KIND_RE: Final[re.Pattern[str]] = re.compile(r'^            attribute kind = "(\w+)";$')

# Attributes whose value is another part's real name, not free-text data -- each one becomes an
# edge from this part to the part it names (Generator.bus -> the real bus it's wired to; Agent.uses
# -> the real MCPServer/DataSource its own script actually calls; Phase.next -> the real next stage
# in a pipeline). Matching either generically (not per-part-type) is what let Track A gain edges
# with zero new edge-emission code once `uses` existed -- the same mechanism Track B's `bus`
# attribute already used. The edge *type* still varies by attribute (`EDGE_TYPE_BY_REFERENCE_ATTR`
# below): `bus`/`uses` are undirected ownership-style links (`attachment`), but `next` is a real
# directed, ordered relationship (`sequence`) -- collapsing them into one edge type would lose the
# distinction the Cassowary layout needs to pick the right algorithm (see `_iso_positions`).
REFERENCE_ATTR_RE: Final[dict[str, re.Pattern[str]]] = {
    "bus": re.compile(r'^            attribute bus = "(\w+)";$'),
    "uses": re.compile(r'^            attribute uses = "(\w+)";$'),
    "next": re.compile(r'^            attribute next = "(\w+)";$'),
}
EDGE_TYPE_BY_REFERENCE_ATTR: Final[dict[str, str]] = {
    "bus": "attachment",
    "uses": "attachment",
    "next": "sequence",
}


def parse_parts(sysml_text: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Walk the .sysml text's part usages -> (nodes, edges). Grid-track Line parts become
    `branch` edges (fromBus->toBus, carrying `kind`), not nodes; any part with a real
    part-reference attribute (`REFERENCE_ATTR_RE` -- Generator.bus, Agent.uses) gets a matching
    `attachment` edge back to the part it names -- everything else becomes a plain node. Line-by-
    line, not a real parser: this is the same Part/containment-only subset validate_sysml.py
    checks."""
    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    lines = sysml_text.splitlines()
    i = 0
    while i < len(lines):
        m = PART_RE.match(lines[i])
        if m:
            name, part_type = m.group(1), m.group(2)
            attrs: dict[str, str] = {}
            j = i + 1
            while j < len(lines) and lines[j].strip() != "}":
                fb = FROM_BUS_RE.match(lines[j])
                tb = TO_BUS_RE.match(lines[j])
                kind_m = KIND_RE.match(lines[j])
                if fb:
                    attrs["from_bus"] = fb.group(1)
                if tb:
                    attrs["to_bus"] = tb.group(1)
                if kind_m:
                    attrs["kind"] = kind_m.group(1)
                for attr_name, attr_re in REFERENCE_ATTR_RE.items():
                    ref_m = attr_re.match(lines[j])
                    if ref_m:
                        attrs[attr_name] = ref_m.group(1)
                j += 1
            if part_type == "Line":
                if "from_bus" in attrs and "to_bus" in attrs:
                    edges.append(
                        {
                            "id": name,
                            "from": attrs["from_bus"],
                            "to": attrs["to_bus"],
                            "type": "branch",
                            "kind": attrs.get("kind", "transmission"),
                        }
                    )
            else:
                nodes.append({"id": name, "label": name, "type": part_type})
                for attr_name in REFERENCE_ATTR_RE:
                    if attr_name in attrs:
                        edge_type = EDGE_TYPE_BY_REFERENCE_ATTR[attr_name]
                        # `_attach` preserved for the original attachment-edge id shape (Track A/B's
                        # committed fixtures already depend on it); other edge types get their own
                        # attribute-named suffix instead of inheriting that name.
                        suffix = "attach" if edge_type == "attachment" else attr_name
                        edges.append(
                            {
                                "id": f"{name}_{suffix}",
                                "from": name,
                                "to": attrs[attr_name],
                                "type": edge_type,
                            }
                        )
        i += 1
    return nodes, edges


def _grid_positions(n: int, per_row: int = 3, spacing: int = 2) -> list[dict[str, int]]:
    """Deterministic grid layout -- row-major, fixed spacing. Used for Track A (no attachment
    topology to lay out around -- see `_iso_positions` below for the track that has one)."""
    return [{"x": (i % per_row) * spacing, "y": (i // per_row) * spacing} for i in range(n)]


ROW_SPACING: Final[float] = 2.0
BUS_GAP: Final[float] = 2.0


def _anchor_forest(anchor_ids: list[str], adjacency: dict[str, set[str]]) -> tuple[dict[str, int], dict[str, str], list[str]]:
    """BFS forest over the real anchor-to-anchor `branch` graph -- one tree per connected
    component, each rooted at that component's own highest-real-degree anchor (tie-broken by id
    for determinism, not an arbitrary pick). An anchor with zero branch edges (Track A's
    MCPServer/DataSource nodes -- there is no Line-equivalent connecting them to each other) is
    simply its own one-node component/root; this is what lets the same forest logic lay out both
    Track B's single-hub network and Track A's disconnected component/data-source set without a
    type-specific special case. Returns each anchor's depth (its row), parent (its sibling-group
    at the next depth), and the list of component roots. Same discipline as
    `build_grid_instances.py`'s own BFS selection walk: real graph structure decides the shape,
    not array order."""
    depth: dict[str, int] = {}
    parent: dict[str, str] = {}
    roots: list[str] = []
    remaining = set(anchor_ids)
    while remaining:
        root = min(remaining, key=lambda b: (-len(adjacency[b] & remaining), b))
        roots.append(root)
        depth[root] = 0
        remaining.discard(root)
        queue: deque[str] = deque([root])
        while queue:
            current = queue.popleft()
            for neighbour in sorted(adjacency[current]):
                if neighbour in remaining:
                    depth[neighbour] = depth[current] + 1
                    parent[neighbour] = current
                    remaining.discard(neighbour)
                    queue.append(neighbour)
    return depth, parent, roots


def _level_x_positions(
    anchor_ids: list[str], depth: dict[str, int], parent: dict[str, str], roots: list[str]
) -> dict[str, float]:
    """Solve each depth level's x positions with `kiwisolver`, one level at a time (each level's
    solve only needs the previous level's already-solved positions as fixed inputs, so a single
    global solve isn't needed). Depth 0 is the component roots themselves, treated as one sibling
    group with no parent (ordered by id, first pinned to 0.0) -- this is what spreads Track A's
    several disconnected anchors (no real edges between MCPServer/DataSource instances) apart from
    each other instead of collapsing them onto the same point. From depth 1 on, within one
    parent's sibling group: REQUIRED gaps of at least `BUS_GAP` keep them from overlapping, and a
    REQUIRED centroid-equals-parent constraint (`sum(children) == n * parent_x`, real linear
    arithmetic, not a hand-picked offset formula) centers the whole group symmetrically under its
    parent -- confirmed by hand: a 4-child hub at x=0 with gap=2 solves to exactly [-3, -1, 1, 3].
    Sibling *groups* at the same depth (cousin subtrees under different parents, or different
    components' roots) are also kept `BUS_GAP` apart, ordered left-to-right by their own parent's
    already-solved x, so unrelated branches never overlap either."""
    x_by_anchor: dict[str, float] = {}
    if not anchor_ids:
        return x_by_anchor

    ordered_roots = sorted(roots)
    root_solver = kiwi.Solver()
    root_vars = {r: kiwi.Variable(r) for r in ordered_roots}
    for left, right in zip(ordered_roots, ordered_roots[1:]):
        root_solver.addConstraint((root_vars[left] + BUS_GAP <= root_vars[right]) | kiwi.strength.required)
    if ordered_roots:
        root_solver.addConstraint((root_vars[ordered_roots[0]] == 0.0) | kiwi.strength.weak)
    root_solver.updateVariables()
    for r in ordered_roots:
        x_by_anchor[r] = round(root_vars[r].value() + 0.0, 6)

    max_depth = max(depth.values())
    for d in range(1, max_depth + 1):
        level = [b for b in anchor_ids if depth.get(b) == d]
        if not level:
            continue
        groups: dict[str, list[str]] = {}
        for b in level:
            groups.setdefault(parent[b], []).append(b)
        ordered_parents = sorted(groups, key=lambda p: x_by_anchor[p])

        solver = kiwi.Solver()
        x_vars: dict[str, kiwi.Variable] = {}
        previous_group_last: kiwi.Variable | None = None
        for p in ordered_parents:
            siblings = groups[p]
            for b in siblings:
                x_vars[b] = kiwi.Variable(b)
            for left, right in zip(siblings, siblings[1:]):
                solver.addConstraint((x_vars[left] + BUS_GAP <= x_vars[right]) | kiwi.strength.required)
            total = x_vars[siblings[0]]
            for b in siblings[1:]:
                total = total + x_vars[b]
            solver.addConstraint((total == len(siblings) * x_by_anchor[p]) | kiwi.strength.required)
            if previous_group_last is not None:
                solver.addConstraint(
                    (previous_group_last + BUS_GAP <= x_vars[siblings[0]]) | kiwi.strength.required
                )
            previous_group_last = x_vars[siblings[-1]]
        solver.updateVariables()
        for b, var in x_vars.items():
            x_by_anchor[b] = round(var.value() + 0.0, 6)  # `+ 0.0` normalises a possible -0.0
    return x_by_anchor


def _cassowary_positions(
    nodes: list[dict[str, str]], edges: list[dict[str, str]]
) -> list[dict[str, float]]:
    """Cassowary constraint layout via `kiwisolver` -- the same constraint-solving algorithm
    (linear-arithmetic, incremental simplex), and the same Variable/Constraint/Strength
    primitives, as the Rust `kasuari` crate (`kasuari::{Solver, Variable, Strength,
    WeightedRelation}`) used by the `ledgrrr` codebase's own diagram-layout solver
    (`ledger-core/src/visualize.rs::layout::LayoutSolver`) -- consulted directly as the reference
    pattern this mirrors: REQUIRED constraints for non-negotiable ordering/spacing, weighted
    (WEAK/STRONG) constraints for preferences that yield rather than break a REQUIRED one.

    Deterministic, not physics/force-directed: Cassowary's simplex solve returns the same values
    for the same constraint set on every run (confirmed: repeated runs against Track B's real
    five-bus cluster produced bit-identical output), so this keeps the pipeline's byte-identical
    re-run kill check true -- a force-directed/spring layout would not.

    Nodes split into two structural roles, by real edge shape rather than by SysML part type
    (`type == "Bus"` was an earlier, narrower version of this check that only worked for Track B):
    an **anchor** is any node that is not the `from` side of an `attachment` edge; a **leaf** is
    one that is. Anchors are laid out by their real `branch`-edge graph (`_anchor_forest`,
    `_level_x_positions`): each anchor's row is its BFS depth from its own component's real hub,
    and each depth level's x positions fan out symmetrically under their real parent. A first
    version of this laid every Bus on one shared row regardless of topology, which meant Track B's
    real hub (`bus_4128`, four real branches) got squashed onto a straight line with its two
    non-adjacent branches forced to bow over the others just to stay visible; rooting the layout in
    the real branch graph instead means a hub's branches actually radiate in different directions.
    Track A has no `branch` edges at all (no Line-equivalent between Agent/MCPServer/DataSource),
    so every one of its anchors is its own single-node component -- handled by the same forest
    logic with no special case, spread apart by the depth-0 root-separation rule.

    Every leaf is STRONGLY pulled to sit at the same x as the anchor its own `attachment` edge
    points to, one row below whatever row that anchor landed on -- Generator.bus and Agent.uses
    both resolve through this one mechanism (`REFERENCE_ATTR_RE`), so an attached node visually
    sits under whatever it's really wired to, for either track, with no per-type code.
    """
    attach_target = {e["from"]: e["to"] for e in edges if e["type"] == "attachment"}
    leaf_ids = set(attach_target)
    anchor_ids = [n["id"] for n in nodes if n["id"] not in leaf_ids]

    adjacency: dict[str, set[str]] = {a: set() for a in anchor_ids}
    for e in edges:
        if e.get("type") == "branch" and e["from"] in adjacency and e["to"] in adjacency:
            adjacency[e["from"]].add(e["to"])
            adjacency[e["to"]].add(e["from"])

    depth, parent, roots = _anchor_forest(anchor_ids, adjacency)
    x_by_anchor = _level_x_positions(anchor_ids, depth, parent, roots)

    # Leaves that share one anchor (e.g. two Agents both `uses`-ing the same DataSource) need the
    # same sibling-group spreading anchors get -- a single STRONG "== anchor x" pull for every leaf
    # under the same target would collapse them all onto one identical point. Grouped and centered
    # with the exact same REQUIRED-gap + centroid-equals-parent technique as `_level_x_positions`.
    leaf_order = [n["id"] for n in nodes if n["id"] in leaf_ids]
    groups: dict[str, list[str]] = {}
    unattached: list[str] = []
    for leaf in leaf_order:
        target = attach_target.get(leaf)
        (groups.setdefault(target, []) if target in x_by_anchor else unattached).append(leaf)

    solver = kiwi.Solver()
    x_vars: dict[str, kiwi.Variable] = {}
    for target, siblings in groups.items():
        for leaf in siblings:
            x_vars[leaf] = kiwi.Variable(leaf)
        for left, right in zip(siblings, siblings[1:]):
            solver.addConstraint((x_vars[left] + BUS_GAP <= x_vars[right]) | kiwi.strength.required)
        total = x_vars[siblings[0]]
        for leaf in siblings[1:]:
            total = total + x_vars[leaf]
        solver.addConstraint((total == len(siblings) * x_by_anchor[target]) | kiwi.strength.required)
    for leaf in unattached:
        x_vars[leaf] = kiwi.Variable(leaf)
        solver.addConstraint((x_vars[leaf] == 0.0) | kiwi.strength.weak)
    solver.updateVariables()

    positions: dict[str, dict[str, float]] = {
        a: {"x": x_by_anchor[a], "y": depth[a] * ROW_SPACING} for a in anchor_ids
    }
    for n in nodes:
        if n["id"] not in leaf_ids:
            continue
        target = attach_target.get(n["id"])
        row = (depth.get(target, -1) + 1) * ROW_SPACING if target in depth else ROW_SPACING
        positions[n["id"]] = {"x": round(x_vars[n["id"]].value() + 0.0, 6), "y": row}

    return [positions[n["id"]] for n in nodes]


def _sequence_positions(
    nodes: list[dict[str, str]], edges: list[dict[str, str]]
) -> list[dict[str, float]]:
    """Cassowary layout for a real *ordered* chain (Track C's `Phase.next`) -- this is the direct
    port of the actual reference pattern this whole design was pointed at
    (`ledger-core/src/visualize.rs::layout::LayoutSolver::generate_layout`): REQUIRED consecutive
    `x_i + gap <= x_(i+1)` constraints walking the schema's own declared order, plus a WEAK STAY
    pinning the first element -- the same primitives `_cassowary_positions` uses, applied to a
    single ordered row instead of a hub/star.

    Deliberately a separate function from `_cassowary_positions`, not a variant of it: a `sequence`
    edge encodes a real declared order (this phase's real next step), not an undirected graph
    relationship the way Track B's `branch` edges are -- rooting a chain at its highest-*degree*
    node (what `_anchor_forest` does) would ignore that order and center the diagram on whichever
    interior phase happens to have two neighbours, misrepresenting a real "step 1 then 2 then 3"
    sequence as an undirected star. A pipeline's real meaning is its order, so its layout is solved
    directly from that order.
    """
    next_of = {e["from"]: e["to"] for e in edges if e["type"] == "sequence"}
    has_incoming = set(next_of.values())
    starts = [n["id"] for n in nodes if n["id"] not in has_incoming]
    order: list[str] = []
    seen: set[str] = set()
    for start in sorted(starts):
        current: str | None = start
        while current is not None and current not in seen:
            order.append(current)
            seen.add(current)
            current = next_of.get(current)
    # Any node untouched by a `sequence` edge at all (shouldn't happen for a real, fully-chained
    # pipeline, but kept honest rather than silently dropping a node) is appended last, sorted for
    # determinism.
    order += sorted(n["id"] for n in nodes if n["id"] not in seen)

    solver = kiwi.Solver()
    x_vars = {node_id: kiwi.Variable(node_id) for node_id in order}
    for left, right in zip(order, order[1:]):
        solver.addConstraint((x_vars[left] + BUS_GAP <= x_vars[right]) | kiwi.strength.required)
    if order:
        solver.addConstraint((x_vars[order[0]] == 0.0) | kiwi.strength.weak)
    solver.updateVariables()

    positions = {
        node_id: {"x": round(var.value() + 0.0, 6), "y": 0.0} for node_id, var in x_vars.items()
    }
    return [positions[n["id"]] for n in nodes]


def _iso_positions(
    nodes: list[dict[str, str]], edges: list[dict[str, str]]
) -> list[dict[str, float]]:
    """Three layout modes, by real edge shape: a `sequence` edge (Track C's `Phase.next`) means a
    real declared order, laid out by `_sequence_positions`; any other edges (Track A/B's
    `attachment`/`branch`) mean an undirected hub/star graph, laid out by `_cassowary_positions`;
    no edges at all (see `_grid_positions`'s own docstring) keeps the plain row-major grid."""
    if any(e.get("type") == "sequence" for e in edges):
        return _sequence_positions(nodes, edges)
    if edges:
        return _cassowary_positions(nodes, edges)
    return _grid_positions(len(nodes))


def build_iso_ir(track: str) -> dict[str, Any]:
    """Chains directly off `generate_sysml.generate(track)` (an in-process function call, not a
    file read) -- so editing schema/*_instances.yaml and re-running this script always reflects
    the current schema, never a stale committed `.sysml` fixture. This is what makes the "edit one
    schema, watch it propagate" demo actually true past the first pipeline stage; reading
    `fixtures/expected_*.sysml` here (an earlier version of this file did) would silently freeze
    every downstream artifact to whatever `.sysml` text happened to be committed."""
    cfg = TRACKS[track]
    sysml_text = generate_sysml.generate(track)
    nodes, edges = parse_parts(sysml_text)
    positions = _iso_positions(nodes, edges)
    diagram_nodes = [
        {
            "id": n["id"],
            "label": n["label"],
            "type": (node_type := TYPE_BY_PART_TYPE.get(n["type"], "generic")),
            "shape": SHAPE_BY_TYPE.get(node_type, DEFAULT_SHAPE),
            "position": pos,
        }
        for n, pos in zip(nodes, positions)
    ]
    spec: dict[str, Any] = {
        "title": cfg["title"],
        "type": "generic",
        "nodes": diagram_nodes,
    }
    if edges:
        spec["edges"] = edges
    return spec


def check_step(track: str) -> bool:
    fresh = build_iso_ir(track)
    expected_path = FIXTURES_DIR / TRACKS[track]["expected"]
    if not expected_path.exists():
        print(f"FAIL: {expected_path} does not exist")
        return False
    expected = json.loads(expected_path.read_text())
    if fresh == expected:
        print(f"MATCH: iso-IR for track '{track}' vs {expected_path.name}")
        return True
    print(f"FAIL: iso-IR for track '{track}' differs from {expected_path.name}")
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--track", choices=sorted(TRACKS), required=True)
    parser.add_argument("--step", choices=["run", "check"], default="run")
    args = parser.parse_args()

    if args.step == "check":
        sys.exit(0 if check_step(args.track) else 1)

    spec = build_iso_ir(args.track)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / TRACKS[args.track]["output"]
    out_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out_path} ({len(spec['nodes'])} nodes, {len(spec.get('edges', []))} edges)")


if __name__ == "__main__":
    main()
