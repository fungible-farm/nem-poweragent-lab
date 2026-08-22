//! Phase 1 -- one Bevy `Entity` per Lab 6 cluster element.
//!
//! **Scope, stated plainly:** the grid2op episode behind
//! [`crate::grid2op_bridge`] runs the real, full snemSA.m network (503 buses,
//! 698 branches). Only Lab 6's already-modelled 15-bus cluster
//! (`labs/06-sysml-digital-thread/schema/grid_instances.yaml`, rendered to
//! `.sysml` and parsed by [`crate::sysml_types`]) gets Bevy entities,
//! objectives, or cards. Modelling the whole grid is explicitly out of scope
//! for this lab.

use bevy::prelude::*;

use crate::sysml_types::{collect_parts, SysmlModel};

/// The element's Lab 6 name (`bus_4052`, `line_4125_4128`, ...).
#[derive(Component, Debug, Clone, PartialEq, Eq)]
pub struct GridElementName(pub String);

/// Lab 6's `source` provenance string, carried onto the entity verbatim.
#[derive(Component, Debug, Clone, PartialEq, Eq)]
pub struct SourceProvenance(pub String);

#[derive(Component, Debug, Clone, Copy, PartialEq, Eq)]
pub struct BusElement;

#[derive(Component, Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeneratorElement;

#[derive(Component, Debug, Clone, PartialEq, Eq)]
pub struct LineElement {
    pub from_bus: String,
    pub to_bus: String,
}

/// Live loading, refreshed each tick from the bridge's latest observation.
#[derive(Component, Debug, Clone, Copy, PartialEq)]
pub struct LineLoading {
    pub rho: f64,
    pub grid2op_line_id: Option<usize>,
}

pub struct GridEntitiesPlugin;

impl Plugin for GridEntitiesPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, spawn_cluster_entities)
            // Explicit ordering, not incidental: without it Bevy is free to
            // run this before `drain_observations` in the same tick, which
            // leaves the entities a full step behind the Resource.
            .add_systems(
                Update,
                update_line_loadings.after(crate::grid2op_bridge::drain_observations),
            );
    }
}

/// Spawns the cluster straight out of the parsed SysML model -- Lab 6's model
/// is the source of truth for what exists, not a hand-listed constant here.
pub fn spawn_cluster_entities(mut commands: Commands, model: Res<SysmlModel>) {
    for part in collect_parts(&model.root) {
        let name = GridElementName(part.name.clone());
        let source = SourceProvenance(part.source.clone().unwrap_or_default());
        match part.type_name.as_str() {
            "Bus" => {
                commands.spawn((name, source, BusElement));
            }
            "Generator" => {
                commands.spawn((name, source, GeneratorElement));
            }
            "Line" => {
                commands.spawn((
                    name,
                    source,
                    LineElement {
                        from_bus: part.from_bus.clone().unwrap_or_default(),
                        to_bus: part.to_bus.clone().unwrap_or_default(),
                    },
                    LineLoading {
                        rho: f64::NAN,
                        grid2op_line_id: None,
                    },
                ));
            }
            _ => {}
        }
    }
}

/// Copies the current observation's per-branch rho onto the matching entities.
pub fn update_line_loadings(
    bridge: Res<crate::grid2op_bridge::Grid2OpBridge>,
    mut query: Query<(&GridElementName, &mut LineLoading)>,
) {
    let Some(obs) = bridge.latest.as_ref() else {
        return;
    };
    for (name, mut loading) in &mut query {
        if let Some(line) = obs.lines.iter().find(|l| l.name == name.0) {
            loading.rho = line.rho;
            loading.grid2op_line_id = Some(line.grid2op_line_id);
        }
    }
}
