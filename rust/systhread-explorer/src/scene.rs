//! Every coordinate, length, rotation axis and camera placement the renderer needs, computed as a
//! pure function of a `PositionedGraph`. No Bevy, no GPU, no window -- so all of it is really
//! tested, rather than assumed from a screenshot nobody took (design §6).

use std::collections::BTreeMap;
use systhread_core::positioned::{Layout, PositionedGraph};

/// Sphere radius for a node, in layout units (`IDEAL_EDGE_LENGTH` is 2.0, so nodes occupy about a
/// quarter of a typical edge).
pub const NODE_RADIUS: f32 = 0.25;
/// Cylinder radius for an edge.
pub const EDGE_RADIUS: f32 = 0.03;
/// How far back the camera sits, as a multiple of the model's largest extent.
pub const CAMERA_DISTANCE_FACTOR: f32 = 1.2;
/// Floor on the camera distance, so a one- or two-node model doesn't put the camera inside a node.
pub const MIN_CAMERA_DISTANCE: f32 = 5.0;

#[derive(Debug, Clone, PartialEq)]
pub struct NodeVisual {
    pub node_id: String,
    pub position: [f32; 3],
    pub radius: f32,
}

/// A unit-height, Y-aligned cylinder's placement: translate to `midpoint`, rotate `Vec3::Y` onto
/// `direction`, scale Y by `length`.
#[derive(Debug, Clone, PartialEq)]
pub struct EdgeVisual {
    pub source_id: String,
    pub target_id: String,
    pub midpoint: [f32; 3],
    pub direction: [f32; 3],
    pub length: f32,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SceneSpec {
    pub nodes: Vec<NodeVisual>,
    pub edges: Vec<EdgeVisual>,
    pub camera_position: [f32; 3],
    pub camera_target: [f32; 3],
    /// True when the source layout was `Layout::TwoD`. The camera then faces the plane head-on and
    /// Task 11 locks orbit pitch: a flat layout has no depth axis worth orbiting around, which is
    /// design §3's 2D/3D distinction carried through to the camera instead of being flattened away.
    pub flat: bool,
}

/// Below this, two nodes are coincident and the edge between them has no direction to point along.
const MIN_EDGE_LENGTH: f32 = 1.0e-6;

fn positions(graph: &PositionedGraph) -> (Vec<[f32; 3]>, bool) {
    match &graph.layout {
        Layout::ThreeD(p) => (
            p.iter().map(|n| [n.x as f32, n.y as f32, n.z as f32]).collect(),
            false,
        ),
        Layout::TwoD(p) => (p.iter().map(|n| [n.x as f32, n.y as f32, 0.0]).collect(), true),
    }
}

/// Infallible: `loader::load_positioned_graph` has already established that the layout has one
/// entry per node, in order, so the zip below cannot mismatch.
pub fn scene_spec(graph: &PositionedGraph) -> SceneSpec {
    debug_assert!(
        graph.layout_matches_graph(),
        "PositionedGraph layout does not match its graph -- see layout_matches_graph()"
    );
    let (points, flat) = positions(graph);

    let nodes: Vec<NodeVisual> = graph
        .graph
        .nodes
        .iter()
        .zip(points.iter())
        .map(|(node, position)| NodeVisual {
            node_id: node.data.id.clone(),
            position: *position,
            radius: NODE_RADIUS,
        })
        .collect();

    let index: BTreeMap<&str, usize> = graph
        .graph
        .nodes
        .iter()
        .enumerate()
        .map(|(i, n)| (n.data.id.as_str(), i))
        .collect();

    let edges: Vec<EdgeVisual> = graph
        .graph
        .edges
        .iter()
        .filter_map(|e| {
            let a = points[*index.get(e.data.source.as_str())?];
            let b = points[*index.get(e.data.target.as_str())?];
            let delta = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
            let length =
                (delta[0] * delta[0] + delta[1] * delta[1] + delta[2] * delta[2]).sqrt();
            if length < MIN_EDGE_LENGTH {
                return None;
            }
            Some(EdgeVisual {
                source_id: e.data.source.clone(),
                target_id: e.data.target.clone(),
                midpoint: [
                    (a[0] + b[0]) / 2.0,
                    (a[1] + b[1]) / 2.0,
                    (a[2] + b[2]) / 2.0,
                ],
                direction: [delta[0] / length, delta[1] / length, delta[2] / length],
                length,
            })
        })
        .collect();

    let (camera_position, camera_target) = camera(&points, flat);

    SceneSpec { nodes, edges, camera_position, camera_target, flat }
}

fn camera(points: &[[f32; 3]], flat: bool) -> ([f32; 3], [f32; 3]) {
    if points.is_empty() {
        return ([0.0, 0.0, MIN_CAMERA_DISTANCE], [0.0, 0.0, 0.0]);
    }
    let mut min = points[0];
    let mut max = points[0];
    for p in points {
        for d in 0..3 {
            min[d] = min[d].min(p[d]);
            max[d] = max[d].max(p[d]);
        }
    }
    let target = [
        (min[0] + max[0]) / 2.0,
        (min[1] + max[1]) / 2.0,
        (min[2] + max[2]) / 2.0,
    ];
    let extent = (0..3).fold(0.0_f32, |acc, d| acc.max(max[d] - min[d]));
    let distance = (extent * CAMERA_DISTANCE_FACTOR).max(MIN_CAMERA_DISTANCE);

    let position = if flat {
        // Head-on: the plane fills the view without a perspective skew.
        [target[0], target[1], target[2] + distance]
    } else {
        // Off all three axes, so depth reads immediately on the first frame.
        [target[0] + distance, target[1] + distance, target[2] + distance]
    };
    (position, target)
}
