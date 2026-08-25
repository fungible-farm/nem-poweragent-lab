mod common;
use common::fixture_path;
use systhread_core::instances::{load_digital_thread, load_grid, load_pipeline};
use systhread_core::sysml_gen::{render_digital_thread, render_grid_topology, render_pipeline_phases};
use systhread_core::validate::is_valid_sysml;

#[test]
fn accepts_all_three_generated_tracks() {
    let dt = load_digital_thread(&fixture_path("schema/digital_thread_instances.yaml"));
    assert!(is_valid_sysml(&render_digital_thread(&dt)).is_ok());

    let grid = load_grid(&fixture_path("schema/grid_instances.yaml"));
    assert!(is_valid_sysml(&render_grid_topology(&grid)).is_ok());

    let pipeline = load_pipeline(&fixture_path("schema/pipeline_phases_instances.yaml"));
    assert!(is_valid_sysml(&render_pipeline_phases(&pipeline)).is_ok());
}

#[test]
fn rejects_broken_input_with_a_real_error() {
    let broken = "package Broken {\n    part def X {\n";
    let err = is_valid_sysml(broken).expect_err("unterminated block must be rejected");
    assert!(!err.is_empty());
}
