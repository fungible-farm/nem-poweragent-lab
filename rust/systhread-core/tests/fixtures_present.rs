mod common;
use common::fixture_path;

#[test]
fn lab6_fixtures_were_copied_verbatim() {
    let grid_instances = std::fs::read_to_string(fixture_path("schema/grid_instances.yaml"))
        .expect("grid_instances.yaml should have been copied in Task 0");
    assert!(grid_instances.contains("bus_4052"));

    let expected_grid_sysml =
        std::fs::read_to_string(fixture_path("expected/expected_grid_topology.sysml"))
            .expect("expected_grid_topology.sysml should have been copied in Task 0");
    assert!(expected_grid_sysml.starts_with("package GridTopology {"));
}
