mod common;
use common::fixture_path;
use systhread_core::instances::{load_digital_thread, load_grid, load_pipeline};
use systhread_core::sysml_gen::{render_digital_thread, render_grid_topology, render_pipeline_phases};

#[test]
fn digital_thread_matches_fixture_byte_identical() {
    let inst = load_digital_thread(&fixture_path("schema/digital_thread_instances.yaml")).unwrap();
    let got = render_digital_thread(&inst);
    let expected = std::fs::read_to_string(fixture_path("expected/expected_digital_thread.sysml")).unwrap();
    assert_eq!(got, expected);
}

#[test]
fn grid_topology_matches_fixture_byte_identical() {
    let inst = load_grid(&fixture_path("schema/grid_instances.yaml")).unwrap();
    let got = render_grid_topology(&inst);
    let expected = std::fs::read_to_string(fixture_path("expected/expected_grid_topology.sysml")).unwrap();
    assert_eq!(got, expected);
}

#[test]
fn pipeline_phases_matches_fixture_byte_identical() {
    let inst = load_pipeline(&fixture_path("schema/pipeline_phases_instances.yaml")).unwrap();
    let got = render_pipeline_phases(&inst);
    let expected = std::fs::read_to_string(fixture_path("expected/expected_pipeline_phases.sysml")).unwrap();
    assert_eq!(got, expected);
}
