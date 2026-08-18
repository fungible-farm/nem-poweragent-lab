"""Render an iso-IR JSON spec (see `translate_iso_ir.py`) to a deterministic isometric SVG.

This is the named stand-in for a real headless DaanV2/isometric-diagrams render -- see
`translate_iso_ir.py`'s module docstring for the real attempt (confirmed working via Playwright on
2026-08-18, not committed to this repo's pipeline: it needs a Node/Svelte toolchain and a
~290MB headless-Chromium download this Python-only repo doesn't otherwise have). This module
instead does the isometric-projection math directly -- no browser, no DOM, no external renderer --
which also trivially satisfies this MVP's own "re-run on unchanged input -> byte-identical SVG"
kill check: there is no font-shaping engine or animation frame to introduce variance, only fixed
arithmetic on the iso-IR JSON's own node positions.

Projection: standard 2:1 isometric tile math, `sx = (col - row) * TILE_W/2`,
`sy = (col + row) * TILE_H/2` (the same formula named in this lab's original sprint plan). Each
node renders as a 3-face isometric box (top/left/right parallelograms) at its grid position, colour
-coded by `type`, labelled underneath -- "straight boxes are enough" (Part/containment only, no
Port/Flow), matching this MVP's explicit scope cut.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Final, NamedTuple

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

# One fill colour per DaanV2 NodeType this translator actually assigns (translate_iso_ir.py's
# TYPE_BY_PART_TYPE) -- arbitrary but fixed, chosen for readable contrast against the dark
# background this lab's iso-IR specs request (settings.theme: dark, matching every other DaanV2
# example this lab's translator was checked against).
FILL_BY_TYPE: Final[dict[str, str]] = {
    "generic": "#6b7280",
    "server": "#2563eb",
    "database": "#059669",
    "router": "#d97706",
    "warehouse": "#7c3aed",
}
DEFAULT_FILL: Final[str] = "#6b7280"
BACKGROUND: Final[str] = "#0f172a"
EDGE_STROKE: Final[str] = "#94a3b8"
LABEL_FILL: Final[str] = "#e2e8f0"


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


def _poly(points: list[Point], fill: str, opacity: float = 1.0) -> str:
    pts = " ".join(f"{p.x:.1f},{p.y:.1f}" for p in points)
    return f'<polygon points="{pts}" fill="{fill}" fill-opacity="{opacity}" stroke="#0f172a" stroke-width="1"/>'


def render_svg(spec: dict[str, Any]) -> str:
    nodes = spec["nodes"]
    edges = spec.get("edges", [])
    centers: dict[str, Point] = {
        n["id"]: _tile_center(n["position"]["x"], n["position"]["y"]) for n in nodes
    }

    body: list[str] = []

    for edge in edges:
        a, b = centers[edge["from"]], centers[edge["to"]]
        body.append(
            f'<line x1="{a.x:.1f}" y1="{a.y:.1f}" x2="{b.x:.1f}" y2="{b.y:.1f}" '
            f'stroke="{EDGE_STROKE}" stroke-width="2" stroke-dasharray="4,3"/>'
        )

    all_points: list[Point] = []
    for node in nodes:
        pos = node["position"]
        center = _tile_center(pos["x"], pos["y"])
        fill = FILL_BY_TYPE.get(node["type"], DEFAULT_FILL)
        top_face, left_face, right_face = _box_faces(center)
        all_points += top_face + left_face + right_face

        body.append(f'<g data-node-id="{node["id"]}">')
        body.append(_poly(left_face, fill, opacity=0.7))
        body.append(_poly(right_face, fill, opacity=0.55))
        body.append(_poly(top_face, fill, opacity=1.0))
        label = node["label"]
        label_y = center.y + BOX_HEIGHT + TILE_H / 2 + FONT_SIZE
        body.append(
            f'<text x="{center.x:.1f}" y="{label_y:.1f}" font-family="monospace" '
            f'font-size="{FONT_SIZE:.0f}" fill="{LABEL_FILL}" text-anchor="middle">{label}</text>'
        )
        body.append("</g>")
        all_points.append(Point(center.x - len(label) * CHAR_WIDTH / 2, label_y))
        all_points.append(Point(center.x + len(label) * CHAR_WIDTH / 2, label_y))

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
        *body,
        "</svg>",
    ]
    return "\n".join(svg) + "\n"


TRACKS: Final[dict[str, dict[str, str]]] = {
    "digital-thread": {
        "iso_ir": "expected_digital_thread_iso_ir.json",
        "output": "digital_thread.svg",
        "expected": "expected_digital_thread.svg",
    },
    "grid": {
        "iso_ir": "expected_grid_topology_iso_ir.json",
        "output": "grid_topology.svg",
        "expected": "expected_grid_topology.svg",
    },
}


def generate(track: str) -> str:
    spec = json.loads((FIXTURES_DIR / TRACKS[track]["iso_ir"]).read_text())
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
