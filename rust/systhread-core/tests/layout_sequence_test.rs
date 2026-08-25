mod common;
use common::fixture_path;
use systhread_core::instances::load_pipeline;
use systhread_core::iso_ir::extract_pipeline;
use systhread_core::layout::sequence_positions;

#[test]
fn pipeline_positions_match_fixture() {
    let inst = load_pipeline(&fixture_path("schema/pipeline_phases_instances.yaml"));
    let (nodes, edges) = extract_pipeline(&inst);
    let got = sequence_positions(&nodes, &edges);

    let text = std::fs::read_to_string(fixture_path("expected/expected_pipeline_phases_iso_ir.json")).unwrap();
    let json: serde_json::Value = serde_json::from_str(&text).unwrap();
    let expected: Vec<(f64, f64)> = json["nodes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|n| (n["position"]["x"].as_f64().unwrap(), n["position"]["y"].as_f64().unwrap()))
        .collect();

    assert_eq!(got, expected);
}
