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
