mod common;
use common::fixture_path;
use systhread_core::instances::{load_digital_thread, load_grid, load_pipeline};

#[test]
fn loads_digital_thread_instances() {
    let inst = load_digital_thread(&fixture_path("schema/digital_thread_instances.yaml"));
    assert_eq!(inst.agents.len(), 2);
    assert_eq!(inst.mcp_servers.len(), 2);
    assert_eq!(inst.data_sources.len(), 3);

    let lab1 = &inst.agents[0];
    assert_eq!(lab1.name, "lab1_bisection_search");
    assert_eq!(lab1.source, "labs/01-simple-loadflow-fit/run.py");
    assert_eq!(lab1.uses.as_deref(), Some("csiro_synthetic_nem_2000bus"));
    assert_eq!(lab1.refresh_cadence, "on every lab run (--step fit)");
    assert_eq!(lab1.owner, "Lab 1 -- load-flow parameter fit");
}

#[test]
fn loads_grid_instances() {
    let inst = load_grid(&fixture_path("schema/grid_instances.yaml"));
    assert_eq!(inst.buses.len(), 15);
    assert_eq!(inst.generators.len(), 5);
    assert!(!inst.lines.is_empty());

    let bus_4052 = inst.buses.iter().find(|b| b.name == "bus_4052").unwrap();
    assert_eq!(bus_4052.voltage_kv, 15.75);
    assert_eq!(
        bus_4052.cim_class_uri,
        "http://iec.ch/TC57/2013/CIM-schema-cim16#TopologicalNode"
    );

    let gen_4052 = inst.generators.iter().find(|g| g.name == "gen_4052").unwrap();
    assert_eq!(gen_4052.bus, "bus_4052");
    assert_eq!(gen_4052.rated_mw, 127.3);
    assert_eq!(
        gen_4052.cim_class_uri,
        "http://iec.ch/TC57/2013/CIM-schema-cim16#SynchronousMachine"
    );
}

#[test]
fn loads_pipeline_instances() {
    let inst = load_pipeline(&fixture_path("schema/pipeline_phases_instances.yaml"));
    assert!(!inst.phases.is_empty());
    let phase0 = &inst.phases[0];
    assert_eq!(phase0.name, "phase0_source_location");
    assert_eq!(phase0.next.as_deref(), Some("phase1_grid_forming"));
}
