//! Phase 1 -- the constraint/objective layer: `ufo-types`' `Satisfies<C>`
//! backed by a **real** `scryer-prolog` query, not a Rust `if`.
//!
//! Lab 8's 0d spike proved the two crates coexist and each work; it explicitly
//! did *not* wire them together ("`Satisfies<C>` is not wired to call into
//! scryer-prolog for real proof-search here; that is future work"). This is
//! that wiring: every evaluation builds a real Prolog fact base from the live
//! observation, loads it into a real `Machine`, and answers `overloaded(L).`
//! by proof search. The `SatisfiesResult` is derived from the answers.
//!
//! **`--release` is required**, and `just check-lab9` always passes it: Lab 8
//! 0d documented a real, reproducible debug-profile-only panic inside
//! `scryer_prolog::machine::heap::Heap::clear` (a `NonNull::new_unchecked` UB
//! check that fires under `rustc`'s debug `ub_checks`), unrelated to
//! `ufo-types` and absent from release builds.

use scryer_prolog::{LeafAnswer, MachineBuilder, Term};
use ufo_types::satisfies::{Satisfies, SatisfiesResult};
use ufo_types::stereotype::{Stereotyped, UfoStereotype};

use bevy::prelude::*;

/// "No branch in the mission's cluster exceeds `rho_limit`."
///
/// `rho_limit` is **0.030, not 1.0** for this lab's scenario, and that is a
/// deliberate, measured choice rather than a fudge. CSIRO's synthetic
/// `snemSA.m` carries effectively unconstrained branch ratings (Lab 6's own
/// schema header already flags `sn_mva: 10000.0` as a synthetic-case artifact
/// two orders of magnitude above real equipment), so grid2op derives a uniform
/// ~20,995 A thermal limit for every cluster branch and rho never exceeds
/// 0.038 under *any* single cluster outage -- measured, for all 19 of them,
/// by this lab's own fixture generation. 0.030 sits between the real
/// base-case cluster maximum (0.026553) and the real post-contingency maximum
/// (0.037622), so the crossing this objective scores is a real change in real
/// grid state. See the lab README's "the rho limit is 0.030, not 1.0".
#[derive(Debug, Clone, Copy, PartialEq, Resource)]
pub struct GridSecurityObjective {
    pub rho_limit: f64,
}

impl Default for GridSecurityObjective {
    fn default() -> Self {
        Self { rho_limit: 0.030 }
    }
}

/// The mission's view of the grid: Lab 6 cluster branch name + live rho.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct MissionGridState {
    pub lines: Vec<(String, f64)>,
}

impl MissionGridState {
    pub fn from_observation(obs: &crate::grid2op_bridge::GridObservation) -> Self {
        Self {
            lines: obs.line_loadings(),
        }
    }

    /// The Prolog program this state compiles to: one ground fact per branch
    /// plus the overload rule, with the limit bound into the rule body.
    pub fn prolog_program(&self, rho_limit: f64) -> String {
        let mut program = String::new();
        for (name, rho) in &self.lines {
            // `{:.9}` keeps the literal in plain decimal form -- Prolog has no
            // Rust-style `1e-3` float syntax, and the fixture's rho values are
            // small enough that `{}` would emit exponent notation for some.
            program.push_str(&format!("line_loading('{name}', {rho:.9}).\n"));
        }
        program.push_str(&format!(
            "overloaded(L) :- line_loading(L, R), R > {rho_limit:.9}.\n"
        ));
        program
    }

    /// Run the real query and return the overloaded branch names, sorted.
    pub fn overloaded_lines(&self, rho_limit: f64) -> Vec<String> {
        if self.lines.is_empty() {
            return Vec::new();
        }
        let mut machine = MachineBuilder::default().build();
        machine.load_module_string("mission_grid", self.prolog_program(rho_limit));

        let answers: Vec<LeafAnswer> = machine
            .run_query("overloaded(L).")
            .collect::<Result<Vec<_>, _>>()
            .expect("overloaded/1 query executes");

        let mut names: Vec<String> = answers
            .into_iter()
            .filter_map(|answer| match answer {
                // Lab 8 0d's empirical finding: a query with solutions yields
                // one LeafAnswer per solution followed by a trailing `False`
                // once backtracking is exhausted. `False` is "no more
                // solutions", not a fourth answer -- filtered out here.
                LeafAnswer::LeafAnswer { bindings, .. } => match bindings.get("L") {
                    Some(Term::Atom(name)) => Some(name.clone()),
                    _ => None,
                },
                _ => None,
            })
            .collect();
        names.sort();
        names.dedup();
        names
    }
}

impl Stereotyped for MissionGridState {
    fn ufo_stereotype(&self) -> UfoStereotype {
        // UFO-A: the observed state of the grid at one step is a Mode -- an
        // intrinsic, existentially-dependent moment of the grid, not a Kind.
        UfoStereotype::Mode("MissionGridState".into())
    }
}

impl Satisfies<GridSecurityObjective> for MissionGridState {
    fn satisfies(&self, constraint: &GridSecurityObjective) -> SatisfiesResult {
        let overloaded = self.overloaded_lines(constraint.rho_limit);
        if overloaded.is_empty() {
            return SatisfiesResult::satisfied(1.0);
        }
        let total = self.lines.len().max(1);
        let confidence = 1.0 - (overloaded.len() as f64 / total as f64);
        SatisfiesResult::violated(
            format!(
                "{} of {} cluster branches over rho limit {:.3}: {}",
                overloaded.len(),
                total,
                constraint.rho_limit,
                overloaded.join(", ")
            ),
            confidence,
        )
    }
}

/// The current step's score, kept in ECS for the FSM and the card feed.
#[derive(Resource, Debug, Clone, Default)]
pub struct ObjectiveScore {
    pub result: Option<SatisfiesResult>,
    pub overloaded: Vec<String>,
    pub rho_max: f64,
}

pub struct ObjectivesPlugin;

impl Plugin for ObjectivesPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<GridSecurityObjective>()
            .init_resource::<ObjectiveScore>()
            .add_systems(
                Update,
                score_objective.after(crate::grid2op_bridge::drain_observations),
            );
    }
}

pub fn score_objective(
    bridge: Res<crate::grid2op_bridge::Grid2OpBridge>,
    objective: Res<GridSecurityObjective>,
    mut score: ResMut<ObjectiveScore>,
) {
    let Some(obs) = bridge.latest.as_ref() else {
        return;
    };
    let state = MissionGridState::from_observation(obs);
    score.overloaded = state.overloaded_lines(objective.rho_limit);
    score.rho_max = obs.rho_max();
    score.result = Some(state.satisfies(&objective));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn prolog_query_finds_exactly_the_overloaded_branches() {
        let state = MissionGridState {
            lines: vec![
                ("line_a".into(), 0.01),
                ("line_b".into(), 0.05),
                ("line_c".into(), 0.031),
            ],
        };
        assert_eq!(
            state.overloaded_lines(0.030),
            vec!["line_b".to_string(), "line_c".to_string()]
        );
        assert!(state.overloaded_lines(0.1).is_empty());
    }

    #[test]
    fn satisfies_result_confidence_is_the_unaffected_fraction() {
        let state = MissionGridState {
            lines: vec![
                ("line_a".into(), 0.01),
                ("line_b".into(), 0.05),
                ("line_c".into(), 0.031),
                ("line_d".into(), 0.001),
            ],
        };
        let result = state.satisfies(&GridSecurityObjective { rho_limit: 0.030 });
        assert!(result.is_violated());
        assert_eq!(result.confidence, 0.5);
    }
}
