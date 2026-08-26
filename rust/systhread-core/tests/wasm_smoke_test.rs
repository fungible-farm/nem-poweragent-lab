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
