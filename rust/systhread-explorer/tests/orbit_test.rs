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
