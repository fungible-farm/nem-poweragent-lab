mod common;
use common::fixture_path;
use systhread_core::instances::{load_digital_thread, load_grid, load_pipeline};
use systhread_core::iso_ir::{build_digital_thread_iso_ir, build_grid_iso_ir, build_pipeline_iso_ir};
use systhread_core::render::render_svg;

#[test]
fn digital_thread_svg_matches_fixture_byte_identical() {
    let inst = load_digital_thread(&fixture_path("schema/digital_thread_instances.yaml")).unwrap();
    let got = render_svg(&build_digital_thread_iso_ir(&inst));
    let expected = std::fs::read_to_string(fixture_path("expected/expected_digital_thread.svg")).unwrap();
    assert_eq!(got, expected);
}

#[test]
fn grid_svg_matches_fixture_byte_identical() {
    let inst = load_grid(&fixture_path("schema/grid_instances.yaml")).unwrap();
    let got = render_svg(&build_grid_iso_ir(&inst));
    let expected = std::fs::read_to_string(fixture_path("expected/expected_grid_topology.svg")).unwrap();
    assert_eq!(got, expected);
}

#[test]
fn pipeline_svg_matches_fixture_byte_identical() {
    let inst = load_pipeline(&fixture_path("schema/pipeline_phases_instances.yaml")).unwrap();
    let got = render_svg(&build_pipeline_iso_ir(&inst));
    let expected = std::fs::read_to_string(fixture_path("expected/expected_pipeline_phases.svg")).unwrap();
    assert_eq!(got, expected);
}
