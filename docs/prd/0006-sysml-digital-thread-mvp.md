# 0006 — SysML v2 digital-thread MVP: MBSE tooling evaluation (Lab 6)

- **Status:** implemented (three tracks, first pass — see Open questions for what's deliberately
  left for a later phase)
- **Depends on:** none directly; reuses real components from Labs 1, 3, 4, 5 as Track A seed data,
  a real `data/snemSA.m` subset (the same CSIRO case Lab 1 loads) as Track B seed data, and
  PRD-0005's own real Phase 0/1/1.5/2 sequence (Lab 5) as Track C seed data
- **Touches:** new `labs/06-sysml-digital-thread/`, `pyproject.toml`/`uv.lock` (`linkml`,
  `linkml-runtime`, `cyclonedx-python-lib`), `Justfile` (`check-lab6`, `lab6`, `lab6-demo`),
  `.gitignore`, `AGENTS.md`, `docs/VISION.md`, `docs/DEFINITION_OF_DONE.md`, root `README.md`,
  `docs/PSCADOSSE.md` (license map), `docs/prd/0004-plexos-direct-mcp-and-strangler-fig.md`
  (renumber note — its own `labs/06-plexos...` reference becomes `labs/07` whenever that work
  starts, since this PRD claims Lab 6 first)

## Problem

This is a **greenfield capability evaluation**, not a feature build: is MBSE/SysML v2 (a formal
systems-modelling notation and its current, 2025-era language version) viable tooling for two
different, emerging jobs in this repo's world — **(1) modelling AI agent/MCP/data workflows**, the
software side of what this repo already runs, and **(2) grid network system design/simulation**,
the power-systems side every other lab studies? The sprint's own framing: "buying knowledge," with
breadth (as many real options de-risked as feasible) weighted over picking the cheapest path on day
one. `linkml.io` was named as one candidate schema technology, explicitly "not essential — just
under consideration," not a hard requirement.

## What was checked this session, not assumed

**Tool landscape, researched before any code was written:**

- **SysML v2 Pilot/Reference Implementation**
  (`Systems-Modeling/SysML-v2-Pilot-Implementation`, EPL-2.0, normative, Java ≥21) is real, and
  there's prior container art (`gorenje/sysmlv2-jupyter-docker`), directly analogous to how this
  repo already handles VILLASnode in Lab 5 (a real OCI image, run via `podman`, not reimplemented).
- **Syside** (Sensmetry) — the free tier is a VS Code *editor* extension only; the scriptable
  headless CLI/Python API is part of the paid Modeler tier. Not confirmed usable for a non-commercial
  evaluation without a purchase; not pursued further this sprint.
- Browser-only diagram tools (a Svelte/SvelteKit and a React project, both YAML-spec-to-isometric-
  SVG, both rendered in-browser only, no server-side export path) were surveyed and ruled out for
  this MVP's pipeline without a same-sprint browser-automation toolchain to drive them headlessly —
  not pursued further.

**Real-tool attempt, genuinely tried and timeboxed, written up in full in
[`labs/06-sysml-digital-thread/README.md`](../../labs/06-sysml-digital-thread/README.md)'s
"Design notes" (not repeated in full here):**

- **Syntax gate**: the official Pilot Implementation's `.github/workflows/build.yml` proved a real
  headless Maven/Tycho build path exists (JDK 21, no IDE). A `ghcr.io/graalvm/graalvm-community:21`
  podman container removed this host's Java-17 blocker cleanly. Scoping the Tycho reactor to
  `org.omg.sysml.interactive` got real progress (pom parsing, plugin resolution, first module build
  all clean) before failing on a specific, confirmed third-party defect: an `UnsatisfiedLinkError` in
  `com.sensmetry:sysand-maven-plugin:0.1.0-rc.1`'s native JNI loader — not an architecture mismatch,
  not an environment misconfiguration on this repo's side. Fallback: a named structural stand-in
  (`validate_sysml.py`) checking exactly the grammar subset this lab's generator emits, with real
  line/column error reporting.
- **Diagram renderer**: `render_diagram.py` is a pure, deterministic, in-repo isometric-projection
  SVG writer — no browser, no DOM, no external renderer — driven by `translate_iso_ir.py`'s own
  iso-IR JSON.

**Two real gaps found by scrutinizing the first pass, not just accepted as done, fixed same
session (full write-up in the lab's own README "Design notes" §3–4):**

- **Track B's seed data was a one-time hand transcription, not re-derivable.** `schema/
  grid_instances.yaml`'s header claimed real provenance from `data/snemSA.m` via a documented
  selection method, but no script implementing that method was ever committed — `git log` confirmed
  the file had only ever been hand-authored. Closed with `build_grid_instances.py`: a deterministic
  BFS graph walk (real transmission-line neighbours preferred over real transformer neighbours at
  each frontier step) that re-derives the identical real cluster from the case file on demand,
  `--step check`-gated exactly like `build_k8s_fixture.py` already does for Track A.
- **The pipeline didn't actually chain past the first stage.** `translate_iso_ir.py` and
  `render_diagram.py` both read their input from the *committed* fixture snapshot, not the previous
  stage's fresh output — so editing a schema file only ever regenerated `.sysml` text; the iso-IR
  JSON and rendered SVG silently stayed frozen. Fixed by chaining each stage as a direct in-process
  function call instead of a file read. Also fixed in the same pass: Track B's isometric renderer
  technically drew all 4 real branches, but two were visually indistinguishable against node fills,
  and generators had no edge to their own bus at all (a missing-data bug, not just styling —
  `Generator.bus` was parsed but never turned into an edge). Track B now renders as a real bus/branch
  diagram (bars for buses, circles for generators, styled edges by kind), verified live by adding a
  throwaway bus to the schema and watching it propagate to the SVG with zero other edits.
- **Track B's node layout was a fixed grid with no relationship to real edges.** Replaced with a real
  Cassowary constraint solver (`kiwisolver`, the Python equivalent of the Rust `kasuari` crate used by
  the external `ledgrrr` codebase's own diagram-layout solver, consulted directly as a reference
  pattern). A first version put every bus on one shared row, which surfaced a second real problem on
  inspection: Track B's network is a real star (one hub bus with four branches, four leaf buses), and
  a single row can't represent a star's shape regardless of edge styling. Root-caused by rooting the
  layout in the real Bus-to-Bus branch graph instead of array order — a BFS finds the actual hub, each
  bus's row is its real depth from that hub, and each row's x positions are solved via the same
  Cassowary primitives (required sibling gaps, a required centroid constraint that symmetrically
  centers each parent's children). Deterministic throughout (confirmed via repeated identical
  re-solves), not physics/force-directed (full write-up: the lab's own README "Design notes" §5).
- **Track A had the same missing-edges gap class Track B had, just not yet noticed.** Its Agent/
  MCPServer/DataSource nodes rendered as disconnected boxes with no relationships drawn at all.
  Checked what's real (not invented): both agents' own scripts call the same real CSIRO case file
  via `_shared.gridfit.load_case()` (a real `Agent uses DataSource` edge), and neither actually
  calls the real `powermcp_pandapower` MCP server (`orchestrator.py`'s own docstring says so
  directly — a real negative finding, not an omission). Added a `uses` slot, generalized the
  attachment-edge and Cassowary-layout code from Bus/Generator-specific type checks to a structural
  anchor/leaf split (any node that isn't an attachment-edge source is an anchor), which handled
  Track A's disconnected-component case with no new layout code. Surfaced and fixed one more real
  bug in the process: two leaves attached to the same anchor solved to the identical point until
  leaf sibling-groups got the same gap-plus-centroid treatment anchors already had (full write-up:
  README "Design notes" §6).
- **Stress-tested the layout against a denser real cluster.** `TARGET_CLUSTER_SIZE` bumped 5 -> 15
  (same anchor, same BFS walk) reaches several genuine multi-degree substations (bus 1740, degree
  11; bus 1728, degree 9) instead of one single hub. Layout held up (multiple real hubs radiate
  correctly, still bit-identical across re-runs); the only visual crowding is a real graph cycle
  (redundant loop connectivity around one hub) a tree-based layout can't fully untangle -- a known,
  out-of-scope limitation, not a bug. Surfaced a real naming bug in the process: this cluster
  contains genuine parallel branches (two real transformers on one bus pair, two more on another,
  two real parallel lines on a third), which a bus-pair-only naming scheme collapsed into duplicate
  part names -- invisible at the original size purely because no parallel pair happened to be
  included. Fixed with a deterministic suffix scheme; the header's own "real quirk" prose was also
  hardcoded from the original 2-transformer case and is now derived from the actual data (full
  write-up: README "Design notes" §7).
- **Added a third, genuinely different track (Track C) rather than more instance data on the
  existing two.** Grounded in PRD-0005's own real, already-implemented Phase 0/1/1.5/2 sequence (Lab
  5's grid-forming-stabilizer sprint) -- every `source`/`role` read from that phase's own script
  docstring or PRD-0005's own Phasing/Open-questions sections. This is the exact use case the
  Cassowary investigation was originally pointed at (`ledger-core/src/visualize.rs`'s own pipeline-
  state diagram), and it needed a real new layout, not a reuse of Track A/B's hub/star one: a
  `Phase.next` chain is a declared *order*, not an undirected graph, so rooting it at the highest-
  degree node (Track A/B's approach) would misrepresent it. Added a `sequence` edge type and
  `_sequence_positions` -- the most direct port yet of the actual `ledgrrr` reference pattern
  (`LayoutSolver::generate_layout`'s own consecutive-gap-constraint chain) -- plus a real arrowhead
  in the renderer, since `sequence` is the first genuinely directed relationship this renderer draws
  (full write-up: README "Design notes" §8).

## Goals

1. Prove or disprove, with a real generated pipeline (not a mockup), that one SysML v2 schema/
   generator/validator/renderer approach generalizes across both named business cases (AI workflow
   modelling and grid topology modelling) — Track A and Track B share the exact same code.
2. Attempt the real, normative tools first for both the syntax gate and the diagram render, timeboxed,
   and treat the findings — whichever way each lands — as a first-class deliverable, not a discarded
   exploration.
3. Ground every seed instance in real, already-committed data (this repo's own agents/MCP
   servers/data sources for Track A; a real `data/snemSA.m` subset for Track B) rather than
   fabricated examples.
4. Demonstrate the full "one schema edit → one command → regenerated artifacts" loop end to end,
   under a 2-minute walkthrough budget.

## Non-goals

- **Not building Port/Flow/connection-usage SysML v2 syntax.** Part/containment only — "straight
  boxes are enough" for this MVP; Track B's `Line.fromBus`/`toBus` are plain string attributes, named
  explicitly as the exact substitution a future phase would replace with real reference/connection
  syntax.
- **Not a semantic/type-checking gate** (`mercurio-sysml` or equivalent) — `validate_sysml.py` is a
  structural syntax check only, named as such.
- **Not a git-hook/CI-integrated modelling workflow** (`Rocky` or equivalent) — out of scope for this
  evaluation sprint.
- **Not live k8s cluster enumeration** — `build_k8s_fixture.py` reshapes this repo's own committed,
  already-proven `kube/*.yaml` manifests, not a live `kubectl` call.
- **Not SBOM drift/vulnerability detection** — `generate_sbom.py` emits `version: "unknown"` for
  every component; no scanner integration.
- **Not SHACL or any other RDF-based validation layer** for the LinkML schemas.
- **Not a Track-B SBOM equivalent** — a CycloneDX bill of materials doesn't map onto physical grid
  assets; what that third artifact should be (an equipment register? NER asset schedule shape?) is
  named as an open question below, not invented under time pressure.
- **Not settling LinkML as a permanent dependency** — explicitly provisional, see Open questions.

## Phasing

- **Phase 1 (this sprint, complete)** — both tracks' schemas + instance data, the generator/
  validator/translator/renderer pipeline, Track A's SBOM, the chained demo script, and the two
  real-tool-evaluation write-ups above.
- **Phase 2 (not started)** — revisit the syntax gate once `sysand-maven-plugin` ships a fixed
  release past `0.1.0-rc.1`, or a newer/maintained community SysML v2 API container appears.
- **Phase 3 (not started)** — revisit the diagram renderer as a dedicated follow-up (a Node/Svelte +
  Playwright toolchain addition to this repo, if the business case justifies the added
  infrastructure) rather than folding it into this sprint.
- **Phase 4 (not started, contingent on Phase 1's findings holding up)** — Track B's own
  third-artifact question (equipment register / NER asset schedule shape).

## Acceptance criteria for this PRD

- [x] `uv run python -m pytest labs/06-sysml-digital-thread/test_lab6.py -v` passes, all three
      tracks, on a clean checkout.
- [x] `./scripts/demo_lab6.sh` (and `just lab6-demo`) runs end to end, all three tracks, under 2
      minutes (measured: well under a second on this host).
- [x] Every Track A seed instance's `source` field traces to a real, already-committed file in this
      repo; every Track B seed instance traces to a real row/table entry in `data/snemSA.m`; every
      Track C seed instance traces to a real script docstring or PRD-0005 section.
- [x] Track B's seed data (`schema/grid_instances.yaml`) is re-derivable from `data/snemSA.m` by a
      committed, `--step check`-gated script (`build_grid_instances.py`), not a one-time hand
      transcription — confirmed via `git log` before the fix that no such script had existed.
- [x] Editing any schema/instance file and re-running the pipeline propagates through every
      downstream artifact (`.sysml`, iso-IR JSON, rendered SVG) with no stale intermediate — verified
      live by adding a throwaway node and confirming it appears in the regenerated SVG, then
      reverting and confirming every stage reports `MATCH` against its committed fixture again.
- [x] Both real-tool attempts (syntax gate, diagram renderer) are genuinely attempted, not assumed
      to fail, and precisely root-caused (not "too hard") wherever they didn't land — written up in
      the lab's own README.
- [x] Zero secrets in `fixtures/k8s_snapshot.json` (source manifests and the generated fixture both
      checked).
- [x] `podman build`/`podman run` parity against the Lab 6 `Containerfile`, matching every other
      lab's container-parity bar.
- [x] New dependencies' licenses (`linkml`, `linkml-runtime`, `cyclonedx-python-lib`, and their new
      transitive packages) recorded in `docs/PSCADOSSE.md`.

## Open questions

- **Does LinkML earn its keep, or would plain Pydantic/dataclasses serve this repo just as well for
  Track A/B's schema needs?** Left genuinely open — LinkML's own tooling (`linkml validate`, its
  broader ecosystem) wasn't stress-tested past this MVP's two small schemas.
- **Is Syside's paid Modeler tier worth a trial license for a future phase**, given the free tier is
  editor-only and this sprint didn't purchase access to check its scriptable API directly?
- **What is Track B's own third downstream artifact** (an equipment register? a NER asset schedule
  shape?), now that SBOM is confirmed Track-A-only — not decided in this PRD, a Phase 4 question.
- **Does Track B map onto CIM (IEC 61970/61968, the CGMES profile) for network-model exchange
  traceability?** Resolved for the annotation layer only —
  [PRD-0007](0007-lab6-cim-class-uri-traceability.md) (Phase 4a) scopes a small class-URI mapping
  on generated `.sysml` output, LinkML remaining the schema authority. Still genuinely open: whether
  CIM/CGMES RDF-XML should ever become Track B's schema-of-record instead of LinkML — explicitly
  out of PRD-0007's scope, a larger, separate workstream if pursued at all.
- **Would a newer/maintained SysML v2 API container (replacing the stale `2023-02`-pinned
  `gorenje/sysmlv2-jupyter-docker`) or a fixed `sysand-maven-plugin` release change the syntax-gate
  finding?** Worth re-checking periodically, not attempted again this sprint.
