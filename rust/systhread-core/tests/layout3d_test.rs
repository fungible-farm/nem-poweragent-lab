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
