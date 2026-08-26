//! Deterministic, ahead-of-time graph layout for the model explorer.
//!
//! Design: `docs/superpowers/specs/2026-08-26-systhread-3d-explorer-design.md` §4. This module is
//! a *sibling* of `layout.rs`, not an extension of it: `layout.rs` positions Part/containment
//! boxes for the isometric SVG diagram, this one positions an abstract node/edge graph for the
//! explorer. Design §3 is explicit that conflating the two "2D"s misunderstands both.
//!
//! Determinism rules this module obeys, all load-bearing for the byte-identical artifact gate:
//! a compile-time seed (never entropy), a fixed iteration count (never a convergence threshold or
//! a time budget), input-order iteration everywhere (never a `HashMap`), and no transcendental
//! functions (`sqrt` only, which IEEE-754 requires to be correctly rounded on every target).

use crate::cytoscape::CytoscapeGraph;
use crate::positioned::{Layout, NodePosition2D, NodePosition3D, PositionedGraph};
use std::collections::BTreeMap;

/// Fixed layout seed: the ASCII bytes of "SYSTHRED". Changing this value changes every explorer
/// artifact in every adopting project -- treat it as a wire-format constant, not a tuning knob.
pub const LAYOUT_SEED: u64 = 0x5359_5354_4852_4544;

/// Fixed iteration count. Not a convergence threshold on purpose: "run until it stops moving"
/// makes the output depend on float noise, and "run for 50ms" makes it depend on the machine.
pub const LAYOUT_ITERATIONS: usize = 300;

/// Target distance between two connected nodes, in the layout's own arbitrary units.
pub const IDEAL_EDGE_LENGTH: f64 = 2.0;

/// Starting per-iteration displacement cap; cooled linearly to zero over `LAYOUT_ITERATIONS`.
pub const INITIAL_TEMPERATURE: f64 = 4.0;

/// Distances below this are treated as coincident (see `delta_and_distance`), and displacements
/// below it are treated as zero. Guards every division by a distance in this module.
const MIN_DISTANCE: f64 = 1.0e-9;

/// Six-decimal rounding with `-0.0` normalized to `0.0`.
///
/// Deliberately a copy of `layout.rs`'s private `round6` rather than a shared helper: design §4
/// requires `layout.rs` to stay untouched, and making its private fn `pub(crate)` would be a
/// modification. Ten duplicated lines is the cheaper side of that trade.
fn round6(v: f64) -> f64 {
    (v * 1_000_000.0).round() / 1_000_000.0 + 0.0
}

/// SplitMix64 -- a fixed-seed PRNG in pure wrapping `u64` arithmetic, identical on every target.
/// Used only to spread the initial placement; nothing downstream of `initial_positions` is random.
struct SplitMix64 {
    state: u64,
}

impl SplitMix64 {
    fn new(seed: u64) -> Self {
        Self { state: seed }
    }

    fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    /// Uniform in `[-1.0, 1.0)`, built from the top 53 bits so the conversion is exact.
    fn next_unit(&mut self) -> f64 {
        let bits = self.next_u64() >> 11;
        let unit = bits as f64 / (1_u64 << 53) as f64;
        unit * 2.0 - 1.0
    }
}

/// Seeded initial placement inside a cube/square whose half-width grows linearly with node count,
/// so a large graph doesn't start hopelessly overlapped. Same seed, same stream order, every run.
fn initial_positions<const D: usize>(n: usize) -> Vec<[f64; D]> {
    let mut rng = SplitMix64::new(LAYOUT_SEED);
    let radius = IDEAL_EDGE_LENGTH * (n.max(1) as f64) / 2.0;
    (0..n)
        .map(|_| {
            let mut point = [0.0_f64; D];
            for coordinate in point.iter_mut() {
                *coordinate = rng.next_unit() * radius;
            }
            point
        })
        .collect()
}

/// Translates the layout so its centroid sits at the origin, then rounds to six decimals.
/// Centering makes the artifact translation-invariant (a camera framing the origin always frames
/// the model) and is the single place rounding happens, so every coordinate in the artifact has
/// passed through the same normalization.
fn center<const D: usize>(positions: &mut [[f64; D]]) {
    let n = positions.len();
    if n == 0 {
        return;
    }
    let mut centroid = [0.0_f64; D];
    for point in positions.iter() {
        for d in 0..D {
            centroid[d] += point[d];
        }
    }
    for value in centroid.iter_mut() {
        *value /= n as f64;
    }
    for point in positions.iter_mut() {
        for d in 0..D {
            point[d] = round6(point[d] - centroid[d]);
        }
    }
}

/// Which geometry to compute. Separate from `Layout` because a caller choosing a mode has no
/// positions yet: `Layout` carries data, `LayoutMode` carries only the choice.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LayoutMode {
    TwoD,
    ThreeD,
}

/// Vector from `b` to `a` and its length. Coincident points (distance below `MIN_DISTANCE`) get a
/// deterministic nudge along an axis picked from the two node *indices* -- never from an RNG, a
/// pointer, or iteration order, all of which would leak nondeterminism into the artifact.
fn delta_and_distance<const D: usize>(
    a: &[f64; D],
    b: &[f64; D],
    index_a: usize,
    index_b: usize,
) -> ([f64; D], f64) {
    let mut delta = [0.0_f64; D];
    let mut sum_of_squares = 0.0;
    for d in 0..D {
        delta[d] = a[d] - b[d];
        sum_of_squares += delta[d] * delta[d];
    }
    let distance = sum_of_squares.sqrt();
    if distance < MIN_DISTANCE {
        let mut nudge = [0.0_f64; D];
        nudge[(index_a + index_b) % D] = MIN_DISTANCE;
        return (nudge, MIN_DISTANCE);
    }
    (delta, distance)
}

/// Resolves each edge to a pair of node indices, dropping edges that name a node the graph does
/// not contain and self-loops (neither contributes a direction to push along). Uses a `BTreeMap`,
/// not a `HashMap`: iteration order never reaches the output, but the crate-wide rule is that no
/// hash-ordered container sits anywhere on an artifact's data path.
fn edge_indices(graph: &CytoscapeGraph) -> Vec<(usize, usize)> {
    let index: BTreeMap<&str, usize> = graph
        .nodes
        .iter()
        .enumerate()
        .map(|(i, n)| (n.data.id.as_str(), i))
        .collect();
    graph
        .edges
        .iter()
        .filter_map(|e| {
            let a = *index.get(e.data.source.as_str())?;
            let b = *index.get(e.data.target.as_str())?;
            if a == b { None } else { Some((a, b)) }
        })
        .collect()
}

/// Fruchterman-Reingold refinement: all-pairs repulsion `k²/d`, per-edge attraction `d²/k`, with
/// a per-iteration displacement cap cooled linearly to zero. Fixed iteration count, fixed
/// traversal order, no early exit -- the three things that make the result reproducible.
fn refine<const D: usize>(positions: &mut [[f64; D]], edges: &[(usize, usize)]) {
    let n = positions.len();
    if n < 2 {
        return;
    }
    let k = IDEAL_EDGE_LENGTH;
    for iteration in 0..LAYOUT_ITERATIONS {
        let mut displacement = vec![[0.0_f64; D]; n];

        for i in 0..n {
            for j in (i + 1)..n {
                let (delta, distance) = delta_and_distance(&positions[i], &positions[j], i, j);
                let force = (k * k) / distance;
                for d in 0..D {
                    let unit = delta[d] / distance;
                    displacement[i][d] += unit * force;
                    displacement[j][d] -= unit * force;
                }
            }
        }

        for &(a, b) in edges {
            let (delta, distance) = delta_and_distance(&positions[a], &positions[b], a, b);
            let force = (distance * distance) / k;
            for d in 0..D {
                let unit = delta[d] / distance;
                displacement[a][d] -= unit * force;
                displacement[b][d] += unit * force;
            }
        }

        let temperature =
            INITIAL_TEMPERATURE * (1.0 - (iteration as f64) / (LAYOUT_ITERATIONS as f64));
        for i in 0..n {
            let mut sum_of_squares = 0.0;
            for d in 0..D {
                sum_of_squares += displacement[i][d] * displacement[i][d];
            }
            let magnitude = sum_of_squares.sqrt();
            if magnitude < MIN_DISTANCE {
                continue;
            }
            let scale = magnitude.min(temperature) / magnitude;
            for d in 0..D {
                positions[i][d] += displacement[i][d] * scale;
            }
        }
    }
}

fn solve<const D: usize>(graph: &CytoscapeGraph) -> Vec<[f64; D]> {
    let mut positions = initial_positions::<D>(graph.nodes.len());
    refine(&mut positions, &edge_indices(graph));
    center(&mut positions);
    positions
}

/// Flat force-directed layout -- the same solver as `layout_3d` with one dimension removed, which
/// is exactly what design §4 specifies ("computes `Layout::TwoD` and `Layout::ThreeD` ... using a
/// fixed-seed, fixed-iteration-count force-directed algorithm"). This is *not* the isometric
/// diagram layout in `layout.rs`; see design §3 on not conflating the two.
pub fn layout_2d(graph: &CytoscapeGraph) -> Layout {
    let positions = solve::<2>(graph);
    Layout::TwoD(
        graph
            .nodes
            .iter()
            .zip(positions)
            .map(|(node, p)| NodePosition2D {
                node_id: node.data.id.clone(),
                x: p[0],
                y: p[1],
            })
            .collect(),
    )
}

pub fn layout_3d(graph: &CytoscapeGraph) -> Layout {
    let positions = solve::<3>(graph);
    Layout::ThreeD(
        graph
            .nodes
            .iter()
            .zip(positions)
            .map(|(node, p)| NodePosition3D {
                node_id: node.data.id.clone(),
                x: p[0],
                y: p[1],
                z: p[2],
            })
            .collect(),
    )
}

/// The one entry point the CLI and the explorer both use.
pub fn build_positioned_graph(graph: CytoscapeGraph, mode: LayoutMode) -> PositionedGraph {
    let layout = match mode {
        LayoutMode::TwoD => layout_2d(&graph),
        LayoutMode::ThreeD => layout_3d(&graph),
    };
    PositionedGraph { graph, layout }
}

#[cfg(test)]
mod placement_tests {
    use super::{SplitMix64, center, initial_positions, round6, LAYOUT_SEED};

    #[test]
    fn splitmix64_is_reproducible_for_a_fixed_seed() {
        let mut a = SplitMix64::new(LAYOUT_SEED);
        let mut b = SplitMix64::new(LAYOUT_SEED);
        let first: Vec<u64> = (0..8).map(|_| a.next_u64()).collect();
        let second: Vec<u64> = (0..8).map(|_| b.next_u64()).collect();
        assert_eq!(first, second);
        // A real generator, not a constant sequence.
        assert!(first.windows(2).any(|w| w[0] != w[1]));
    }

    #[test]
    fn next_unit_stays_inside_the_half_open_unit_interval() {
        let mut rng = SplitMix64::new(LAYOUT_SEED);
        for _ in 0..10_000 {
            let v = rng.next_unit();
            assert!((-1.0..1.0).contains(&v), "next_unit produced {v}");
        }
    }

    #[test]
    fn initial_positions_are_reproducible_and_shaped_by_dimension() {
        let a = initial_positions::<3>(5);
        let b = initial_positions::<3>(5);
        assert_eq!(a, b);
        assert_eq!(a.len(), 5);

        let flat = initial_positions::<2>(5);
        assert_eq!(flat.len(), 5);
        // The 2D and 3D placements draw from the same seeded stream in the same order, so their
        // first two coordinates agree -- a 2D layout is a projection of the same starting state.
        assert_eq!(flat[0][0], a[0][0]);
    }

    #[test]
    fn initial_positions_are_not_all_coincident() {
        let p = initial_positions::<3>(4);
        assert!(p.iter().any(|q| *q != p[0]), "every node landed on the same point: {p:?}");
    }

    #[test]
    fn center_moves_the_centroid_to_the_origin_and_rounds() {
        let mut p = [[1.0, 2.0, 3.0], [3.0, 4.0, 5.0]];
        center(&mut p);
        assert_eq!(p, [[-1.0, -1.0, -1.0], [1.0, 1.0, 1.0]]);
    }

    #[test]
    fn center_normalizes_negative_zero() {
        // Same hazard layout.rs's round6 already guards: JSON prints "-0.0" and "0.0" as different
        // bytes, which would break the byte-identical gate on a run-to-run sign flip.
        let mut p = [[0.0_f64, 0.0, 0.0]];
        center(&mut p);
        assert!(!p[0][0].is_sign_negative());
    }

    #[test]
    fn round6_matches_the_isometric_pipelines_rounding() {
        assert_eq!(round6(1.234_567_89), 1.234_568);
        assert!(!round6(-0.0_f64).is_sign_negative());
    }

    #[test]
    fn round6_normalizes_negative_zero_produced_by_rounding_a_tiny_negative_input() {
        // -1e-7 rounds to -0.0 at the rounding step itself (not the input), so the normalization
        // must happen after rounding, not before. `-0.0 == 0.0` is true in IEEE 754, so assert on
        // sign rather than equality -- otherwise this test would pass even with the bug present.
        assert!(!round6(-1.0e-7_f64).is_sign_negative());
    }
}
