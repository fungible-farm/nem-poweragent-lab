"""Render an iso-IR JSON spec (see `translate_iso_ir.py`) to a deterministic isometric SVG.

This module does the isometric-projection math directly -- no browser, no DOM, no external
renderer -- which trivially satisfies this MVP's own "re-run on unchanged input -> byte-identical
SVG" kill check: there is no font-shaping engine or animation frame to introduce variance, only
fixed arithmetic on the iso-IR JSON's own node positions.

Projection: standard 2:1 isometric tile math, `sx = (col - row) * TILE_W/2`,
`sy = (col + row) * TILE_H/2` (the same formula named in this lab's original sprint plan).

Shape dispatch, per node's `shape` field (`translate_iso_ir.py`'s `SHAPE_BY_TYPE`) -- Track B reads
as an actual single-line-diagram (bus/branch), not undifferentiated boxes: a `bar` (a flat isometric
plate, no side walls -- the standard SLD convention for a bus bar) for grid `Bus` parts, a `circle`
(a "G"-labelled isometric ellipse) for `Generator` parts, and the original 3-face isometric `box`
for everything else (Track A's Agent/MCPServer/DataSource have no bus/branch concept, so they keep
the box). Edges render *after* nodes (on top, not underneath -- the earlier ordering made two of
Track B's four real branches nearly invisible) with real visual differentiation: `transmission`
branches are a solid, bright, thick line; `transformer` branches are the same but amber with a
double-circle winding glyph at its third-points (the classic transformer symbol); `attachment` edges
(a generator's real link to its own bus -- previously not drawn *at all*, a genuine gap fixed here,
not just a style change) are a thin, dotted, muted stub.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Final, NamedTuple

import translate_iso_ir

LAB_DIR: Final[Path] = Path(__file__).resolve().parent
OUTPUT_DIR: Final[Path] = LAB_DIR / "output"
FIXTURES_DIR: Final[Path] = LAB_DIR / "fixtures"

# Isometric tile dimensions in SVG user units. 2:1 width:height is the standard isometric-art
# ratio (a tile viewed from a ~30-degree elevation projects to a diamond twice as wide as tall).
TILE_W: Final[float] = 120.0
TILE_H: Final[float] = 60.0
# Vertical wall height of each rendered box -- gives the top face a visible "raised" 3D look
# rather than a flat diamond. Chosen to be less than TILE_H so boxes at adjacent grid cells don't
# visually overlap at this lab's node spacing (translate_iso_ir.py's _grid_positions spacing=2).
BOX_HEIGHT: Final[float] = 40.0
PADDING: Final[float] = 60.0
# Fixed-width label-sizing assumption (SVG user units per character at FONT_SIZE) -- avoids
# depending on any font-shaping engine for the bounding-box computation, which is what keeps
# re-runs on unchanged input byte-identical (no font/platform-dependent text metrics involved).
FONT_SIZE: Final[float] = 13.0
CHAR_WIDTH: Final[float] = FONT_SIZE * 0.6
# Generator "circle" shape's isometric ellipse radii -- squashed to the tile's own 2:1 ratio so it
# reads as a disc lying flat on the same projected plane as everything else, not a true circle.
GEN_RX: Final[float] = TILE_W * 0.28
GEN_RY: Final[float] = TILE_H * 0.28
# Radius of the small "winding" circles drawn at a transformer branch's third-points -- the
# classic two-circle transformer symbol, small enough to read as a glyph on the line, not a node.
XFMR_GLYPH_R: Final[float] = 4.0
# Vertical bow height (SVG user units) for a branch edge whose two endpoints share a row but have
# another node's position strictly between them -- see `_edge_skips_node`'s docstring for why this
# is needed: `translate_iso_ir.py`'s Cassowary bus-row layout only gives each bus two array-
# adjacent neighbours' worth of straight-line room, but a real hub bus can have more real branches
# than that (Track B's bus_4128 has four). Without this, such a branch draws as a straight line
# directly on top of the buses/branches between its two ends, hiding them.
BOW_HEIGHT: Final[float] = TILE_H

# One fill colour per node type this translator actually assigns (translate_iso_ir.py's
# TYPE_BY_PART_TYPE) -- arbitrary but fixed, chosen for readable contrast against this lab's dark
# SVG background.
FILL_BY_TYPE: Final[dict[str, str]] = {
    "generic": "#6b7280",
    "server": "#2563eb",
    "database": "#059669",
    "router": "#d97706",
    "warehouse": "#7c3aed",
}
DEFAULT_FILL: Final[str] = "#6b7280"
BACKGROUND: Final[str] = "#0f172a"
LABEL_FILL: Final[str] = "#e2e8f0"

# Per-edge-kind stroke styling. Bright, high-contrast, and drawn *after* nodes (see render_svg) so
# real branches are never hidden behind a box -- the earlier single muted dashed style made two of
# Track B's four real branches nearly invisible against its own node fills.
TRANSMISSION_STROKE: Final[str] = "#38bdf8"
TRANSFORMER_STROKE: Final[str] = "#f59e0b"
ATTACHMENT_STROKE: Final[str] = "#a78bfa"
# Track C's `Phase.next` edges are a real *directed* relationship (unlike attachment/branch, which
# read as undirected ownership/topology links) -- a distinct colour plus an arrowhead at the `to`
# end is what actually shows that direction, not just a differently-coloured undirected line.
SEQUENCE_STROKE: Final[str] = "#34d399"
SEQUENCE_ARROW_LEN: Final[float] = 10.0
SEQUENCE_ARROW_WIDTH: Final[float] = 6.0


class Point(NamedTuple):
    x: float
    y: float


def _tile_center(col: float, row: float) -> Point:
    return Point((col - row) * TILE_W / 2, (col + row) * TILE_H / 2)


def _box_faces(center: Point) -> tuple[list[Point], list[Point], list[Point]]:
    """Top/left/right face vertices for an isometric box centered (at its top face) on `center`."""
    top_apex = Point(center.x, center.y - TILE_H / 2)
    right_apex = Point(center.x + TILE_W / 2, center.y)
    bottom_apex = Point(center.x, center.y + TILE_H / 2)
    left_apex = Point(center.x - TILE_W / 2, center.y)

    def down(p: Point, h: float = BOX_HEIGHT) -> Point:
        return Point(p.x, p.y + h)

    top_face = [top_apex, right_apex, bottom_apex, left_apex]
    left_face = [left_apex, bottom_apex, down(bottom_apex), down(left_apex)]
    right_face = [right_apex, bottom_apex, down(bottom_apex), down(right_apex)]
    return top_face, left_face, right_face


def _bar_face(center: Point) -> list[Point]:
    """A flat isometric diamond -- the full top face, no side walls -- standing in for a real
    single-line-diagram bus bar: a bus is a connection *plane*, not a physical volume."""
    return [
        Point(center.x, center.y - TILE_H / 2),
        Point(center.x + TILE_W / 2, center.y),
        Point(center.x, center.y + TILE_H / 2),
        Point(center.x - TILE_W / 2, center.y),
    ]


def _poly(points: list[Point], fill: str, opacity: float = 1.0, stroke: str = "#0f172a", stroke_width: float = 1.0) -> str:
    pts = " ".join(f"{p.x:.1f},{p.y:.1f}" for p in points)
    return f'<polygon points="{pts}" fill="{fill}" fill-opacity="{opacity}" stroke="{stroke}" stroke-width="{stroke_width:g}"/>'


def _edge_skips_node(edge: dict[str, Any], positions_by_id: dict[str, dict[str, float]]) -> bool:
    """True when a branch edge's two endpoints sit on the same grid row and some other node's
    position lies strictly between their x -- i.e. a straight line between them would run
    directly over that in-between node (and anything connecting to it). Grid-space, not pixel
    space: row/col equality here is the layout's own real adjacency, unaffected by the isometric
    projection's skew."""
    a, b = positions_by_id.get(edge["from"]), positions_by_id.get(edge["to"])
    if a is None or b is None or a["y"] != b["y"]:
        return False
    lo, hi = sorted((a["x"], b["x"]))
    return any(
        nid not in (edge["from"], edge["to"]) and pos["y"] == a["y"] and lo < pos["x"] < hi
        for nid, pos in positions_by_id.items()
    )


def _quad_point(p0: Point, ctrl: Point, p1: Point, t: float) -> Point:
    """Point at parameter `t` along the quadratic Bezier (p0, ctrl, p1) -- used to place a bowed
    transformer edge's winding glyphs at its real third-points, matching the straight-line case."""
    x = (1 - t) ** 2 * p0.x + 2 * (1 - t) * t * ctrl.x + t**2 * p1.x
    y = (1 - t) ** 2 * p0.y + 2 * (1 - t) * t * ctrl.y + t**2 * p1.y
    return Point(x, y)


def _edge_style(edge: dict[str, Any]) -> tuple[str, str]:
    """(stroke colour, extra SVG attrs) for one edge, by its `type`/`kind`."""
    if edge.get("type") == "attachment":
        return ATTACHMENT_STROKE, 'stroke-width="1.5" stroke-dasharray="1,3" stroke-linecap="round"'
    if edge.get("type") == "sequence":
        return SEQUENCE_STROKE, 'stroke-width="3" stroke-linecap="round"'
    if edge.get("kind") == "transformer":
        return TRANSFORMER_STROKE, 'stroke-width="3"'
    return TRANSMISSION_STROKE, 'stroke-width="3"'


def _arrowhead(tip: Point, tail_direction: Point, fill: str) -> str:
    """A small filled triangle at `tip`, pointing along the direction from `tail_direction` to
    `tip` -- Track C's `sequence` edges are the first genuinely *directed* relationship this
    renderer draws (attachment/branch are undirected ownership/topology links), so a plain
    differently-coloured line isn't enough to show which way a phase actually flows into the
    next."""
    dx, dy = tip.x - tail_direction.x, tip.y - tail_direction.y
    length = (dx**2 + dy**2) ** 0.5
    if length == 0:
        return ""
    ux, uy = dx / length, dy / length
    # perpendicular unit vector, for the arrowhead's base width
    px, py = -uy, ux
    base = Point(tip.x - ux * SEQUENCE_ARROW_LEN, tip.y - uy * SEQUENCE_ARROW_LEN)
    left = Point(base.x + px * SEQUENCE_ARROW_WIDTH / 2, base.y + py * SEQUENCE_ARROW_WIDTH / 2)
    right = Point(base.x - px * SEQUENCE_ARROW_WIDTH / 2, base.y - py * SEQUENCE_ARROW_WIDTH / 2)
    pts = " ".join(f"{p.x:.1f},{p.y:.1f}" for p in (tip, left, right))
    return f'<polygon points="{pts}" fill="{fill}"/>'


def render_svg(spec: dict[str, Any]) -> str:
    nodes = spec["nodes"]
    edges = spec.get("edges", [])
    centers: dict[str, Point] = {
        n["id"]: _tile_center(n["position"]["x"], n["position"]["y"]) for n in nodes
    }

    node_body: list[str] = []
    all_points: list[Point] = []

    for node in nodes:
        pos = node["position"]
        center = _tile_center(pos["x"], pos["y"])
        fill = FILL_BY_TYPE.get(node["type"], DEFAULT_FILL)
        shape = node.get("shape", "box")
        label = node["label"]

        node_body.append(f'<g data-node-id="{node["id"]}">')
        if shape == "bar":
            bar = _bar_face(center)
            all_points += bar
            node_body.append(_poly(bar, fill, opacity=1.0, stroke=LABEL_FILL, stroke_width=1.5))
            label_y = center.y + TILE_H / 2 + FONT_SIZE
        elif shape == "circle":
            node_body.append(
                f'<ellipse cx="{center.x:.1f}" cy="{center.y:.1f}" rx="{GEN_RX:.1f}" ry="{GEN_RY:.1f}" '
                f'fill="{fill}" stroke="{LABEL_FILL}" stroke-width="1.5"/>'
            )
            node_body.append(
                f'<text x="{center.x:.1f}" y="{center.y + FONT_SIZE * 0.35:.1f}" font-family="monospace" '
                f'font-weight="bold" font-size="{FONT_SIZE:.0f}" fill="{LABEL_FILL}" text-anchor="middle">G</text>'
            )
            all_points += [
                Point(center.x - GEN_RX, center.y - GEN_RY),
                Point(center.x + GEN_RX, center.y + GEN_RY),
            ]
            label_y = center.y + GEN_RY + FONT_SIZE
        else:
            top_face, left_face, right_face = _box_faces(center)
            all_points += top_face + left_face + right_face
            node_body.append(_poly(left_face, fill, opacity=0.7))
            node_body.append(_poly(right_face, fill, opacity=0.55))
            node_body.append(_poly(top_face, fill, opacity=1.0))
            label_y = center.y + BOX_HEIGHT + TILE_H / 2 + FONT_SIZE

        node_body.append(
            f'<text x="{center.x:.1f}" y="{label_y:.1f}" font-family="monospace" '
            f'font-size="{FONT_SIZE:.0f}" fill="{LABEL_FILL}" text-anchor="middle">{label}</text>'
        )
        node_body.append("</g>")
        all_points.append(Point(center.x - len(label) * CHAR_WIDTH / 2, label_y))
        all_points.append(Point(center.x + len(label) * CHAR_WIDTH / 2, label_y))

    # Edges render *after* nodes -- on top, never hidden behind a box/bar/circle.
    positions_by_id = {n["id"]: n["position"] for n in nodes}
    edge_body: list[str] = []
    for edge in edges:
        a, b = centers[edge["from"]], centers[edge["to"]]
        stroke, extra_attrs = _edge_style(edge)
        if _edge_skips_node(edge, positions_by_id):
            ctrl = Point((a.x + b.x) / 2, (a.y + b.y) / 2 - BOW_HEIGHT)
            all_points.append(ctrl)
            edge_body.append(
                f'<path d="M {a.x:.1f} {a.y:.1f} Q {ctrl.x:.1f} {ctrl.y:.1f} {b.x:.1f} {b.y:.1f}" '
                f'fill="none" stroke="{stroke}" {extra_attrs}/>'
            )
            glyph_points = [_quad_point(a, ctrl, b, frac) for frac in (1 / 3, 2 / 3)]
        else:
            edge_body.append(f'<line x1="{a.x:.1f}" y1="{a.y:.1f}" x2="{b.x:.1f}" y2="{b.y:.1f}" stroke="{stroke}" {extra_attrs}/>')
            glyph_points = [Point(a.x + (b.x - a.x) * frac, a.y + (b.y - a.y) * frac) for frac in (1 / 3, 2 / 3)]
        if edge.get("kind") == "transformer":
            for gp in glyph_points:
                edge_body.append(f'<circle cx="{gp.x:.1f}" cy="{gp.y:.1f}" r="{XFMR_GLYPH_R:.1f}" fill="{BACKGROUND}" stroke="{stroke}" stroke-width="2"/>')
        if edge.get("type") == "sequence":
            edge_body.append(_arrowhead(b, a, stroke))

    min_x = min(p.x for p in all_points) - PADDING
    max_x = max(p.x for p in all_points) + PADDING
    min_y = min(p.y for p in all_points) - PADDING
    max_y = max(p.y for p in all_points) + PADDING
    width = max_x - min_x
    height = max_y - min_y

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{min_x:.1f} {min_y:.1f} {width:.1f} {height:.1f}" '
        f'width="{width:.0f}" height="{height:.0f}">',
        f'<rect x="{min_x:.1f}" y="{min_y:.1f}" width="{width:.1f}" height="{height:.1f}" fill="{BACKGROUND}"/>',
        f'<title>{spec["title"]}</title>',
        *node_body,
        *edge_body,
        "</svg>",
    ]
    return "\n".join(svg) + "\n"


TRACKS: Final[dict[str, dict[str, str]]] = {
    "digital-thread": {
        "output": "digital_thread.svg",
        "expected": "expected_digital_thread.svg",
    },
    "grid": {
        "output": "grid_topology.svg",
        "expected": "expected_grid_topology.svg",
    },
    "pipeline": {
        "output": "pipeline_phases.svg",
        "expected": "expected_pipeline_phases.svg",
    },
}


def generate(track: str) -> str:
    """Chains directly off `translate_iso_ir.build_iso_ir(track)` (an in-process call, not a file
    read) -- see that module's own `build_iso_ir` docstring for why: reading
    `fixtures/expected_*_iso_ir.json` here (an earlier version of this file did) would freeze the
    rendered SVG to a stale committed snapshot even if the real schema/instance data changed."""
    spec = translate_iso_ir.build_iso_ir(track)
    return render_svg(spec)


def check_step(track: str) -> bool:
    fresh = generate(track)
    expected_path = FIXTURES_DIR / TRACKS[track]["expected"]
    if not expected_path.exists():
        print(f"FAIL: {expected_path} does not exist")
        return False
    expected = expected_path.read_text()
    if fresh == expected:
        print(f"MATCH: rendered SVG for track '{track}' vs {expected_path.name}")
        return True
    print(f"FAIL: rendered SVG for track '{track}' differs from {expected_path.name}")
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--track", choices=sorted(TRACKS), required=True)
    parser.add_argument("--step", choices=["run", "check"], default="run")
    args = parser.parse_args()

    if args.step == "check":
        sys.exit(0 if check_step(args.track) else 1)

    svg = generate(args.track)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / TRACKS[args.track]["output"]
    out_path.write_text(svg)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
