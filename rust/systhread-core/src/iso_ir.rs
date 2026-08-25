use crate::instances::{DigitalThreadInstances, GridInstances, PipelinePhasesInstances};

#[derive(Debug, Clone, PartialEq)]
pub struct Node {
    pub id: String,
    pub label: String,
    /// The SysML part-def type name this node came from ("Agent" | "MCPServer" | "DataSource" |
    /// "Bus" | "Generator" | "Phase") -- Task 8 maps this to the iso-IR "type"/"shape" fields.
    pub part_type: &'static str,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Edge {
    pub id: String,
    pub from: String,
    pub to: String,
    pub edge_type: String,
    pub kind: Option<String>,
}

pub fn extract_digital_thread(inst: &DigitalThreadInstances) -> (Vec<Node>, Vec<Edge>) {
    let mut nodes = Vec::new();
    let mut edges = Vec::new();

    for a in &inst.agents {
        nodes.push(Node {
            id: a.name.clone(),
            label: a.name.clone(),
            part_type: "Agent",
        });
        if let Some(uses) = &a.uses {
            edges.push(Edge {
                id: format!("{}_attach", a.name),
                from: a.name.clone(),
                to: uses.clone(),
                edge_type: "attachment".to_string(),
                kind: None,
            });
        }
    }
    for m in &inst.mcp_servers {
        nodes.push(Node {
            id: m.name.clone(),
            label: m.name.clone(),
            part_type: "MCPServer",
        });
    }
    for d in &inst.data_sources {
        nodes.push(Node {
            id: d.name.clone(),
            label: d.name.clone(),
            part_type: "DataSource",
        });
    }
    (nodes, edges)
}

pub fn extract_grid(inst: &GridInstances) -> (Vec<Node>, Vec<Edge>) {
    let mut nodes = Vec::new();
    let mut edges = Vec::new();

    for b in &inst.buses {
        nodes.push(Node {
            id: b.name.clone(),
            label: b.name.clone(),
            part_type: "Bus",
        });
    }
    for g in &inst.generators {
        nodes.push(Node {
            id: g.name.clone(),
            label: g.name.clone(),
            part_type: "Generator",
        });
        edges.push(Edge {
            id: format!("{}_attach", g.name),
            from: g.name.clone(),
            to: g.bus.clone(),
            edge_type: "attachment".to_string(),
            kind: None,
        });
    }
    for l in &inst.lines {
        edges.push(Edge {
            id: l.name.clone(),
            from: l.from_bus.clone(),
            to: l.to_bus.clone(),
            edge_type: "branch".to_string(),
            kind: Some(l.kind.clone()),
        });
    }
    (nodes, edges)
}

pub fn extract_pipeline(inst: &PipelinePhasesInstances) -> (Vec<Node>, Vec<Edge>) {
    let mut nodes = Vec::new();
    let mut edges = Vec::new();

    for p in &inst.phases {
        nodes.push(Node {
            id: p.name.clone(),
            label: p.name.clone(),
            part_type: "Phase",
        });
        if let Some(next) = &p.next {
            edges.push(Edge {
                id: format!("{}_next", p.name),
                from: p.name.clone(),
                to: next.clone(),
                edge_type: "sequence".to_string(),
                kind: None,
            });
        }
    }
    (nodes, edges)
}

const PER_ROW: usize = 3;
const SPACING: f64 = 2.0;

/// Deterministic row-major grid layout -- Lab 6's fallback for a track with no edges at all.
/// None of the three real committed tracks currently hits this path (see this task's own
/// docstring in the plan); ported for dispatch completeness.
pub fn grid_positions(n: usize) -> Vec<(f64, f64)> {
    (0..n)
        .map(|i| (((i % PER_ROW) as f64) * SPACING, ((i / PER_ROW) as f64) * SPACING))
        .collect()
}

#[cfg(test)]
mod grid_positions_tests {
    use super::grid_positions;

    #[test]
    fn lays_out_row_major_with_spacing_two_per_row_three() {
        // Ports translate_iso_ir.py's _grid_positions(n, per_row=3, spacing=2) defaults exactly:
        // (i % 3) * 2, (i // 3) * 2.
        let positions = grid_positions(5);
        assert_eq!(
            positions,
            vec![(0.0, 0.0), (2.0, 0.0), (4.0, 0.0), (0.0, 2.0), (2.0, 2.0)]
        );
    }
}
