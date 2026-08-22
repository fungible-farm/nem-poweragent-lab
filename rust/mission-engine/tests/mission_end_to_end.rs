//! Phase 1's paired right-side V-model check: does the whole chain -- Grid2Op
//! observation -> Bevy ECS -> SysML type layer -> scryer-prolog-backed
//! `Satisfies<GridSecurityObjective>` -> Rhai mission FSM -> Mermaid -- run
//! end to end for one minimal mission, and produce the exact numbers the real
//! grid2op episode produced?
//!
//! Mirrors `rust/phase-model/tests/physics.rs::real_log_matches_python`'s
//! discipline: exact reference values, committed fixture, no tolerances that
//! would let a regression through.
//!
//! Headless throughout (`MinimalPlugins`, `ObservationSource::Fixture`). This
//! never spawns the real grid2op subprocess -- see the lab README.

use bevy::prelude::*;

use mission_engine::MissionEnginePlugin;
use mission_engine::cim_trace::{CimClassUri, Grid2OpSubId, PandapowerBusId};
use mission_engine::grid2op_bridge::{Grid2OpBridge, Grid2OpBridgePlugin, ObservationSource};
use mission_engine::grid_entities::{BusElement, GeneratorElement, GridElementName, LineElement, LineLoading};
use mission_engine::mission_fsm::{MissionFsm, MissionPhase, MissionPhaseHistory};
use mission_engine::objectives::ObjectiveScore;

/// The exact per-step result the real 5-step episode produces, transcribed
/// from `fixtures/episode_observations.jsonl` scored at rho_limit 0.030.
struct ExpectedStep {
    step: u32,
    rho_max: f64,
    satisfied: bool,
    confidence: f64,
    overloaded: &'static [&'static str],
    phase: MissionPhase,
}

const EXPECTED: [ExpectedStep; 5] = [
    ExpectedStep {
        step: 0,
        rho_max: 0.026552679,
        satisfied: true,
        confidence: 1.0,
        overloaded: &[],
        phase: MissionPhase::Monitoring,
    },
    ExpectedStep {
        step: 1,
        rho_max: 0.026552679,
        satisfied: true,
        confidence: 1.0,
        overloaded: &[],
        phase: MissionPhase::Monitoring,
    },
    ExpectedStep {
        step: 2,
        rho_max: 0.037622131,
        satisfied: false,
        confidence: 1.0 - 2.0 / 19.0,
        overloaded: &["line_4128_4148", "line_4129_4148"],
        phase: MissionPhase::ContingencyDetected,
    },
    ExpectedStep {
        step: 3,
        rho_max: 0.037622131,
        satisfied: false,
        confidence: 1.0 - 2.0 / 19.0,
        overloaded: &["line_4128_4148", "line_4129_4148"],
        phase: MissionPhase::MitigationSelected,
    },
    ExpectedStep {
        step: 4,
        rho_max: 0.026552679,
        satisfied: true,
        confidence: 1.0,
        overloaded: &[],
        phase: MissionPhase::Resolved,
    },
];

fn headless_app() -> App {
    let mut app = App::new();
    app.add_plugins(MinimalPlugins)
        .add_plugins(Grid2OpBridgePlugin(ObservationSource::fixture()))
        .add_plugins(MissionEnginePlugin);
    app
}

#[test]
fn real_episode_scores_and_drives_the_mission_fsm() {
    let mut app = headless_app();

    for expected in EXPECTED.iter() {
        app.update();

        let world = app.world();
        let bridge = world.resource::<Grid2OpBridge>();
        let obs = bridge
            .latest
            .as_ref()
            .unwrap_or_else(|| panic!("no observation at step {}", expected.step));
        assert_eq!(obs.step, expected.step);
        assert_eq!(obs.lines.len(), 19, "Lab 6's cluster has 19 branches");

        let score = world.resource::<ObjectiveScore>();
        assert_eq!(
            score.rho_max, expected.rho_max,
            "step {} rho_max",
            expected.step
        );
        assert_eq!(
            score.overloaded,
            expected.overloaded,
            "step {} overloaded set (from the real scryer-prolog query)",
            expected.step
        );

        let result = score
            .result
            .as_ref()
            .unwrap_or_else(|| panic!("no SatisfiesResult at step {}", expected.step));
        assert_eq!(
            result.is_satisfied(),
            expected.satisfied,
            "step {} disposition",
            expected.step
        );
        assert_eq!(
            result.confidence, expected.confidence,
            "step {} confidence",
            expected.step
        );
        if !expected.satisfied {
            assert_eq!(
                result.disposition.to_string(),
                format!(
                    "Violated({} of 19 cluster branches over rho limit 0.030: {})",
                    expected.overloaded.len(),
                    expected.overloaded.join(", ")
                ),
                "step {} violation reason",
                expected.step
            );
        }

        assert_eq!(
            *world.resource::<MissionPhase>(),
            expected.phase,
            "step {} mission phase",
            expected.step
        );
    }

    // (b) the FSM reached the expected phase by the final step, via the
    // expected path -- not by luck on the last tick.
    let world = app.world();
    assert_eq!(
        world.resource::<MissionPhaseHistory>().0,
        vec![
            MissionPhase::Monitoring,
            MissionPhase::Monitoring,
            MissionPhase::ContingencyDetected,
            MissionPhase::MitigationSelected,
            MissionPhase::Resolved,
        ]
    );

    // (c) the rendered Mermaid text exactly matches the committed fixture.
    let expected_mermaid =
        std::fs::read_to_string(mission_engine::paths::mission_fsm_mermaid()).unwrap();
    assert_eq!(
        world.resource::<MissionFsm>().render_mermaid(),
        expected_mermaid
    );
}

#[test]
fn cluster_entities_are_spawned_and_carry_live_loading() {
    let mut app = headless_app();
    app.update();

    let world = app.world_mut();
    let buses = world.query_filtered::<&GridElementName, With<BusElement>>().iter(world).count();
    let gens = world
        .query_filtered::<&GridElementName, With<GeneratorElement>>()
        .iter(world)
        .count();
    assert_eq!(buses, 15, "Lab 6's cluster has 15 buses");
    assert_eq!(gens, 5, "Lab 6's cluster has 5 generators");

    let mut lines = world.query::<(&GridElementName, &LineElement, &LineLoading, &CimClassUri)>();
    let mut seen = 0;
    for (name, element, loading, uri) in lines.iter(world) {
        seen += 1;
        assert!(loading.rho.is_finite(), "{} has no live rho", name.0);
        assert!(loading.grid2op_line_id.is_some(), "{} has no grid2op id", name.0);
        assert!(!element.from_bus.is_empty());
        assert!(uri.0.starts_with("http://iec.ch/TC57/2013/CIM-schema-cim16#"));
    }
    assert_eq!(seen, 19, "Lab 6's cluster has 19 branches");

    // Phase 2's join: bus_4052 is "pandapower bus index 1683" in Lab 6's model,
    // and bus_lookup.json (real create_continuous_bus_index output) maps that
    // to the dense substation id grid2op actually uses.
    let mut anchors = world.query::<(&GridElementName, &PandapowerBusId, &Grid2OpSubId)>();
    let anchor = anchors
        .iter(world)
        .find(|(name, _, _)| name.0 == "bus_4052")
        .expect("bus_4052 has both ids");
    assert_eq!(anchor.1.0, 1683);
    assert_eq!(anchor.2.0, 52, "dense substation id from the real bus_lookup");
}
