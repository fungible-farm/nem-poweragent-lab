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
