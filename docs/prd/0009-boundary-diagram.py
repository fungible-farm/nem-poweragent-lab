"""Render the PRD-0009 project-ownership boundary/Venn diagram to a deterministic SVG.

Answers the "second wave" open question in `0009-cim-gridy-incose-v-plan.md`: what each of
cim-gridy, `ledgrrr`, the two independently-diverged `ufo-types` implementations, `b00t`,
Open-MBEE, and the SysML parser crates *is* and *is not*, and how they relate. Ground truth for
every boundary and relationship drawn here is the PRD's own "MECE capability-ownership table"
(Wave 1, 2026-08-22) -- nothing here is invented; each shape/edge is traceable to a specific row
of that table, cited in this module's own constants below.

Hand-built SVG via plain string templates, no third-party graphing library -- this repo has no
`svgwrite`/`graphviz` dependency in `pyproject.toml`, and `labs/06-sysml-digital-thread/
render_diagram.py` already establishes the local convention: a deterministic generator script
committed alongside its output, so diffs across regenerations stay meaningful (fixed-point
coordinate formatting, insertion-ordered dict/list iteration, no wall-clock/random input). This
diagram is a different shape from Lab 6's isometric network renders (circles/ellipses for set
membership, arrows for cross-project integration, a hatched lens for the one genuine unresolved
overlap) so it does not reuse Lab 6's isometric projection math, only its "generator + committed
SVG" discipline.

Visual grammar (see `LEGEND_ITEMS` below, rendered on-canvas so the SVG is self-explaining):
  - Solid circle border  = resolved/owned boundary, High confidence in the MECE table.
  - Dashed circle border = still Open -- no owner decided, or reconciliation not yet done.
  - Solid arrow           = real code dependency (a Cargo/git dependency).
  - Dashed blue arrow     = MCP-datum integration (registered, not a Cargo dependency).
  - Dashed amber arrow    = an Open/undecided relationship (future candidate, not yet real).
  - Dashed grey arrow     = evaluated and NOT adopted.
  - Muted/grey fill       = evaluated, not adopted.
  - Hatched lens          = a genuine unresolved overlap between two circles (the two `ufo-types`
    implementations occupying the same conceptual space, independently diverged, no sync
    mechanism since PR #145 -- MECE table row "Reconciling the two `ufo-types` implementations").
  - No arrow at all between two circles is itself a claim: e.g. cim-gridy <-> b00t have none,
    which is the point -- b00t is "NOT a Cargo dependency of anything here" (per the PRD).

Edge endpoints are computed automatically (`_boundary_point_toward`) as the point on each
circle's own boundary facing the other circle's center, rather than hand-picked angles -- keeps
the diagram robust to re-tuning `CIRCLES`' positions without every edge needing re-aiming by hand.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Final, Literal, NamedTuple, TypedDict

DIAGRAM_DIR: Final[Path] = Path(__file__).resolve().parent
OUTPUT_SVG: Final[Path] = DIAGRAM_DIR / "0009-boundary-diagram.svg"

# Canvas + typography constants, fixed (not measured from any font-shaping engine) so re-runs on
# unchanged input are byte-identical -- same discipline as Lab 6's render_diagram.py CHAR_WIDTH.
CANVAS_W: Final[float] = 1600.0
CANVAS_H: Final[float] = 1250.0
FONT_FAMILY: Final[str] = "monospace"
TITLE_SIZE: Final[float] = 20.0
SUBTITLE_SIZE: Final[float] = 12.0
LABEL_SIZE: Final[float] = 15.0
SUBLABEL_SIZE: Final[float] = 11.0
EDGE_LABEL_SIZE: Final[float] = 10.5
LEGEND_SIZE: Final[float] = 11.5

BACKGROUND: Final[str] = "#0f172a"
TEXT_PRIMARY: Final[str] = "#e2e8f0"
TEXT_MUTED: Final[str] = "#94a3b8"

# One fill per project circle -- arbitrary but fixed, chosen for contrast against BACKGROUND and
# for enough separation between adjacent circles that overlaps (deliberate ones) stay legible.
FILL_CIM_GRIDY: Final[str] = "#1d4ed8"
FILL_LEDGRRR: Final[str] = "#7c3aed"
FILL_UFO_STANDALONE: Final[str] = "#059669"
FILL_UFO_VENDORED: Final[str] = "#a78bfa"
FILL_B00T: Final[str] = "#d97706"
FILL_OPEN_MBEE: Final[str] = "#0891b2"
FILL_SYSML_PARSER: Final[str] = "#2563eb"
FILL_SYSTER_BASE: Final[str] = "#475569"  # muted grey: evaluated, not adopted
FILL_OPEN_CLIF: Final[str] = "#374151"  # muted, dashed: genuinely unowned

STROKE_RESOLVED: Final[str] = "#e2e8f0"
STROKE_OPEN: Final[str] = "#f59e0b"
DASH_OPEN: Final[str] = "8,6"
DASH_EDGE: Final[str] = "5,5"

EDGE_STROKE_CARGO: Final[str] = TEXT_PRIMARY
EDGE_STROKE_MCP: Final[str] = "#38bdf8"
EDGE_STROKE_OPEN: Final[str] = STROKE_OPEN
EDGE_STROKE_EVALUATED: Final[str] = TEXT_MUTED

ARROW_LEN: Final[float] = 12.0
ARROW_WIDTH: Final[float] = 8.0


class Pt(NamedTuple):
    x: float
    y: float


class Circle(TypedDict):
    """One project boundary. `resolved=False` renders a dashed, Open-styled border."""

    id: str
    center: Pt
    r: float
    fill: str
    label: str
    sublabel: str
    resolved: bool
    label_dy: float  # offset from center for the main label, so nested/overlapping circles
    # don't collide with their own text


# Layout, left to right / top to bottom:
#   Row 1 (y=300): cim-gridy (anchor, this repo) -- ufo-types standalone -- ufo-types vendored
#     (mostly nested inside ledgrrr, poking out just far enough to lens-overlap standalone) --
#     ledgrrr. The standalone/vendored overlap is the one deliberate Venn lens on this diagram --
#     MECE table row "Reconciling the two `ufo-types` implementations" (Open, not a drop-in dedup,
#     incompatible enum shapes, no sync mechanism since PR #145).
#   Top-right, clear of the title band: the CLIF/ISO-24707 parser -- Open, nobody owns it yet.
#   Row 2 (y=620-800): sysml-v2-parser + syster-base nest/sit near cim-gridy (SysML tooling
#     Lab 8 0b spiked); b00t and Open-MBEE sit apart from both cim-gridy and ledgrrr's boundaries
#     -- deliberately touching neither, since b00t is "NOT a Cargo dependency of anything here"
#     (integration is MCP-datum registration only, drawn as dashed blue arrows below).
CIRCLES: Final[list[Circle]] = [
    {
        "id": "cim-gridy",
        "center": Pt(340, 330),
        "r": 200,
        "fill": FILL_CIM_GRIDY,
        "label": "cim-gridy",
        "sublabel": "Bevy/Rust mission-engine (Labs 8-9)\nrhai mission FSM, Grid2Op bridge",
        "resolved": True,
        "label_dy": -140,
    },
    {
        "id": "ufo-standalone",
        "center": Pt(840, 330),
        "r": 100,
        "fill": FILL_UFO_STANDALONE,
        "label": "ufo-types (standalone)",
        "sublabel": "promptexecution/ufo-types\nUfoStereotype (1 enum) + dare.rs\npinned git dep, Phase 3 optimizer",
        "resolved": True,
        "label_dy": -134,
    },
    {
        "id": "ufo-vendored",
        "center": Pt(1000, 330),
        "r": 80,
        "fill": FILL_UFO_VENDORED,
        "label": "ufo-types (vendored)",
        "sublabel": "ledgrrr's crates/ufo-types\n4-enum split, no dare.rs",
        "resolved": True,
        "label_dy": 100,
    },
    {
        "id": "ledgrrr",
        "center": Pt(1150, 330),
        "r": 200,
        "fill": FILL_LEDGRRR,
        "label": "ledgrrr",
        "sublabel": "CLIF/FOL/regulatory ontology layer\narc-kit-au::EvidenceGraph, ledgerr-mcp,\nholon-viz, Z3 (vendored, separate repo)",
        "resolved": True,
        "label_dy": -140,
    },
    {
        "id": "clif-fol",
        "center": Pt(1460, 200),
        "r": 75,
        "fill": FILL_OPEN_CLIF,
        "label": "CLIF / ISO-24707 parser",
        "sublabel": "Open -- confirmed absent\neverywhere (fresh grep)",
        "resolved": False,
        "label_dy": -95,
    },
    {
        "id": "sysml-v2-parser",
        "center": Pt(560, 680),
        "r": 65,
        "fill": FILL_SYSML_PARSER,
        "label": "sysml-v2-parser",
        "sublabel": "external upstream,\nconsumed directly",
        "resolved": True,
        "label_dy": -85,
    },
    {
        "id": "syster-base",
        "center": Pt(130, 900),
        "r": 58,
        "fill": FILL_SYSTER_BASE,
        "label": "syster-base",
        "sublabel": "kept in reserve\n(Lab 8 0b spike)",
        "resolved": True,
        "label_dy": -72,
    },
    {
        "id": "b00t",
        "center": Pt(800, 800),
        "r": 100,
        "fill": FILL_B00T,
        "label": "b00t",
        "sublabel": "hive CLI / orchestration /\ndatum registry -- NOT a\nCargo dep of anything here",
        "resolved": True,
        "label_dy": -68,
    },
    {
        "id": "open-mbee",
        "center": Pt(1160, 800),
        "r": 90,
        "fill": FILL_OPEN_MBEE,
        "label": "Open-MBEE / Flexo MMS",
        "sublabel": "flexo-mms-layer1-mcp,\nflexo-mms-sysmlv2-mcp\n(RDF/SPARQL, Jena Fuseki)",
        "resolved": True,
        "label_dy": -105,
    },
]


class Edge(TypedDict):
    src: str
    dst: str
    kind: Literal["cargo", "mcp", "open", "evaluated"]
    label: str
    label_side: float  # +1/-1: which perpendicular side of the line to place the label on
    t: float  # 0..1 position along the line for the label anchor -- 0.5 is the midpoint;
    # nudged off-center on some edges so the label doesn't land on the destination circle's
    # own label text
    offset: float  # perpendicular distance (px) from the line to the label -- default 14,
    # widened on edges that would otherwise land on a nearby circle's own label


# Every edge here traces to a specific MECE table row (cited per edge below); nothing is a guess.
# Absence of an edge is also a claim -- e.g. no edge connects cim-gridy directly to b00t or
# open-mbee: both integrate through b00t's MCP-datum registry (the b00t->ledgrrr / b00t->open-mbee
# edges below), never a Cargo dependency.
EDGES: Final[list[Edge]] = [
    {
        "src": "cim-gridy",
        "dst": "ufo-standalone",
        "kind": "cargo",
        "label": "Cargo git dep (dare.rs, Phase 3 optimizer)",
        "label_side": -1,
        "t": 0.5,
        "offset": 14.0,
    },
    {
        "src": "cim-gridy",
        "dst": "sysml-v2-parser",
        "kind": "cargo",
        "label": "consumed directly",
        "label_side": 1,
        "t": 0.5,
        "offset": 14.0,
    },
    {
        "src": "cim-gridy",
        "dst": "syster-base",
        "kind": "evaluated",
        "label": "evaluated, not adopted",
        "label_side": -1,
        "t": 0.4,
        "offset": 14.0,
    },
    {
        "src": "b00t",
        "dst": "ledgrrr",
        "kind": "mcp",
        "label": "MCP-datum: ledgerr-mcp (registered, not Cargo)",
        "label_side": -1,
        "t": 0.5,
        "offset": 14.0,
    },
    {
        "src": "b00t",
        "dst": "open-mbee",
        "kind": "mcp",
        "label": "MCP-datum: flexo-mms-*-mcp.mcp.toml",
        "label_side": -1,
        "t": 0.5,
        "offset": 14.0,
    },
    {
        "src": "ledgrrr",
        "dst": "clif-fol",
        "kind": "open",
        "label": "recommended future owner (ledgrrr#182, #114)",
        "label_side": 1,
        "t": 0.45,
        "offset": 14.0,
    },
]

EDGE_STROKE_BY_KIND: Final[dict[str, str]] = {
    "cargo": EDGE_STROKE_CARGO,
    "mcp": EDGE_STROKE_MCP,
    "open": EDGE_STROKE_OPEN,
    "evaluated": EDGE_STROKE_EVALUATED,
}

LEGEND_ITEMS: Final[list[tuple[str, str]]] = [
    ("solid border", "resolved/owned boundary, High confidence (MECE table)"),
    ("dashed border", "still Open -- no owner decided / not reconciled"),
    ("solid arrow", "real code dependency (Cargo/git)"),
    ("dashed blue arrow", "MCP-datum integration -- registered, not a Cargo dependency"),
    ("dashed amber arrow", "Open / undecided relationship, not yet real"),
    ("dashed grey arrow", "evaluated and NOT adopted"),
    ("grey fill", "evaluated, not adopted"),
    ("hatched lens", "genuine unresolved overlap (diverged, no sync since PR #145)"),
    ("no arrow at all", "a claim too -- e.g. cim-gridy / b00t: no direct integration exists"),
]


def _circle_by_id(cid: str) -> Circle:
    for c in CIRCLES:
        if c["id"] == cid:
            return c
    raise KeyError(cid)


def _boundary_point_toward(c: Circle, target: Pt) -> Pt:
    """Point on circle `c`'s own boundary, facing `target` -- used for both circle-overlap
    geometry checks (none needed at render time) and as an edge's endpoint, so arrows always
    start/end exactly on the rim regardless of how `CIRCLES` gets re-tuned."""
    dx, dy = target.x - c["center"].x, target.y - c["center"].y
    dist = math.hypot(dx, dy)
    if dist == 0:
        return c["center"]
    ux, uy = dx / dist, dy / dist
    return Pt(c["center"].x + ux * c["r"], c["center"].y + uy * c["r"])


def _multiline_text(x: float, y: float, text: str, size: float, fill: str, weight: str = "normal", anchor: str = "middle") -> str:
    lines = text.split("\n")
    parts = [
        f'<text x="{x:.1f}" y="{(y + i * size * 1.25):.1f}" font-family="{FONT_FAMILY}" '
        f'font-size="{size:.1f}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{line}</text>'
        for i, line in enumerate(lines)
    ]
    return "\n".join(parts)


def _arrowhead(tip: Pt, from_pt: Pt, fill: str) -> str:
    dx, dy = tip.x - from_pt.x, tip.y - from_pt.y
    length = math.hypot(dx, dy)
    if length == 0:
        return ""
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    base = Pt(tip.x - ux * ARROW_LEN, tip.y - uy * ARROW_LEN)
    left = Pt(base.x + px * ARROW_WIDTH / 2, base.y + py * ARROW_WIDTH / 2)
    right = Pt(base.x - px * ARROW_WIDTH / 2, base.y - py * ARROW_WIDTH / 2)
    pts = " ".join(f"{p.x:.1f},{p.y:.1f}" for p in (tip, left, right))
    return f'<polygon points="{pts}" fill="{fill}"/>'


def _render_hatch_defs() -> str:
    """A diagonal-hatch pattern for the one deliberate Venn overlap (the two `ufo-types`
    implementations) -- flags it visually as "genuinely contested/unresolved space", distinct
    from every other circle's flat fill."""
    return (
        '<defs>\n'
        '<pattern id="open-hatch" width="10" height="10" patternTransform="rotate(45)" '
        'patternUnits="userSpaceOnUse">\n'
        f'<rect width="10" height="10" fill="{STROKE_OPEN}" fill-opacity="0.18"/>\n'
        f'<line x1="0" y1="0" x2="0" y2="10" stroke="{STROKE_OPEN}" stroke-width="3"/>\n'
        '</pattern>\n'
        '</defs>'
    )


def _render_circle(c: Circle) -> str:
    stroke = STROKE_RESOLVED if c["resolved"] else STROKE_OPEN
    dash_attr = "" if c["resolved"] else f' stroke-dasharray="{DASH_OPEN}"'
    fill_opacity = 0.55 if c["resolved"] else 0.30
    body = [
        f'<g data-circle-id="{c["id"]}">',
        f'<circle cx="{c["center"].x:.1f}" cy="{c["center"].y:.1f}" r="{c["r"]:.1f}" '
        f'fill="{c["fill"]}" fill-opacity="{fill_opacity}" stroke="{stroke}" '
        f'stroke-width="2.5"{dash_attr}/>',
    ]
    label_y = c["center"].y + c["label_dy"]
    body.append(_multiline_text(c["center"].x, label_y, c["label"], LABEL_SIZE, TEXT_PRIMARY, weight="bold"))
    sub_y = label_y + LABEL_SIZE * 1.5
    body.append(_multiline_text(c["center"].x, sub_y, c["sublabel"], SUBLABEL_SIZE, TEXT_MUTED))
    body.append("</g>")
    return "\n".join(body)


def _render_overlap_lens() -> str:
    """The standalone/vendored `ufo-types` overlap, hatched, with its own Open annotation --
    MECE table: "Reconciling the two `ufo-types` implementations" -> Open, incompatible enum
    shapes, no sync mechanism since PR #145 dropped the one real attempt. Clipped to the exact
    circle-circle intersection, not a hand-fit shape."""
    a = _circle_by_id("ufo-standalone")
    b = _circle_by_id("ufo-vendored")
    clip = (
        f'<clipPath id="ufo-overlap-clip">'
        f'<circle cx="{a["center"].x:.1f}" cy="{a["center"].y:.1f}" r="{a["r"]:.1f}"/>'
        f'</clipPath>'
    )
    lens = (
        f'<circle cx="{b["center"].x:.1f}" cy="{b["center"].y:.1f}" r="{b["r"]:.1f}" '
        f'fill="url(#open-hatch)" clip-path="url(#ufo-overlap-clip)" '
        f'stroke="{STROKE_OPEN}" stroke-width="2" stroke-dasharray="{DASH_OPEN}"/>'
    )
    mid_x = (a["center"].x + b["center"].x) / 2
    label_y = max(a["center"].y + a["r"], b["center"].y + b["r"]) + 70
    label = _multiline_text(
        mid_x, label_y,
        "Open: reconciling the two ufo-types\nimplementations (no sync since PR #145)",
        SUBLABEL_SIZE, STROKE_OPEN, weight="bold",
    )
    return f'{clip}\n{lens}\n{label}'


def _render_edge(e: Edge) -> str:
    src_c, dst_c = _circle_by_id(e["src"]), _circle_by_id(e["dst"])
    p0 = _boundary_point_toward(src_c, dst_c["center"])
    p1 = _boundary_point_toward(dst_c, src_c["center"])
    stroke = EDGE_STROKE_BY_KIND[e["kind"]]
    dash = "" if e["kind"] == "cargo" else f' stroke-dasharray="{DASH_EDGE}"'
    line = f'<line x1="{p0.x:.1f}" y1="{p0.y:.1f}" x2="{p1.x:.1f}" y2="{p1.y:.1f}" stroke="{stroke}" stroke-width="2"{dash}/>'
    head = _arrowhead(p1, p0, stroke)
    # Label anchor at parameter `t` along the line (not always the midpoint -- some edges nudge
    # `t` toward the source so the label doesn't land on the destination circle's own label).
    anchor = Pt(p0.x + (p1.x - p0.x) * e["t"], p0.y + (p1.y - p0.y) * e["t"])
    # Offset the label perpendicular to the line so it doesn't sit directly on the stroke.
    dx, dy = p1.x - p0.x, p1.y - p0.y
    length = math.hypot(dx, dy) or 1.0
    perp = Pt(-dy / length, dx / length)
    offset = e["offset"] * e["label_side"]
    label_pt = Pt(anchor.x + perp.x * offset, anchor.y + perp.y * offset)
    label = _multiline_text(label_pt.x, label_pt.y, e["label"], EDGE_LABEL_SIZE, stroke)
    return f'{line}\n{head}\n{label}'


def _render_legend() -> str:
    x0, y0 = 40.0, CANVAS_H - 190.0
    row_h = 17.0
    lines = ['<g data-legend="true">']
    box_h = len(LEGEND_ITEMS) * row_h + 30
    lines.append(
        f'<rect x="{x0 - 12:.1f}" y="{y0 - 22:.1f}" width="620" height="{box_h:.1f}" '
        f'fill="{BACKGROUND}" fill-opacity="0.9" stroke="{TEXT_MUTED}" stroke-width="1"/>'
    )
    lines.append(
        f'<text x="{x0:.1f}" y="{y0 - 4:.1f}" font-family="{FONT_FAMILY}" font-size="{LABEL_SIZE:.1f}" '
        f'font-weight="bold" fill="{TEXT_PRIMARY}" text-anchor="start">Legend</text>'
    )
    for i, (token, meaning) in enumerate(LEGEND_ITEMS):
        y = y0 + i * row_h + 12
        lines.append(
            f'<text x="{x0:.1f}" y="{y:.1f}" font-family="{FONT_FAMILY}" font-size="{LEGEND_SIZE:.1f}" '
            f'fill="{TEXT_PRIMARY}" text-anchor="start">{token}</text>'
        )
        lines.append(
            f'<text x="{x0 + 190:.1f}" y="{y:.1f}" font-family="{FONT_FAMILY}" font-size="{LEGEND_SIZE:.1f}" '
            f'fill="{TEXT_MUTED}" text-anchor="start">{meaning}</text>'
        )
    lines.append("</g>")
    return "\n".join(lines)


def render_svg() -> str:
    """Build the full boundary/Venn diagram SVG. Pure function of the module-level CIRCLES/EDGES/
    LEGEND_ITEMS constants -- no filesystem/network/clock input, so re-running with unchanged
    source produces a byte-identical file (the same "diffable regeneration" discipline as Lab 6's
    render_diagram.py)."""
    body: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CANVAS_W:.0f} {CANVAS_H:.0f}" '
        f'width="{CANVAS_W:.0f}" height="{CANVAS_H:.0f}">',
        f'<rect x="0" y="0" width="{CANVAS_W:.0f}" height="{CANVAS_H:.0f}" fill="{BACKGROUND}"/>',
        "<title>PRD-0009 project-ownership boundary diagram</title>",
        _render_hatch_defs(),
        f'<text x="{CANVAS_W / 2:.1f}" y="36" font-family="{FONT_FAMILY}" font-size="{TITLE_SIZE:.1f}" '
        f'font-weight="bold" fill="{TEXT_PRIMARY}" text-anchor="middle">'
        "PRD-0009: project ownership boundaries</text>",
        f'<text x="{CANVAS_W / 2:.1f}" y="58" font-family="{FONT_FAMILY}" font-size="{SUBTITLE_SIZE:.1f}" '
        f'fill="{TEXT_MUTED}" text-anchor="middle">'
        "cim-gridy / ledgrrr / ufo-types (x2) / b00t / Open-MBEE / SysML crates -- "
        "grounded in the MECE capability-ownership table, Wave 1, 2026-08-22</text>",
        f'<text x="{CANVAS_W / 2:.1f}" y="76" font-family="{FONT_FAMILY}" font-size="{SUBTITLE_SIZE - 1:.1f}" '
        f'fill="{TEXT_MUTED}" text-anchor="middle">'
        "Note: mission_fsm.rs (rhai FSM, currently cim-gridy's own) is a Phase 2.5 candidate "
        "migration to ledgrrr's future CLIF layer once built -- not drawn as an edge here, to "
        "avoid crossing every circle in between.</text>",
    ]

    # Circles first (fills), overlap lens on top of the two ufo-types circles, then edges, then
    # legend last -- same "draw order = z-order, edges never hidden" discipline as Lab 6.
    for c in CIRCLES:
        body.append(_render_circle(c))
    body.append(_render_overlap_lens())
    for e in EDGES:
        body.append(_render_edge(e))
    body.append(_render_legend())

    body.append("</svg>")
    return "\n".join(body) + "\n"


def check_step() -> bool:
    """Regeneration check: fresh render must byte-match the committed SVG. Mirrors Lab 6's own
    `--step check` convention, adapted for this non-lab doc diagram (no `fixtures/expected_*`
    directory here -- the single committed output file *is* the expected artifact)."""
    fresh = render_svg()
    if not OUTPUT_SVG.exists():
        print(f"FAIL: {OUTPUT_SVG} does not exist")
        return False
    committed = OUTPUT_SVG.read_text()
    if fresh == committed:
        print(f"MATCH: rendered SVG matches committed {OUTPUT_SVG.name}")
        return True
    print(f"FAIL: rendered SVG differs from committed {OUTPUT_SVG.name} -- re-run without --step check and commit the diff")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", choices=["run", "check"], default="run")
    args = parser.parse_args()

    if args.step == "check":
        sys.exit(0 if check_step() else 1)

    svg = render_svg()
    OUTPUT_SVG.write_text(svg)
    print(f"wrote {OUTPUT_SVG}")


if __name__ == "__main__":
    main()
