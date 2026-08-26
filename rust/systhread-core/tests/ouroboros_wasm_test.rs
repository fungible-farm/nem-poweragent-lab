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
