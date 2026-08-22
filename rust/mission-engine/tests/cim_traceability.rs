//! Phase 2's paired right-side check: do the CIM class URIs the SysML v2
//! parser recovers from Lab 6's `.sysml` model match, exactly and for every
//! element, the `cim_class_uri` fields in Lab 6's own LinkML instance data?
//!
//! Two independent representations of the same thing (PRD-0007's traceability
//! claim) reconciled against each other -- the `.sysml` is generated from the
//! YAML, so any drift in either the generator or this parser shows up here.

use std::collections::BTreeMap;

use mission_engine::cim_trace::{cim_class_uris, pandapower_bus_id_from_source};
use mission_engine::sysml_types::{SysmlModel, collect_parts};
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct YamlElement {
    name: String,
    source: String,
    cim_class_uri: String,
}

#[derive(Debug, Deserialize)]
struct GridInstances {
    buses: Vec<YamlElement>,
    generators: Vec<YamlElement>,
    lines: Vec<YamlElement>,
}

fn load_yaml() -> GridInstances {
    let raw = std::fs::read_to_string(mission_engine::paths::lab6_grid_instances()).unwrap();
    serde_norway::from_str(&raw).expect("Lab 6's grid_instances.yaml parses")
}

fn load_model() -> SysmlModel {
    let path = mission_engine::paths::lab6_sysml();
    let src = std::fs::read_to_string(&path).unwrap();
    SysmlModel {
        root: sysml_v2_parser::parse(&src).expect("Lab 6's .sysml parses strictly"),
        source_path: path,
    }
}

#[test]
fn sysml_cim_class_uris_match_lab6_instance_data_exactly() {
    let yaml = load_yaml();
    let mut expected: BTreeMap<String, String> = BTreeMap::new();
    for group in [&yaml.buses, &yaml.generators, &yaml.lines] {
        for element in group {
            expected.insert(element.name.clone(), element.cim_class_uri.clone());
        }
    }
    assert_eq!(
        expected.len(),
        39,
        "Lab 6's cluster is 15 buses + 5 generators + 19 branches"
    );

    let from_sysml: BTreeMap<String, String> = cim_class_uris(&load_model()).into_iter().collect();
    assert_eq!(
        from_sysml, expected,
        "CIM class URIs recovered from the .sysml differ from grid_instances.yaml"
    );
}

#[test]
fn every_cluster_bus_resolves_through_the_real_bus_lookup() {
    let yaml = load_yaml();
    let lookup = mission_engine::cim_trace::BusLookup::load().unwrap();
    assert_eq!(lookup.0.len(), 503, "snemSA.m has 503 buses");

    for bus in &yaml.buses {
        let pp_id = pandapower_bus_id_from_source(&bus.source)
            .unwrap_or_else(|| panic!("{}: no pandapower bus index in {:?}", bus.name, bus.source));
        assert!(
            lookup.0.contains_key(&pp_id),
            "{} (pandapower bus {pp_id}) is missing from bus_lookup.json",
            bus.name
        );
    }

    // The anchor bus of Lab 6's own cluster walk, checked against the real
    // create_continuous_bus_index output.
    assert_eq!(lookup.0.get(&1683), Some(&52));
}

#[test]
fn sysml_parts_carry_lab6s_own_provenance_strings() {
    let yaml = load_yaml();
    let by_name: BTreeMap<&str, &str> = yaml
        .buses
        .iter()
        .chain(&yaml.generators)
        .chain(&yaml.lines)
        .map(|e| (e.name.as_str(), e.source.as_str()))
        .collect();

    for part in collect_parts(&load_model().root) {
        let expected = by_name
            .get(part.name.as_str())
            .unwrap_or_else(|| panic!("{} is in the .sysml but not in the YAML", part.name));
        assert_eq!(part.source.as_deref(), Some(*expected), "{}", part.name);
    }
}
