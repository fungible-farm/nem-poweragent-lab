//! Phase 1 -- the mission state machine: TOML table -> Rhai guards -> Mermaid.
//!
//! PRD-0009 names `ledgrrr`'s "TOML -> Rhai FSM -> Mermaid -> Rust enum"
//! pipeline as the pattern for the mission/calendar-step loop. This is that
//! pattern implemented **directly against the `rhai` crate**. `ledgrrr` itself
//! is a large, unrelated local FinOps-ledger product (`~/.dotfiles/vendor/
//! ledgrrr`); it is not vendored, not depended on, and not required to build
//! or run this lab. Only the shape is borrowed.
//!
//! The transition table lives in
//! `labs/09-cim-gridy-phase1-3-vertical-slice/mission_fsm.toml`; every guard
//! there is a real Rhai boolean expression evaluated against a `rhai::Scope`
//! built from the live observation each tick.

use bevy::prelude::*;
use rhai::{Engine, Scope};
use serde::Deserialize;

/// The mission's phase. Cross-checked against `mission_fsm.toml`'s own
/// `states` list by a unit test so the code and the data cannot drift.
#[derive(Resource, Debug, Clone, Copy, PartialEq, Eq, Hash, Default)]
pub enum MissionPhase {
    #[default]
    Briefing,
    Monitoring,
    ContingencyDetected,
    MitigationSelected,
    Resolved,
}

impl MissionPhase {
    pub const ALL: [MissionPhase; 5] = [
        MissionPhase::Briefing,
        MissionPhase::Monitoring,
        MissionPhase::ContingencyDetected,
        MissionPhase::MitigationSelected,
        MissionPhase::Resolved,
    ];

    pub fn as_str(&self) -> &'static str {
        match self {
            MissionPhase::Briefing => "Briefing",
            MissionPhase::Monitoring => "Monitoring",
            MissionPhase::ContingencyDetected => "ContingencyDetected",
            MissionPhase::MitigationSelected => "MitigationSelected",
            MissionPhase::Resolved => "Resolved",
        }
    }

    pub fn from_str_exact(s: &str) -> Option<Self> {
        MissionPhase::ALL.into_iter().find(|p| p.as_str() == s)
    }
}

impl std::fmt::Display for MissionPhase {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct Transition {
    pub from: String,
    pub to: String,
    /// A Rhai boolean expression.
    pub guard: String,
    pub label: String,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct MissionFsmTable {
    pub states: Vec<String>,
    pub initial: String,
    pub transitions: Vec<Transition>,
}

/// The loaded table plus its Rhai engine.
#[derive(Resource)]
pub struct MissionFsm {
    pub table: MissionFsmTable,
    engine: Engine,
}

/// The inputs a guard expression can see.
#[derive(Debug, Clone, Copy, Default)]
pub struct GuardInputs {
    pub step: i64,
    pub rho_max: f64,
    pub rho_limit: f64,
    pub overloaded_count: i64,
    pub total_lines: i64,
}

impl MissionFsm {
    pub fn load(path: &std::path::Path) -> Result<Self, String> {
        let raw = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
        let table: MissionFsmTable =
            toml::from_str(&raw).map_err(|e| format!("{}: {e}", path.display()))?;

        for t in &table.transitions {
            for state in [&t.from, &t.to] {
                if !table.states.contains(state) {
                    return Err(format!(
                        "{}: transition references unknown state {state:?}",
                        path.display()
                    ));
                }
            }
        }
        if !table.states.contains(&table.initial) {
            return Err(format!(
                "{}: initial state {:?} is not in `states`",
                path.display(),
                table.initial
            ));
        }

        Ok(Self {
            table,
            engine: Engine::new(),
        })
    }

    pub fn initial_phase(&self) -> MissionPhase {
        MissionPhase::from_str_exact(&self.table.initial).expect("validated in load()")
    }

    /// Evaluate every transition out of `current`, in table order, and take the
    /// first whose Rhai guard evaluates true.
    pub fn next_phase(&self, current: MissionPhase, inputs: GuardInputs) -> MissionPhase {
        for t in self
            .table
            .transitions
            .iter()
            .filter(|t| t.from == current.as_str())
        {
            let mut scope = Scope::new();
            scope.push("step", inputs.step);
            scope.push("rho_max", inputs.rho_max);
            scope.push("rho_limit", inputs.rho_limit);
            scope.push("overloaded_count", inputs.overloaded_count);
            scope.push("total_lines", inputs.total_lines);
            match self
                .engine
                .eval_with_scope::<bool>(&mut scope, &t.guard)
            {
                Ok(true) => {
                    return MissionPhase::from_str_exact(&t.to).expect("validated in load()")
                }
                Ok(false) => {}
                Err(e) => panic!("guard {:?} ({} -> {}) failed: {e}", t.guard, t.from, t.to),
            }
        }
        current
    }

    /// Emit a Mermaid `stateDiagram-v2` block straight from the TOML table.
    ///
    /// Hand-written rather than pulled from a crate for the same reason Lab 7's
    /// COMTRADE writer is hand-written: the output is small, fixed-shape, and
    /// exactly round-trippable against a committed fixture.
    pub fn render_mermaid(&self) -> String {
        let mut out = String::from("stateDiagram-v2\n");
        out.push_str(&format!("    [*] --> {}\n", self.table.initial));
        for state in &self.table.states {
            out.push_str(&format!("    {state}\n"));
        }
        for t in &self.table.transitions {
            out.push_str(&format!(
                "    {} --> {}: {} [{}]\n",
                t.from, t.to, t.label, t.guard
            ));
        }
        out.push_str("    Resolved --> [*]\n");
        out
    }
}

/// Every phase the mission has been in, in order -- the audit trail the card
/// feed and the tests both read.
#[derive(Resource, Debug, Clone, Default)]
pub struct MissionPhaseHistory(pub Vec<MissionPhase>);

pub struct MissionFsmPlugin;

impl Plugin for MissionFsmPlugin {
    fn build(&self, app: &mut App) {
        let fsm = MissionFsm::load(&crate::paths::mission_fsm_toml())
            .unwrap_or_else(|e| panic!("loading mission_fsm.toml: {e}"));
        let initial = fsm.initial_phase();
        app.insert_resource(fsm)
            .insert_resource(initial)
            .init_resource::<MissionPhaseHistory>()
            .add_systems(Update, advance_phase.after(crate::objectives::score_objective));
    }
}

pub fn advance_phase(
    bridge: Res<crate::grid2op_bridge::Grid2OpBridge>,
    fsm: Res<MissionFsm>,
    objective: Res<crate::objectives::GridSecurityObjective>,
    score: Res<crate::objectives::ObjectiveScore>,
    mut phase: ResMut<MissionPhase>,
    mut history: ResMut<MissionPhaseHistory>,
) {
    let Some(obs) = bridge.latest.as_ref() else {
        return;
    };
    // Only advance once per real observation.
    if history.0.len() >= bridge.history.len() {
        return;
    }
    let inputs = GuardInputs {
        step: obs.step as i64,
        rho_max: score.rho_max,
        rho_limit: objective.rho_limit,
        overloaded_count: score.overloaded.len() as i64,
        total_lines: obs.lines.len() as i64,
    };
    *phase = fsm.next_phase(*phase, inputs);
    history.0.push(*phase);
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fsm() -> MissionFsm {
        MissionFsm::load(&crate::paths::mission_fsm_toml()).unwrap()
    }

    #[test]
    fn toml_states_match_the_rust_enum() {
        let table = fsm().table;
        let from_rust: Vec<&str> = MissionPhase::ALL.iter().map(|p| p.as_str()).collect();
        assert_eq!(
            table.states, from_rust,
            "mission_fsm.toml's `states` and MissionPhase's variants have drifted apart"
        );
    }

    #[test]
    fn rendered_mermaid_matches_the_committed_fixture() {
        let expected = std::fs::read_to_string(crate::paths::mission_fsm_mermaid()).unwrap();
        assert_eq!(fsm().render_mermaid(), expected);
    }

    #[test]
    fn guards_evaluate_as_real_rhai_expressions() {
        let f = fsm();
        let secure = GuardInputs {
            step: 1,
            rho_max: 0.0265,
            rho_limit: 0.030,
            overloaded_count: 0,
            total_lines: 19,
        };
        let overloaded = GuardInputs {
            rho_max: 0.0376,
            overloaded_count: 2,
            ..secure
        };
        assert_eq!(
            f.next_phase(MissionPhase::Briefing, secure),
            MissionPhase::Monitoring
        );
        assert_eq!(
            f.next_phase(MissionPhase::Monitoring, secure),
            MissionPhase::Monitoring
        );
        assert_eq!(
            f.next_phase(MissionPhase::Monitoring, overloaded),
            MissionPhase::ContingencyDetected
        );
        assert_eq!(
            f.next_phase(MissionPhase::ContingencyDetected, overloaded),
            MissionPhase::MitigationSelected
        );
        assert_eq!(
            f.next_phase(MissionPhase::MitigationSelected, secure),
            MissionPhase::Resolved
        );
    }
}
