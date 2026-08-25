mod common;
use common::fixture_path;
use systhread_core::instances::{load_digital_thread, load_grid, load_pipeline};
use systhread_core::iso_ir::{extract_digital_thread, extract_grid, extract_pipeline, Edge};

/// Reads a `nodes`/`edges` fixture JSON and returns just the (id, part_type-independent label)
/// pairs and the edges list, both in fixture order -- Task 4 doesn't compute positions/shape/type
/// yet, so this helper strips those fields before comparing.
fn expected_node_ids(fixture_rel: &str) -> Vec<String> {
    let text = std::fs::read_to_string(fixture_path(fixture_rel)).unwrap();
    let json: serde_json::Value = serde_json::from_str(&text).unwrap();
    json["nodes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|n| n["id"].as_str().unwrap().to_string())
        .collect()
}

fn expected_edges(fixture_rel: &str) -> Vec<Edge> {
    let text = std::fs::read_to_string(fixture_path(fixture_rel)).unwrap();
    let json: serde_json::Value = serde_json::from_str(&text).unwrap();
    json.get("edges")
        .and_then(|e| e.as_array())
        .map(|arr| {
            arr.iter()
                .map(|e| Edge {
                    id: e["id"].as_str().unwrap().to_string(),
                    from: e["from"].as_str().unwrap().to_string(),
                    to: e["to"].as_str().unwrap().to_string(),
                    edge_type: e["type"].as_str().unwrap().to_string(),
                    kind: e.get("kind").and_then(|k| k.as_str()).map(String::from),
                })
                .collect()
        })
        .unwrap_or_default()
}

#[test]
fn digital_thread_structure_matches_fixture() {
    let inst = load_digital_thread(&fixture_path("schema/digital_thread_instances.yaml"));
    let (nodes, edges) = extract_digital_thread(&inst);
    let ids: Vec<String> = nodes.iter().map(|n| n.id.clone()).collect();
    assert_eq!(ids, expected_node_ids("expected/expected_digital_thread_iso_ir.json"));
    assert_eq!(edges, expected_edges("expected/expected_digital_thread_iso_ir.json"));
}

#[test]
fn grid_structure_matches_fixture() {
    let inst = load_grid(&fixture_path("schema/grid_instances.yaml"));
    let (nodes, edges) = extract_grid(&inst);
    let ids: Vec<String> = nodes.iter().map(|n| n.id.clone()).collect();
    assert_eq!(ids, expected_node_ids("expected/expected_grid_topology_iso_ir.json"));
    assert_eq!(edges, expected_edges("expected/expected_grid_topology_iso_ir.json"));
}

#[test]
fn pipeline_structure_matches_fixture() {
    let inst = load_pipeline(&fixture_path("schema/pipeline_phases_instances.yaml"));
    let (nodes, edges) = extract_pipeline(&inst);
    let ids: Vec<String> = nodes.iter().map(|n| n.id.clone()).collect();
    assert_eq!(ids, expected_node_ids("expected/expected_pipeline_phases_iso_ir.json"));
    assert_eq!(edges, expected_edges("expected/expected_pipeline_phases_iso_ir.json"));
}
