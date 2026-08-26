# systhread 2D/3D Model Explorer v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship v1 of `systhread-explorer` — a Bevy crate compiled to `wasm32-unknown-unknown` that renders a project's SysML model as an interactive 3D (or flat-2D) graph, fed by a new byte-identical `PositionedGraph` JSON artifact that `systhread render --explorer` computes ahead of time with a deterministic, fixed-seed layout in `systhread-core`.

**Architecture:** Three layers, split exactly where the spec splits them. (1) `systhread-core` gains the shared data model — a `CytoscapeGraph` (holon-viz's real shape), a `PositionedGraph` that wraps it with a `Layout` sum type, and `layout3d.rs`, a fixed-seed/fixed-iteration force-directed solver that computes both the 2D and 3D variants. `layout.rs`/`render.rs` (the existing isometric-diagram pipeline) are untouched — a different, unrelated "2D". (2) `systhread-cli` writes the `PositionedGraph` as a new manifest-described artifact behind a `--explorer` flag, held to the same byte-identical bar as every other systhread artifact. (3) `systhread-explorer` is a Bevy app whose Bevy-free core (`loader`, `scene`) compiles to both targets and whose ECS layer only consumes an already-computed `SceneSpec`, so all the layout/geometry math is unit-tested without a GPU. The ouroboros gate closes the loop: `systhread-core` itself is the one crate compiled to both native and `wasm32-unknown-unknown`, with a real CI test that loads native-produced bytes through the wasm-compiled deserialization path.

**Tech Stack:** Rust 2024 edition; `serde`/`serde_json` (already `systhread-core` deps); Bevy `0.19` with `default-features = false` and an explicit component feature list (no meta-features — see Global Constraints); `wasm-bindgen-test` `0.3.77` + `wasm-bindgen-cli` `0.2.127` running under Node (v24.19.0 on this machine) for the wasm half of the ouroboros test; `wasm-bindgen --target web` for the browser bundle. No RNG crate: the layout's PRNG is a ~10-line SplitMix64 written inline, because `rand` on `wasm32-unknown-unknown` drags in `getrandom`'s `js` backend for no benefit when the seed is a constant.

**Spec:** `docs/superpowers/specs/2026-08-26-systhread-3d-explorer-design.md` (v1 scope, §§1–6 and §8; §7 is v2 and explicitly not built here), plus `docs/superpowers/specs/2026-08-25-systhread-design.md` (FR7, §2's determinism principle). Executors read the spec too — it is the binding authority, this plan is its argument.

## Global Constraints

- **`holon-viz` as a real (non-dev) dependency is NOT yet approved.** A decision-request issue is open: `PromptExecution/ledgrrr#203`. Tasks 1–12 deliberately use a **locally-defined mirror** of holon-viz's public `CytoscapeGraph` shape (copied from the real struct definition quoted verbatim in design §3, not invented), because that shape is public and stable regardless of how #203 resolves. **Task 13 — and only Task 13 — adds the real `holon-viz` dependency, and it is BLOCKED until `ledgrrr#203` is resolved by ledgrrr's owner.** Do not start Task 13 on your own judgment; do not sneak a `holon-viz` entry into any earlier task's `Cargo.toml`. If #203 is still open when Tasks 1–12 are green, that is a complete, shippable v1 — stop there and report.
- **Byte-identical output on unchanged input is a hard gate** (main spec §2, this spec §2/§4). The new `PositionedGraph` JSON is held to it exactly like `.sysml`/SVG/iso-IR JSON: no wall-clock, no unseeded RNG, no HashMap iteration order, no absolute paths, no `-0.0` (the layout rounds through the same `+ 0.0` normalization `layout.rs` already uses).
- **Do not modify `rust/systhread-core/src/layout.rs` or `render.rs`.** They implement the *isometric diagram* pipeline, which design §3 explicitly separates from this spec's graph "2D view". `layout3d.rs` is a sibling module, not an extension of them. (It carries its own private `round6` copy for exactly this reason — a deliberate ten-line duplication that keeps `layout.rs` untouched.)
- **No Bevy meta-features, ever.** Bevy `0.19.1` shipped with broken sub-crate version pins: `bevy_animation 0.19.1` was never published (already documented in `rust/mission-engine/Cargo.toml`), and — found during this plan's own spike — `bevy_dev_tools 0.19.1` requires `bevy_picking ^0.19.1`, which does not exist either (latest `bevy_picking` is `0.16.1`). Every Bevy feature must be an explicit component feature, and `bevy/webgl2` / `bevy/webgpu` / `bevy/web` are all unusable on `0.19.1` (see Verified During Planning).
- **`systhread-core` must keep compiling for `wasm32-unknown-unknown`.** It does today (verified — see below). Any dependency added to it from now on must be checked against that target in the same task that adds it.
- **`systhread-core`'s error-handling convention applies** (`rust/systhread-core/src/lib.rs`'s crate docs): a `pub fn` returns `Result<T, String>` iff it crosses the crate boundary with the outside world (parsing text this crate didn't generate). Pure in-memory transforms return bare values. `PositionedGraph::from_json` is fallible; `to_json`, `layout_2d`, `layout_3d`, `scene_spec` are not.
- **No `ufo-types` / `sysml-derive` work here.** FR8/FR9 remain Phase 2, still gated on `ledgrrr#202`. `CytoscapeNodeData::semantic_type` is populated as `None` in v1 with a comment naming that future owner — it is not a placeholder to fill in later in this plan.
- **v2 (design §7) is not started.** No telemetry ingestion, no mutable overlay, no XR. The one v1 obligation §7 imposes is negative: do not hard-code mouse/keyboard-only assumptions into the camera/ECS structure such that an XR rig would need a re-architecture. Task 11 satisfies this by keeping the camera a data-driven `SceneSpec` field rather than an input-system side effect.

## Verified During Planning

Every claim below was produced by running the command named, in this repo, during this planning pass — not assumed. Tasks cite these instead of re-deriving them.

1. **The 3D Bevy feature list resolves and compiles clean for `wasm32-unknown-unknown`** (`cargo check`, exit 0, ~1 min cold):
   ```toml
   explorer-3d = ["bevy/bevy_pbr", "bevy/bevy_render", "bevy/bevy_core_pipeline", "bevy/bevy_asset", "bevy/bevy_winit", "bevy/bevy_window"]
   ```
   `cargo tree -i bevy_animation` / `bevy_gltf` / `bevy_scene` confirm none of the three problem packages are anywhere in the resolved graph. Root cause: `bevy_pbr` never asks for them; only the `ui` → `default_app` → `scene` meta-feature path reaches the bug, which `mission-engine`'s `interactive` feature already avoids the same way.
2. **`DefaultPlugins`, the PBR/camera/light API shapes, and a custom `AssetLoader` all compile under exactly that feature list, for wasm32.** Spiked as a standalone crate during this planning pass, iterated until clean. The one non-obvious compiler requirement found: `AssetLoader` requires `TypePath` on the *loader* type as well as the asset (`pub trait AssetLoader: TypePath + Send + Sync + 'static`, `bevy_asset-0.19.1/src/loader.rs:32`), so the loader struct needs `#[derive(TypePath)]`. Task 10's code is the spike's verified code.
3. **`bevy/webgl2`, `bevy/webgpu`, and `bevy/web` all fail to *resolve* on `bevy 0.19.1`** — each maps to `bevy_internal/*`, whose weak `bevy_dev_tools?/webgl` edge still forces cargo to resolve `bevy_dev_tools 0.19.1`, which requires the unpublished `bevy_picking ^0.19.1`. This is the previously-untested runtime-backend question, and the answer is that the obvious lever is broken.
4. **A verified workaround for (3) exists**, compiled clean for wasm32 during planning: declare the sub-crates directly and turn on *their* `webgl` features, bypassing the `bevy` facade's broken mapping:
   ```toml
   bevy_render = { version = "0.19", default-features = false, optional = true }
   bevy_core_pipeline = { version = "0.19", default-features = false, optional = true }
   bevy_pbr = { version = "0.19", default-features = false, optional = true }
   # ...
   explorer-web = ["explorer-3d", "dep:bevy_render", "bevy_render/webgl", "dep:bevy_core_pipeline", "bevy_core_pipeline/webgl", "dep:bevy_pbr", "bevy_pbr/webgl"]
   ```
   Task 12 uses this only if the plain `explorer-3d` build fails to get a WebGPU adapter in a real browser. Whether a canvas actually *draws* is still unverified and is Task 12's job.
5. **`systhread-core` already compiles AND links for `wasm32-unknown-unknown`, including all its test targets** (`cargo check` and `cargo build --tests`, both exit 0, with `sysml-v2-parser`, `kasuari`, `serde_norway`, `psm`/`stacker` all in the graph). This is what makes `systhread-core` itself the ouroboros crate — no separate shared crate is needed.
6. **`wasm-bindgen-test 0.3.77` pins `wasm-bindgen =0.2.127`** (read from the crates.io sparse index during planning), while this machine's installed CLI is `0.2.126`. Task 6 owns the one-line upgrade.
7. **`wasm32-unknown-unknown` is installed** (`rustup target list --installed`), as are `wasm-bindgen 0.2.126`, `wasm-pack 0.13.1`, and `node v24.19.0` — so the wasm tests run under Node with no browser driver.

---

## Milestone A: the shared data model and the deterministic layout (`systhread-core`)

### Task 1: `cytoscape.rs` — the local mirror of holon-viz's graph shape

**Files:**
- Create: `rust/systhread-core/src/cytoscape.rs`
- Modify: `rust/systhread-core/src/lib.rs`
- Test: `rust/systhread-core/tests/cytoscape_test.rs`

**Interfaces:**
- Consumes: `iso_ir::{Node, Edge}` and `iso_ir::{extract_digital_thread, extract_grid, extract_pipeline}` (Phase 0, unchanged); `common::fixture_path` (Phase 0's test helper); `instances::{load_digital_thread, load_grid}` (returns `Result`, so tests call `.unwrap()`).
- Produces: `cytoscape::{CytoscapeGraph, CytoscapeNode, CytoscapeNodeData, CytoscapeEdge, CytoscapeEdgeData}` and `cytoscape::from_iso_ir(nodes: &[Node], edges: &[Edge]) -> CytoscapeGraph`. Tasks 2, 3, 4, 5 and 13 all depend on these exact names — they are deliberately identical to holon-viz's own, so Task 13's swap is a re-export, not a rename.

**Design note:** the struct definitions below are copied from design §3, which quotes `ledgrrr`'s real `crates/holon-viz/src/cytoscape.rs` verbatim ("real and verified against source"). Field names, types and nesting (`node.data.id`, not `node.id`) are load-bearing. Two deliberate v1 decisions, both stated in the code's own comments so a future reader doesn't have to guess: `parent` is `None` (none of the three tracks has a containment hierarchy today) and `z_layer` is `None` (design §3: "**Do not assume it is a 3D coordinate**" — it is an unverified 2D-stacking concept and this plan does not repurpose it).

- [ ] **Step 1: Write the failing test**

`rust/systhread-core/tests/cytoscape_test.rs`:

```rust
mod common;
use common::fixture_path;
use systhread_core::cytoscape::from_iso_ir;
use systhread_core::instances::{load_digital_thread, load_grid};
use systhread_core::iso_ir::{extract_digital_thread, extract_grid};

#[test]
fn grid_nodes_carry_id_label_and_part_type_as_kind() {
    let inst = load_grid(&fixture_path("schema/grid_instances.yaml")).unwrap();
    let (nodes, edges) = extract_grid(&inst);
    let graph = from_iso_ir(&nodes, &edges);

    assert_eq!(graph.nodes.len(), nodes.len());
    let bus = graph
        .nodes
        .iter()
        .find(|n| n.data.id == "bus_4052")
        .expect("bus_4052 should be a node");
    assert_eq!(bus.data.label, "bus_4052");
    assert_eq!(bus.data.kind, "Bus");
    assert_eq!(bus.data.parent, None);
    assert_eq!(bus.data.z_layer, None);
    assert_eq!(bus.data.semantic_type, None);

    let gen = graph
        .nodes
        .iter()
        .find(|n| n.data.id == "gen_4052")
        .expect("gen_4052 should be a node");
    assert_eq!(gen.data.kind, "Generator");
}

#[test]
fn grid_edges_map_from_to_onto_source_target() {
    let inst = load_grid(&fixture_path("schema/grid_instances.yaml")).unwrap();
    let (nodes, edges) = extract_grid(&inst);
    let graph = from_iso_ir(&nodes, &edges);

    assert_eq!(graph.edges.len(), edges.len());
    let attach = graph
        .edges
        .iter()
        .find(|e| e.data.id == "gen_4052_attach")
        .expect("gen_4052_attach should be an edge");
    assert_eq!(attach.data.source, "gen_4052");
    assert_eq!(attach.data.target, "bus_4052");
    assert_eq!(attach.data.label, "attachment");

    // A `branch` edge carries iso-IR's `kind` too -- it must survive into the label rather than
    // being silently dropped, since it is the only place line type is represented in the graph.
    let branch = graph
        .edges
        .iter()
        .find(|e| e.data.label.starts_with("branch:"))
        .expect("grid has branch edges with a kind");
    assert!(branch.data.label.len() > "branch:".len());
}

#[test]
fn node_and_edge_order_follows_iso_ir_order_exactly() {
    let inst = load_digital_thread(&fixture_path("schema/digital_thread_instances.yaml")).unwrap();
    let (nodes, edges) = extract_digital_thread(&inst);
    let graph = from_iso_ir(&nodes, &edges);

    let got: Vec<&str> = graph.nodes.iter().map(|n| n.data.id.as_str()).collect();
    let want: Vec<&str> = nodes.iter().map(|n| n.id.as_str()).collect();
    assert_eq!(got, want);

    let got: Vec<&str> = graph.edges.iter().map(|e| e.data.id.as_str()).collect();
    let want: Vec<&str> = edges.iter().map(|e| e.id.as_str()).collect();
    assert_eq!(got, want);
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml cytoscape_test`
Expected: FAIL to compile — `systhread_core::cytoscape` does not exist yet.

- [ ] **Step 3: Write the implementation**

`rust/systhread-core/src/cytoscape.rs`:

```rust
//! A local mirror of `ledgrrr`'s `holon-viz` `CytoscapeGraph` shape.
//!
//! These structs are copied field-for-field from the real definitions in
//! `ledgrrr`'s `crates/holon-viz/src/cytoscape.rs`, quoted verbatim in
//! `docs/superpowers/specs/2026-08-26-systhread-3d-explorer-design.md` §3. They exist here, rather
//! than as a `holon-viz` dependency, only because making `holon-viz` a real (non-dev) dependency of
//! this codebase is an open decision request -- `PromptExecution/ledgrrr#203`. When #203 resolves in
//! favour, this module becomes a re-export of the real crate's types (that swap is the plan's Task
//! 13, and nothing else changes, because the names here are deliberately identical).

use crate::iso_ir::{Edge, Node};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CytoscapeNodeData {
    pub id: String,
    pub label: String,
    pub kind: String,
    /// Containment parent. Always `None` in v1: none of systhread's three tracks
    /// (digital-thread, grid, pipeline) has a nested containment hierarchy today.
    pub parent: Option<String>,
    /// holon-viz documents this as "a `ZLayer` variant from `HasVisualization::viz_spec()`".
    /// That enum is not defined inside holon-viz and was not located during design. Design §3:
    /// "**Do not assume it is a 3D coordinate**." v1 leaves it `None` and computes depth in
    /// `layout3d` instead -- do not repurpose this field for the Z axis.
    pub z_layer: Option<String>,
    /// Reserved for FR8/FR9's `UfoStereotype` wiring (Phase 2, gated on `ledgrrr#202`).
    /// `None` in v1 because there is no stereotype source to populate it from yet.
    pub semantic_type: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CytoscapeNode {
    pub data: CytoscapeNodeData,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CytoscapeEdgeData {
    pub id: String,
    pub source: String,
    pub target: String,
    pub label: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CytoscapeEdge {
    pub data: CytoscapeEdgeData,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CytoscapeGraph {
    pub nodes: Vec<CytoscapeNode>,
    pub edges: Vec<CytoscapeEdge>,
}

/// Converts Phase 0's iso-IR structural extraction into the Cytoscape graph shape, preserving
/// input order exactly (the layout in `layout3d` indexes positions by node order, and the
/// byte-identical gate makes any reordering a visible artifact change).
///
/// iso-IR's `Edge::kind` (e.g. a grid line's type) has no field of its own on the Cytoscape side,
/// so it is folded into the label as `"{edge_type}:{kind}"` rather than dropped -- lossless and
/// deterministic. Edges with no `kind` keep the bare `edge_type` as their label.
pub fn from_iso_ir(nodes: &[Node], edges: &[Edge]) -> CytoscapeGraph {
    CytoscapeGraph {
        nodes: nodes
            .iter()
            .map(|n| CytoscapeNode {
                data: CytoscapeNodeData {
                    id: n.id.clone(),
                    label: n.label.clone(),
                    kind: n.part_type.to_string(),
                    parent: None,
                    z_layer: None,
                    semantic_type: None,
                },
            })
            .collect(),
        edges: edges
            .iter()
            .map(|e| CytoscapeEdge {
                data: CytoscapeEdgeData {
                    id: e.id.clone(),
                    source: e.from.clone(),
                    target: e.to.clone(),
                    label: match &e.kind {
                        Some(kind) => format!("{}:{}", e.edge_type, kind),
                        None => e.edge_type.clone(),
                    },
                },
            })
            .collect(),
    }
}
```

Modify `rust/systhread-core/src/lib.rs` to add, in alphabetical position (before `pub mod instances;`):

```rust
pub mod cytoscape;
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml cytoscape_test`
Expected: PASS, all three tests, zero warnings.

- [ ] **Step 5: Commit**

```bash
git add rust/systhread-core/src/cytoscape.rs rust/systhread-core/src/lib.rs rust/systhread-core/tests/cytoscape_test.rs
git commit -m "systhread-core: local CytoscapeGraph mirror (holon-viz shape) + iso-IR conversion"
```

---

### Task 2: `positioned.rs` — `PositionedGraph`, `Layout`, and the JSON artifact form

**Files:**
- Create: `rust/systhread-core/src/positioned.rs`
- Modify: `rust/systhread-core/src/lib.rs`
- Test: `rust/systhread-core/tests/positioned_test.rs`

**Interfaces:**
- Consumes: `cytoscape::{CytoscapeGraph, CytoscapeNode, CytoscapeNodeData, CytoscapeEdge, CytoscapeEdgeData}` (Task 1).
- Produces: `positioned::{PositionedGraph, Layout, NodePosition2D, NodePosition3D}`; `PositionedGraph::to_json(&self) -> String`, `PositionedGraph::from_json(text: &str) -> Result<PositionedGraph, String>`, `PositionedGraph::layout_matches_graph(&self) -> bool`; `Layout::len(&self) -> usize`, `Layout::is_empty(&self) -> bool`, `Layout::node_ids(&self) -> Vec<&str>`. Tasks 3, 4, 5, 7, 8, 9, 10, 11 all use these exact signatures.

**Design note:** `Layout` is a sum type, not a struct with an ignorable `z` — design §3 is explicit that this is the "represent incompatible concepts logically" instruction applied to geometry. Serde's default external tagging plus `rename_all = "snake_case"` gives `{"two_d": [...]}` / `{"three_d": [...]}` on the wire, which makes the variant self-describing in the artifact. `to_json` mirrors the CLI's existing artifact convention exactly (`serde_json::to_string_pretty` + a trailing newline — see `rust/systhread-cli/src/commands/render.rs`'s iso-IR write), so the new artifact diffs in git like the old ones.

- [ ] **Step 1: Write the failing test**

`rust/systhread-core/tests/positioned_test.rs`:

```rust
use systhread_core::cytoscape::{
    CytoscapeEdge, CytoscapeEdgeData, CytoscapeGraph, CytoscapeNode, CytoscapeNodeData,
};
use systhread_core::positioned::{Layout, NodePosition2D, NodePosition3D, PositionedGraph};

fn node(id: &str) -> CytoscapeNode {
    CytoscapeNode {
        data: CytoscapeNodeData {
            id: id.to_string(),
            label: id.to_string(),
            kind: "Bus".to_string(),
            parent: None,
            z_layer: None,
            semantic_type: None,
        },
    }
}

fn sample_graph() -> CytoscapeGraph {
    CytoscapeGraph {
        nodes: vec![node("a"), node("b")],
        edges: vec![CytoscapeEdge {
            data: CytoscapeEdgeData {
                id: "a_b".to_string(),
                source: "a".to_string(),
                target: "b".to_string(),
                label: "branch".to_string(),
            },
        }],
    }
}

fn sample_3d() -> PositionedGraph {
    PositionedGraph {
        graph: sample_graph(),
        layout: Layout::ThreeD(vec![
            NodePosition3D { node_id: "a".to_string(), x: -1.0, y: 0.5, z: 0.0 },
            NodePosition3D { node_id: "b".to_string(), x: 1.0, y: -0.5, z: 0.25 },
        ]),
    }
}

#[test]
fn json_round_trips_through_from_json_unchanged() {
    let original = sample_3d();
    let text = original.to_json();
    let parsed = PositionedGraph::from_json(&text).unwrap();
    assert_eq!(parsed, original);
    assert_eq!(parsed.to_json(), text);
}

#[test]
fn json_ends_with_exactly_one_newline_and_names_its_layout_variant() {
    let text = sample_3d().to_json();
    assert!(text.ends_with("}\n"));
    assert!(!text.ends_with("\n\n"));
    assert!(text.contains("\"three_d\""), "layout variant must be self-describing: {text}");

    let flat = PositionedGraph {
        graph: sample_graph(),
        layout: Layout::TwoD(vec![
            NodePosition2D { node_id: "a".to_string(), x: 0.0, y: 0.0 },
            NodePosition2D { node_id: "b".to_string(), x: 2.0, y: 0.0 },
        ]),
    };
    assert!(flat.to_json().contains("\"two_d\""));
}

#[test]
fn serialization_is_stable_across_repeated_calls() {
    let pg = sample_3d();
    assert_eq!(pg.to_json(), pg.to_json());
}

#[test]
fn layout_matches_graph_detects_id_and_length_mismatches() {
    assert!(sample_3d().layout_matches_graph());

    let short = PositionedGraph {
        graph: sample_graph(),
        layout: Layout::ThreeD(vec![NodePosition3D {
            node_id: "a".to_string(),
            x: 0.0,
            y: 0.0,
            z: 0.0,
        }]),
    };
    assert!(!short.layout_matches_graph());

    let misnamed = PositionedGraph {
        graph: sample_graph(),
        layout: Layout::ThreeD(vec![
            NodePosition3D { node_id: "a".to_string(), x: 0.0, y: 0.0, z: 0.0 },
            NodePosition3D { node_id: "WRONG".to_string(), x: 0.0, y: 0.0, z: 0.0 },
        ]),
    };
    assert!(!misnamed.layout_matches_graph());
}

#[test]
fn from_json_rejects_garbage_with_a_real_message() {
    let err = PositionedGraph::from_json("{ not json").unwrap_err();
    assert!(!err.is_empty());
}

#[test]
fn layout_len_and_node_ids_read_either_variant() {
    assert_eq!(sample_3d().layout.len(), 2);
    assert_eq!(sample_3d().layout.node_ids(), vec!["a", "b"]);
    assert!(!sample_3d().layout.is_empty());
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml positioned_test`
Expected: FAIL to compile — `systhread_core::positioned` does not exist yet.

- [ ] **Step 3: Write the implementation**

`rust/systhread-core/src/positioned.rs`:

```rust
//! `PositionedGraph` -- a `CytoscapeGraph` plus an ahead-of-time-computed `Layout`.
//!
//! Design: `docs/superpowers/specs/2026-08-26-systhread-3d-explorer-design.md` §3. This type
//! *wraps* the graph rather than duplicating its fields, so the graph half stays byte-compatible
//! with whatever holon-viz produces.

use crate::cytoscape::CytoscapeGraph;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct NodePosition2D {
    pub node_id: String,
    pub x: f64,
    pub y: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct NodePosition3D {
    pub node_id: String,
    pub x: f64,
    pub y: f64,
    pub z: f64,
}

/// A sum type, not a struct with an ignorable `z`: a 2D layout has no camera/depth-sorting
/// concept and a 3D layout has no meaningful flat projection without one (design §3). The type
/// system states the incompatibility so no consumer has to remember it.
///
/// Every variant holds exactly one entry per `PositionedGraph::graph.nodes`, in the same order,
/// with matching `node_id`s -- `layout_matches_graph` is the enforcement point.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Layout {
    TwoD(Vec<NodePosition2D>),
    ThreeD(Vec<NodePosition3D>),
}

impl Layout {
    pub fn len(&self) -> usize {
        match self {
            Layout::TwoD(p) => p.len(),
            Layout::ThreeD(p) => p.len(),
        }
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    pub fn node_ids(&self) -> Vec<&str> {
        match self {
            Layout::TwoD(p) => p.iter().map(|n| n.node_id.as_str()).collect(),
            Layout::ThreeD(p) => p.iter().map(|n| n.node_id.as_str()).collect(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PositionedGraph {
    pub graph: CytoscapeGraph,
    pub layout: Layout,
}

impl PositionedGraph {
    /// The artifact form: pretty-printed JSON with a trailing newline, matching every other
    /// systhread artifact's convention (see systhread-cli's render command). Infallible by
    /// construction per this crate's error-handling convention -- `serde_json` can only fail here
    /// on a non-finite float, and `layout3d` guarantees finite coordinates (Task 4 tests that
    /// invariant directly). A panic here would mean that invariant was violated upstream.
    pub fn to_json(&self) -> String {
        serde_json::to_string_pretty(self)
            .expect("PositionedGraph holds only finite f64 coordinates and plain strings")
            + "\n"
    }

    /// Parses text that originated outside this crate (a file on disk, a fetched asset), so it is
    /// fallible per the crate's error-handling convention.
    pub fn from_json(text: &str) -> Result<PositionedGraph, String> {
        serde_json::from_str(text).map_err(|e| format!("parse PositionedGraph JSON: {e}"))
    }

    /// True when the layout has exactly one entry per graph node, in the same order, with matching
    /// ids. Consumers (the explorer's loader) check this before trusting positional indexing.
    pub fn layout_matches_graph(&self) -> bool {
        let graph_ids: Vec<&str> = self.graph.nodes.iter().map(|n| n.data.id.as_str()).collect();
        graph_ids == self.layout.node_ids()
    }
}
```

Modify `rust/systhread-core/src/lib.rs` to add (after `mod numfmt;`):

```rust
pub mod positioned;
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml positioned_test`
Expected: PASS, all six tests.

- [ ] **Step 5: Commit**

```bash
git add rust/systhread-core/src/positioned.rs rust/systhread-core/src/lib.rs rust/systhread-core/tests/positioned_test.rs
git commit -m "systhread-core: PositionedGraph/Layout types and their byte-stable JSON artifact form"
```

---

### Task 3: `layout3d.rs` part 1 — seeded PRNG, initial placement, centering

**Files:**
- Create: `rust/systhread-core/src/layout3d.rs`
- Modify: `rust/systhread-core/src/lib.rs`
- Test: inline `#[cfg(test)] mod` in `rust/systhread-core/src/layout3d.rs` (these are private helpers; `layout.rs`'s own `round6_tests` establishes this file-local pattern in this crate)

**Interfaces:**
- Consumes: nothing (pure numerics).
- Produces (crate-private, consumed by Task 4 in the same file): `SplitMix64::{new, next_u64, next_unit}`, `initial_positions::<const D: usize>(n: usize) -> Vec<[f64; D]>`, `center::<const D: usize>(positions: &mut [[f64; D]])`, `round6(v: f64) -> f64`. Produces (public): `LAYOUT_SEED: u64`, `LAYOUT_ITERATIONS: usize`, `IDEAL_EDGE_LENGTH: f64`, `INITIAL_TEMPERATURE: f64` — Task 6's wasm smoke test asserts two of these constants, so their names and values are load-bearing.

**Design note — why a hand-written PRNG:** the layout needs a *reproducible* pseudo-random initial placement, not entropy. Pulling in `rand` would drag `getrandom` onto `wasm32-unknown-unknown` (where it needs an explicit JS backend) to service a constant seed — pure cost. SplitMix64 is ten lines, has no dependencies, is bit-identical on every target (pure `u64` wrapping arithmetic), and is the standard seeding generator for exactly this job. **No transcendental functions anywhere in this module** (`cbrt`, `powf`, `exp`, trig): they are libm-implementation-defined and would put cross-target agreement at risk. `sqrt` is fine — IEEE-754 requires it to be correctly rounded.

- [ ] **Step 1: Write the failing test**

Create `rust/systhread-core/src/layout3d.rs` containing *only* this test module for now (the implementation lands in Step 3):

```rust
#[cfg(test)]
mod placement_tests {
    use super::{SplitMix64, center, initial_positions, round6, LAYOUT_SEED};

    #[test]
    fn splitmix64_is_reproducible_for_a_fixed_seed() {
        let mut a = SplitMix64::new(LAYOUT_SEED);
        let mut b = SplitMix64::new(LAYOUT_SEED);
        let first: Vec<u64> = (0..8).map(|_| a.next_u64()).collect();
        let second: Vec<u64> = (0..8).map(|_| b.next_u64()).collect();
        assert_eq!(first, second);
        // A real generator, not a constant sequence.
        assert!(first.windows(2).any(|w| w[0] != w[1]));
    }

    #[test]
    fn next_unit_stays_inside_the_half_open_unit_interval() {
        let mut rng = SplitMix64::new(LAYOUT_SEED);
        for _ in 0..10_000 {
            let v = rng.next_unit();
            assert!((-1.0..1.0).contains(&v), "next_unit produced {v}");
        }
    }

    #[test]
    fn initial_positions_are_reproducible_and_shaped_by_dimension() {
        let a = initial_positions::<3>(5);
        let b = initial_positions::<3>(5);
        assert_eq!(a, b);
        assert_eq!(a.len(), 5);

        let flat = initial_positions::<2>(5);
        assert_eq!(flat.len(), 5);
        // The 2D and 3D placements draw from the same seeded stream in the same order, so their
        // first two coordinates agree -- a 2D layout is a projection of the same starting state.
        assert_eq!(flat[0][0], a[0][0]);
    }

    #[test]
    fn initial_positions_are_not_all_coincident() {
        let p = initial_positions::<3>(4);
        assert!(p.iter().any(|q| *q != p[0]), "every node landed on the same point: {p:?}");
    }

    #[test]
    fn center_moves_the_centroid_to_the_origin_and_rounds() {
        let mut p = [[1.0, 2.0, 3.0], [3.0, 4.0, 5.0]];
        center(&mut p);
        assert_eq!(p, [[-1.0, -1.0, -1.0], [1.0, 1.0, 1.0]]);
    }

    #[test]
    fn center_normalizes_negative_zero() {
        // Same hazard layout.rs's round6 already guards: JSON prints "-0.0" and "0.0" as different
        // bytes, which would break the byte-identical gate on a run-to-run sign flip.
        let mut p = [[0.0_f64, 0.0, 0.0]];
        center(&mut p);
        assert!(!p[0][0].is_sign_negative());
    }

    #[test]
    fn round6_matches_the_isometric_pipelines_rounding() {
        assert_eq!(round6(1.234_567_89), 1.234_568);
        assert!(!round6(-0.0_f64).is_sign_negative());
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Add `pub mod layout3d;` to `rust/systhread-core/src/lib.rs` (after `pub mod layout;`), then run:
`cargo test -p systhread-core --manifest-path rust/Cargo.toml --lib placement_tests`
Expected: FAIL to compile — `SplitMix64`, `initial_positions`, `center`, `round6`, `LAYOUT_SEED` are all undefined.

- [ ] **Step 3: Write the implementation**

Prepend to `rust/systhread-core/src/layout3d.rs` (above the test module):

```rust
//! Deterministic, ahead-of-time graph layout for the model explorer.
//!
//! Design: `docs/superpowers/specs/2026-08-26-systhread-3d-explorer-design.md` §4. This module is
//! a *sibling* of `layout.rs`, not an extension of it: `layout.rs` positions Part/containment
//! boxes for the isometric SVG diagram, this one positions an abstract node/edge graph for the
//! explorer. Design §3 is explicit that conflating the two "2D"s misunderstands both.
//!
//! Determinism rules this module obeys, all load-bearing for the byte-identical artifact gate:
//! a compile-time seed (never entropy), a fixed iteration count (never a convergence threshold or
//! a time budget), input-order iteration everywhere (never a `HashMap`), and no transcendental
//! functions (`sqrt` only, which IEEE-754 requires to be correctly rounded on every target).

/// Fixed layout seed: the ASCII bytes of "SYSTHRED". Changing this value changes every explorer
/// artifact in every adopting project -- treat it as a wire-format constant, not a tuning knob.
pub const LAYOUT_SEED: u64 = 0x5359_5354_4852_4544;

/// Fixed iteration count. Not a convergence threshold on purpose: "run until it stops moving"
/// makes the output depend on float noise, and "run for 50ms" makes it depend on the machine.
pub const LAYOUT_ITERATIONS: usize = 300;

/// Target distance between two connected nodes, in the layout's own arbitrary units.
pub const IDEAL_EDGE_LENGTH: f64 = 2.0;

/// Starting per-iteration displacement cap; cooled linearly to zero over `LAYOUT_ITERATIONS`.
pub const INITIAL_TEMPERATURE: f64 = 4.0;

/// Distances below this are treated as coincident (see `delta_and_distance`), and displacements
/// below it are treated as zero. Guards every division by a distance in this module.
const MIN_DISTANCE: f64 = 1.0e-9;

/// Six-decimal rounding with `-0.0` normalized to `0.0`.
///
/// Deliberately a copy of `layout.rs`'s private `round6` rather than a shared helper: design §4
/// requires `layout.rs` to stay untouched, and making its private fn `pub(crate)` would be a
/// modification. Ten duplicated lines is the cheaper side of that trade.
fn round6(v: f64) -> f64 {
    let v = v + 0.0;
    (v * 1_000_000.0).round() / 1_000_000.0
}

/// SplitMix64 -- a fixed-seed PRNG in pure wrapping `u64` arithmetic, identical on every target.
/// Used only to spread the initial placement; nothing downstream of `initial_positions` is random.
struct SplitMix64 {
    state: u64,
}

impl SplitMix64 {
    fn new(seed: u64) -> Self {
        Self { state: seed }
    }

    fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    /// Uniform in `[-1.0, 1.0)`, built from the top 53 bits so the conversion is exact.
    fn next_unit(&mut self) -> f64 {
        let bits = self.next_u64() >> 11;
        let unit = bits as f64 / (1_u64 << 53) as f64;
        unit * 2.0 - 1.0
    }
}

/// Seeded initial placement inside a cube/square whose half-width grows linearly with node count,
/// so a large graph doesn't start hopelessly overlapped. Same seed, same stream order, every run.
fn initial_positions<const D: usize>(n: usize) -> Vec<[f64; D]> {
    let mut rng = SplitMix64::new(LAYOUT_SEED);
    let radius = IDEAL_EDGE_LENGTH * (n.max(1) as f64) / 2.0;
    (0..n)
        .map(|_| {
            let mut point = [0.0_f64; D];
            for coordinate in point.iter_mut() {
                *coordinate = rng.next_unit() * radius;
            }
            point
        })
        .collect()
}

/// Translates the layout so its centroid sits at the origin, then rounds to six decimals.
/// Centering makes the artifact translation-invariant (a camera framing the origin always frames
/// the model) and is the single place rounding happens, so every coordinate in the artifact has
/// passed through the same normalization.
fn center<const D: usize>(positions: &mut [[f64; D]]) {
    let n = positions.len();
    if n == 0 {
        return;
    }
    let mut centroid = [0.0_f64; D];
    for point in positions.iter() {
        for d in 0..D {
            centroid[d] += point[d];
        }
    }
    for value in centroid.iter_mut() {
        *value /= n as f64;
    }
    for point in positions.iter_mut() {
        for d in 0..D {
            point[d] = round6(point[d] - centroid[d]);
        }
    }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml --lib placement_tests`
Expected: PASS, all seven tests.

- [ ] **Step 5: Confirm the new module still compiles for the wasm target**

Run: `cargo check -p systhread-core --manifest-path rust/Cargo.toml --target wasm32-unknown-unknown`
Expected: exit 0 (it did before this task — see Verified During Planning #5 — and nothing added here is target-specific; this step is the Global Constraint's "check it in the same task that changes it").

- [ ] **Step 6: Commit**

```bash
git add rust/systhread-core/src/layout3d.rs rust/systhread-core/src/lib.rs
git commit -m "systhread-core: layout3d seeded PRNG, initial placement, and centroid normalization"
```

---

### Task 4: `layout3d.rs` part 2 — the force-directed solver and the public layout API

**Files:**
- Modify: `rust/systhread-core/src/layout3d.rs`
- Test: `rust/systhread-core/tests/layout3d_test.rs`

**Interfaces:**
- Consumes: Task 3's `initial_positions`, `center`, `round6`, `MIN_DISTANCE`, `IDEAL_EDGE_LENGTH`, `LAYOUT_ITERATIONS`, `INITIAL_TEMPERATURE`; `cytoscape::CytoscapeGraph` (Task 1); `positioned::{Layout, NodePosition2D, NodePosition3D, PositionedGraph}` (Task 2).
- Produces: `layout3d::LayoutMode` (`TwoD` | `ThreeD`), `layout3d::layout_2d(graph: &CytoscapeGraph) -> Layout`, `layout3d::layout_3d(graph: &CytoscapeGraph) -> Layout`, `layout3d::build_positioned_graph(graph: CytoscapeGraph, mode: LayoutMode) -> PositionedGraph`. Tasks 5, 7, 8, 9 and 11 consume these exact signatures. Note `build_positioned_graph` takes the graph **by value** (it moves it into the returned `PositionedGraph`) while `layout_2d`/`layout_3d` borrow.

**Design note — the algorithm, and why 2D and 3D share it:** this is Fruchterman-Reingold force-directed placement, generic over dimension via a `const D: usize`. Design §4 assigns *both* `Layout::TwoD` and `Layout::ThreeD` to this one module and this one "fixed-seed, fixed-iteration-count force-directed algorithm", so 2D here is genuinely the same solver with `D = 2`, not a second algorithm needing its own design decision. Repulsion runs over every unordered pair (`O(n²)`, and the real tracks are ~20 nodes — no spatial index needed or wanted, since an approximation would be another determinism surface). `LayoutMode` exists alongside `Layout` because a caller selecting a mode has no positions to hand over yet — `Layout` carries data, `LayoutMode` carries only the choice.

**Design note — cross-target float agreement:** the layout only ever *runs* on the native target (the wasm side deserializes what native produced), so nothing here depends on cross-target bit-identity. That said, the algorithm is restricted to `+ - * /` and `sqrt`, all IEEE-754-exact, which is what lets Task 7's second wasm test assert that a wasm recomputation agrees exactly. That test is a genuine check, not a formality — if it fails, that is real information (see Task 7).

- [ ] **Step 1: Write the failing test**

`rust/systhread-core/tests/layout3d_test.rs`:

```rust
mod common;
use common::fixture_path;
use systhread_core::cytoscape::{
    from_iso_ir, CytoscapeEdge, CytoscapeEdgeData, CytoscapeGraph, CytoscapeNode, CytoscapeNodeData,
};
use systhread_core::instances::load_grid;
use systhread_core::iso_ir::extract_grid;
use systhread_core::layout3d::{build_positioned_graph, layout_2d, layout_3d, LayoutMode};
use systhread_core::positioned::Layout;

fn grid_graph() -> CytoscapeGraph {
    let inst = load_grid(&fixture_path("schema/grid_instances.yaml")).unwrap();
    let (nodes, edges) = extract_grid(&inst);
    from_iso_ir(&nodes, &edges)
}

fn node(id: &str) -> CytoscapeNode {
    CytoscapeNode {
        data: CytoscapeNodeData {
            id: id.to_string(),
            label: id.to_string(),
            kind: "Bus".to_string(),
            parent: None,
            z_layer: None,
            semantic_type: None,
        },
    }
}

fn edge(id: &str, source: &str, target: &str) -> CytoscapeEdge {
    CytoscapeEdge {
        data: CytoscapeEdgeData {
            id: id.to_string(),
            source: source.to_string(),
            target: target.to_string(),
            label: "branch".to_string(),
        },
    }
}

fn xyz(layout: &Layout) -> Vec<(f64, f64, f64)> {
    match layout {
        Layout::ThreeD(p) => p.iter().map(|n| (n.x, n.y, n.z)).collect(),
        Layout::TwoD(_) => panic!("expected a 3D layout"),
    }
}

#[test]
fn layout_3d_is_identical_across_repeated_runs() {
    let graph = grid_graph();
    assert_eq!(layout_3d(&graph), layout_3d(&graph));
}

#[test]
fn layout_2d_is_identical_across_repeated_runs() {
    let graph = grid_graph();
    assert_eq!(layout_2d(&graph), layout_2d(&graph));
}

#[test]
fn layout_produces_one_entry_per_node_in_graph_order() {
    let graph = grid_graph();
    let layout = layout_3d(&graph);
    let want: Vec<&str> = graph.nodes.iter().map(|n| n.data.id.as_str()).collect();
    assert_eq!(layout.node_ids(), want);
    assert_eq!(layout.len(), graph.nodes.len());
}

#[test]
fn every_coordinate_is_finite_and_six_decimal_rounded() {
    // to_json's infallibility depends on this invariant, so it gets a real test.
    for (x, y, z) in xyz(&layout_3d(&grid_graph())) {
        for v in [x, y, z] {
            assert!(v.is_finite(), "non-finite coordinate {v}");
            assert_eq!(v, (v * 1_000_000.0).round() / 1_000_000.0, "{v} is not 6dp-rounded");
        }
    }
}

#[test]
fn connected_nodes_end_up_closer_than_unconnected_ones() {
    // Two connected pairs, no edge between the pairs: the real, checkable property of a
    // force-directed layout. Asserting exact coordinates instead would be asserting the
    // implementation, not the behaviour.
    let graph = CytoscapeGraph {
        nodes: vec![node("a"), node("b"), node("c"), node("d")],
        edges: vec![edge("ab", "a", "b"), edge("cd", "c", "d")],
    };
    let p = xyz(&layout_3d(&graph));
    let dist = |i: usize, j: usize| {
        let (a, b) = (p[i], p[j]);
        ((a.0 - b.0).powi(2) + (a.1 - b.1).powi(2) + (a.2 - b.2).powi(2)).sqrt()
    };
    assert!(dist(0, 1) < dist(0, 2), "a-b (connected) should be closer than a-c (not)");
    assert!(dist(2, 3) < dist(1, 3), "c-d (connected) should be closer than b-d (not)");
}

#[test]
fn coincident_nodes_are_separated_rather_than_producing_nan() {
    // Two nodes, no edges, both starting from whatever the seeded placement gives: the guard for
    // the division-by-zero path in delta_and_distance.
    let graph = CytoscapeGraph {
        nodes: vec![node("a"), node("b")],
        edges: vec![],
    };
    for (x, y, z) in xyz(&layout_3d(&graph)) {
        assert!(x.is_finite() && y.is_finite() && z.is_finite());
    }
}

#[test]
fn an_empty_graph_produces_an_empty_layout() {
    let graph = CytoscapeGraph { nodes: vec![], edges: vec![] };
    assert!(layout_3d(&graph).is_empty());
    assert!(layout_2d(&graph).is_empty());
}

#[test]
fn edges_naming_unknown_nodes_are_ignored_rather_than_panicking() {
    let graph = CytoscapeGraph {
        nodes: vec![node("a"), node("b")],
        edges: vec![edge("ghost", "a", "does_not_exist"), edge("self", "b", "b")],
    };
    assert_eq!(layout_3d(&graph).len(), 2);
}

#[test]
fn build_positioned_graph_selects_the_variant_and_keeps_the_graph() {
    let graph = grid_graph();
    let three = build_positioned_graph(graph.clone(), LayoutMode::ThreeD);
    assert!(matches!(three.layout, Layout::ThreeD(_)));
    assert!(three.layout_matches_graph());
    assert_eq!(three.graph, graph);

    let two = build_positioned_graph(graph.clone(), LayoutMode::TwoD);
    assert!(matches!(two.layout, Layout::TwoD(_)));
    assert!(two.layout_matches_graph());
}

#[test]
fn the_json_artifact_is_byte_identical_across_repeated_builds() {
    let graph = grid_graph();
    let a = build_positioned_graph(graph.clone(), LayoutMode::ThreeD).to_json();
    let b = build_positioned_graph(graph, LayoutMode::ThreeD).to_json();
    assert_eq!(a, b);
    assert!(!a.contains("-0.0"), "negative zero would break byte-identity on a sign flip");
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml layout3d_test`
Expected: FAIL to compile — `layout_2d`, `layout_3d`, `build_positioned_graph`, `LayoutMode` are undefined.

- [ ] **Step 3: Write the implementation**

Insert into `rust/systhread-core/src/layout3d.rs`, after `center` and above the `#[cfg(test)]` module, and add the two `use` lines at the top of the file:

```rust
use crate::cytoscape::CytoscapeGraph;
use crate::positioned::{Layout, NodePosition2D, NodePosition3D, PositionedGraph};
use std::collections::BTreeMap;
```

```rust
/// Which geometry to compute. Separate from `Layout` because a caller choosing a mode has no
/// positions yet: `Layout` carries data, `LayoutMode` carries only the choice.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LayoutMode {
    TwoD,
    ThreeD,
}

/// Vector from `b` to `a` and its length. Coincident points (distance below `MIN_DISTANCE`) get a
/// deterministic nudge along an axis picked from the two node *indices* -- never from an RNG, a
/// pointer, or iteration order, all of which would leak nondeterminism into the artifact.
fn delta_and_distance<const D: usize>(
    a: &[f64; D],
    b: &[f64; D],
    index_a: usize,
    index_b: usize,
) -> ([f64; D], f64) {
    let mut delta = [0.0_f64; D];
    let mut sum_of_squares = 0.0;
    for d in 0..D {
        delta[d] = a[d] - b[d];
        sum_of_squares += delta[d] * delta[d];
    }
    let distance = sum_of_squares.sqrt();
    if distance < MIN_DISTANCE {
        let mut nudge = [0.0_f64; D];
        nudge[(index_a + index_b) % D] = MIN_DISTANCE;
        return (nudge, MIN_DISTANCE);
    }
    (delta, distance)
}

/// Resolves each edge to a pair of node indices, dropping edges that name a node the graph does
/// not contain and self-loops (neither contributes a direction to push along). Uses a `BTreeMap`,
/// not a `HashMap`: iteration order never reaches the output, but the crate-wide rule is that no
/// hash-ordered container sits anywhere on an artifact's data path.
fn edge_indices(graph: &CytoscapeGraph) -> Vec<(usize, usize)> {
    let index: BTreeMap<&str, usize> = graph
        .nodes
        .iter()
        .enumerate()
        .map(|(i, n)| (n.data.id.as_str(), i))
        .collect();
    graph
        .edges
        .iter()
        .filter_map(|e| {
            let a = *index.get(e.data.source.as_str())?;
            let b = *index.get(e.data.target.as_str())?;
            if a == b { None } else { Some((a, b)) }
        })
        .collect()
}

/// Fruchterman-Reingold refinement: all-pairs repulsion `k²/d`, per-edge attraction `d²/k`, with
/// a per-iteration displacement cap cooled linearly to zero. Fixed iteration count, fixed
/// traversal order, no early exit -- the three things that make the result reproducible.
fn refine<const D: usize>(positions: &mut [[f64; D]], edges: &[(usize, usize)]) {
    let n = positions.len();
    if n < 2 {
        return;
    }
    let k = IDEAL_EDGE_LENGTH;
    for iteration in 0..LAYOUT_ITERATIONS {
        let mut displacement = vec![[0.0_f64; D]; n];

        for i in 0..n {
            for j in (i + 1)..n {
                let (delta, distance) = delta_and_distance(&positions[i], &positions[j], i, j);
                let force = (k * k) / distance;
                for d in 0..D {
                    let unit = delta[d] / distance;
                    displacement[i][d] += unit * force;
                    displacement[j][d] -= unit * force;
                }
            }
        }

        for &(a, b) in edges {
            let (delta, distance) = delta_and_distance(&positions[a], &positions[b], a, b);
            let force = (distance * distance) / k;
            for d in 0..D {
                let unit = delta[d] / distance;
                displacement[a][d] -= unit * force;
                displacement[b][d] += unit * force;
            }
        }

        let temperature =
            INITIAL_TEMPERATURE * (1.0 - (iteration as f64) / (LAYOUT_ITERATIONS as f64));
        for i in 0..n {
            let mut sum_of_squares = 0.0;
            for d in 0..D {
                sum_of_squares += displacement[i][d] * displacement[i][d];
            }
            let magnitude = sum_of_squares.sqrt();
            if magnitude < MIN_DISTANCE {
                continue;
            }
            let scale = magnitude.min(temperature) / magnitude;
            for d in 0..D {
                positions[i][d] += displacement[i][d] * scale;
            }
        }
    }
}

fn solve<const D: usize>(graph: &CytoscapeGraph) -> Vec<[f64; D]> {
    let mut positions = initial_positions::<D>(graph.nodes.len());
    refine(&mut positions, &edge_indices(graph));
    center(&mut positions);
    positions
}

/// Flat force-directed layout -- the same solver as `layout_3d` with one dimension removed, which
/// is exactly what design §4 specifies ("computes `Layout::TwoD` and `Layout::ThreeD` ... using a
/// fixed-seed, fixed-iteration-count force-directed algorithm"). This is *not* the isometric
/// diagram layout in `layout.rs`; see design §3 on not conflating the two.
pub fn layout_2d(graph: &CytoscapeGraph) -> Layout {
    let positions = solve::<2>(graph);
    Layout::TwoD(
        graph
            .nodes
            .iter()
            .zip(positions)
            .map(|(node, p)| NodePosition2D {
                node_id: node.data.id.clone(),
                x: p[0],
                y: p[1],
            })
            .collect(),
    )
}

pub fn layout_3d(graph: &CytoscapeGraph) -> Layout {
    let positions = solve::<3>(graph);
    Layout::ThreeD(
        graph
            .nodes
            .iter()
            .zip(positions)
            .map(|(node, p)| NodePosition3D {
                node_id: node.data.id.clone(),
                x: p[0],
                y: p[1],
                z: p[2],
            })
            .collect(),
    )
}

/// The one entry point the CLI and the explorer both use.
pub fn build_positioned_graph(graph: CytoscapeGraph, mode: LayoutMode) -> PositionedGraph {
    let layout = match mode {
        LayoutMode::TwoD => layout_2d(&graph),
        LayoutMode::ThreeD => layout_3d(&graph),
    };
    PositionedGraph { graph, layout }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml layout3d_test`
Expected: PASS, all ten tests. If `connected_nodes_end_up_closer_than_unconnected_ones` fails, do not weaken the assertion — a force-directed layout that doesn't pull connected nodes together is broken, and the likely cause is a sign error in `refine` (repulsion pushes `i` along `+delta` where `delta = positions[i] - positions[j]`; attraction pulls `a` along `-delta`).

- [ ] **Step 5: Re-run the whole crate plus the wasm check**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml`
Expected: PASS — every Phase 0 test still green (nothing in this milestone touched them).
Run: `cargo check -p systhread-core --manifest-path rust/Cargo.toml --target wasm32-unknown-unknown`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add rust/systhread-core/src/layout3d.rs rust/systhread-core/tests/layout3d_test.rs
git commit -m "systhread-core: deterministic force-directed 2D/3D layout and build_positioned_graph"
```

**Milestone A complete.** PR boundary: `systhread-core` can turn any of the three tracks into a byte-stable `PositionedGraph`, in either dimensionality, with no CLI or renderer involved yet.

---

## Milestone B: the CLI artifact

### Task 5: `systhread render --explorer` and its manifest entry

**Files:**
- Create: `rust/systhread-cli/src/explorer.rs`
- Modify: `rust/systhread-cli/src/lib.rs`
- Modify: `rust/systhread-cli/src/main.rs`
- Modify: `rust/systhread-cli/src/commands/render.rs`
- Modify: `rust/systhread-cli/systhread.just`
- Test: `rust/systhread-cli/tests/explorer_render_test.rs`

**Interfaces:**
- Consumes: `systhread_core::cytoscape::from_iso_ir`, `systhread_core::layout3d::{build_positioned_graph, LayoutMode}`, `systhread_core::positioned::PositionedGraph::to_json` (Tasks 1–4); the existing `track::Track` and `systhread_core::iso_ir::extract_*`.
- Produces: `explorer::ExplorerLayout` (`TwoD` | `ThreeD`, clap value names `2d`/`3d`) with `ExplorerLayout::mode(self) -> LayoutMode`; `commands::render::run_with_explorer(track: Track, path: &Path, out: &Path, explorer: Option<ExplorerLayout>) -> Result<Vec<PathBuf>, String>`; the artifact file `{slug}_explorer.json` and its manifest `kind` string `"positioned_graph_json"` — Task 7's fixture generation and Task 12's bundle both depend on that exact filename.

**Design note — why `run_with_explorer` instead of changing `run`:** `commands::render::run(track, path, out)` is called from `mcp.rs:59` and from three existing test files. Adding a fourth parameter to it would churn all of those for no behavioural gain, so `run` stays and delegates. The MCP tool surface deliberately does **not** gain an explorer parameter in v1 — FR2's MCP tools expose `check`/`render` as they are, and there is no consumer asking for explorer output over MCP yet (YAGNI).

- [ ] **Step 1: Write the failing test**

`rust/systhread-cli/tests/explorer_render_test.rs`:

```rust
use std::path::PathBuf;
use std::process::Command;

fn systhread_bin() -> &'static str {
    env!("CARGO_BIN_EXE_systhread")
}

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures").join(name)
}

fn render_explorer(out_dir: &PathBuf, layout: &str) {
    std::fs::create_dir_all(out_dir).unwrap();
    let output = Command::new(systhread_bin())
        .args(["render", "--track", "pipeline"])
        .arg(fixture("pipeline_phases_instances.yaml"))
        .arg("--out")
        .arg(out_dir)
        .args(["--explorer", "--explorer-layout", layout])
        .output()
        .unwrap();
    assert!(output.status.success(), "stderr: {}", String::from_utf8_lossy(&output.stderr));
}

#[test]
fn explorer_flag_writes_a_positioned_graph_and_lists_it_in_the_manifest() {
    let out_dir = std::env::temp_dir().join(format!("systhread_explorer_{}", std::process::id()));
    render_explorer(&out_dir, "3d");

    let artifact = out_dir.join("pipeline_explorer.json");
    assert!(artifact.exists(), "expected {}", artifact.display());

    let text = std::fs::read_to_string(&artifact).unwrap();
    assert!(text.contains("\"three_d\""), "layout variant should be self-describing: {text}");
    assert!(text.ends_with("}\n"));

    let manifest: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(out_dir.join("manifest.json")).unwrap())
            .unwrap();
    let entry = manifest["artifacts"]
        .as_array()
        .unwrap()
        .iter()
        .find(|a| a["path"] == "pipeline_explorer.json")
        .expect("the explorer artifact must appear in the manifest");
    assert_eq!(entry["kind"], "positioned_graph_json");
    assert!(entry["content_hash"].as_str().unwrap().starts_with("sha256:"));

    std::fs::remove_dir_all(&out_dir).ok();
}

#[test]
fn explorer_layout_2d_selects_the_flat_variant() {
    let out_dir = std::env::temp_dir().join(format!("systhread_explorer_2d_{}", std::process::id()));
    render_explorer(&out_dir, "2d");
    let text = std::fs::read_to_string(out_dir.join("pipeline_explorer.json")).unwrap();
    assert!(text.contains("\"two_d\""));
    std::fs::remove_dir_all(&out_dir).ok();
}

#[test]
fn repeated_renders_are_byte_identical() {
    let a = std::env::temp_dir().join(format!("systhread_explorer_a_{}", std::process::id()));
    let b = std::env::temp_dir().join(format!("systhread_explorer_b_{}", std::process::id()));
    render_explorer(&a, "3d");
    render_explorer(&b, "3d");
    assert_eq!(
        std::fs::read(a.join("pipeline_explorer.json")).unwrap(),
        std::fs::read(b.join("pipeline_explorer.json")).unwrap()
    );
    std::fs::remove_dir_all(&a).ok();
    std::fs::remove_dir_all(&b).ok();
}

#[test]
fn without_the_flag_no_explorer_artifact_is_written() {
    let out_dir = std::env::temp_dir().join(format!("systhread_no_explorer_{}", std::process::id()));
    std::fs::create_dir_all(&out_dir).unwrap();
    let output = Command::new(systhread_bin())
        .args(["render", "--track", "pipeline"])
        .arg(fixture("pipeline_phases_instances.yaml"))
        .arg("--out")
        .arg(&out_dir)
        .output()
        .unwrap();
    assert!(output.status.success());
    assert!(!out_dir.join("pipeline_explorer.json").exists());

    let manifest: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(out_dir.join("manifest.json")).unwrap())
            .unwrap();
    assert_eq!(manifest["artifacts"].as_array().unwrap().len(), 3);

    std::fs::remove_dir_all(&out_dir).ok();
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p systhread-cli --manifest-path rust/Cargo.toml explorer_render_test`
Expected: FAIL — `--explorer` is an unrecognized argument, so the CLI exits non-zero and the first assertion (`output.status.success()`) trips.

- [ ] **Step 3: Write the implementation**

`rust/systhread-cli/src/explorer.rs`:

```rust
use systhread_core::layout3d::LayoutMode;

/// Which explorer geometry `--explorer` should compute. Its clap value names are `2d`/`3d`
/// because that is what a user types; the Rust variant names match `LayoutMode`'s.
#[derive(Clone, Copy, Debug, clap::ValueEnum)]
pub enum ExplorerLayout {
    #[value(name = "2d")]
    TwoD,
    #[value(name = "3d")]
    ThreeD,
}

impl ExplorerLayout {
    pub fn mode(self) -> LayoutMode {
        match self {
            ExplorerLayout::TwoD => LayoutMode::TwoD,
            ExplorerLayout::ThreeD => LayoutMode::ThreeD,
        }
    }
}
```

Add to `rust/systhread-cli/src/lib.rs`:

```rust
pub mod explorer;
```

In `rust/systhread-cli/src/main.rs`, change the import line and the `Render` variant, then its match arm:

```rust
use systhread_cli::{commands, explorer::ExplorerLayout, mcp, track::Track};
```

```rust
    /// Generate, validate, translate to iso-IR, and render SVG + a ledgrrr manifest.
    Render {
        #[arg(long, value_enum)]
        track: Track,
        path: PathBuf,
        #[arg(long)]
        out: PathBuf,
        /// Also emit the explorer's PositionedGraph JSON (FR7).
        #[arg(long)]
        explorer: bool,
        /// Geometry for --explorer. Ignored without it.
        #[arg(long, value_enum, default_value = "3d")]
        explorer_layout: ExplorerLayout,
    },
```

```rust
        Some(Commands::Render { track, path, out, explorer, explorer_layout }) => {
            let explorer = explorer.then_some(explorer_layout);
            match commands::render::run_with_explorer(track, &path, &out, explorer) {
                Ok(paths) => {
                    for p in paths {
                        println!("wrote {}", p.display());
                    }
                    std::process::ExitCode::SUCCESS
                }
                Err(e) => {
                    eprintln!("systhread render: {e}");
                    std::process::ExitCode::FAILURE
                }
            }
        }
```

In `rust/systhread-cli/src/commands/render.rs`, change the imports, split `run`, extend the track match to also build the graph, and rebuild the artifact list:

```rust
use crate::explorer::ExplorerLayout;
use crate::track::Track;
use serde_json::json;
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};
use systhread_core::cytoscape::{self, CytoscapeGraph};
use systhread_core::{instances, iso_ir, layout3d, render as core_render, sysml_gen, validate};

/// Unchanged behaviour for every existing caller (`mcp.rs`, the Phase 1 tests): render without
/// the explorer artifact.
pub fn run(track: Track, path: &Path, out: &Path) -> Result<Vec<PathBuf>, String> {
    run_with_explorer(track, path, out, None)
}

pub fn run_with_explorer(
    track: Track,
    path: &Path,
    out: &Path,
    explorer: Option<ExplorerLayout>,
) -> Result<Vec<PathBuf>, String> {
    std::fs::create_dir_all(out).map_err(|e| format!("create {}: {e}", out.display()))?;
    let slug = track.slug();

    // The iso-IR builders re-run `extract_*` internally; calling it again here to build the
    // Cytoscape graph is a pure, cheap repeat over already-loaded structs, not a second parse.
    let (sysml_text, iso_ir_value, graph): (String, serde_json::Value, CytoscapeGraph) = match track
    {
        Track::DigitalThread => {
            let inst = instances::load_digital_thread(path)?;
            if inst.agents.is_empty() && inst.mcp_servers.is_empty() && inst.data_sources.is_empty()
            {
                return Err(crate::commands::check::empty_instances_error(path, track));
            }
            let (nodes, edges) = iso_ir::extract_digital_thread(&inst);
            (
                sysml_gen::render_digital_thread(&inst),
                iso_ir::build_digital_thread_iso_ir(&inst),
                cytoscape::from_iso_ir(&nodes, &edges),
            )
        }
        Track::Grid => {
            let inst = instances::load_grid(path)?;
            if inst.buses.is_empty() && inst.generators.is_empty() && inst.lines.is_empty() {
                return Err(crate::commands::check::empty_instances_error(path, track));
            }
            let (nodes, edges) = iso_ir::extract_grid(&inst);
            (
                sysml_gen::render_grid_topology(&inst),
                iso_ir::build_grid_iso_ir(&inst),
                cytoscape::from_iso_ir(&nodes, &edges),
            )
        }
        Track::Pipeline => {
            let inst = instances::load_pipeline(path)?;
            if inst.phases.is_empty() {
                return Err(crate::commands::check::empty_instances_error(path, track));
            }
            let (nodes, edges) = iso_ir::extract_pipeline(&inst);
            (
                sysml_gen::render_pipeline_phases(&inst),
                iso_ir::build_pipeline_iso_ir(&inst),
                cytoscape::from_iso_ir(&nodes, &edges),
            )
        }
    };

    validate::is_valid_sysml(&sysml_text)?;

    let svg_text = core_render::render_svg(&iso_ir_value);
    let iso_ir_text = serde_json::to_string_pretty(&iso_ir_value).map_err(|e| e.to_string())? + "\n";

    let sysml_path = out.join(format!("{slug}.sysml"));
    let svg_path = out.join(format!("{slug}.svg"));
    let iso_ir_path = out.join(format!("{slug}_iso_ir.json"));

    std::fs::write(&sysml_path, &sysml_text)
        .map_err(|e| format!("write {}: {e}", sysml_path.display()))?;
    std::fs::write(&svg_path, &svg_text)
        .map_err(|e| format!("write {}: {e}", svg_path.display()))?;
    std::fs::write(&iso_ir_path, &iso_ir_text)
        .map_err(|e| format!("write {}: {e}", iso_ir_path.display()))?;

    let mut artifacts: Vec<(PathBuf, &'static str)> = vec![
        (sysml_path, "sysml"),
        (svg_path, "svg"),
        (iso_ir_path, "iso_ir_json"),
    ];

    if let Some(layout) = explorer {
        let positioned = layout3d::build_positioned_graph(graph, layout.mode());
        let explorer_path = out.join(format!("{slug}_explorer.json"));
        std::fs::write(&explorer_path, positioned.to_json())
            .map_err(|e| format!("write {}: {e}", explorer_path.display()))?;
        artifacts.push((explorer_path, "positioned_graph_json"));
    }

    let mut manifest_artifacts = Vec::new();
    for (artifact_path, kind) in &artifacts {
        let bytes = std::fs::read(artifact_path)
            .map_err(|e| format!("read back {}: {e}", artifact_path.display()))?;
        let hash = format!("sha256:{:x}", Sha256::digest(&bytes));
        let filename = artifact_path
            .file_name()
            .and_then(|n| n.to_str())
            .ok_or_else(|| format!("{} has no valid filename", artifact_path.display()))?
            .to_string();
        manifest_artifacts.push(json!({ "path": filename, "kind": kind, "content_hash": hash }));
    }

    let manifest = json!({ "artifacts": manifest_artifacts });
    let manifest_path = out.join("manifest.json");
    let manifest_text = serde_json::to_string_pretty(&manifest).map_err(|e| e.to_string())? + "\n";
    std::fs::write(&manifest_path, &manifest_text)
        .map_err(|e| format!("write {}: {e}", manifest_path.display()))?;

    let mut written: Vec<PathBuf> = artifacts.into_iter().map(|(p, _)| p).collect();
    written.push(manifest_path);
    Ok(written)
}
```

Append to `rust/systhread-cli/systhread.just`:

```just
# Render one track AND the explorer's PositionedGraph JSON (layout: 2d | 3d, default 3d).
sysml-render-explorer track path out layout="3d":
    cd {{justfile_directory()}} && systhread render --track {{track}} {{path}} --out {{out}} --explorer --explorer-layout {{layout}}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p systhread-cli --manifest-path rust/Cargo.toml explorer_render_test`
Expected: PASS, all four tests.

- [ ] **Step 5: Run the whole CLI suite to confirm nothing regressed**

Run: `cargo test -p systhread-cli --manifest-path rust/Cargo.toml`
Expected: PASS — in particular `render_test`, `manifest_test`, `mcp_dispatch_test` and `mcp_server_test`, which all go through the unchanged three-argument `run` and must still see exactly three artifacts plus the manifest, in the original order.

- [ ] **Step 6: Commit**

```bash
git add rust/systhread-cli/src/explorer.rs rust/systhread-cli/src/lib.rs rust/systhread-cli/src/main.rs rust/systhread-cli/src/commands/render.rs rust/systhread-cli/systhread.just rust/systhread-cli/tests/explorer_render_test.rs
git commit -m "systhread-cli: systhread render --explorer emits a manifest-described PositionedGraph JSON"
```

**Milestone B complete.** PR boundary: the explorer's data artifact is real, reproducible, manifest-described, and reachable from both the CLI and the `just` module.

---

## Milestone C: the ouroboros gate (native + `wasm32-unknown-unknown`)

### Task 6: wasm test harness — runner config, dev-dependency, CLI version, `just` wiring

**Files:**
- Create: `.cargo/config.toml` (repo root)
- Modify: `rust/systhread-core/Cargo.toml`
- Modify: `Justfile`
- Test: `rust/systhread-core/tests/wasm_smoke_test.rs`

**Interfaces:**
- Consumes: `layout3d::{LAYOUT_SEED, LAYOUT_ITERATIONS}` (Task 3).
- Produces: a working `cargo test --target wasm32-unknown-unknown` path for `systhread-core`, and the `just check-systhread-wasm` recipe Task 7 extends. No Rust API.

**Design note — why the config file lives at the repo root:** cargo discovers `.cargo/config.toml` by walking up from the **current working directory**, not from `--manifest-path`. This repo's recipes all run cargo from the repo root with `--manifest-path rust/Cargo.toml`, so a `rust/.cargo/config.toml` would be silently ignored. The root file adds exactly one key — a runner for one target that nothing else in this repo builds. Confirmed during planning that no `.cargo/` directory exists at the repo root yet; if one has appeared by execution time, append the section rather than overwriting the file.

- [ ] **Step 1: Write the failing test**

`rust/systhread-core/tests/wasm_smoke_test.rs`:

```rust
//! The wasm half of the ouroboros requirement (design §6): proof that this crate's code really is
//! compiled and executed on `wasm32-unknown-unknown`, not merely type-checked for it. The whole
//! file compiles away to nothing on native targets.
#![cfg(target_arch = "wasm32")]

use wasm_bindgen_test::wasm_bindgen_test;

#[wasm_bindgen_test]
fn layout_constants_survive_the_wasm_build() {
    assert_eq!(systhread_core::layout3d::LAYOUT_SEED, 0x5359_5354_4852_4544);
    assert_eq!(systhread_core::layout3d::LAYOUT_ITERATIONS, 300);
}

#[wasm_bindgen_test]
fn the_layout_solver_runs_under_wasm() {
    use systhread_core::cytoscape::{CytoscapeGraph, CytoscapeNode, CytoscapeNodeData};
    let node = |id: &str| CytoscapeNode {
        data: CytoscapeNodeData {
            id: id.to_string(),
            label: id.to_string(),
            kind: "Bus".to_string(),
            parent: None,
            z_layer: None,
            semantic_type: None,
        },
    };
    let graph = CytoscapeGraph { nodes: vec![node("a"), node("b")], edges: vec![] };
    assert_eq!(systhread_core::layout3d::layout_3d(&graph).len(), 2);
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml --target wasm32-unknown-unknown --test wasm_smoke_test`
Expected: FAIL to compile — `wasm_bindgen_test` is not a dependency. (If cargo instead reports it cannot run the test binary, that is the missing runner from Step 3 — both failures are expected at this point and both are fixed below.)

- [ ] **Step 3: Wire the harness**

Create `.cargo/config.toml` at the **repo root**:

```toml
# `cargo test --target wasm32-unknown-unknown` needs a runner that can execute a wasm module.
# wasm-bindgen-test-runner drives it under Node (no browser or webdriver involved). This exists
# for systhread-core's ouroboros test (docs/superpowers/specs/2026-08-26-systhread-3d-explorer-design.md
# §6); no other crate in this repo targets wasm today.
[target.wasm32-unknown-unknown]
runner = "wasm-bindgen-test-runner"
```

Append to `rust/systhread-core/Cargo.toml`:

```toml
# wasm-only dev-dependency: the native test build is completely unaffected by it.
# 0.3.77 pins wasm-bindgen =0.2.127, so the installed wasm-bindgen-cli must be 0.2.127 too --
# `just systhread-wasm-setup` installs the matching pair.
[target.'cfg(target_arch = "wasm32")'.dev-dependencies]
wasm-bindgen-test = "0.3.77"
```

Add to the repo-root `Justfile`, next to the existing `check-systhread-core` recipe:

```just
# One-time (idempotent) setup for the wasm half of systhread's ouroboros test.
# wasm-bindgen-test 0.3.77 pins wasm-bindgen =0.2.127; the CLI must match exactly or the runner
# rejects the module with a schema-version error.
systhread-wasm-setup:
    rustup target add wasm32-unknown-unknown
    cargo install -f wasm-bindgen-cli --version 0.2.127

# The ouroboros gate: systhread-core's own code, compiled to wasm32 and actually executed.
check-systhread-wasm:
    cargo test -p systhread-core --manifest-path rust/Cargo.toml --target wasm32-unknown-unknown --test wasm_smoke_test
```

and append `check-systhread-wasm` to the `check:` dependency list, keeping every existing entry:

```just
check: check-lab1 check-lab2 check-lab3 check-lab4 check-lab5 check-lab6 check-lab7 check-lab8 check-lab9 check-systhread-core check-systhread-wasm
```

- [ ] **Step 4: Install the matching CLI and run the test to verify it passes**

Run: `just systhread-wasm-setup`
(Planning found `wasm-bindgen 0.2.126` installed against a required `=0.2.127` — this step is the fix, not a precaution. Confirm with `wasm-bindgen --version` afterwards.)

Run: `just check-systhread-wasm`
Expected: PASS, 2 tests, executed under Node. If the runner reports a schema-version mismatch ("rust wasm file schema version: X, this binary schema version: Y"), the CLI and the crate are still out of step — re-run `cargo install -f wasm-bindgen-cli --version <the version cargo resolved for the wasm-bindgen crate>`, which you can read from `rust/Cargo.lock`.

- [ ] **Step 5: Confirm the native suite is untouched**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml`
Expected: PASS — `wasm_smoke_test` compiles to an empty test binary on native (0 tests), everything else green.

- [ ] **Step 6: Commit**

```bash
git add .cargo/config.toml Justfile rust/systhread-core/Cargo.toml rust/systhread-core/tests/wasm_smoke_test.rs
git commit -m "systhread-core: wasm32 test harness (wasm-bindgen-test runner) and just check wiring"
```

---

### Task 7: the real ouroboros round-trip — native-produced bytes, wasm-side consumption

**Files:**
- Create: `rust/systhread-core/tests/fixtures/explorer/grid_explorer_3d.json` (generated by the real CLI, then committed)
- Create: `rust/systhread-core/tests/ouroboros_native_test.rs`
- Create: `rust/systhread-core/tests/ouroboros_wasm_test.rs`
- Modify: `Justfile`

**Interfaces:**
- Consumes: `instances::load_grid`, `iso_ir::extract_grid`, `cytoscape::from_iso_ir`, `layout3d::{build_positioned_graph, LayoutMode}`, `positioned::PositionedGraph::{to_json, from_json, layout_matches_graph}`; the `systhread render --explorer` CLI path (Task 5); `common::fixture_path`.
- Produces: the committed artifact fixture every later task can point a viewer at, and the CI gate design §6 mandates. No Rust API.

**Design note:** design §6 asks for "a test that generates a `PositionedGraph` on the native target, loads the same bytes through the wasm-compiled deserialization path ... and asserts structural equality". That is split here into three assertions, because they fail for different reasons and a single test would hide which: (a) native regeneration still produces the committed bytes exactly — catches an accidental layout or serialization change; (b) wasm deserializes those bytes and re-serializes them byte-identically — the actual cross-target (de)serialization round-trip; (c) wasm *recomputes* the layout from the same graph and gets the same coordinates — the strongest form, and the one that would expose a genuine cross-target float divergence. (c) is expected to pass because the solver uses only IEEE-exact operations (Task 4's design note). **If (c) fails, that is real, load-bearing information: do not delete it and do not loosen it to an epsilon comparison.** Investigate with `superpowers:systematic-debugging`, and if the divergence is genuine, the honest outcome is a documented note that native layout output is authoritative and wasm must consume rather than recompute — reported back, not patched over.

- [ ] **Step 1: Generate the fixture with the real CLI and commit it**

```bash
mkdir -p rust/systhread-core/tests/fixtures/explorer
cargo run -p systhread-cli --manifest-path rust/Cargo.toml -- render --track grid \
  rust/systhread-core/tests/fixtures/lab6/schema/grid_instances.yaml \
  --out /tmp/systhread-explorer-fixture --explorer --explorer-layout 3d
cp /tmp/systhread-explorer-fixture/grid_explorer.json \
   rust/systhread-core/tests/fixtures/explorer/grid_explorer_3d.json
```

Sanity-check by eye before continuing: the file should start with `{`, contain `"three_d"`, list 20 node entries under `"nodes"` (15 buses + 5 generators — the grid track's real node count), and end with `}` plus a newline.

- [ ] **Step 2: Write the failing tests**

`rust/systhread-core/tests/ouroboros_native_test.rs`:

```rust
mod common;
use common::fixture_path;
use systhread_core::cytoscape::from_iso_ir;
use systhread_core::instances::load_grid;
use systhread_core::iso_ir::extract_grid;
use systhread_core::layout3d::{build_positioned_graph, LayoutMode};
use systhread_core::positioned::PositionedGraph;

/// The committed artifact, as produced by `systhread render --track grid --explorer` (Task 7
/// Step 1). Its bytes are the input to the wasm side of the ouroboros test, so this test exists
/// to keep them honest: if the layout or the serialization ever changes, this fails first and
/// says so, instead of the wasm test failing mysteriously.
fn committed_artifact() -> String {
    std::fs::read_to_string(fixture_path("../explorer/grid_explorer_3d.json"))
        .expect("Task 7 Step 1 generates and commits this fixture")
}

fn rebuild() -> PositionedGraph {
    let inst = load_grid(&fixture_path("schema/grid_instances.yaml")).unwrap();
    let (nodes, edges) = extract_grid(&inst);
    build_positioned_graph(from_iso_ir(&nodes, &edges), LayoutMode::ThreeD)
}

#[test]
fn native_regeneration_reproduces_the_committed_artifact_byte_for_byte() {
    assert_eq!(rebuild().to_json(), committed_artifact());
}

#[test]
fn the_committed_artifact_parses_and_is_internally_consistent() {
    let parsed = PositionedGraph::from_json(&committed_artifact()).unwrap();
    assert!(parsed.layout_matches_graph());
    assert_eq!(parsed.layout.len(), parsed.graph.nodes.len());
    assert!(!parsed.graph.edges.is_empty(), "the grid track has real edges");
}
```

`rust/systhread-core/tests/ouroboros_wasm_test.rs`:

```rust
//! Design §6's ouroboros gate: bytes produced by this crate on the native target, consumed by
//! this same crate compiled to `wasm32-unknown-unknown`. Empty on native targets.
#![cfg(target_arch = "wasm32")]

use systhread_core::layout3d::{build_positioned_graph, LayoutMode};
use systhread_core::positioned::PositionedGraph;
use wasm_bindgen_test::wasm_bindgen_test;

/// The exact bytes `systhread render --explorer` wrote on the native target, embedded at compile
/// time because `wasm32-unknown-unknown` has no filesystem to read them from at runtime.
const NATIVE_ARTIFACT: &str = include_str!("fixtures/explorer/grid_explorer_3d.json");

#[wasm_bindgen_test]
fn wasm_deserializes_the_native_artifact_and_reserializes_it_identically() {
    let parsed = PositionedGraph::from_json(NATIVE_ARTIFACT).expect("native artifact must parse");
    assert!(parsed.layout_matches_graph());
    assert_eq!(parsed.layout.len(), parsed.graph.nodes.len());
    assert_eq!(parsed.to_json(), NATIVE_ARTIFACT);
}

#[wasm_bindgen_test]
fn wasm_recomputation_agrees_with_the_native_layout() {
    // The strongest form of the round-trip: same graph, same solver, different target. It holds
    // because the solver uses only IEEE-754-exact operations (+ - * / sqrt). If this ever fails,
    // see this task's design note -- it is a real finding, not a test to loosen.
    let native = PositionedGraph::from_json(NATIVE_ARTIFACT).unwrap();
    let recomputed = build_positioned_graph(native.graph.clone(), LayoutMode::ThreeD);
    assert_eq!(recomputed.layout, native.layout);
}
```

- [ ] **Step 3: Run both to verify they fail for the right reason**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml ouroboros_native_test`
Expected: PASS immediately — the fixture was generated from this exact code path in Step 1. (This test is a regression guard, not a red-then-green step; if it *fails* now, the CLI and the library disagree, which is a real bug to fix before continuing.)

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml --target wasm32-unknown-unknown --test ouroboros_wasm_test`
Expected: PASS, 2 tests, under Node.

- [ ] **Step 4: Add the wasm test to the gate**

In the repo-root `Justfile`, extend the `check-systhread-wasm` recipe to run both wasm test targets:

```just
check-systhread-wasm:
    cargo test -p systhread-core --manifest-path rust/Cargo.toml --target wasm32-unknown-unknown --test wasm_smoke_test --test ouroboros_wasm_test
```

- [ ] **Step 5: Run the gate**

Run: `just check-systhread-wasm`
Expected: PASS, 4 tests total.
Run: `just check-systhread-core`
Expected: PASS, including the two new native tests.

- [ ] **Step 6: Commit**

```bash
git add rust/systhread-core/tests/fixtures/explorer/grid_explorer_3d.json rust/systhread-core/tests/ouroboros_native_test.rs rust/systhread-core/tests/ouroboros_wasm_test.rs Justfile
git commit -m "systhread-core: ouroboros gate -- native-produced PositionedGraph bytes consumed by the wasm build"
```

**Milestone C complete.** PR boundary: design §6's testing requirement is satisfied by a real, CI-wired test, before any renderer exists to depend on it.

---

## Milestone D: the `systhread-explorer` crate

### Task 8: crate scaffold and the target-agnostic loader

**Files:**
- Modify: `rust/Cargo.toml`
- Create: `rust/systhread-explorer/Cargo.toml`
- Create: `rust/systhread-explorer/src/lib.rs`
- Create: `rust/systhread-explorer/src/loader.rs`
- Modify: `Justfile`
- Test: `rust/systhread-explorer/tests/loader_test.rs`

**Interfaces:**
- Consumes: `systhread_core::positioned::{PositionedGraph, Layout, NodePosition3D}` and `systhread_core::layout3d::{build_positioned_graph, LayoutMode}` (Milestone A).
- Produces: the `systhread-explorer` crate (library `systhread_explorer`, binary `systhread-explorer` gated on the `explorer-3d` feature); `loader::load_positioned_graph(json: &str) -> Result<PositionedGraph, String>`; the `explorer-3d` Cargo feature. Tasks 9–12 build inside this crate; Task 10's asset loader calls `load_positioned_graph`.

**Design note — why Bevy is `optional` and off by default:** the crate's Bevy-free half (this task's `loader`, Task 9's `scene`) is the part that has to compile for *both* targets and be unit-testable without a GPU, and it is also the only part `just check` needs to build on a headless machine. Making Bevy an optional dependency behind `explorer-3d` means a default `cargo check`/`cargo test` of this crate compiles no Bevy at all. The feature list itself is quoted **verbatim** from the spike recorded in Verified During Planning #1 — do not "tidy" it, and do not replace any entry with a Bevy meta-feature. Note that `"bevy/bevy_pbr"`-style entries implicitly enable the optional `bevy` dependency (that is cargo's `pkg/feat` rule), which is why no `"dep:bevy"` entry is needed and none was in the verified list.

- [ ] **Step 1: Write the failing test**

`rust/systhread-explorer/tests/loader_test.rs`:

```rust
use systhread_core::cytoscape::{
    CytoscapeEdge, CytoscapeEdgeData, CytoscapeGraph, CytoscapeNode, CytoscapeNodeData,
};
use systhread_core::layout3d::{build_positioned_graph, LayoutMode};
use systhread_core::positioned::{Layout, NodePosition3D, PositionedGraph};
use systhread_explorer::loader::load_positioned_graph;

fn node(id: &str) -> CytoscapeNode {
    CytoscapeNode {
        data: CytoscapeNodeData {
            id: id.to_string(),
            label: id.to_string(),
            kind: "Bus".to_string(),
            parent: None,
            z_layer: None,
            semantic_type: None,
        },
    }
}

fn sample_graph() -> CytoscapeGraph {
    CytoscapeGraph {
        nodes: vec![node("a"), node("b"), node("c")],
        edges: vec![CytoscapeEdge {
            data: CytoscapeEdgeData {
                id: "ab".to_string(),
                source: "a".to_string(),
                target: "b".to_string(),
                label: "branch".to_string(),
            },
        }],
    }
}

#[test]
fn loads_a_real_positioned_graph_produced_by_systhread_core() {
    let json = build_positioned_graph(sample_graph(), LayoutMode::ThreeD).to_json();
    let loaded = load_positioned_graph(&json).unwrap();
    assert_eq!(loaded.graph.nodes.len(), 3);
    assert!(matches!(loaded.layout, Layout::ThreeD(_)));
}

#[test]
fn rejects_malformed_json_with_a_message_naming_the_problem() {
    let err = load_positioned_graph("{ nope").unwrap_err();
    assert!(err.contains("PositionedGraph"), "unhelpful error: {err}");
}

#[test]
fn rejects_a_graph_whose_layout_does_not_line_up_with_its_nodes() {
    // A hand-edited or truncated artifact must be refused at load time, not indexed into later.
    let broken = PositionedGraph {
        graph: sample_graph(),
        layout: Layout::ThreeD(vec![NodePosition3D {
            node_id: "a".to_string(),
            x: 0.0,
            y: 0.0,
            z: 0.0,
        }]),
    };
    let err = load_positioned_graph(&broken.to_json()).unwrap_err();
    assert!(err.contains("layout"), "unhelpful error: {err}");
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p systhread-explorer --manifest-path rust/Cargo.toml`
Expected: FAIL — cargo errors before compiling anything: "package ID specification `systhread-explorer` matched no packages".

- [ ] **Step 3: Write the scaffold and the loader**

Add `"systhread-explorer"` to `rust/Cargo.toml`'s workspace members, keeping every existing entry:

```toml
[workspace]
members = ["phase-model", "demo-app", "fft-detector", "lab-launcher", "mission-engine", "systhread-core", "systhread-cli", "systhread-explorer"]
resolver = "2"
```

`rust/systhread-explorer/Cargo.toml`:

```toml
[package]
name = "systhread-explorer"
version = "0.1.0"
edition = "2024"
publish = false
description = "v1 of the systhread model explorer (docs/superpowers/specs/2026-08-26-systhread-3d-explorer-design.md): a Bevy app, compiled to wasm32-unknown-unknown, that renders a PositionedGraph artifact."

[lib]
name = "systhread_explorer"
path = "src/lib.rs"

[[bin]]
name = "systhread-explorer"
path = "src/main.rs"
required-features = ["explorer-3d"]

[dependencies]
systhread-core = { path = "../systhread-core" }
# Optional so that a default `cargo check`/`cargo test` of this crate -- the loader and scene
# math, which must build for both targets on a headless machine -- compiles no Bevy at all.
bevy = { version = "0.19", default-features = false, features = ["std", "bevy_log", "async_executor"], optional = true }

[features]
default = []
# Explicit component list, never a Bevy meta-feature. bevy 0.19.1 was published with broken
# sub-crate pins (`bevy_animation 0.19.1` and `bevy_picking 0.19.1` were never published), so every
# meta-feature path that reaches them -- `ui` -> `default_app` -> `scene`, and `webgl2`/`webgpu`/
# `web` -> `bevy_dev_tools` -> `bevy_picking` -- fails to resolve on crates.io today. This exact
# list was verified with `cargo check --target wasm32-unknown-unknown` (exit 0) and with
# `cargo tree -i bevy_animation`/`bevy_gltf`/`bevy_scene` confirming none of the three are anywhere
# in the resolved graph. `rust/mission-engine/Cargo.toml`'s `interactive` feature is the same
# workaround for the 2D/UI case.
explorer-3d = ["bevy/bevy_pbr", "bevy/bevy_render", "bevy/bevy_core_pipeline", "bevy/bevy_asset", "bevy/bevy_winit", "bevy/bevy_window"]
```

`rust/systhread-explorer/src/lib.rs`:

```rust
//! The systhread model explorer. See
//! `docs/superpowers/specs/2026-08-26-systhread-3d-explorer-design.md`.
//!
//! The crate is split so that everything except the ECS layer is Bevy-free and target-agnostic:
//! `loader` and `scene` compile (and are tested) on native and `wasm32-unknown-unknown` with no
//! Bevy and no GPU, and the `explorer-3d` modules only turn already-computed data into entities.
//! That split is what makes the geometry unit-testable at all -- see design §6 on not settling for
//! a visual smoke check.

pub mod loader;
```

`rust/systhread-explorer/src/loader.rs`:

```rust
use systhread_core::positioned::PositionedGraph;

/// Parses a `PositionedGraph` artifact and refuses one whose layout does not line up with its
/// graph. Everything downstream indexes nodes and positions in parallel, so this is the single
/// place that invariant is enforced -- after this returns `Ok`, `scene::scene_spec` is infallible.
pub fn load_positioned_graph(json: &str) -> Result<PositionedGraph, String> {
    let graph = PositionedGraph::from_json(json)?;
    if !graph.layout_matches_graph() {
        return Err(format!(
            "PositionedGraph layout does not match its graph: {} nodes but {} layout entries (or ids in a different order)",
            graph.graph.nodes.len(),
            graph.layout.len()
        ));
    }
    Ok(graph)
}
```

Add to the repo-root `Justfile`, next to the other systhread recipes:

```just
check-systhread-explorer:
    cargo test -p systhread-explorer --manifest-path rust/Cargo.toml
    cargo check -p systhread-explorer --manifest-path rust/Cargo.toml --target wasm32-unknown-unknown
```

and append `check-systhread-explorer` to the `check:` dependency list, keeping every existing entry.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p systhread-explorer --manifest-path rust/Cargo.toml`
Expected: PASS, all three tests, and note that no Bevy crates appear in the build output (the default feature set has none).

- [ ] **Step 5: Verify both targets, including the Bevy feature set**

Run: `cargo check -p systhread-explorer --manifest-path rust/Cargo.toml --target wasm32-unknown-unknown`
Expected: exit 0 (default features — the "one crate, two targets" property, now held by this crate too).

Run: `cargo check -p systhread-explorer --manifest-path rust/Cargo.toml --features explorer-3d --target wasm32-unknown-unknown`
Expected: exit 0, a few minutes cold. This is the first in-repo confirmation of the verified feature list. If it fails to *resolve* (not compile), read the error for which sub-crate is missing a `0.19.1` publish and report it — do not start adding meta-features.

- [ ] **Step 6: Commit**

```bash
git add rust/Cargo.toml rust/systhread-explorer/ Justfile
git commit -m "systhread-explorer: crate scaffold, target-agnostic PositionedGraph loader, explorer-3d feature"
```

---

### Task 9: `scene.rs` — all the geometry, with no Bevy in sight

**Files:**
- Create: `rust/systhread-explorer/src/scene.rs`
- Modify: `rust/systhread-explorer/src/lib.rs`
- Test: `rust/systhread-explorer/tests/scene_test.rs`

**Interfaces:**
- Consumes: `systhread_core::positioned::{PositionedGraph, Layout}` (Task 2); `loader::load_positioned_graph` guarantees the layout/graph invariant (Task 8).
- Produces: `scene::{SceneSpec, NodeVisual, EdgeVisual}`; `scene::scene_spec(graph: &PositionedGraph) -> SceneSpec`; `scene::{NODE_RADIUS, EDGE_RADIUS, CAMERA_DISTANCE_FACTOR, MIN_CAMERA_DISTANCE}`. Task 11's ECS spawn systems consume `SceneSpec` and nothing else.

**Design note — why this is a separate module from the Bevy app:** a Bevy `App` with a real render pipeline cannot be asserted on in a headless CI process, which is exactly the gap design §6 calls out in Lab 9's `--interactive` feature ("not run visually... claiming a screenshot would be claiming something not done"). Putting every coordinate, length, rotation axis and camera placement in a pure function makes all of it testable for real, and leaves the ECS layer with nothing to get wrong but entity spawning. `EdgeVisual` describes a unit-height cylinder's placement — Bevy's `Cylinder` mesh is Y-aligned and centred on its origin, so Task 11 spawns one shared unit mesh, rotates `Vec3::Y` onto `direction`, and scales Y by `length`.

**Design note — 2D in the 3D viewer:** design §5 says the viewer renders "either mode, selected by which `Layout` variant the JSON contains", so a `Layout::TwoD` artifact is embedded at `z = 0` and flagged `flat: true`, which Task 11 uses to face the camera straight at the plane. This is *not* a second renderer, and it does not collapse the sum type — the two variants still get different camera treatment, which is precisely why design §3 made them different types.

- [ ] **Step 1: Write the failing test**

`rust/systhread-explorer/tests/scene_test.rs`:

```rust
use systhread_core::cytoscape::{
    CytoscapeEdge, CytoscapeEdgeData, CytoscapeGraph, CytoscapeNode, CytoscapeNodeData,
};
use systhread_core::positioned::{Layout, NodePosition2D, NodePosition3D, PositionedGraph};
use systhread_explorer::scene::{scene_spec, MIN_CAMERA_DISTANCE, NODE_RADIUS};

fn node(id: &str) -> CytoscapeNode {
    CytoscapeNode {
        data: CytoscapeNodeData {
            id: id.to_string(),
            label: id.to_string(),
            kind: "Bus".to_string(),
            parent: None,
            z_layer: None,
            semantic_type: None,
        },
    }
}

fn edge(id: &str, source: &str, target: &str) -> CytoscapeEdge {
    CytoscapeEdge {
        data: CytoscapeEdgeData {
            id: id.to_string(),
            source: source.to_string(),
            target: target.to_string(),
            label: "branch".to_string(),
        },
    }
}

fn two_node_3d(edges: Vec<CytoscapeEdge>) -> PositionedGraph {
    PositionedGraph {
        graph: CytoscapeGraph { nodes: vec![node("a"), node("b")], edges },
        layout: Layout::ThreeD(vec![
            NodePosition3D { node_id: "a".to_string(), x: -1.0, y: 0.0, z: 0.0 },
            NodePosition3D { node_id: "b".to_string(), x: 1.0, y: 0.0, z: 0.0 },
        ]),
    }
}

#[test]
fn nodes_become_visuals_at_their_layout_positions_in_order() {
    let spec = scene_spec(&two_node_3d(vec![]));
    assert_eq!(spec.nodes.len(), 2);
    assert_eq!(spec.nodes[0].node_id, "a");
    assert_eq!(spec.nodes[0].position, [-1.0, 0.0, 0.0]);
    assert_eq!(spec.nodes[1].position, [1.0, 0.0, 0.0]);
    assert_eq!(spec.nodes[0].radius, NODE_RADIUS);
}

#[test]
fn an_edge_becomes_a_midpoint_a_unit_direction_and_a_length() {
    let spec = scene_spec(&two_node_3d(vec![edge("ab", "a", "b")]));
    assert_eq!(spec.edges.len(), 1);
    let e = &spec.edges[0];
    assert_eq!(e.source_id, "a");
    assert_eq!(e.target_id, "b");
    assert_eq!(e.midpoint, [0.0, 0.0, 0.0]);
    assert_eq!(e.length, 2.0);
    assert_eq!(e.direction, [1.0, 0.0, 0.0]);
}

#[test]
fn edges_naming_unknown_nodes_or_zero_length_are_skipped() {
    let mut pg = two_node_3d(vec![edge("ghost", "a", "nope"), edge("selfloop", "a", "a")]);
    // A zero-length edge between two coincident nodes has no direction to point a cylinder along.
    pg.layout = Layout::ThreeD(vec![
        NodePosition3D { node_id: "a".to_string(), x: 0.0, y: 0.0, z: 0.0 },
        NodePosition3D { node_id: "b".to_string(), x: 0.0, y: 0.0, z: 0.0 },
    ]);
    pg.graph.edges.push(edge("coincident", "a", "b"));
    assert!(scene_spec(&pg).edges.is_empty());
}

#[test]
fn the_camera_is_pulled_back_off_the_model_and_aimed_at_its_centre() {
    let spec = scene_spec(&two_node_3d(vec![edge("ab", "a", "b")]));
    assert_eq!(spec.camera_target, [0.0, 0.0, 0.0]);
    assert!(!spec.flat);
    let d = |a: [f32; 3], b: [f32; 3]| {
        ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)).sqrt()
    };
    assert!(
        d(spec.camera_position, spec.camera_target) >= MIN_CAMERA_DISTANCE,
        "a tiny model must not put the camera inside itself"
    );
}

#[test]
fn a_two_d_layout_is_embedded_flat_and_faced_head_on() {
    let pg = PositionedGraph {
        graph: CytoscapeGraph { nodes: vec![node("a"), node("b")], edges: vec![] },
        layout: Layout::TwoD(vec![
            NodePosition2D { node_id: "a".to_string(), x: -3.0, y: 1.0 },
            NodePosition2D { node_id: "b".to_string(), x: 3.0, y: 1.0 },
        ]),
    };
    let spec = scene_spec(&pg);
    assert!(spec.flat);
    assert!(spec.nodes.iter().all(|n| n.position[2] == 0.0));
    // Facing the plane head-on: the camera differs from its target only along Z.
    assert_eq!(spec.camera_position[0], spec.camera_target[0]);
    assert_eq!(spec.camera_position[1], spec.camera_target[1]);
    assert!(spec.camera_position[2] > spec.camera_target[2]);
}

#[test]
fn an_empty_graph_yields_an_empty_but_valid_scene() {
    let pg = PositionedGraph {
        graph: CytoscapeGraph { nodes: vec![], edges: vec![] },
        layout: Layout::ThreeD(vec![]),
    };
    let spec = scene_spec(&pg);
    assert!(spec.nodes.is_empty());
    assert!(spec.edges.is_empty());
    assert!(spec.camera_position[2].is_finite());
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p systhread-explorer --manifest-path rust/Cargo.toml scene_test`
Expected: FAIL to compile — `systhread_explorer::scene` does not exist yet.

- [ ] **Step 3: Write the implementation**

`rust/systhread-explorer/src/scene.rs`:

```rust
//! Every coordinate, length, rotation axis and camera placement the renderer needs, computed as a
//! pure function of a `PositionedGraph`. No Bevy, no GPU, no window -- so all of it is really
//! tested, rather than assumed from a screenshot nobody took (design §6).

use std::collections::BTreeMap;
use systhread_core::positioned::{Layout, PositionedGraph};

/// Sphere radius for a node, in layout units (`IDEAL_EDGE_LENGTH` is 2.0, so nodes occupy about a
/// quarter of a typical edge).
pub const NODE_RADIUS: f32 = 0.25;
/// Cylinder radius for an edge.
pub const EDGE_RADIUS: f32 = 0.03;
/// How far back the camera sits, as a multiple of the model's largest extent.
pub const CAMERA_DISTANCE_FACTOR: f32 = 1.2;
/// Floor on the camera distance, so a one- or two-node model doesn't put the camera inside a node.
pub const MIN_CAMERA_DISTANCE: f32 = 5.0;

#[derive(Debug, Clone, PartialEq)]
pub struct NodeVisual {
    pub node_id: String,
    pub position: [f32; 3],
    pub radius: f32,
}

/// A unit-height, Y-aligned cylinder's placement: translate to `midpoint`, rotate `Vec3::Y` onto
/// `direction`, scale Y by `length`.
#[derive(Debug, Clone, PartialEq)]
pub struct EdgeVisual {
    pub source_id: String,
    pub target_id: String,
    pub midpoint: [f32; 3],
    pub direction: [f32; 3],
    pub length: f32,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SceneSpec {
    pub nodes: Vec<NodeVisual>,
    pub edges: Vec<EdgeVisual>,
    pub camera_position: [f32; 3],
    pub camera_target: [f32; 3],
    /// True when the source layout was `Layout::TwoD`. The camera then faces the plane head-on and
    /// Task 11 locks orbit pitch: a flat layout has no depth axis worth orbiting around, which is
    /// design §3's 2D/3D distinction carried through to the camera instead of being flattened away.
    pub flat: bool,
}

/// Below this, two nodes are coincident and the edge between them has no direction to point along.
const MIN_EDGE_LENGTH: f32 = 1.0e-6;

fn positions(graph: &PositionedGraph) -> (Vec<[f32; 3]>, bool) {
    match &graph.layout {
        Layout::ThreeD(p) => (
            p.iter().map(|n| [n.x as f32, n.y as f32, n.z as f32]).collect(),
            false,
        ),
        Layout::TwoD(p) => (p.iter().map(|n| [n.x as f32, n.y as f32, 0.0]).collect(), true),
    }
}

/// Infallible: `loader::load_positioned_graph` has already established that the layout has one
/// entry per node, in order, so the zip below cannot mismatch.
pub fn scene_spec(graph: &PositionedGraph) -> SceneSpec {
    let (points, flat) = positions(graph);

    let nodes: Vec<NodeVisual> = graph
        .graph
        .nodes
        .iter()
        .zip(points.iter())
        .map(|(node, position)| NodeVisual {
            node_id: node.data.id.clone(),
            position: *position,
            radius: NODE_RADIUS,
        })
        .collect();

    let index: BTreeMap<&str, usize> = graph
        .graph
        .nodes
        .iter()
        .enumerate()
        .map(|(i, n)| (n.data.id.as_str(), i))
        .collect();

    let edges: Vec<EdgeVisual> = graph
        .graph
        .edges
        .iter()
        .filter_map(|e| {
            let a = points[*index.get(e.data.source.as_str())?];
            let b = points[*index.get(e.data.target.as_str())?];
            let delta = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
            let length =
                (delta[0] * delta[0] + delta[1] * delta[1] + delta[2] * delta[2]).sqrt();
            if length < MIN_EDGE_LENGTH {
                return None;
            }
            Some(EdgeVisual {
                source_id: e.data.source.clone(),
                target_id: e.data.target.clone(),
                midpoint: [
                    (a[0] + b[0]) / 2.0,
                    (a[1] + b[1]) / 2.0,
                    (a[2] + b[2]) / 2.0,
                ],
                direction: [delta[0] / length, delta[1] / length, delta[2] / length],
                length,
            })
        })
        .collect();

    let (camera_position, camera_target) = camera(&points, flat);

    SceneSpec { nodes, edges, camera_position, camera_target, flat }
}

fn camera(points: &[[f32; 3]], flat: bool) -> ([f32; 3], [f32; 3]) {
    if points.is_empty() {
        return ([0.0, 0.0, MIN_CAMERA_DISTANCE], [0.0, 0.0, 0.0]);
    }
    let mut min = points[0];
    let mut max = points[0];
    for p in points {
        for d in 0..3 {
            min[d] = min[d].min(p[d]);
            max[d] = max[d].max(p[d]);
        }
    }
    let target = [
        (min[0] + max[0]) / 2.0,
        (min[1] + max[1]) / 2.0,
        (min[2] + max[2]) / 2.0,
    ];
    let extent = (0..3).fold(0.0_f32, |acc, d| acc.max(max[d] - min[d]));
    let distance = (extent * CAMERA_DISTANCE_FACTOR).max(MIN_CAMERA_DISTANCE);

    let position = if flat {
        // Head-on: the plane fills the view without a perspective skew.
        [target[0], target[1], target[2] + distance]
    } else {
        // Off all three axes, so depth reads immediately on the first frame.
        [target[0] + distance, target[1] + distance, target[2] + distance]
    };
    (position, target)
}
```

Add to `rust/systhread-explorer/src/lib.rs`:

```rust
pub mod scene;
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p systhread-explorer --manifest-path rust/Cargo.toml scene_test`
Expected: PASS, all six tests.

- [ ] **Step 5: Confirm the scene math builds for wasm too**

Run: `cargo check -p systhread-explorer --manifest-path rust/Cargo.toml --target wasm32-unknown-unknown`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add rust/systhread-explorer/src/scene.rs rust/systhread-explorer/src/lib.rs rust/systhread-explorer/tests/scene_test.rs
git commit -m "systhread-explorer: pure SceneSpec geometry (nodes, edges, camera) with no Bevy dependency"
```

---

### Task 10: runtime asset loading — bytes to `PositionedGraph`, wired as a Bevy asset

**Files:**
- Modify: `rust/systhread-explorer/src/loader.rs`
- Create: `rust/systhread-explorer/src/asset.rs`
- Modify: `rust/systhread-explorer/src/lib.rs`
- Test: `rust/systhread-explorer/tests/loader_test.rs` (extend)

**Interfaces:**
- Consumes: `loader::load_positioned_graph` (Task 8); `bevy::asset::{Asset, AssetLoader, LoadContext}`, `bevy::asset::io::Reader`, `bevy::reflect::TypePath`.
- Produces: `loader::positioned_graph_from_bytes(bytes: &[u8]) -> Result<PositionedGraph, String>`; `asset::{PositionedGraphAsset, PositionedGraphAssetLoader, ExplorerAssetPlugin}`. Task 11 adds `ExplorerAssetPlugin` to its `App` and reads `PositionedGraphAsset` out of `Assets<PositionedGraphAsset>`.

**Design note — why an asset and not `include_str!`:** design §5 rejects baking the data into the binary (its "Approach C"): the viewer is *one* build reused by every adopting project, and the per-project part is the JSON. Bevy's own asset system is the right loader because it already has a working fetch-based backend on wasm and a filesystem backend natively — which is exactly why `bevy_asset` is in the verified feature list. The parsing itself stays in `loader` (Bevy-free, testable on both targets); the `AssetLoader` impl is a five-line adapter.

**Design note — a verified API gotcha:** `bevy_asset 0.19.1` declares `pub trait AssetLoader: TypePath + Send + Sync + 'static` (`src/loader.rs:32`), so the **loader struct itself** needs `#[derive(TypePath)]`, not just the asset type. This was found by compiling during planning, and it is the one thing about this API that does not look necessary until the compiler says so.

- [ ] **Step 1: Write the failing test**

Append to `rust/systhread-explorer/tests/loader_test.rs`:

```rust
use systhread_explorer::loader::positioned_graph_from_bytes;

#[test]
fn parses_a_positioned_graph_from_raw_bytes() {
    let json = build_positioned_graph(sample_graph(), LayoutMode::ThreeD).to_json();
    let loaded = positioned_graph_from_bytes(json.as_bytes()).unwrap();
    assert_eq!(loaded.graph.nodes.len(), 3);
}

#[test]
fn rejects_bytes_that_are_not_utf8_with_a_clear_message() {
    let err = positioned_graph_from_bytes(&[0xff, 0xfe, 0xfd]).unwrap_err();
    assert!(err.contains("UTF-8"), "unhelpful error: {err}");
}

#[test]
fn byte_parsing_enforces_the_same_layout_invariant_as_string_parsing() {
    let broken = PositionedGraph {
        graph: sample_graph(),
        layout: Layout::ThreeD(vec![NodePosition3D {
            node_id: "a".to_string(),
            x: 0.0,
            y: 0.0,
            z: 0.0,
        }]),
    };
    assert!(positioned_graph_from_bytes(broken.to_json().as_bytes()).is_err());
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p systhread-explorer --manifest-path rust/Cargo.toml loader_test`
Expected: FAIL to compile — `positioned_graph_from_bytes` does not exist.

- [ ] **Step 3: Write the implementation**

Append to `rust/systhread-explorer/src/loader.rs`:

```rust
/// The byte-oriented entry point the Bevy asset loader uses. Kept here, outside the `explorer-3d`
/// feature, so the only parsing logic in the crate is testable on both targets without Bevy.
pub fn positioned_graph_from_bytes(bytes: &[u8]) -> Result<PositionedGraph, String> {
    let text = std::str::from_utf8(bytes)
        .map_err(|e| format!("PositionedGraph artifact is not valid UTF-8: {e}"))?;
    load_positioned_graph(text)
}
```

`rust/systhread-explorer/src/asset.rs`:

```rust
//! Bevy asset plumbing for the `PositionedGraph` artifact -- a thin adapter over `loader`, which
//! holds all the real parsing. Design §5: the viewer is one generic build that *loads* a
//! per-project artifact at runtime, never one compiled per project.

use bevy::asset::io::Reader;
use bevy::asset::{Asset, AssetLoader, LoadContext};
use bevy::prelude::*;
use bevy::reflect::TypePath;
use systhread_core::positioned::PositionedGraph;

#[derive(Asset, TypePath, Debug)]
pub struct PositionedGraphAsset {
    pub graph: PositionedGraph,
}

/// `TypePath` is required on the loader itself, not only on the asset:
/// `pub trait AssetLoader: TypePath + Send + Sync + 'static` (bevy_asset 0.19.1, src/loader.rs:32).
#[derive(Default, TypePath)]
pub struct PositionedGraphAssetLoader;

impl AssetLoader for PositionedGraphAssetLoader {
    type Asset = PositionedGraphAsset;
    type Settings = ();
    type Error = std::io::Error;

    async fn load(
        &self,
        reader: &mut dyn Reader,
        _settings: &(),
        _load_context: &mut LoadContext<'_>,
    ) -> Result<Self::Asset, Self::Error> {
        let mut bytes = Vec::new();
        reader.read_to_end(&mut bytes).await?;
        let graph = crate::loader::positioned_graph_from_bytes(&bytes)
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidData, e))?;
        Ok(PositionedGraphAsset { graph })
    }

    fn extensions(&self) -> &[&str] {
        &["json"]
    }
}

pub struct ExplorerAssetPlugin;

impl Plugin for ExplorerAssetPlugin {
    fn build(&self, app: &mut App) {
        app.init_asset::<PositionedGraphAsset>()
            .init_asset_loader::<PositionedGraphAssetLoader>();
    }
}
```

Add to `rust/systhread-explorer/src/lib.rs`:

```rust
#[cfg(feature = "explorer-3d")]
pub mod asset;
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p systhread-explorer --manifest-path rust/Cargo.toml loader_test`
Expected: PASS, all six tests (three from Task 8, three new).

- [ ] **Step 5: Verify the Bevy adapter compiles**

Run: `cargo check -p systhread-explorer --manifest-path rust/Cargo.toml --features explorer-3d --target wasm32-unknown-unknown`
Expected: exit 0. If `read_to_end` is not found, the `Reader` trait's extension method has moved — import `bevy::asset::AsyncReadExt` as well (planning found it *unnecessary* on 0.19.1, which is why it is not imported above).

- [ ] **Step 6: Commit**

```bash
git add rust/systhread-explorer/src/asset.rs rust/systhread-explorer/src/loader.rs rust/systhread-explorer/src/lib.rs rust/systhread-explorer/tests/loader_test.rs
git commit -m "systhread-explorer: PositionedGraph Bevy asset + loader, parsing kept Bevy-free"
```

---

### Task 11: the Bevy app — spawn the scene, place the camera, orbit it

**Files:**
- Create: `rust/systhread-explorer/src/app.rs`
- Create: `rust/systhread-explorer/src/main.rs`
- Modify: `rust/systhread-explorer/src/lib.rs`
- Test: `rust/systhread-explorer/tests/orbit_test.rs`

**Interfaces:**
- Consumes: `scene::{scene_spec, SceneSpec, NodeVisual, EdgeVisual, EDGE_RADIUS}` (Task 9); `asset::{ExplorerAssetPlugin, PositionedGraphAsset}` (Task 10).
- Produces: `app::{ExplorerPlugin, Orbit, orbit_from_scene, orbit_offset}`; `app::run(asset_path: &str)`. Nothing consumes these except `main.rs` and Task 12's bundle.

**Design note — the API shapes here were compiled, not guessed.** During planning a standalone spike compiled all of this for `wasm32-unknown-unknown` under the exact `explorer-3d` feature list: `DefaultPlugins`, `Mesh3d`/`MeshMaterial3d`/`StandardMaterial::from_color`, `Sphere`/`Cylinder`, `Camera3d`, `DirectionalLight`, `Quat::from_rotation_arc`, `init_asset`/`init_asset_loader`, and the orbit system below. Two Bevy-0.19-specific spellings worth noting because they differ from older tutorials: input events are read with **`MessageReader`**, not `EventReader` (e.g. `MessageReader<bevy::input::mouse::MouseMotion>`), and mesh/material components are the `Mesh3d`/`MeshMaterial3d` wrappers rather than a bundle.

**Design note — what "interactive" means in v1, and the v2 constraint it respects:** v1's interaction is camera navigation only (drag to orbit, wheel to zoom) — design §2 is explicit that v1 is "static, deterministic, read-only" and that nothing mutates. The orbit state lives in an `Orbit` **component** whose target/radius come from `SceneSpec`, and the camera pose is recomputed from that state each frame. That is what satisfies design §7's one v1 obligation: an XR rig would replace the *system* that writes `Orbit`, not the scene-building code, so no re-architecture is implied. `orbit_from_scene` and `orbit_offset` are pure functions specifically so this task has something real to test in CI without a GPU.

- [ ] **Step 1: Write the failing test**

`rust/systhread-explorer/tests/orbit_test.rs`:

```rust
//! Only builds when the Bevy layer is enabled; `just check-systhread-explorer` runs the default
//! (Bevy-free) feature set, and Task 12's bundle recipe runs this one.
#![cfg(feature = "explorer-3d")]

use systhread_core::cytoscape::{CytoscapeGraph, CytoscapeNode, CytoscapeNodeData};
use systhread_core::positioned::{Layout, NodePosition2D, NodePosition3D, PositionedGraph};
use systhread_explorer::app::{orbit_from_scene, orbit_offset};
use systhread_explorer::scene::scene_spec;

fn node(id: &str) -> CytoscapeNode {
    CytoscapeNode {
        data: CytoscapeNodeData {
            id: id.to_string(),
            label: id.to_string(),
            kind: "Bus".to_string(),
            parent: None,
            z_layer: None,
            semantic_type: None,
        },
    }
}

#[test]
fn the_initial_orbit_reproduces_the_scenes_own_camera_placement() {
    let pg = PositionedGraph {
        graph: CytoscapeGraph { nodes: vec![node("a"), node("b")], edges: vec![] },
        layout: Layout::ThreeD(vec![
            NodePosition3D { node_id: "a".to_string(), x: -4.0, y: 0.0, z: 0.0 },
            NodePosition3D { node_id: "b".to_string(), x: 4.0, y: 0.0, z: 0.0 },
        ]),
    };
    let spec = scene_spec(&pg);
    let orbit = orbit_from_scene(&spec);

    assert_eq!(orbit.target, spec.camera_target);
    assert!(!orbit.lock_pitch);

    // Recomputing the pose from the orbit state must land back on the scene's camera position.
    let offset = orbit_offset(&orbit);
    for d in 0..3 {
        let got = spec.camera_target[d] + offset[d];
        assert!(
            (got - spec.camera_position[d]).abs() < 1.0e-3,
            "axis {d}: orbit gave {got}, scene said {}",
            spec.camera_position[d]
        );
    }
}

#[test]
fn a_flat_scene_locks_pitch_so_the_plane_is_never_orbited_edge_on() {
    let pg = PositionedGraph {
        graph: CytoscapeGraph { nodes: vec![node("a")], edges: vec![] },
        layout: Layout::TwoD(vec![NodePosition2D { node_id: "a".to_string(), x: 0.0, y: 0.0 }]),
    };
    let orbit = orbit_from_scene(&scene_spec(&pg));
    assert!(orbit.lock_pitch);
    assert_eq!(orbit.pitch, 0.0);
}

#[test]
fn the_orbit_radius_matches_the_scenes_camera_distance() {
    let pg = PositionedGraph {
        graph: CytoscapeGraph { nodes: vec![node("a")], edges: vec![] },
        layout: Layout::ThreeD(vec![NodePosition3D {
            node_id: "a".to_string(),
            x: 0.0,
            y: 0.0,
            z: 0.0,
        }]),
    };
    let spec = scene_spec(&pg);
    let orbit = orbit_from_scene(&spec);
    let expected: f32 = (0..3)
        .map(|d| (spec.camera_position[d] - spec.camera_target[d]).powi(2))
        .sum::<f32>()
        .sqrt();
    assert!((orbit.radius - expected).abs() < 1.0e-3);
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p systhread-explorer --manifest-path rust/Cargo.toml --features explorer-3d orbit_test`
Expected: FAIL to compile — `systhread_explorer::app` does not exist.

> If this native build fails inside `bevy_winit` with "Please select a feature to build for unix" (or an X11/Wayland system-header error), that is the known desktop-only gap covered in Open Items — switch the command to `--target wasm32-unknown-unknown` for this task's compile checks and run the unit tests with `--features explorer-3d` once `explorer-desktop` (Step 3) is available.

- [ ] **Step 3: Write the implementation**

`rust/systhread-explorer/src/app.rs`:

```rust
//! The ECS layer: turns a `SceneSpec` into entities and drives an orbit camera. All geometry
//! arrives already computed (see `scene`), so nothing here does math a test can't reach.

use crate::asset::{ExplorerAssetPlugin, PositionedGraphAsset};
use crate::scene::{scene_spec, EdgeVisual, NodeVisual, SceneSpec, EDGE_RADIUS};
use bevy::prelude::*;

/// Camera state. Kept as data rather than as accumulated `Transform` mutations so that a future
/// XR rig (design §7) replaces only the system that writes it, not the scene-building code.
#[derive(Component, Debug, Clone, PartialEq)]
pub struct Orbit {
    pub target: [f32; 3],
    pub yaw: f32,
    pub pitch: f32,
    pub radius: f32,
    /// A flat (2D) layout has no depth axis worth orbiting around, so pitch stays at zero.
    pub lock_pitch: bool,
}

/// The camera offset implied by an `Orbit`, in the same convention `scene::camera` used.
pub fn orbit_offset(orbit: &Orbit) -> [f32; 3] {
    [
        orbit.radius * orbit.yaw.cos() * orbit.pitch.cos(),
        orbit.radius * orbit.pitch.sin(),
        orbit.radius * orbit.yaw.sin() * orbit.pitch.cos(),
    ]
}

/// Seeds the orbit from the scene's own camera placement, so frame zero looks exactly like what
/// `scene_spec` described and the first drag continues from there rather than jumping.
pub fn orbit_from_scene(spec: &SceneSpec) -> Orbit {
    let delta = [
        spec.camera_position[0] - spec.camera_target[0],
        spec.camera_position[1] - spec.camera_target[1],
        spec.camera_position[2] - spec.camera_target[2],
    ];
    let radius = (delta[0] * delta[0] + delta[1] * delta[1] + delta[2] * delta[2]).sqrt();
    let pitch = if spec.flat || radius == 0.0 {
        0.0
    } else {
        (delta[1] / radius).asin()
    };
    let yaw = if spec.flat { std::f32::consts::FRAC_PI_2 } else { delta[2].atan2(delta[0]) };
    Orbit { target: spec.camera_target, yaw, pitch, radius, lock_pitch: spec.flat }
}

#[derive(Resource)]
struct GraphHandle(Handle<PositionedGraphAsset>);

#[derive(Resource, Default)]
struct SceneSpawned(bool);

/// Drop-in plugin: loads `asset_path` through Bevy's asset system and renders it.
pub struct ExplorerPlugin {
    pub asset_path: String,
}

impl Plugin for ExplorerPlugin {
    fn build(&self, app: &mut App) {
        let path = self.asset_path.clone();
        app.add_plugins(ExplorerAssetPlugin)
            .init_resource::<SceneSpawned>()
            .insert_resource(AssetPathToLoad(path))
            .add_systems(Startup, request_graph)
            .add_systems(Update, (spawn_scene_when_loaded, orbit_camera));
    }
}

#[derive(Resource)]
struct AssetPathToLoad(String);

fn request_graph(
    mut commands: Commands,
    asset_server: Res<AssetServer>,
    path: Res<AssetPathToLoad>,
) {
    let handle: Handle<PositionedGraphAsset> = asset_server.load(path.0.clone());
    commands.insert_resource(GraphHandle(handle));
}

fn spawn_scene_when_loaded(
    mut commands: Commands,
    handle: Option<Res<GraphHandle>>,
    graphs: Res<Assets<PositionedGraphAsset>>,
    mut spawned: ResMut<SceneSpawned>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    if spawned.0 {
        return;
    }
    let Some(handle) = handle else { return };
    let Some(asset) = graphs.get(&handle.0) else { return };

    let spec = scene_spec(&asset.graph);
    info!(
        "systhread-explorer: {} nodes, {} edges, flat={}",
        spec.nodes.len(),
        spec.edges.len(),
        spec.flat
    );

    // One shared unit mesh per kind: a unit-radius sphere and a unit-height, Y-aligned cylinder,
    // both scaled per entity. Reusing two meshes keeps the draw-call count independent of graph
    // size and matches how `EdgeVisual` was defined in `scene`.
    let sphere = meshes.add(Sphere::new(1.0));
    let cylinder = meshes.add(Cylinder::new(EDGE_RADIUS, 1.0));
    let node_material = materials.add(StandardMaterial::from_color(Color::srgb(0.35, 0.67, 0.94)));
    let edge_material = materials.add(StandardMaterial::from_color(Color::srgb(0.55, 0.58, 0.62)));

    for NodeVisual { position, radius, .. } in &spec.nodes {
        commands.spawn((
            Mesh3d(sphere.clone()),
            MeshMaterial3d(node_material.clone()),
            Transform::from_translation(Vec3::from_array(*position)).with_scale(Vec3::splat(*radius)),
        ));
    }

    for EdgeVisual { midpoint, direction, length, .. } in &spec.edges {
        commands.spawn((
            Mesh3d(cylinder.clone()),
            MeshMaterial3d(edge_material.clone()),
            Transform::from_translation(Vec3::from_array(*midpoint))
                .with_rotation(Quat::from_rotation_arc(Vec3::Y, Vec3::from_array(*direction)))
                .with_scale(Vec3::new(1.0, *length, 1.0)),
        ));
    }

    let orbit = orbit_from_scene(&spec);
    commands.spawn((
        Camera3d::default(),
        Transform::from_translation(Vec3::from_array(spec.camera_position))
            .looking_at(Vec3::from_array(spec.camera_target), Vec3::Y),
        orbit,
    ));
    commands.spawn((
        DirectionalLight::default(),
        Transform::from_translation(
            Vec3::from_array(spec.camera_position) + Vec3::new(0.0, 4.0, 0.0),
        )
        .looking_at(Vec3::from_array(spec.camera_target), Vec3::Y),
    ));

    spawned.0 = true;
}

fn orbit_camera(
    mut motion: MessageReader<bevy::input::mouse::MouseMotion>,
    mut wheel: MessageReader<bevy::input::mouse::MouseWheel>,
    buttons: Res<ButtonInput<MouseButton>>,
    mut cameras: Query<(&mut Orbit, &mut Transform)>,
) {
    let mut drag = Vec2::ZERO;
    for event in motion.read() {
        drag += event.delta;
    }
    let mut zoom = 0.0;
    for event in wheel.read() {
        zoom += event.y;
    }
    if drag == Vec2::ZERO && zoom == 0.0 {
        return;
    }
    for (mut orbit, mut transform) in cameras.iter_mut() {
        if buttons.pressed(MouseButton::Left) {
            orbit.yaw -= drag.x * 0.005;
            if !orbit.lock_pitch {
                orbit.pitch = (orbit.pitch - drag.y * 0.005).clamp(-1.5, 1.5);
            }
        }
        orbit.radius = (orbit.radius - zoom * 0.5).max(1.0);
        let target = Vec3::from_array(orbit.target);
        transform.translation = target + Vec3::from_array(orbit_offset(&orbit));
        transform.look_at(target, Vec3::Y);
    }
}

/// Runs the explorer against an asset path relative to Bevy's asset root (`assets/` next to the
/// executable natively; the served directory on the web).
pub fn run(asset_path: &str) {
    App::new()
        .add_plugins(DefaultPlugins)
        .add_plugins(ExplorerPlugin { asset_path: asset_path.to_string() })
        .run();
}
```

`rust/systhread-explorer/src/main.rs`:

```rust
//! `systhread-explorer [asset-path]` -- one generic viewer binary, reused by every adopting
//! project (design §5). The per-project part is the PositionedGraph JSON it loads, never a
//! recompile.

fn main() {
    let asset_path = std::env::args().nth(1).unwrap_or_else(|| "graph.json".to_string());
    systhread_explorer::app::run(&asset_path);
}
```

Add to `rust/systhread-explorer/src/lib.rs`:

```rust
#[cfg(feature = "explorer-3d")]
pub mod app;
```

Add a desktop feature to `rust/systhread-explorer/Cargo.toml`'s `[features]` (native windowing needs a backend selected explicitly on Linux; the wasm build must not have it):

```toml
# Native desktop run of the same viewer. Separate from `explorer-3d` because `bevy_winit` requires
# an explicit windowing backend on Linux, and the wasm build must not pull x11.
explorer-desktop = ["explorer-3d", "bevy/x11"]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p systhread-explorer --manifest-path rust/Cargo.toml --features explorer-3d orbit_test`
Expected: PASS, all three tests. (If the native Bevy build hits the windowing-backend error from Step 2's note, run `cargo test -p systhread-explorer --manifest-path rust/Cargo.toml --features explorer-desktop orbit_test` instead and record which one worked in the crate README in Task 12.)

- [ ] **Step 5: Verify the full app compiles for the web target**

Run: `cargo check -p systhread-explorer --manifest-path rust/Cargo.toml --features explorer-3d --target wasm32-unknown-unknown`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add rust/systhread-explorer/src/app.rs rust/systhread-explorer/src/main.rs rust/systhread-explorer/src/lib.rs rust/systhread-explorer/Cargo.toml rust/systhread-explorer/tests/orbit_test.rs
git commit -m "systhread-explorer: Bevy scene spawning, orbit camera, and the generic viewer binary"
```

---

### Task 12: the web bundle, the real browser check, and the crate README

**Files:**
- Create: `rust/systhread-explorer/web/index.html`
- Create: `scripts/build_systhread_explorer.sh`
- Create: `rust/systhread-explorer/README.md`
- Modify: `rust/systhread-explorer/Cargo.toml`
- Modify: `Justfile`
- Modify: `.gitignore` (add `rust/systhread-explorer/dist/`)

**Interfaces:**
- Consumes: the `systhread-explorer` binary built for `wasm32-unknown-unknown` with `explorer-3d` (Task 11); `systhread render --explorer` (Task 5) for the demo artifact.
- Produces: `rust/systhread-explorer/dist/` (a self-contained `index.html` + `.js` + `.wasm` + `assets/graph.json`), the `just systhread-explorer-bundle` recipe, and the `explorer-web` fallback feature. No Rust API.

**Design note — this task answers the one runtime question the spike left open.** Compilation for wasm is proven; whether `bevy_winit` + wgpu actually acquire an adapter and draw to a canvas is not, and cannot be, until a real browser loads the bundle. Two paths, in order: (1) plain `explorer-3d`, relying on wgpu's default WebGPU backend on wasm — works in a WebGPU-capable browser over `localhost` (a secure context); (2) if no adapter is acquired, the `explorer-web` feature added below, which was **verified during planning to resolve and compile** for wasm32 and turns on WebGL2 by declaring `bevy_render`/`bevy_core_pipeline`/`bevy_pbr` directly. The direct-sub-crate route exists because `bevy/webgl2`, `bevy/webgpu` and `bevy/web` all fail to resolve on `0.19.1` (Verified During Planning #3) — do not try them again expecting a different result.

- [ ] **Step 1: Add the fallback feature and the bundle inputs**

Add to `rust/systhread-explorer/Cargo.toml`'s `[dependencies]`:

```toml
# Only used by the `explorer-web` fallback below -- see its comment. Unused otherwise.
bevy_render = { version = "0.19", default-features = false, optional = true }
bevy_core_pipeline = { version = "0.19", default-features = false, optional = true }
bevy_pbr = { version = "0.19", default-features = false, optional = true }
```

and to `[features]`:

```toml
# WebGL2 fallback for browsers without WebGPU. `bevy/webgl2` cannot be used: it maps to
# `bevy_internal/webgl`, whose `bevy_dev_tools?/webgl` edge forces cargo to resolve
# `bevy_dev_tools 0.19.1`, which requires the never-published `bevy_picking 0.19.1` (latest is
# 0.16.1). Declaring the three render sub-crates directly turns the same feature on by
# unification while keeping bevy_dev_tools out of the graph. Verified: resolves and compiles for
# wasm32-unknown-unknown.
explorer-web = ["explorer-3d", "dep:bevy_render", "bevy_render/webgl", "dep:bevy_core_pipeline", "bevy_core_pipeline/webgl", "dep:bevy_pbr", "bevy_pbr/webgl"]
```

`rust/systhread-explorer/web/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>systhread explorer</title>
    <style>
      html, body { margin: 0; height: 100%; background: #101418; overflow: hidden; }
      canvas { display: block; }
    </style>
  </head>
  <body>
    <script type="module">
      import init from "./systhread-explorer.js";
      // winit ends its startup call by throwing a control-flow exception; that one is expected,
      // anything else is a real failure and must not be swallowed.
      init().catch((e) => {
        if (!String(e).includes("Using exceptions for control flow")) throw e;
      });
    </script>
  </body>
</html>
```

`scripts/build_systhread_explorer.sh`:

```bash
#!/usr/bin/env bash
# Builds the systhread explorer's self-contained web bundle into
# rust/systhread-explorer/dist/. Optional first argument: a PositionedGraph JSON to ship as the
# viewer's data (default: freshly rendered from Lab 6's grid track, so the bundle always has real
# content to show). Set SYSTHREAD_EXPLORER_FEATURES=explorer-web to use the WebGL2 fallback.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
features="${SYSTHREAD_EXPLORER_FEATURES:-explorer-3d}"
dist="$root/rust/systhread-explorer/dist"
graph="${1:-}"

echo "building systhread-explorer for wasm32-unknown-unknown (features: $features)"
cargo build -p systhread-explorer --manifest-path "$root/rust/Cargo.toml" \
    --target wasm32-unknown-unknown --features "$features" --release

rm -rf "$dist"
mkdir -p "$dist/assets"

wasm-bindgen --out-dir "$dist" --target web --no-typescript \
    "$root/rust/target/wasm32-unknown-unknown/release/systhread-explorer.wasm"

cp "$root/rust/systhread-explorer/web/index.html" "$dist/index.html"

if [[ -n "$graph" ]]; then
    cp "$graph" "$dist/assets/graph.json"
else
    tmp="$(mktemp -d)"
    cargo run -p systhread-cli --manifest-path "$root/rust/Cargo.toml" -- render --track grid \
        "$root/rust/systhread-core/tests/fixtures/lab6/schema/grid_instances.yaml" \
        --out "$tmp" --explorer --explorer-layout 3d
    cp "$tmp/grid_explorer.json" "$dist/assets/graph.json"
    rm -rf "$tmp"
fi

echo "bundle ready: $dist"
echo "serve it with:  python3 -m http.server 8765 --directory $dist"
```

Make it executable: `chmod +x scripts/build_systhread_explorer.sh`

Add to the repo-root `Justfile`:

```just
# Build the explorer's self-contained web bundle (optionally from a specific PositionedGraph JSON).
systhread-explorer-bundle graph="":
    ./scripts/build_systhread_explorer.sh {{graph}}

# Serve the built bundle for a real browser check.
systhread-explorer-serve port="8765":
    python3 -m http.server {{port}} --directory rust/systhread-explorer/dist
```

Add to `.gitignore`:

```gitignore
rust/systhread-explorer/dist/
```

- [ ] **Step 2: Build the bundle**

Run: `just systhread-explorer-bundle`
Expected: the script finishes with "bundle ready", and `rust/systhread-explorer/dist/` contains `index.html`, `systhread-explorer.js`, `systhread-explorer_bg.wasm`, and `assets/graph.json`. Confirm with `ls -la rust/systhread-explorer/dist rust/systhread-explorer/dist/assets`.

If `wasm-bindgen` errors with a schema-version mismatch, the CLI is out of step with the `wasm-bindgen` crate in `rust/Cargo.lock` — same fix as Task 6 Step 4.

- [ ] **Step 3: Verify it actually draws in a real browser**

Run: `just systhread-explorer-serve` (leave it running), then open `http://localhost:8765/` in a browser.

This is the verification, and it has three concrete pass conditions — check all three, do not settle for "the page loaded":
1. The browser console shows the app's own log line: `systhread-explorer: 20 nodes, N edges, flat=false`.
2. Spheres and connecting cylinders are visible on the canvas (the grid track's 15 buses + 5 generators).
3. Dragging with the left mouse button orbits the model and the scroll wheel zooms.

If the console instead shows a wgpu adapter error (`Failed to find an appropriate adapter`, `no supported backend`, or similar):
```bash
SYSTHREAD_EXPLORER_FEATURES=explorer-web just systhread-explorer-bundle
```
and re-check. Record which feature set worked in the README (Step 4) — that outcome is the answer to the design's open runtime question and must not be left undocumented.

If **neither** works, stop and report rather than inventing a third feature combination: the honest state is "compiles for wasm, does not yet draw", and the next step is a narrow spike against a stock Bevy web example on the same machine to isolate whether the problem is this crate or Bevy 0.19.1 on the web generally.

- [ ] **Step 4: Write the README, recording what actually happened**

`rust/systhread-explorer/README.md` — write it after Step 3, filling in the real outcome:

```markdown
# systhread-explorer

The systhread model explorer: one generic Bevy viewer, compiled to `wasm32-unknown-unknown`, that
renders a project's SysML model as an interactive 3D (or flat 2D) graph.

Design: `docs/superpowers/specs/2026-08-26-systhread-3d-explorer-design.md`.
Plan: `docs/superpowers/plans/2026-08-26-systhread-3d-explorer-v1.md`.

## How the pieces fit

- `systhread render --track <track> <instances.yaml> --out <dir> --explorer` writes
  `<track>_explorer.json`, a `PositionedGraph`: the Cytoscape-shaped graph plus an
  ahead-of-time, deterministic layout. Byte-identical on unchanged input, like every other
  systhread artifact, and listed in the output directory's `manifest.json` as
  `kind: "positioned_graph_json"`.
- This crate is the viewer for that file. It is **one build, reused by every project** — the
  per-project part is the JSON, never a recompile.
- `loader` and `scene` are Bevy-free and compile for both native and wasm; `asset` and `app` are
  the ECS layer behind the `explorer-3d` feature.

## Commands

    just systhread-explorer-bundle                 # build dist/ (renders the grid track as demo data)
    just systhread-explorer-bundle path/to/x.json  # ...or bundle a specific PositionedGraph
    just systhread-explorer-serve                  # http://localhost:8765/
    just check-systhread-explorer                  # tests (default, Bevy-free features)
    just check-systhread-wasm                      # systhread-core's ouroboros gate
    just systhread-wasm-setup                      # one-time: wasm32 target + matching wasm-bindgen CLI

Controls: left-drag orbits, scroll wheel zooms. A 2D layout locks pitch and faces the plane head-on.

## Cargo features

- `explorer-3d` — the Bevy renderer. An explicit component list, never a Bevy meta-feature.
- `explorer-web` — `explorer-3d` plus WebGL2, for browsers without WebGPU.
- `explorer-desktop` — `explorer-3d` plus `bevy/x11`, for running the viewer natively on Linux.

**Bevy 0.19.1 packaging bugs this crate works around** (both real, both hit during development):
`bevy_animation 0.19.1` and `bevy_picking 0.19.1` were never published, so any feature path
reaching them fails to resolve. That rules out `ui`/`default_app`/`scene` *and* `bevy/webgl2`,
`bevy/webgpu`, `bevy/web` (which reach `bevy_dev_tools` → `bevy_picking`). `explorer-web`
therefore turns WebGL2 on by declaring `bevy_render`/`bevy_core_pipeline`/`bevy_pbr` directly.

## Browser status

<!-- Replace this with what Step 3 actually showed: which feature set drew the scene, in which
     browser and version, and whether orbit/zoom worked. If it did not draw, say so plainly and
     link the follow-up issue -- do not leave this section optimistic. -->
```

- [ ] **Step 5: Run the full gate**

Run: `just check-systhread-core && just check-systhread-wasm && just check-systhread-explorer && cargo test -p systhread-cli --manifest-path rust/Cargo.toml`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add rust/systhread-explorer/web/index.html rust/systhread-explorer/README.md rust/systhread-explorer/Cargo.toml scripts/build_systhread_explorer.sh Justfile .gitignore
git commit -m "systhread-explorer: web bundle build, browser verification, and crate README"
```

**Milestone D complete.** PR boundary: a working, self-contained explorer bundle rendering a real systhread artifact, with the runtime browser question answered on the record.

---

## Milestone E: the blocked holon-viz integration

### Task 13: replace the local mirror with the real `holon-viz` types — **BLOCKED on `ledgrrr#203`**

> **DO NOT START THIS TASK** until `PromptExecution/ledgrrr#203` — "may `holon-viz` become a real
> (non-dev) dependency of nem-poweragent-lab?" — is resolved **in the affirmative by ledgrrr's
> owner**. This is the same posture FR8/FR9 take toward `ledgrrr#202`: a cross-repo dependency
> decision belongs to the owner of the depended-on repo, not to whoever is executing this plan.
> If #203 is still open, Tasks 1–12 are a complete, shippable v1 — the local mirror in
> `cytoscape.rs` is a deliberate, documented, spec-sanctioned stand-in, not technical debt to
> resolve unilaterally. Report the block and stop.
>
> If #203 is resolved **against** the dependency, this task is cancelled outright, not deferred:
> the local mirror simply becomes the permanent type, and the only follow-up is deleting the
> "when #203 resolves" sentence from `cytoscape.rs`'s module docs.

**Files:**
- Modify: `rust/systhread-core/Cargo.toml`
- Modify: `rust/systhread-core/src/cytoscape.rs`
- Modify: `rust/systhread-core/tests/fixtures/explorer/grid_explorer_3d.json` (only if the byte comparison in Step 4 shows the real types serialize differently)
- Test: the existing `cytoscape_test.rs`, `positioned_test.rs`, `layout3d_test.rs`, `ouroboros_native_test.rs`, `ouroboros_wasm_test.rs` — all of them are the test for this task, unchanged.

**Interfaces:**
- Consumes: `holon_viz::{CytoscapeGraph, CytoscapeNode, CytoscapeNodeData, CytoscapeEdge, CytoscapeEdgeData}` (the real crate).
- Produces: the same `systhread_core::cytoscape::*` paths every other task already imports — this task changes where the types come from, not what they are called. `from_iso_ir` keeps its exact signature.

**Design note — three real risks to check before writing code, in this order.** The design quotes holon-viz's field names and types verbatim, but not its derives, its serde attributes, or its wasm-compatibility, and none of those can be assumed:
1. **Does `holon-viz` derive `Deserialize`?** The explorer *reads* `PositionedGraph` back, so `CytoscapeGraph` must round-trip. If holon-viz derives only `Serialize`, the swap is not possible as written — keep the local mirror as the wire type, add a `From` conversion, and report that finding on #203.
2. **Do its serde attributes match?** If it renames fields (camelCase, `skip_serializing_if`), the artifact bytes change. That is allowed — but it makes the committed fixture stale, which Step 4 catches and Step 5 regenerates.
3. **Does `holon-viz` compile for `wasm32-unknown-unknown`?** `systhread-core` must keep doing so (Global Constraints). Step 2 checks it before anything else, because a `holon-viz` that pulls in a native-only dependency would sink the ouroboros gate, and that is a finding for #203 rather than something to work around locally.

- [ ] **Step 1: Confirm the block is lifted, and record how**

Read `PromptExecution/ledgrrr#203` and confirm an affirmative resolution from ledgrrr's owner. Note the issue's resolution comment URL — it goes in this task's commit message as the authorization, the same way `ledgrrr#202` is cited for FR8/FR9.

- [ ] **Step 2: Add the dependency and check the wasm target first**

Add to `rust/systhread-core/Cargo.toml`'s `[dependencies]` (use the exact source form #203's resolution specifies — a git rev pin if holon-viz is not on crates.io, matching how `mission-engine` pins `ufo-types`):

```toml
# Authorized by PromptExecution/ledgrrr#203. Design §3: PositionedGraph wraps holon-viz's real
# CytoscapeGraph rather than duplicating it.
holon-viz = { git = "https://github.com/PromptExecution/ledgrrr", rev = "<the rev #203 names>" }
```

Run: `cargo check -p systhread-core --manifest-path rust/Cargo.toml --target wasm32-unknown-unknown`
Expected: exit 0. **If this fails, stop here and revert the dependency** — report on #203 that holon-viz is not wasm-compatible, which is decision-relevant information the issue's resolution presumably did not have.

- [ ] **Step 3: Replace the mirror with a re-export**

Replace the struct definitions in `rust/systhread-core/src/cytoscape.rs` with a re-export, keeping `from_iso_ir` exactly as it is (it constructs the same fields either way):

```rust
//! The Cytoscape graph shape, re-exported from `ledgrrr`'s `holon-viz` crate.
//!
//! Until PromptExecution/ledgrrr#203 was resolved, these types were mirrored locally (design §3's
//! "open dependency question"). #203 authorized the real dependency, so they now come from the
//! crate that owns them and cannot drift from it.

pub use holon_viz::{
    CytoscapeEdge, CytoscapeEdgeData, CytoscapeGraph, CytoscapeNode, CytoscapeNodeData,
};

use crate::iso_ir::{Edge, Node};

// `from_iso_ir` is unchanged -- see its existing doc comment.
```

If the real types are not constructible with struct literals from outside their crate (private fields, or a builder API), use whatever constructor holon-viz actually exposes and adjust `from_iso_ir` only — no other file may change.

- [ ] **Step 4: Run every existing test and see what moved**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml`
Expected: `cytoscape_test`, `positioned_test`, `layout3d_test` PASS unchanged — they assert on field values, which the real types share.

`ouroboros_native_test::native_regeneration_reproduces_the_committed_artifact_byte_for_byte` is the interesting one. It PASSES if holon-viz's serde output matches the local mirror's byte for byte. It FAILS if holon-viz renames or skips fields — which is expected and fine, and is exactly what Step 5 handles. Read the diff before deciding which case you are in (write both strings to files and `diff` them).

- [ ] **Step 5: Regenerate the fixture if — and only if — the bytes legitimately changed**

Only if Step 4's byte comparison failed *because of a serde-attribute difference in the real types* (not because the layout changed):

```bash
cargo run -p systhread-cli --manifest-path rust/Cargo.toml -- render --track grid \
  rust/systhread-core/tests/fixtures/lab6/schema/grid_instances.yaml \
  --out /tmp/systhread-explorer-fixture --explorer --explorer-layout 3d
cp /tmp/systhread-explorer-fixture/grid_explorer.json \
   rust/systhread-core/tests/fixtures/explorer/grid_explorer_3d.json
```

Then re-run `cargo test -p systhread-core --manifest-path rust/Cargo.toml` and expect PASS. If the coordinates themselves changed, that is **not** a serde difference — the layout is not supposed to depend on the graph's serialization at all, so investigate before regenerating anything.

- [ ] **Step 6: Run the whole gate, both targets**

Run: `just check-systhread-core && just check-systhread-wasm && just check-systhread-explorer && cargo test -p systhread-cli --manifest-path rust/Cargo.toml`
Expected: all PASS. The ouroboros test passing here is the real proof the swap is complete: the same holon-viz-derived bytes are produced natively and consumed under wasm.

- [ ] **Step 7: Commit**

```bash
git add rust/systhread-core/Cargo.toml rust/systhread-core/src/cytoscape.rs rust/systhread-core/tests/fixtures/explorer/grid_explorer_3d.json
git commit -m "systhread-core: use holon-viz's real CytoscapeGraph types (authorized by ledgrrr#203)"
```

**Milestone E complete.** The data model now shares holon-viz's real types rather than mirroring them, with no other file changed — which was the point of naming them identically in Task 1.

---

## Open Items (not tasks — decisions this plan deliberately does not make)

1. **2D layout parity with holon-viz's `HtmlRenderer` is not a target, and is not achievable.**
   Design §4 *does* specify 2D's algorithm — the same fixed-seed, fixed-iteration force-directed
   solver as 3D, which is what Task 4 implements — so 2D needed no separate design decision and
   is fully covered by this plan. But design §3 also describes this spec's 2D view as "the
   Cytoscape.js `cose`-style layout `holon-viz`'s existing `HtmlRenderer` already produces". Those
   are two different things: `cose` runs in JavaScript, in the browser, at view time, and its
   output is not reproducible from Rust. This plan produces a *deterministic force-directed layout
   of the same family*, not a byte-match of `cose`. If someone later wants the two views to line
   up node-for-node, that is a real, unmade decision (most likely: have holon-viz's HTML renderer
   consume the `PositionedGraph`'s precomputed 2D coordinates instead of running `cose`) — raise
   it on `ledgrrr#203`'s thread rather than tuning constants here.
2. **`CytoscapeNodeData::z_layer`'s real meaning is still unknown upstream.** Design §3 could not
   locate the `ZLayer` enum. v1 writes `None` and never reads it. If holon-viz's owner clarifies it
   (plausibly on #203), decide then whether it maps to anything in `Layout` — do not guess.
3. **The native desktop build (`explorer-desktop`) is unverified on this machine.** `bevy_winit`
   needs X11/Wayland dev headers on Linux and this environment is headless, so Tasks 11–12 gate on
   the wasm build. The feature is declared and plausible, not proven; the first person on a desktop
   should run it and record the result in the crate README.
4. **The MCP surface does not expose `--explorer`.** FR2's `systhread_render` tool keeps its Phase 1
   signature. Adding an explorer parameter is a one-line change if a consumer ever asks; none has.
5. **No recorded tour for the explorer.** Phase 1 shipped `scripts/record_tour.sh` demos for the
   CLI; a GIF/MP4 tour of the explorer needs a display and a browser, which the tour script does not
   currently drive. Worth a follow-up once Task 12's browser status is on the record.

## Plan Self-Review Notes (for the executing agent, not a task)

- **Spec coverage.** §1/§2 (v1 scope, static deterministic viewer): Tasks 4, 5, 11. §3 (the
  `PositionedGraph`/`Layout` data model over holon-viz's real shape, and the open dependency
  question): Tasks 1, 2, 13. §4 (`layout3d.rs` sibling module, fixed-seed force-directed, both
  variants, new byte-identical artifact from `systhread render --explorer`): Tasks 3, 4, 5. §5
  (one generic Bevy/WASM binary loading the JSON at runtime, explicit Bevy component features):
  Tasks 8, 10, 11, 12. §6 (ouroboros: one crate, two targets, real round-trip in CI): Tasks 6, 7.
  §8 (non-goals): honoured — no model editing, no scene authoring, no domain-specific spatial grid,
  and the Bevy feature question is *resolved* rather than deferred. §7 (v2): not started; its one
  v1 obligation is met by Task 11's data-driven camera.
- **Placeholder scan.** No `TBD`, no "add error handling", no "similar to Task N", no test bodies
  described rather than written. The two conditional branches in the plan (Task 12's WebGL2
  fallback, Task 13's fixture regeneration) each name the exact command and the exact condition
  that selects it, and both alternatives were verified during planning. The README's "Browser
  status" section is an HTML comment instructing the author to write what actually happened — it is
  filled in during Task 12 Step 4, and is not carried forward as an unfinished artifact.
- **Type consistency, checked across tasks.** `CytoscapeGraph`/`CytoscapeNodeData` field names and
  the `node.data.id` nesting are identical in Tasks 1, 2, 4, 5, 8, 9, 10, 11, 13. `Layout::{TwoD,
  ThreeD}`, `NodePosition2D/3D`, `PositionedGraph::{to_json, from_json, layout_matches_graph}` and
  `Layout::{len, is_empty, node_ids}` are defined once (Task 2) and used with those exact spellings
  everywhere after. `LayoutMode` (core) vs `ExplorerLayout` (CLI) are deliberately two types with
  one conversion (`ExplorerLayout::mode`), never used interchangeably. `scene_spec` returns a bare
  `SceneSpec` (infallible) in both its definition (Task 9) and its call site (Task 11), because
  `load_positioned_graph` (Task 8) enforces the invariant that would otherwise make it fallible.
  `EDGE_RADIUS` is defined in Task 9 and consumed in Task 11; `NODE_RADIUS` is carried per-node on
  `NodeVisual` and applied as a uniform scale on a unit sphere.
- **The highest-risk task is Task 12, not Task 4.** The layout algorithm is textbook and fully
  tested offline; the unproven thing is a browser actually drawing. That risk is isolated in one
  task, with a verified fallback and an explicit "stop and report" branch if both paths fail.
- **What this plan does NOT include, by design:** any `holon-viz` dependency before #203 resolves,
  any `ufo-types`/`sysml-derive` work (Phase 2), telemetry or overlays (v2), an XR rig (v2), a
  domain-specific spatial grid scene (a later cim-gridy-only extension), and any change to the
  isometric `layout.rs`/`render.rs` pipeline.

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-26-systhread-3d-explorer-v1.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast iteration. This is how Phase 0 and Phase 1 were both actually executed in this repo, and this plan's task boundaries (each ending in a green test run and a commit) are drawn for it.

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints for review.

**Which approach?**

- If Subagent-Driven: **REQUIRED SUB-SKILL** — use `superpowers:subagent-driven-development`.
- If Inline: **REQUIRED SUB-SKILL** — use `superpowers:executing-plans`.

Either way, **stop at the end of Task 12 and report** unless `ledgrrr#203` has been resolved in the affirmative — Task 13 needs that authorization, and Tasks 1–12 are a complete v1 without it.
