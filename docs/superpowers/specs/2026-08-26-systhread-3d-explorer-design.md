# systhread 2D/3D model explorer — design

**Status:** Draft v1.0. Fulfils and supersedes the sourcing decision for FR7 in
`docs/superpowers/specs/2026-08-25-systhread-design.md` (that spec's §5 picked a
Cytoscape.js/d3-only sourcing path specifically to avoid forking MM-AR's AGPL codebase — FR7's
own text already named "3D/graph exploration of a metamodel instance" as the target capability,
so this amends the *how*, not the *what*). This document is v1 scope (build now) plus v2 scope
(§7, explicitly deferred, not started).

**Spec:** this document, plus `docs/superpowers/specs/2026-08-25-systhread-design.md` (FR7, §2's
determinism principle, §5's sourcing table).

## 1. Vision

One `systhread-explorer` crate renders a project's SysML model as either a 2D or a 3D interactive
graph, from the same underlying data, deterministically, embeddable with no server dependency —
fulfilling FR7's original "3D/graph exploration" capability using a Bevy-native renderer instead
of the AGPL MM-AR stack it was scoped to avoid.

## 2. Scope: v1 vs v2

**v1 (this document, build now):** a static, deterministic, read-only structural model viewer.
Given a fixed `.sysml` model, `systhread render --explorer` MUST produce byte-identical output on
unchanged input — same hard requirement as every other systhread artifact (§2 of the main spec).
Both 2D and 3D are views over one shared graph; nothing in v1 mutates, nothing in v1 is live.

**v2 (§7, explicitly deferred):** SysML v2/KerML typed visualization, live telemetry ingestion,
mutable operational overlay state, an operations-dashboard mode, and a future AR/VR front-end.
Named and scoped now so v1's data model doesn't foreclose it, not built now — same treatment
already given to the `rustc_driver` direction in the main spec's §9.

## 3. Data model — extending, not replacing, holon-viz's `CytoscapeGraph`

`ledgrrr`'s `holon-viz` crate (`crates/holon-viz/src/cytoscape.rs`) already defines, real and
verified against source:

```rust
pub struct CytoscapeNodeData { id: String, label: String, kind: String, parent: Option<String>, z_layer: Option<String>, semantic_type: Option<String> }
pub struct CytoscapeNode { data: CytoscapeNodeData }
pub struct CytoscapeEdgeData { id: String, source: String, target: String, label: String }
pub struct CytoscapeEdge { data: CytoscapeEdgeData }
pub struct CytoscapeGraph { nodes: Vec<CytoscapeNode>, edges: Vec<CytoscapeEdge> }
```

No coordinate or dimensionality field exists today. `z_layer` is an existing `Option<String>` on
`CytoscapeNodeData`, documented as "a `ZLayer` variant from `HasVisualization::viz_spec()`" — that
enum is not defined inside `holon-viz` itself and was not located during this design pass. **Do
not assume it is a 3D coordinate** — treat it as an unverified, likely 2D-stacking concept until
confirmed, and do not silently repurpose it for 3D depth.

v1 adds a new type, `PositionedGraph`, that wraps `CytoscapeGraph` rather than duplicating its
fields — the harmonization the brainstorming session asked for:

```rust
pub struct PositionedGraph {
    pub graph: holon_viz::CytoscapeGraph,   // unmodified, reused directly
    pub layout: Layout,
}

pub enum Layout {
    TwoD(Vec<NodePosition2D>),   // one entry per graph.nodes, same order/id
    ThreeD(Vec<NodePosition3D>),
}

pub struct NodePosition2D { pub node_id: String, pub x: f64, pub y: f64 }
pub struct NodePosition3D { pub node_id: String, pub x: f64, pub y: f64, pub z: f64 }
```

`Layout` is a sum type, not a shared struct with an ignorable `z`, because 2D and 3D are not
interchangeable here: a 2D layout has no camera/depth-sorting concept and a 3D layout has no
meaningful flat projection without one. This is the "represent incompatible concepts logically"
instruction applied directly — the type system states the incompatibility instead of a comment
stating it.

**Open dependency question, not decided in this document:** this makes `holon-viz` a real, direct
dependency of `systhread-core` or `systhread-explorer` (not a dev-dependency workaround, unlike
`sysml-derive`/`ufo-types`'s current pin). Same posture as FR8/FR9's `ledgrrr#202` — this needs
`ledgrrr`'s owner's agreement before v1 implementation starts, not a unilateral decision here. File
a decision-request issue when v1 moves from spec to plan, cross-referencing `ledgrrr#202` and this
document.

**Two different "2D" concepts exist in this ecosystem — do not conflate them.** `systhread-core`
already ships a real, deterministic 2D isometric diagram renderer (`layout.rs`/`render.rs`, Phase
0, a Rust port of Lab 6's Cassowary/`kiwisolver` layout — Part/containment boxes in isometric
projection, already shipping SVGs). That stays exactly as-is; it is not this document's concern.
This spec's "2D view" is a *different* thing: the same abstract node/edge graph that also drives
the 3D view, laid out as a flat force-directed graph (the Cytoscape.js `cose`-style layout
`holon-viz`'s existing `HtmlRenderer` already produces, per this session's grounding pass) — not
an isometric diagram. A future reader who conflates these will misunderstand both.

## 4. Layout computation — deterministic, ahead-of-time, in Rust

`systhread-core` gains a new module, `layout3d.rs`, sibling to the existing `layout.rs` (which
stays untouched — isometric-diagram-specific, unrelated). It computes `Layout::TwoD` and
`Layout::ThreeD` from a `CytoscapeGraph` using a fixed-seed, fixed-iteration-count force-directed
algorithm (a 3D extension of the same category of problem `layout.rs` already solved once by
porting Lab 6's Python Cassowary solver to Rust — same methodological precedent, not a new kind of
engineering risk for this codebase).

`systhread render --explorer` writes `PositionedGraph` as JSON — a new artifact type, alongside
the existing `.sysml`/SVG/`manifest.json` outputs, held to the exact same byte-identical-on-
unchanged-input bar. This is the half of the determinism problem this codebase already knows how
to solve (deterministic Rust, deterministic serialization, CI-diffable text).

## 5. Viewer — one generic Bevy/WASM binary, not per-project

**Resolving a real wording tension in the main spec:** FR7 describes `systhread-explorer` as "an
output artifact, not a Rust crate," while the main spec's §7 amendment 6 lists `systhread-explorer`
as one of four crates in the workspace's crate layout. This document resolves it the same way
`systhread-cli` already resolves the analogous case for SVGs: `systhread-explorer` **is** a Rust
crate (Bevy source, compiled to `wasm32-unknown-unknown`) whose job is to *produce* an output
artifact (the embeddable HTML/JS/WASM bundle) — a reader of that artifact adds no crate dependency
of their own, which is what FR7's wording was actually protecting.

`systhread-explorer` is a Bevy application, compiled to `wasm32-unknown-unknown`, that loads a
`PositionedGraph` JSON at runtime and renders it — either mode, selected by which `Layout` variant the JSON contains. It is
**one build, reused across every adopting project** — not compiled fresh per project (rejects
Approach C from the brainstorming session: baking data in at compile time would make every
project's binary itself a determinism-and-CI-cost problem, for no benefit over a generic loader).

This resolves the split the brainstorming session converged on: the **generated data** (the
`PositionedGraph` JSON) is the byte-identical, per-project, git-diffable artifact; the **viewer
binary** is a versioned, pinned, compiled dependency, tested for reproducible builds the way any
compiled artifact is (locked toolchain, no embedded timestamps/build IDs) — a normal, solved
engineering practice, not the harder "bit-identical floats inside a browser's WASM engine on an
end-user's machine" problem Approach B would have required. Rendering a fixed input deterministically
does not require the layout computation itself to happen at render time — Bevy's ECS only needs to
render what it's given the same way every time, which is close to free once §4's data is fixed.

**Real, live constraint to design around, not solved yet:** Bevy 0.19.1 shipped with a broken
`bevy_animation` version pin (confirmed this session, `rust/mission-engine/Cargo.toml`) — any
Bevy feature path that reaches `bevy_animation` (`ui` → `default_app` → `scene` → …) fails to
resolve. 3D rendering typically wants `bevy_pbr`/`bevy_gltf`/asset loading, which commonly pulls
`bevy_animation` transitively for animated-mesh support. `systhread-explorer`'s Cargo feature list
will likely need the same explicit-component-list workaround `mission-engine`'s `interactive`
feature already uses (`bevy_ui`, `bevy_ui_render`, `bevy_core_pipeline`, `bevy_winit`,
`bevy_window`, `bevy_text`, `default_font`, `x11` — but adapted for 3D: `bevy_pbr`,
`bevy_render`, `bevy_core_pipeline`, `bevy_asset`, explicitly avoiding whatever pulls
`bevy_animation`). This needs its own spike when implementation starts; not resolved here. Worth
re-checking against Bevy 0.19.2 once it ships.

## 6. Ouroboros testing — one crate, two targets, real round-trip verification

"Rust exports and consumes itself" becomes a concrete testing requirement: the `PositionedGraph`
type and its (de)serialization logic live in a crate compiled to **both** the native target (used
by `systhread-core`/`systhread-cli` to generate the JSON) **and** `wasm32-unknown-unknown` (used
by `systhread-explorer` to load it). CI MUST include a test that generates a `PositionedGraph` on
the native target, loads the same bytes through the wasm-compiled deserialization path (via
`wasm-bindgen-test` or an equivalent headless wasm test runner), and asserts structural equality —
closing the exact gap Lab 9's own `--interactive` feature currently admits to leaving open ("not
run visually... this is a headless shared host, so claiming a screenshot would be claiming
something not done"). This is a real regression test, not a visual smoke check, and it is a
genuine, non-obvious testing pattern worth this codebase adopting more broadly.

## 7. v2 (explicitly deferred, not started, no target date)

Named now so v1's data model doesn't foreclose it — same posture as the main spec's §9.

- **SysML v2/KerML typed visualization, owned by systhread, backed by `ufo-types`.** `systhread`
  is the visualization/control-plane consumer of the shared `promptexecution/ufo-types` vocabulary:
  it MUST NOT pretend Kroki or any other text-diagram renderer directly understands SysML v2
  semantics. Kroki issue [yuzutech/kroki#1020](https://github.com/yuzutech/kroki/issues/1020)
  remains a useful warning: "render SysML" is not a native Kroki diagram family to build product
  behavior around. v2 therefore adds a typed intermediate model *before* `CytoscapeGraph` lowering,
  retaining the source SysML/KerML construct and UFO stereotype for each visual element. The current
  `CytoscapeNodeData.semantic_type: Option<String>` field is the v1 placeholder for this, not the
  whole design.
- **Canonical v2 graph vocabulary.** The generic `Node`/`Edge` shape already promoted to
  `ufo-types::iso_ir` stays the cross-crate transport floor, but v2 needs a typed layer above it:
  package/namespace containment, part/item/action/requirement definitions and usages, feature
  membership, port/interface/connection relationships, succession/control-flow, allocation,
  satisfaction, verification, alias/import provenance, and metadata extensions. Each typed node or
  edge MUST carry a stable model id, a qualified SysML/KerML name when available, source-span or
  generation provenance, and the resolved `ufo_types::UfoStereotype` when one exists. Lowering to
  `Node`/`Edge`, Cytoscape JSON, D2, GraphViz, PlantUML, Mermaid, or Structurizr is derived output;
  the typed model remains the source for view selection and validation.
- **Required views.** v2 needs multiple projections over the same typed model, not one universal
  force graph: package/containment tree, internal connection view, action/control-flow view,
  requirement-satisfaction-verification trace view, allocation view, state/transition view, and a
  semantic-alignment view. The alignment view is grounded in the approach described by
  [arXiv:2508.16181v1](https://arxiv.org/pdf/2508.16181v1): LLM-assisted model extraction,
  semantic matching, and verification can be useful, but the output must be represented with
  explicit alias/import/metadata provenance rather than silently rewriting either source model.
- **Reference toolchain posture.** The curated
  [SysML v2 Resources](https://github.com/daltskin/SysML-v2-Resources) list points at the OMG
  SysML v2/KerML specifications, the official release repositories, the Pilot Implementation, LSPs,
  and editors/viewers. v2 should use those as reference or oracle inputs where practical, while
  keeping systhread's generated artifact contract Rust-owned and deterministic. `sysml-v2-parser`
  remains the lightweight syntax gate for the subset it can parse; any richer parser or Pilot
  Implementation dependency must be isolated behind an oracle boundary unless it becomes a
  deliberately accepted core dependency.
- **b00t ontology integration.** The b00t datums `PRD-ONTOLOGY-OODA-UFO-SYSML` and
  `PRD-ARCH-005-MBSE-VISUALIZATION` already name the intended ontology direction:
  KerML-profile UFO classes, SHACL/OWL/CLIF-adjacent validation, and diagram export from ontology
  data. v2 systhread should align with those datums by generating/managing the typed visualization
  model as b00t-discoverable capability data. `b00t ontology diagram` can emit text-diagram formats,
  but systhread owns the SysML v2/KerML-specific view model and the explorer artifacts.
- **v2 acceptance hooks.** Add golden typed-graph fixtures before adding new renderers. Every lowered
  artifact must prove: no dangling references, no duplicate stable ids, containment edges form a
  tree or explicitly declared DAG where the SysML/KerML construct permits it, every non-derived
  visual element has source provenance, and each diagram export can be regenerated byte-identically.
- **First real consumer: cim-gridy.** v2's typed model stays consumer-less otherwise, the same trap the main b00t SysML spine epic (`elasticdotventures/_b00t_#1177`, closed) avoided by pointing itself at a real target (b00t's own MCP dispatch chain, `b00t-cli/src/dispatch_sysml.rs`) instead of staying abstract. This repo's own **cim-gridy** (#17 Phase 0, #20 Phases 1-3, both merged) is the natural first golden-fixture target: grid topology maps to the package/containment + internal connection views, dispatch/control logic to the action/control-flow view, and PRD-0009's own requirements to the requirement-satisfaction-verification trace view above. Golden typed-graph fixtures (previous bullet) should be drawn from cim-gridy's real model, not a synthetic example.
- **Live telemetry ingestion and a mutable operational overlay.** The main spec's non-goal
  ("not live collaborative model editing... FR7 is read-only, editing happens in the `.sysml`
  text file") stays true for the **structural model** — v2 does not change that. What v2 adds is
  a logically separate layer: live, mutable, never-git-tracked operational/telemetry state
  (status, alarms, live values) rendered *on top of* the fixed structural `PositionedGraph`,
  connected to Lab 9's existing `--grid2op-live` bridge and `card_feed.rs` concept as a real,
  already-partially-built source of exactly this kind of live data. The structural layer and the
  operational layer are two distinct types with a stated relationship (which node an overlay
  attaches to), never one merged mutable graph — this is the same "represent incompatible
  concepts logically" principle applied a second time, to structural-vs-live data instead of
  2D-vs-3D geometry.
- **Operations-dashboard mode.** A live-refreshing view of the operational overlay, not a new
  editing surface for the structural model.
- **AR/VR front-end.** Bevy has real, existing OpenXR-plugin ecosystem support (not fabricated —
  a genuine, active part of the Bevy plugin ecosystem), making this a plausible eventual target
  for the *same* ECS this design already commits to, unlike a 2D-only Cytoscape.js-based
  alternative. v1's design constraint: don't hard-code mouse/keyboard-only interaction assumptions
  into the core ECS/camera structure in a way that would need to be re-architected for an XR
  camera/interaction rig later. No XR work happens in v1.

**Revisit trigger, not a date:** v2 becomes real once v1 has shipped and Lab 9's live bridge has a
real consumer that actually needs to *see* live state rather than just log it — not on a calendar
schedule, same posture as the main spec's §9.

## 8. Non-goals (v1)

- Not live collaborative editing of the structural model (carried over from the main spec's §4,
  restated here because v2's telemetry overlay could otherwise be misread as loosening it).
- Not a general-purpose 3D scene editor — the viewer renders a `PositionedGraph`; it does not
  provide arbitrary Bevy-scene authoring tools.
- Not committing to solving Bevy's `bevy_animation` 0.19.1 resolution bug here — §5 names the
  workaround pattern to reuse, the actual feature-list spike happens at implementation time.
- Not the domain-specific spatial grid scene (substations/lines as literal spatial objects) —
  that remains the separate, later, cim-gridy-only extension named during brainstorming, layered
  on top of this generic viewer once it exists, not part of v1.
