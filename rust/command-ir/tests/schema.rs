//! The IR's emitted schema must be byte-identical to the one the evaluation serves (FM-23),
//! and its lowering must be what the trained procedure sends.

use command_ir::{parse, study_trial_schema, to_python_json, Command, IrError, Modification, Observation, Simulate, Solve};

/// Written by `uv run python -c` from `studies.tool_schema()`; `powercoder/inference/test_command_ir.py`
/// checks the Python side still serves exactly this.
const SERVED: &str = include_str!("served_run_study_trial.json");

#[test]
fn emitted_schema_is_byte_identical_to_the_served_one() {
    assert_eq!(to_python_json(&study_trial_schema()), SERVED.trim_end());
}

#[test]
fn solve_lowers_to_the_report_call_the_students_were_trained_on() {
    let solve = Command::Solve(Solve { network: "snem-sa-2000".into(), contingency_line: Some(94),
                                       observation: Observation::BusVoltage, observation_id: 985, max_iter: 50 });
    assert_eq!(to_python_json(&solve.lower().unwrap()),
               r#"{"network_id": "snem-sa-2000", "operation": "none", "scale": 1.0, "element_id": 0, "observation": "bus_voltage", "observation_id": 985, "contingency_line": 94, "max_iter": 50}"#);
    let intact = Command::Solve(Solve { contingency_line: None, ..match solve { Command::Solve(s) => s, _ => unreachable!() } });
    assert!(!to_python_json(&intact.lower().unwrap()).contains("contingency_line"));
}

#[test]
fn simulate_observes_what_its_modification_moves_and_refuses_bad_scales() {
    let ok = Command::Simulate(Simulate { network: "snem-1803".into(), modification: Modification::LineRating, scale: 1.05,
                                          element_id: 7, observation_id: 7, contingency_line: None, max_iter: 50 });
    assert!(to_python_json(&ok.lower().unwrap()).contains(r#""observation": "line_loading""#));
    let bad = Command::Simulate(Simulate { scale: 1.2, ..match ok { Command::Simulate(s) => s, _ => unreachable!() } });
    assert_eq!(bad.lower(), Err(IrError::ScaleOutOfRange(1.2)));
}

#[test]
fn the_dsl_compiles_to_the_ir_and_rejects_what_the_tool_would() {
    assert_eq!(parse("SOLVE snem-sa-2000 OUTAGE 94 OBSERVE bus_voltage 985").unwrap(),
               Command::Solve(Solve { network: "snem-sa-2000".into(), contingency_line: Some(94),
                                      observation: Observation::BusVoltage, observation_id: 985, max_iter: 50 }));
    assert!(matches!(parse("SIMULATE snem-sa-2000 load_scale 1.0375 OBSERVE 985").unwrap(), Command::Simulate(_)));
    assert!(matches!(parse("SOLVE elsewhere OBSERVE bus_voltage 1"), Err(IrError::UnknownNetwork(_))));
    assert!(matches!(parse("SIMULATE snem-sa-2000 load_scale 0.5 OBSERVE 985"), Err(IrError::ScaleOutOfRange(_))));
    assert!(matches!(parse("SOLVE snem-sa-2000 OBSERVE bus_voltage None"), Err(IrError::Syntax(_))));
    assert!(matches!(parse("DROP TABLE"), Err(IrError::Syntax(_))));
}
