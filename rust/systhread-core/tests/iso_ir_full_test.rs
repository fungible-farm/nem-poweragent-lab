mod common;
use common::fixture_path;
use systhread_core::instances::{load_digital_thread, load_grid, load_pipeline};
use systhread_core::iso_ir::{build_digital_thread_iso_ir, build_grid_iso_ir, build_pipeline_iso_ir};

fn expected(fixture_rel: &str) -> String {
    std::fs::read_to_string(fixture_path(fixture_rel)).unwrap()
}

#[test]
fn digital_thread_iso_ir_matches_fixture_byte_identical() {
    let inst = load_digital_thread(&fixture_path("schema/digital_thread_instances.yaml")).unwrap();
    let got = serde_json::to_string_pretty(&build_digital_thread_iso_ir(&inst)).unwrap() + "\n";
    assert_eq!(got, expected("expected/expected_digital_thread_iso_ir.json"));
}

#[test]
fn grid_iso_ir_matches_fixture_byte_identical() {
    let inst = load_grid(&fixture_path("schema/grid_instances.yaml")).unwrap();
    let got = serde_json::to_string_pretty(&build_grid_iso_ir(&inst)).unwrap() + "\n";
    assert_eq!(got, expected("expected/expected_grid_topology_iso_ir.json"));
}

#[test]
fn pipeline_iso_ir_matches_fixture_byte_identical() {
    let inst = load_pipeline(&fixture_path("schema/pipeline_phases_instances.yaml")).unwrap();
    let got = serde_json::to_string_pretty(&build_pipeline_iso_ir(&inst)).unwrap() + "\n";
    assert_eq!(got, expected("expected/expected_pipeline_phases_iso_ir.json"));
}
