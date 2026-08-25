use crate::iso_ir::{Edge, Node};
use kasuari::WeightedRelation::{EQ, LE};
use kasuari::{Solver, Strength, Variable};
use std::collections::{BTreeMap, BTreeSet, VecDeque};

pub const ROW_SPACING: f64 = 2.0;
pub const BUS_GAP: f64 = 2.0;

fn round6(v: f64) -> f64 {
    (v * 1_000_000.0).round() / 1_000_000.0
}

/// BFS forest over the real anchor-to-anchor `branch` graph -- one tree per connected component,
/// rooted at that component's own highest-real-degree anchor (ties broken by id for determinism).
/// Ports translate_iso_ir.py's `_anchor_forest` exactly, including its tie-break rule.
fn anchor_forest(
    anchor_ids: &[String],
    adjacency: &BTreeMap<String, BTreeSet<String>>,
) -> (BTreeMap<String, u32>, BTreeMap<String, String>, Vec<String>) {
    let mut depth: BTreeMap<String, u32> = BTreeMap::new();
    let mut parent: BTreeMap<String, String> = BTreeMap::new();
    let mut roots: Vec<String> = Vec::new();
    let mut remaining: BTreeSet<String> = anchor_ids.iter().cloned().collect();

    while !remaining.is_empty() {
        let root = remaining
            .iter()
            .min_by_key(|b| {
                let degree = adjacency.get(*b).map(|n| n.intersection(&remaining).count()).unwrap_or(0);
                (std::cmp::Reverse(degree), (*b).clone())
            })
            .unwrap()
            .clone();
        roots.push(root.clone());
        depth.insert(root.clone(), 0);
        remaining.remove(&root);

        let mut queue: VecDeque<String> = VecDeque::new();
        queue.push_back(root);
        while let Some(current) = queue.pop_front() {
            let neighbours = adjacency.get(&current).cloned().unwrap_or_default();
            for neighbour in neighbours {
                if remaining.contains(&neighbour) {
                    let d = depth[&current] + 1;
                    depth.insert(neighbour.clone(), d);
                    parent.insert(neighbour.clone(), current.clone());
                    remaining.remove(&neighbour);
                    queue.push_back(neighbour);
                }
            }
        }
    }
    (depth, parent, roots)
}

/// Solves each depth level's x positions with `kasuari`, one level at a time. Ports
/// translate_iso_ir.py's `_level_x_positions` exactly: depth 0 (component roots) get REQUIRED
/// gaps plus a WEAK pin on the first root at x=0; each deeper level gets REQUIRED sibling gaps
/// plus a REQUIRED centroid-equals-parent constraint, sibling *groups* also kept BUS_GAP apart.
fn level_x_positions(
    anchor_ids: &[String],
    depth: &BTreeMap<String, u32>,
    parent: &BTreeMap<String, String>,
    roots: &[String],
) -> BTreeMap<String, f64> {
    let mut x_by_anchor: BTreeMap<String, f64> = BTreeMap::new();
    if anchor_ids.is_empty() {
        return x_by_anchor;
    }

    let mut ordered_roots: Vec<String> = roots.to_vec();
    ordered_roots.sort();

    {
        let mut solver = Solver::new();
        let root_vars: BTreeMap<String, Variable> =
            ordered_roots.iter().map(|r| (r.clone(), Variable::new())).collect();
        for pair in ordered_roots.windows(2) {
            let (left, right) = (&pair[0], &pair[1]);
            solver
                .add_constraints([(root_vars[left] + BUS_GAP) | LE(Strength::REQUIRED) | root_vars[right]])
                .unwrap();
        }
        if let Some(first) = ordered_roots.first() {
            solver
                .add_constraints([root_vars[first] | EQ(Strength::WEAK) | 0.0])
                .unwrap();
        }
        for r in &ordered_roots {
            x_by_anchor.insert(r.clone(), round6(solver.get_value(root_vars[r])));
        }
    }

    let max_depth = depth.values().copied().max().unwrap_or(0);
    for d in 1..=max_depth {
        let level: Vec<String> = anchor_ids
            .iter()
            .filter(|b| depth.get(*b) == Some(&d))
            .cloned()
            .collect();
        if level.is_empty() {
            continue;
        }
        let mut groups: BTreeMap<String, Vec<String>> = BTreeMap::new();
        for b in &level {
            groups.entry(parent[b].clone()).or_default().push(b.clone());
        }
        let mut ordered_parents: Vec<String> = groups.keys().cloned().collect();
        ordered_parents.sort_by(|a, b| x_by_anchor[a].total_cmp(&x_by_anchor[b]));

        let mut solver = Solver::new();
        let mut x_vars: BTreeMap<String, Variable> = BTreeMap::new();
        let mut previous_group_last: Option<Variable> = None;
        for p in &ordered_parents {
            let siblings = &groups[p];
            for b in siblings {
                x_vars.insert(b.clone(), Variable::new());
            }
            for pair in siblings.windows(2) {
                let (left, right) = (&pair[0], &pair[1]);
                solver
                    .add_constraints([(x_vars[left] + BUS_GAP) | LE(Strength::REQUIRED) | x_vars[right]])
                    .unwrap();
            }
            let mut total = kasuari::Expression::from_variable(x_vars[&siblings[0]]);
            for b in &siblings[1..] {
                total = total + x_vars[b];
            }
            let target = siblings.len() as f64 * x_by_anchor[p];
            solver.add_constraints([total | EQ(Strength::REQUIRED) | target]).unwrap();
            if let Some(prev_last) = previous_group_last {
                solver
                    .add_constraints([(prev_last + BUS_GAP) | LE(Strength::REQUIRED) | x_vars[&siblings[0]]])
                    .unwrap();
            }
            previous_group_last = Some(x_vars[siblings.last().unwrap()]);
        }
        for (b, var) in &x_vars {
            x_by_anchor.insert(b.clone(), round6(solver.get_value(*var)));
        }
    }
    x_by_anchor
}

/// Ports translate_iso_ir.py's `_cassowary_positions` exactly: anchors (nodes that are not the
/// `from` side of an `attachment` edge) are laid out by their real `branch`-edge graph; leaves
/// (nodes that are the `from` side of an `attachment` edge) are pulled to their target anchor's x,
/// one row below, grouped/centered the same way anchors are.
pub fn cassowary_positions(nodes: &[Node], edges: &[Edge]) -> Vec<(f64, f64)> {
    let attach_target: BTreeMap<String, String> = edges
        .iter()
        .filter(|e| e.edge_type == "attachment")
        .map(|e| (e.from.clone(), e.to.clone()))
        .collect();
    let leaf_ids: BTreeSet<&String> = attach_target.keys().collect();
    let anchor_ids: Vec<String> = nodes
        .iter()
        .map(|n| &n.id)
        .filter(|id| !leaf_ids.contains(id))
        .cloned()
        .collect();

    let mut adjacency: BTreeMap<String, BTreeSet<String>> =
        anchor_ids.iter().map(|a| (a.clone(), BTreeSet::new())).collect();
    for e in edges {
        if e.edge_type == "branch" && adjacency.contains_key(&e.from) && adjacency.contains_key(&e.to) {
            adjacency.get_mut(&e.from).unwrap().insert(e.to.clone());
            adjacency.get_mut(&e.to).unwrap().insert(e.from.clone());
        }
    }

    let (depth, parent, roots) = anchor_forest(&anchor_ids, &adjacency);
    let x_by_anchor = level_x_positions(&anchor_ids, &depth, &parent, &roots);

    let leaf_order: Vec<String> = nodes
        .iter()
        .map(|n| &n.id)
        .filter(|id| leaf_ids.contains(id))
        .cloned()
        .collect();
    let mut groups: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let mut unattached: Vec<String> = Vec::new();
    for leaf in &leaf_order {
        match attach_target.get(leaf) {
            Some(target) if x_by_anchor.contains_key(target) => {
                groups.entry(target.clone()).or_default().push(leaf.clone());
            }
            _ => unattached.push(leaf.clone()),
        }
    }

    let mut solver = Solver::new();
    let mut leaf_x_vars: BTreeMap<String, Variable> = BTreeMap::new();
    for (target, siblings) in &groups {
        for leaf in siblings {
            leaf_x_vars.insert(leaf.clone(), Variable::new());
        }
        for pair in siblings.windows(2) {
            let (left, right) = (&pair[0], &pair[1]);
            solver
                .add_constraints([(leaf_x_vars[left] + BUS_GAP) | LE(Strength::REQUIRED) | leaf_x_vars[right]])
                .unwrap();
        }
        let mut total = kasuari::Expression::from_variable(leaf_x_vars[&siblings[0]]);
        for leaf in &siblings[1..] {
            total = total + leaf_x_vars[leaf];
        }
        let centroid = siblings.len() as f64 * x_by_anchor[target];
        solver.add_constraints([total | EQ(Strength::REQUIRED) | centroid]).unwrap();
    }
    for leaf in &unattached {
        let v = Variable::new();
        leaf_x_vars.insert(leaf.clone(), v);
        solver.add_constraints([v | EQ(Strength::WEAK) | 0.0]).unwrap();
    }

    let mut positions: BTreeMap<String, (f64, f64)> = BTreeMap::new();
    for a in &anchor_ids {
        positions.insert(a.clone(), (x_by_anchor[a], depth[a] as f64 * ROW_SPACING));
    }
    for id in &leaf_order {
        let target = attach_target.get(id);
        let row = match target.and_then(|t| depth.get(t)) {
            Some(d) => (*d as f64 + 1.0) * ROW_SPACING,
            None => ROW_SPACING,
        };
        let x = round6(solver.get_value(leaf_x_vars[id]));
        positions.insert(id.clone(), (x, row));
    }

    nodes.iter().map(|n| positions[&n.id]).collect()
}
