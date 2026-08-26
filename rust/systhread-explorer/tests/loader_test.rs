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
