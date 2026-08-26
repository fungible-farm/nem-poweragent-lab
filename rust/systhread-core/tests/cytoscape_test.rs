mod common;
use common::fixture_path;
use systhread_core::cytoscape::from_iso_ir;
use systhread_core::instances::{load_digital_thread, load_grid};
use systhread_core::iso_ir::{extract_digital_thread, extract_grid};

#[test]
fn grid_nodes_carry_id_label_and_part_type_as_kind() {
    let inst = load_grid(&fixture_path("schema/grid_instances.yaml")).unwrap();
    let (nodes, edges) = extract_grid(&inst);
    let graph = from_iso_ir(&nodes, &edges);

    assert_eq!(graph.nodes.len(), nodes.len());
    let bus = graph
        .nodes
        .iter()
        .find(|n| n.data.id == "bus_4052")
        .expect("bus_4052 should be a node");
    assert_eq!(bus.data.label, "bus_4052");
    assert_eq!(bus.data.kind, "Bus");
    assert_eq!(bus.data.parent, None);
    assert_eq!(bus.data.z_layer, None);
    assert_eq!(bus.data.semantic_type, None);

    let r#gen = graph
        .nodes
        .iter()
        .find(|n| n.data.id == "gen_4052")
        .expect("gen_4052 should be a node");
    assert_eq!(r#gen.data.kind, "Generator");
}

#[test]
fn grid_edges_map_from_to_onto_source_target() {
    let inst = load_grid(&fixture_path("schema/grid_instances.yaml")).unwrap();
    let (nodes, edges) = extract_grid(&inst);
    let graph = from_iso_ir(&nodes, &edges);

    assert_eq!(graph.edges.len(), edges.len());
    let attach = graph
        .edges
        .iter()
        .find(|e| e.data.id == "gen_4052_attach")
        .expect("gen_4052_attach should be an edge");
    assert_eq!(attach.data.source, "gen_4052");
    assert_eq!(attach.data.target, "bus_4052");
    assert_eq!(attach.data.label, "attachment");

    // A `branch` edge carries iso-IR's `kind` too -- it must survive into the label rather than
    // being silently dropped, since it is the only place line type is represented in the graph.
    let branch = graph
        .edges
        .iter()
        .find(|e| e.data.label.starts_with("branch:"))
        .expect("grid has branch edges with a kind");
    assert!(branch.data.label.len() > "branch:".len());
}

#[test]
fn node_and_edge_order_follows_iso_ir_order_exactly() {
    let inst = load_digital_thread(&fixture_path("schema/digital_thread_instances.yaml")).unwrap();
    let (nodes, edges) = extract_digital_thread(&inst);
    let graph = from_iso_ir(&nodes, &edges);

    let got: Vec<&str> = graph.nodes.iter().map(|n| n.data.id.as_str()).collect();
    let want: Vec<&str> = nodes.iter().map(|n| n.id.as_str()).collect();
    assert_eq!(got, want);

    let got: Vec<&str> = graph.edges.iter().map(|e| e.data.id.as_str()).collect();
    let want: Vec<&str> = edges.iter().map(|e| e.id.as_str()).collect();
    assert_eq!(got, want);
}
