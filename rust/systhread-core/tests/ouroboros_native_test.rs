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
