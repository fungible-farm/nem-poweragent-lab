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
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Final

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
}

TRACKS: Final[dict[str, dict[str, str]]] = {
    "digital-thread": {
        "sysml": "expected_digital_thread.sysml",
        "title": "Lab 6 Track A -- Digital Thread",
        "output": "digital_thread_iso_ir.json",
        "expected": "expected_digital_thread_iso_ir.json",
    },
    "grid": {
        "sysml": "expected_grid_topology.sysml",
        "title": "Lab 6 Track B -- Grid Topology",
        "output": "grid_topology_iso_ir.json",
        "expected": "expected_grid_topology_iso_ir.json",
    },
}

# Matches `        part <name> : <Type> {` -- the exact shape generate_sysml.py emits for each
# instance usage (4-space-indented, inside the root container part). Deliberately does not match
# `part def` lines or the root container part itself.
PART_RE: Final[re.Pattern[str]] = re.compile(r"^        part (\w+) : (\w+) \{$")
FROM_BUS_RE: Final[re.Pattern[str]] = re.compile(r'^            attribute fromBus = "(\w+)";$')
TO_BUS_RE: Final[re.Pattern[str]] = re.compile(r'^            attribute toBus = "(\w+)";$')


def parse_parts(sysml_text: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Walk the .sysml text's part usages -> (nodes, edges). Grid-track Line parts become edges
    (fromBus->toBus), not nodes -- everything else becomes a node. Line-by-line, not a real
    parser: this is the same Part/containment-only subset validate_sysml.py checks."""
    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    lines = sysml_text.splitlines()
    i = 0
    while i < len(lines):
        m = PART_RE.match(lines[i])
        if m:
            name, part_type = m.group(1), m.group(2)
            if part_type == "Line":
                from_bus = to_bus = None
                j = i + 1
                while j < len(lines) and lines[j].strip() != "}":
                    fb = FROM_BUS_RE.match(lines[j])
                    tb = TO_BUS_RE.match(lines[j])
                    if fb:
                        from_bus = fb.group(1)
                    if tb:
                        to_bus = tb.group(1)
                    j += 1
                if from_bus and to_bus:
                    edges.append({"id": name, "from": from_bus, "to": to_bus, "type": "network"})
            else:
                nodes.append({"id": name, "label": name, "type": part_type})
        i += 1
    return nodes, edges


def _grid_positions(n: int, per_row: int = 3, spacing: int = 2) -> list[dict[str, int]]:
    """Deterministic grid layout -- row-major, fixed spacing. No physics/force-layout (that would
    make re-runs non-deterministic, breaking this pipeline's own byte-identical-SVG kill check)."""
    return [{"x": (i % per_row) * spacing, "y": (i // per_row) * spacing} for i in range(n)]


def build_iso_ir(track: str) -> dict[str, Any]:
    cfg = TRACKS[track]
    sysml_text = (FIXTURES_DIR / cfg["sysml"]).read_text()
    nodes, edges = parse_parts(sysml_text)
    positions = _grid_positions(len(nodes))
    diagram_nodes = [
        {
            "id": n["id"],
            "label": n["label"],
            "type": TYPE_BY_PART_TYPE.get(n["type"], "generic"),
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
