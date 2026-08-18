# Lab 6 — SysML v2 Digital-Thread MVP

> Status: **implemented** (both tracks). Full scope, decisions, and the tool-evaluation findings
> below live in [`docs/prd/0006-sysml-digital-thread-mvp.md`](../../docs/prd/0006-sysml-digital-thread-mvp.md).
> This README is the lab-local summary and build notes.

*New to MBSE, SysML, or digital threads? See [Concepts for this lab](#concepts-for-this-lab) below.*

## What you'll do

This lab is a tooling **evaluation**, not just a demo: does SysML v2 (a systems-modelling language)
help for two different jobs — modelling an AI agent/MCP/data workflow, and modelling a piece of grid
network topology? One schema, edited by hand, flows through one pipeline to three regenerated
artifacts — text, a diagram, and (for one of the two tracks) a software bill of materials — with no
manual step in between:

```
LinkML instance data  -->  .sysml text  -->  syntax check  -->  isometric diagram (SVG)
                                                              -->  SBOM (Track A only)
```

Two tracks share the exact same generator/validator/renderer code, selected with `--track`:

- **Track A — digital thread**: this repo's own real `Agent`/`MCPServer`/`DataSource` inventory —
  Lab 1's bisection search, Lab 3's provider bake-off, the `powermcp-pandapower` pod, the CSIRO/AEMO/
  SimBench data sources every other lab already reads.
- **Track B — grid topology**: a small real `Bus`/`Generator`/`Line` cluster pulled directly from
  `data/snemSA.m` (the same CSIRO case Lab 1 loads) — proving or disproving the same pipeline on an
  actual power-systems model, not just software components.

## Why this matters

Every other lab in this repo models grid physics. This one asks a different question: can a formal
systems-modelling notation (SysML v2) usefully describe *this repo itself* — its agents, its data
flows, its infrastructure — and does that same notation also hold up for describing a piece of the
grid it studies? The answer for both, and *why*, is the point of this sprint.

## Concepts for this lab

- **MBSE (Model-Based Systems Engineering)** — instead of describing a system in prose documents,
  you build a formal model of its parts and how they relate, and derive diagrams/reports/checks from
  that one model rather than keeping them in sync by hand.
- **SysML v2** — the current (from 2025) version of a systems-modelling language, built on a
  smaller foundational language called KerML. This lab uses only its most basic building block: a
  `part def` (a *type* of thing, like a class) and a `part` (one *instance* of that type, like an
  object) nested inside a containing part — no ports, no signal-flow connections, no behavior
  diagrams. "Straight boxes are enough" for this MVP.
- **Digital thread** — a live, traceable link from a system's real components (code, data, infra)
  through to its model and documentation, so the model doesn't silently drift out of date. Track A's
  point: every entry traces to a real file already in this repo (see
  `schema/digital_thread_instances.yaml`'s `source` fields).
- **LinkML** (linkml.io) — a schema definition language (itself YAML) for describing structured
  data classes and validating instance data against them. Used here as the input schema this lab's
  `.sysml` text is *generated from* — LinkML is explicitly provisional (see the PRD's open
  questions), not treated as a permanent dependency.
- **Isometric diagram** — a 2D drawing that mimics a 3D angled view using flat-color polygons (no
  real 3D engine), the classic "SimCity"-style projection. Nodes here render as 3-face boxes at a
  fixed grid position, colour-coded by type.
- **CycloneDX / SBOM** — a standard JSON format for a software bill of materials: what components
  make up a system, and their provenance. Used here (Track A only) to show the digital-thread model
  can also emit a real, standard downstream artifact, not just a diagram.

## Design notes

Most of this pipeline is straightforward generated code; the two places this sprint deliberately
went and tried the **real** external tool first are the interesting part — this write-up **is** the
knowledge this sprint set out to buy.

### 1. Syntax gate: the real SysML v2 Pilot Implementation (`validate_sysml.py`)

Two real paths to the normative SysML v2 parser were tried and timeboxed out on 2026-08-18:

1. **`gorenje/sysmlv2-jupyter-docker`** — a real, working community container, but it builds
   `Systems-Modeling/SysML-v2-API-Services` via SBT/Scala/Play against a PostgreSQL backend, pinned
   to release `2023-02` (three years stale against this repo's clock), and needs a 3-container
   compose stack (API + Postgres + Jupyter) for what this gate only needs as a single CLI check.
2. The official **`Systems-Modeling/SysML-v2-Pilot-Implementation`** repo's `README.adoc` only
   documents an Eclipse Modeling Tools IDE install — but its own `.github/workflows/build.yml` proves
   a real headless path exists: `./mvnw -B clean verify --file pom.xml` on JDK 21, no IDE. This
   host's system Java is 17; a `ghcr.io/graalvm/graalvm-community:21` podman container (confirmed
   `java -version` clean) removes that blocker with zero build changes. Scoping the Tycho reactor to
   just `org.omg.sysml.interactive` (`-pl org.omg.sysml.interactive -am`, skipping the
   `.editor`/`.edit`/`.plantuml`/`.jupyter.*` UI-only modules) got real progress — pom parsing,
   plugin resolution, and the reactor's first module build all ran cleanly. It then failed on a
   different, more specific problem: `com.sensmetry:sysand-maven-plugin:0.1.0-rc.1`'s `build-kpar`
   goal throws `UnsatisfiedLinkError: Native library resource not found2: linux-x86_64/sysand.so` —
   confirmed **not** an architecture mismatch (`uname -m` is `x86_64` on both host and container).
   This is a packaging bug in a pre-1.0 (`-rc.1`) native-JNI Maven plugin from Sensmetry (the same
   company behind Syside) that the official build's own bootstrap step depends on — a genuine
   third-party defect, not an environment mismatch on our end. Worth revisiting once
   `sysand-maven-plugin` ships a fixed release.

Neither path is "one dependency, ships in a day" territory today. `validate_sysml.py` is instead a
small, **named** structural stand-in: it checks exactly the grammar subset `generate_sysml.py`
actually emits (`package`/`part def`/`part`/`attribute`, line by line), reporting a real line/column
error on the first line that doesn't match an allowed shape, or on unbalanced braces. It is not a
general SysML v2 parser and doesn't claim to be — a future phase revisiting either real path above
would replace this one function, not the rest of the pipeline.

### 2. Diagram renderer: the real DaanV2/isometric-diagrams (`translate_iso_ir.py`, `render_diagram.py`)

`translate_iso_ir.py`'s output JSON is deliberately shaped to match the real
`DaanV2/isometric-diagrams` (MIT-licensed) project's own `DiagramSpec` schema — confirmed by reading
its `src/lib/types/diagram.ts` directly, and by actually driving its real app headlessly (Playwright,
via `nvm use 22` + `npx playwright install chromium`) to render this lab's real Track A instance data
on 2026-08-18: **confirmed real, correct, 7/7 nodes rendered with correct labels and type icons**, via
its `#d=<base64url-yaml>` permalink mechanism.

That real render is **not** wired into this lab's own pipeline: it needs Node ≥20.19/22.13 (this
repo's toolchain is Python/uv-only) plus a ~290MB headless-Chromium download, and its own SVG export
(`src/lib/export.ts`) is DOM-dependent (`getComputedStyle`, `XMLSerializer` inside a live browser
page) — there is no pure-function/server-side render path in that project, confirmed by reading its
source. Vendoring a second-language (Node/Svelte) app plus a browser-automation toolchain into this
Python power-systems repo is real, disproportionate infrastructure for this MVP — a genuine finding
worth revisiting as a dedicated follow-up phase, not a same-sprint integration.

`render_diagram.py` instead does the isometric-projection math directly in Python — no browser, no
DOM — which also trivially satisfies this MVP's own "re-run on unchanged input → byte-identical SVG"
kill check (no font-shaping engine or animation frame to introduce variance). Because the iso-IR
JSON's field names match DaanV2's real `DiagramSpec` 1:1, dumping it to YAML and opening
`https://<a running instance of DaanV2/isometric-diagrams>#d=<base64url(that yaml)>` remains a real,
working way to view this lab's data in the real tool by hand — proven, not just plausible.

### 3. Everything else: real, not simulated

`build_k8s_fixture.py` reads this repo's own real `kube/*.yaml` Pod/Job manifests (not a live
cluster call) — every field traces to a manifest already proven elsewhere in this repo with `podman
kube play`. Track B's `schema/grid_instances.yaml` is a real ~5-bus cluster read directly out of
`data/snemSA.m` via a `networkx` graph walk from a real generator bus (127.3 MW, bus 1683) —
selected, not invented — and it honestly reports a real data quirk rather than smoothing it over: both
transformer branches carry `sn_mva: 10000` in the source case, two orders of magnitude above a real
generator step-up transformer's typical rating — a synthetic-case artifact, named as such in the
schema file's own header. `generate_sbom.py` uses the real `cyclonedx-python-lib` (Apache-2.0), not a
hand-built dict, for Track A's CycloneDX-shaped SBOM.

## Command

```
uv run labs/06-sysml-digital-thread/build_k8s_fixture.py --step check

uv run labs/06-sysml-digital-thread/generate_sysml.py --track digital-thread --step run
uv run labs/06-sysml-digital-thread/generate_sysml.py --track grid --step run
uv run labs/06-sysml-digital-thread/generate_sysml.py --track digital-thread --step check
uv run labs/06-sysml-digital-thread/generate_sysml.py --track grid --step check

uv run labs/06-sysml-digital-thread/validate_sysml.py --step check

uv run labs/06-sysml-digital-thread/translate_iso_ir.py --track digital-thread --step run
uv run labs/06-sysml-digital-thread/translate_iso_ir.py --track grid --step run

uv run labs/06-sysml-digital-thread/render_diagram.py --track digital-thread --step run
uv run labs/06-sysml-digital-thread/render_diagram.py --track grid --step run

uv run labs/06-sysml-digital-thread/generate_sbom.py --step run

uv run python -m pytest labs/06-sysml-digital-thread/test_lab6.py -v
```

Or, all of the above chained in one command: `./scripts/demo_lab6.sh` (also `just lab6-demo`).

To see the live "edit one schema, watch it propagate" demo: add one `Agent`/`MCPServer`/`DataSource`
entry to `schema/digital_thread_instances.yaml` (or one `Bus` to `schema/grid_instances.yaml`), then
re-run `./scripts/demo_lab6.sh` — the new part appears in the regenerated `.sysml` text, diagram, and
(Track A) SBOM with no other hand edits.

## Running in a container

```
podman build -t nem-poweragent-base:local -f Containerfile.base .
podman build -t lab6:local -f labs/06-sysml-digital-thread/Containerfile .
podman run --rm lab6:local
```

(Swap `podman` for `docker` if that's what you have.) The default run chains the same steps
`scripts/demo_lab6.sh` runs natively — well under a minute.

## Step-by-step walkthrough

1. **`build_k8s_fixture.py --step check`** — confirms `fixtures/k8s_snapshot.json` still matches a
   fresh reshape of this repo's real `kube/*.yaml` manifests. Output: `MATCH: 4 pod items vs
   k8s_snapshot.json`.
2. **`generate_sysml.py --track {digital-thread,grid} --step run`** — reads each track's LinkML
   instance YAML, writes `output/digital_thread.sysml` / `output/grid_topology.sysml`. `--step check`
   confirms byte-identical against the committed `fixtures/expected_*.sysml`.
3. **`validate_sysml.py --step check`** — runs the named structural syntax gate (see Design notes
   above) against both committed fixtures. Output: `OK: ... -- 66 lines, structurally clean` /
   `92 lines`. A deliberately broken `.sysml` file fails with a real `path:line:col: message` — see
   `test_lab6.py::test_syntax_gate_rejects_broken_input`.
4. **`translate_iso_ir.py --track {digital-thread,grid} --step run`** — walks each track's `.sysml`
   part usages into iso-IR JSON (Track A: 7 nodes/0 edges; Track B: 7 nodes/4 edges, `Line` parts
   become edges).
5. **`render_diagram.py --track {digital-thread,grid} --step run`** — renders each iso-IR spec to a
   deterministic isometric SVG (`output/digital_thread.svg` / `output/grid_topology.svg`).
6. **`generate_sbom.py --step run`** — Track A only: writes `output/digital_thread_sbom.json`, a real
   CycloneDX v1.5-shaped document, 7 components.

Full chain, timed: `./scripts/demo_lab6.sh` runs in well under a second on this host — comfortably
inside a 2-minute walkthrough budget.

## Files

- `schema/digital_thread.linkml.yaml`, `schema/grid_topology.linkml.yaml` — the two LinkML schemas
  (Track A: `Agent`/`MCPServer`/`DataSource`; Track B: `Bus`/`Generator`/`Line`), each with a
  `tree_root: true` container class.
- `schema/digital_thread_instances.yaml`, `schema/grid_instances.yaml` — the real seed instance data
  for each track (see Design notes above for provenance).
- `build_k8s_fixture.py` — real `kube/*.yaml` manifests → `fixtures/k8s_snapshot.json` (Track A's own
  input fixture).
- `generate_sysml.py` — LinkML instance data → `.sysml` text, both tracks (`--track`, `--step
  run`/`check`).
- `validate_sysml.py` — the named structural syntax gate (`--step check` only; see Design notes).
- `translate_iso_ir.py` — `.sysml` parts/containment → iso-IR JSON, both tracks.
- `render_diagram.py` — iso-IR JSON → deterministic isometric SVG, both tracks.
- `generate_sbom.py` — Track A only: real CycloneDX-shaped SBOM via `cyclonedx-python-lib`.
- `fixtures/` — every committed fixture: `expected_*.sysml`, `expected_*_iso_ir.json`,
  `expected_*.svg`, `expected_sbom.json`, `k8s_snapshot.json`.
- `test_lab6.py` — pytest wrapper, subprocess-driven `--step check` gates per script/track (matching
  `labs/02-.../test_lab2.py`'s pattern).
- `Containerfile` — `FROM nem-poweragent-base:local`, chains `scripts/demo_lab6.sh`.
