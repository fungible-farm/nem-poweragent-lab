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
