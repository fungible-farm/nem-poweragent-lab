//! Phase 2 -- Lab 6 CIM class-URI traceability, joined to the live grid2op
//! index space.
//!
//! PRD-0007 put a `cim_class_uri` on every element of Lab 6's cluster schema;
//! Lab 6's generator carries it through into the `.sysml` as a
//! `cimClassUri` attribute. This module walks the parsed SysML AST (the real
//! one, from `sysml-v2-parser` -- not the YAML), attaches a [`CimClassUri`]
//! `Component` to the matching Bevy entity, and -- for buses -- resolves the
//! original, non-sequential pandapower bus id Lab 6 records in its `source`
//! string through `fixtures/bus_lookup.json` (written by `build_dataset.py`
//! from `create_continuous_bus_index`'s real return value) into the dense
//! substation id grid2op actually uses.
//!
//! That last hop is the whole point: Lab 6's model says `bus_4052` is
//! "pandapower bus index 1683", but grid2op's `PandaPowerBackend` requires a
//! dense 0..N-1 index and so knows it as substation 1683-reindexed. Without
//! the persisted lookup, the static model and the live episode cannot be
//! joined at all.

use std::collections::HashMap;

use bevy::prelude::*;

use crate::grid_entities::{BusElement, GridElementName, SourceProvenance};
use crate::sysml_types::{collect_parts, SysmlModel};

/// The CIM class this element realizes, e.g.
/// `http://iec.ch/TC57/2013/CIM-schema-cim16#TopologicalNode`.
#[derive(Component, Debug, Clone, PartialEq, Eq)]
pub struct CimClassUri(pub String);

/// The dense substation id grid2op uses for this bus.
#[derive(Component, Debug, Clone, Copy, PartialEq, Eq)]
pub struct Grid2OpSubId(pub u32);

/// The original (pre-`create_continuous_bus_index`) pandapower bus id, as
/// quoted in Lab 6's `source` attribute.
#[derive(Component, Debug, Clone, Copy, PartialEq, Eq)]
pub struct PandapowerBusId(pub u32);

/// `original pandapower bus id -> dense grid2op substation id`.
#[derive(Resource, Debug, Clone, Default)]
pub struct BusLookup(pub HashMap<u32, u32>);

impl BusLookup {
    pub fn load() -> std::io::Result<Self> {
        let path = crate::paths::bus_lookup_json();
        let raw = std::fs::read_to_string(&path)?;
        let parsed: HashMap<String, u32> = serde_json::from_str(&raw).map_err(|e| {
            std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("{}: {e}", path.display()),
            )
        })?;
        Ok(BusLookup(
            parsed
                .into_iter()
                .filter_map(|(k, v)| k.parse::<u32>().ok().map(|k| (k, v)))
                .collect(),
        ))
    }
}

/// Pull the integer out of Lab 6's provenance string, e.g.
/// `"data/snemSA.m (pandapower bus index 1683)"` -> `1683`.
pub fn pandapower_bus_id_from_source(source: &str) -> Option<u32> {
    let tail = source.split("pandapower bus index").nth(1)?;
    let digits: String = tail
        .chars()
        .skip_while(|c| !c.is_ascii_digit())
        .take_while(char::is_ascii_digit)
        .collect();
    digits.parse().ok()
}

/// `(part name, cimClassUri)` for every element of the model that declares one,
/// in source order. This is what the Phase 2 test cross-checks against Lab 6's
/// own `grid_instances.yaml`.
pub fn cim_class_uris(model: &SysmlModel) -> Vec<(String, String)> {
    collect_parts(&model.root)
        .into_iter()
        .filter_map(|p| p.cim_class_uri.map(|uri| (p.name, uri)))
        .collect()
}

pub struct CimTracePlugin;

impl Plugin for CimTracePlugin {
    fn build(&self, app: &mut App) {
        let lookup = BusLookup::load()
            .unwrap_or_else(|e| panic!("reading {}: {e}", crate::paths::bus_lookup_json().display()));
        app.insert_resource(lookup)
            .add_systems(Startup, attach_cim_traceability.after(crate::grid_entities::spawn_cluster_entities));
    }
}

pub fn attach_cim_traceability(
    mut commands: Commands,
    model: Res<SysmlModel>,
    lookup: Res<BusLookup>,
    query: Query<(Entity, &GridElementName, &SourceProvenance, Option<&BusElement>)>,
) {
    let uris: HashMap<String, String> = cim_class_uris(&model).into_iter().collect();
    for (entity, name, source, is_bus) in &query {
        if let Some(uri) = uris.get(&name.0) {
            commands.entity(entity).insert(CimClassUri(uri.clone()));
        }
        if is_bus.is_none() {
            continue;
        }
        if let Some(pp_id) = pandapower_bus_id_from_source(&source.0) {
            commands.entity(entity).insert(PandapowerBusId(pp_id));
            if let Some(sub) = lookup.0.get(&pp_id) {
                commands.entity(entity).insert(Grid2OpSubId(*sub));
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extracts_the_pandapower_bus_id_lab6_records() {
        assert_eq!(
            pandapower_bus_id_from_source("data/snemSA.m (pandapower bus index 1683)"),
            Some(1683)
        );
        assert_eq!(
            pandapower_bus_id_from_source("data/snemSA.m (pandapower line table, 1733-1740)"),
            None
        );
    }
}
