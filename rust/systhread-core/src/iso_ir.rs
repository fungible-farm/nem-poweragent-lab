use crate::instances::{DigitalThreadInstances, GridInstances, PipelinePhasesInstances};
use crate::layout::{cassowary_positions, sequence_positions};
use serde_json::{json, Value};

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

fn type_by_part_type(part_type: &str) -> &'static str {
    match part_type {
        "Agent" => "generic",
        "MCPServer" => "server",
        "DataSource" => "database",
        "Bus" => "router",
        "Generator" => "warehouse",
        "Phase" => "generic",
        _ => "generic",
    }
}

fn shape_by_type(node_type: &str) -> &'static str {
    match node_type {
        "router" => "bar",
        "warehouse" => "circle",
        _ => "box",
    }
}

/// Dispatches by real edge shape, exactly like translate_iso_ir.py's `_iso_positions`: a
/// `sequence` edge means a real declared order; any other edges mean an undirected hub/star
/// graph; no edges at all keeps the plain row-major grid.
fn positions_for(nodes: &[Node], edges: &[Edge]) -> Vec<(f64, f64)> {
    if edges.iter().any(|e| e.edge_type == "sequence") {
        sequence_positions(nodes, edges)
    } else if !edges.is_empty() {
        cassowary_positions(nodes, edges)
    } else {
        grid_positions(nodes.len())
    }
}

fn assemble(title: &str, nodes: &[Node], edges: &[Edge]) -> Value {
    // Mirrors translate_iso_ir.py's _iso_positions dispatch: the no-edges fallback calls
    // _grid_positions, which is annotated `list[dict[str, int]]` and computes on Python ints, so
    // json.dumps writes bare integer literals ("x": 2, not "x": 2.0). The other two paths
    // (sequence_positions, cassowary_positions) produce real fractional/rounded values that
    // Python also serializes as floats, so only this fallback path needs integer JSON numbers.
    let grid_fallback = edges.is_empty();
    let positions = positions_for(nodes, edges);
    let node_values: Vec<Value> = nodes
        .iter()
        .zip(positions.iter())
        .map(|(n, (x, y))| {
            let node_type = type_by_part_type(n.part_type);
            let position = if grid_fallback {
                json!({ "x": *x as i64, "y": *y as i64 })
            } else {
                json!({ "x": x, "y": y })
            };
            json!({
                "id": n.id,
                "label": n.label,
                "type": node_type,
                "shape": shape_by_type(node_type),
                "position": position,
            })
        })
        .collect();

    let mut spec = json!({
        "title": title,
        "type": "generic",
        "nodes": node_values,
    });

    if !edges.is_empty() {
        let edge_values: Vec<Value> = edges
            .iter()
            .map(|e| {
                let mut v = json!({
                    "id": e.id,
                    "from": e.from,
                    "to": e.to,
                    "type": e.edge_type,
                });
                if let Some(kind) = &e.kind {
                    v["kind"] = json!(kind);
                }
                v
            })
            .collect();
        spec["edges"] = json!(edge_values);
    }

    spec
}

pub fn build_digital_thread_iso_ir(inst: &DigitalThreadInstances) -> Value {
    let (nodes, edges) = extract_digital_thread(inst);
    assemble("Lab 6 Track A -- Digital Thread", &nodes, &edges)
}

pub fn build_grid_iso_ir(inst: &GridInstances) -> Value {
    let (nodes, edges) = extract_grid(inst);
    assemble("Lab 6 Track B -- Grid Topology", &nodes, &edges)
}

pub fn build_pipeline_iso_ir(inst: &PipelinePhasesInstances) -> Value {
    let (nodes, edges) = extract_pipeline(inst);
    assemble("Lab 6 Track C -- Pipeline Phases", &nodes, &edges)
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

#[cfg(test)]
mod assemble_grid_fallback_tests {
    use super::{assemble, Node};

    #[test]
    fn no_edges_fallback_serializes_positions_as_json_integers_not_floats() {
        // Regression test for the no-edges fallback path (grid_positions via positions_for):
        // translate_iso_ir.py's _grid_positions is annotated `list[dict[str, int]]` and computes
        // on Python ints, so json.dumps writes "x": 2 (an integer literal), never "x": 2.0. The
        // Rust port must match that JSON number type for this one path, even though
        // grid_positions itself still returns Vec<(f64, f64)>.
        let nodes = vec![
            Node { id: "a".to_string(), label: "a".to_string(), part_type: "Agent" },
            Node { id: "b".to_string(), label: "b".to_string(), part_type: "Agent" },
        ];
        let edges: Vec<super::Edge> = vec![];

        let spec = assemble("Test", &nodes, &edges);

        let node_b = &spec["nodes"][1];
        let x = &node_b["position"]["x"];
        let y = &node_b["position"]["y"];

        assert!(x.is_i64(), "expected integer JSON number for x, got {x:?}");
        assert!(y.is_i64(), "expected integer JSON number for y, got {y:?}");
        assert_eq!(x, 2);
        assert_eq!(y, 0);

        // Also check the raw serialized text doesn't contain a decimal point for this field.
        let serialized = serde_json::to_string(&spec).unwrap();
        assert!(
            serialized.contains("\"x\":2") || serialized.contains("\"x\": 2"),
            "serialized output should contain a bare integer \"x\": 2, got: {serialized}"
        );
    }
}
