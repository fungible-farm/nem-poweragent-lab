mod common;
use common::fixture_path;
use systhread_core::instances::{load_digital_thread, load_grid};
use systhread_core::iso_ir::{extract_digital_thread, extract_grid};
use systhread_core::layout::cassowary_positions;

fn expected_positions(fixture_rel: &str) -> Vec<(f64, f64)> {
    let text = std::fs::read_to_string(fixture_path(fixture_rel)).unwrap();
    let json: serde_json::Value = serde_json::from_str(&text).unwrap();
    json["nodes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|n| {
            (
                n["position"]["x"].as_f64().unwrap(),
                n["position"]["y"].as_f64().unwrap(),
            )
        })
        .collect()
}

#[test]
fn digital_thread_positions_match_fixture() {
    let inst = load_digital_thread(&fixture_path("schema/digital_thread_instances.yaml")).unwrap();
    let (nodes, edges) = extract_digital_thread(&inst);
    let got = cassowary_positions(&nodes, &edges);
    assert_eq!(got, expected_positions("expected/expected_digital_thread_iso_ir.json"));
}

#[test]
fn grid_topology_positions_match_fixture() {
    let inst = load_grid(&fixture_path("schema/grid_instances.yaml")).unwrap();
    let (nodes, edges) = extract_grid(&inst);
    let got = cassowary_positions(&nodes, &edges);
    assert_eq!(got, expected_positions("expected/expected_grid_topology_iso_ir.json"));
}
