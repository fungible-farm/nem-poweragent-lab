//! cim-gridy mission engine -- PRD-0009 Phases 1-3 as one minimal, real,
//! end-to-end vertical slice.
//!
//! The full chain PRD-0009's architecture section names, in one Bevy `App`:
//!
//! ```text
//! Grid2Op episode (real snemSA.m, 503 buses / 698 branches)
//!   -> grid2op_bridge   : subprocess or committed JSONL fixture -> Bevy Resource
//!   -> sysml_types      : sysml-v2-parser on Lab 6's real .sysml (static type layer)
//!   -> grid_entities    : one Entity per Lab 6 cluster Bus/Generator/Line
//!   -> cim_trace        : CIM class URIs + live grid2op ids on those Entities  (Phase 2)
//!   -> objectives       : ufo-types Satisfies<C> backed by a real scryer-prolog query
//!   -> mission_fsm      : TOML -> Rhai guards -> MissionPhase -> Mermaid
//!   -> optimizer        : ufo-types DARE ranking of real candidate actions      (Phase 3)
//! ```
//!
//! Everything here is headless-capable: `just check-lab9` runs the whole chain
//! with `MinimalPlugins` against the committed fixture and never spawns the
//! real grid2op subprocess. See `labs/09-cim-gridy-phase1-3-vertical-slice/README.md`.

use bevy::prelude::*;

pub mod cim_trace;
pub mod grid2op_bridge;
pub mod grid_entities;
pub mod mission_fsm;
pub mod objectives;
pub mod optimizer;
pub mod paths;

/// Everything this lab's mission needs, minus the observation source (which is
/// added separately so headless tests can point at the committed fixture and
/// `--grid2op-live` can point at the real subprocess).
pub struct MissionEnginePlugin;

impl Plugin for MissionEnginePlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins(sysml_types::SysmlTypesPlugin)
            .add_plugins(grid_entities::GridEntitiesPlugin)
            .add_plugins(cim_trace::CimTracePlugin)
            .add_plugins(objectives::ObjectivesPlugin)
            .add_plugins(mission_fsm::MissionFsmPlugin);
    }
}

pub mod sysml_types;

/// The interactive `bevy_ui` card feed (Lab 8 0e's verdict: build cards
/// natively in Bevy rather than adopting OperatorFabric). Behind a feature
/// flag because it pulls winit/wgpu/text rendering into the build, which
/// `just check-lab9` deliberately does not need.
#[cfg(feature = "interactive")]
pub mod card_feed;
