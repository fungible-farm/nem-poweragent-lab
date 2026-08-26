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
