# 0002 — Research: pandapower's own diagram options, and open-source symbolic/single-line-diagram packages

- **Status:** done — free-tier recommendations implemented via 0003/0004; the stretch tier
  (symbolic single-line) remains gated on a CIM/CGMES export step (see 0004).
- **Depends on:** 0001 (the gap this is scoping a fix for)
- **Feeds:** 0003 (Lab 3), 0004 (Lab 4 & 5), 0005 (the notebook playbook)

Two questions were asked: (a) what does `pandapower` itself already offer beyond the
`simple_plot()` everyone knows, and (b) outside pandapower, what open-source options exist for
*symbolic* representation — actual single-line-diagram notation (IEC 60617-style breaker/
transformer/generator symbols), not just a generic node-link graph — as libraries or as
CLI/API-driven apps.

## (a) pandapower's own advanced plotting options

Beyond `pandapower.plotting.simple_plot()` (matplotlib, static), pandapower ships:

- **`pandapower.plotting.plotly`** — `simple_plotly()` and `pf_res_plotly()`. Interactive
  (zoom/pan/hover), the latter colormaps line loading and bus voltage from actual power-flow
  results onto the network — this is the direct fit for Lab 2's contingency loadings and Lab 4's
  reconciliation, since it plots *results*, not just topology. Supports Mapbox-based geographic
  plotting if real coordinates are present.
- **Automatic layout when no geodata exists** — pandapower can generate artificial/generic bus
  coordinates for networks that don't carry real geographic data (both the CSIRO case files and
  Lab 5's SimBench-seeded chaos-net topologies are exactly this case), historically via an
  `igraph`- or `networkx`-based force layout. **Verify the exact current function name/signature
  against the installed pandapower version before relying on it** — this moved across pandapower
  2.x/3.x releases and this repo pins a specific version per `docs/VISION.md` §9's reproducibility
  argument, so check `uv run python -c "import pandapower.plotting as p; help(p)"` rather than
  trusting a version-specific tutorial.
- **Geodata transforms** — reprojecting network geodata to WGS84 (lat/long), useful only if real
  coordinates exist (they mostly don't for our synthetic/procedural cases).
- **HTML export** — `pandapower.plotting.to_html()`-family functions for a shareable static/
  interactive file, no server needed.

None of this requires a new dependency — `pandapower` is already a hard dependency of every lab.
This is the cheapest tier of remediation and should be exhausted before reaching for anything
external.

## (b) Open-source symbolic / single-line-diagram (SLD) options

"Symbolic" here means real electrical notation (breaker/transformer/generator glyphs per
IEC 60617 or ANSI convention), which is a materially different, harder problem than node-link
graph layout — none of pandapower/plotly/networkx draw actual switchgear symbols.

| Option | Type | Symbolic? | Language/packaging | Notes |
|---|---|---|---|---|
| **[powsybl-diagram](https://github.com/powsybl/powsybl-diagram)** | Library (+ REST via a server wrapper) | Yes — real single-line substation diagrams *and* network-area diagrams, SVG output, CSS-styleable | Java (LF Energy project); Python access via **[pypowsybl](https://pypi.org/project/pypowsybl/)**, which ships prebuilt wheels **on PyPI** (no JVM install needed — it bundles a native image) | The most complete open-source SLD renderer found. Bonus: PowSyBl natively imports CGMES/CIM network models — the same model family Lab 5's DPsim stack already speaks via CIM++ (see 0004). There's also a JS web-component viewer (`powsybl-diagram-viewer`) if an interactive HTML/dashboard route is wanted later. |
| **[GridCal](https://github.com/SanPen/GridCal)** | App + library + REST API | Partial — Qt schematic editor shows buses/branches as a wired diagram, drag-and-drop, not full IEC glyph fidelity | Pure Python, **on PyPI** (`pip install GridCal`) | Splits into `GridCalEngine` (library, scriptable), `GridCal` (desktop GUI), `GridCalServer` (REST API) — the "CLI/API-driven app" answer to the question. Could be scripted headlessly via `GridCalEngine` without the GUI. |
| **[Grid2Op PlotGrid](https://grid2op.readthedocs.io/en/latest/plot.html)** | Library | No — node-link with state-colored overlays (`PlotMatplot`, `PlotPlotly`), not symbolic | Python, PyPI | Built for RL-agent grid-state visualization, not SLD notation, but directly reusable for "here's the grid, here's what's loaded" the same way pandapower's plotly functions are. |
| **[power-system-shapes](https://github.com/nicorikken/power-system-shapes)** | Shape library, not a renderer | Yes — IEC 60617 shapes for draw.io/other editors | Static SVG/shape assets | Not programmatic from data — useful only for hand-drawn or manually-annotated diagrams, not an automated pipeline. Noted for completeness, not recommended for this repo's "committed script re-derives the result" convention. |
| **[SchemDraw](https://schemdraw.readthedocs.io/)** | Library | Yes, but circuit-schematic scale (R/L/C/sources), not grid/substation scale | Python, PyPI | Wrong grain size for a 1800-bus NEM case; could suit a small didactic inset (e.g., illustrating one bus's local topology) but not the whole network. |
| **PyPSA plotting** | Library | No — matplotlib/cartopy geographic network plots | Python, PyPI | Same tier as pandapower's own plotting; not a reason to add PyPSA as a new dependency when pandapower already does this. |
| **OpenDSS / OpenDSS-GIS** | App | Partial | Windows-native GUI (EPRI) | Commercial-adjacent tooling profile similar to the engines `docs/VISION.md` §12 already excludes from the golden path; not recommended. |
| **PowerPlots.jl** | Library | No — geographic/topological, matplotlib-equivalent for Julia | Julia | Wrong language for this repo (`uv`/Python throughout); noted only because it came up in research as the closest Julia analog. |

### Practical constraint: this sandbox's egress policy

`AGENTS.md` "Known sandbox network restrictions" already documents that **`github.com` itself
returns 403 here** (only `raw.githubusercontent.com` and `pypi.org` are reachable). That directly
rules out anything that requires `pip install git+https://github.com/...`, a Maven fetch, or an
npm install pointed at a GitHub-hosted registry. It does **not** rule out anything published as a
normal wheel on PyPI. Practical effect on the table above: `pypowsybl`, `GridCal`, `grid2op`,
`schemdraw`, and `pypsa` are all installable via plain `uv add` in this sandbox today;
`powsybl-diagram-viewer` (the JS component) and anything requiring a JVM/Maven build from source
are not, without revisiting that restriction first.

## Recommendation, in tiers

1. **Free tier (no new dependency):** `pandapower.plotting` (matplotlib + plotly variants) and
   `networkx.draw()` — already-installed libraries, already-loaded objects, zero new packaging
   risk. Covers node-link topology and results-overlay charts for Labs 1, 2, 4, and the topology
   half of Lab 5. See 0003, 0004.
2. **Stretch tier (one new PyPI dependency, no GUI/server):** `pypowsybl` for real symbolic
   single-line diagrams, scoped to Lab 5 only, and only if/when Lab 5 gains a CIM/CGMES export
   step (it doesn't yet — DPsim's CIM++ input is not the same as producing a CIM file *out*). See
   0004 for the concrete gating.
3. **Not recommended for this repo:** GridCal as a second simulation engine (pandapower already
   fills that role and `docs/VISION.md` §12 is explicit about not multiplying engines), any
   Windows-only or JVM/Maven-from-source tooling, and any manual/non-programmatic shape library —
   all conflict with either an existing non-goal or the "committed script re-derives the result"
   convention in `AGENTS.md`.

Sources consulted: pandapower's plotting docs
(`https://pandapower.readthedocs.io/en/latest/plotting.html` and the plotly built-in-plots page),
`https://github.com/powsybl/powsybl-diagram`, `https://pypi.org/project/pypowsybl/`,
`https://github.com/SanPen/GridCal` / `gridcal-wip.readthedocs.io`,
`https://grid2op.readthedocs.io/en/latest/plot.html`,
`https://github.com/nicorikken/power-system-shapes`, `https://schemdraw.readthedocs.io/`.
