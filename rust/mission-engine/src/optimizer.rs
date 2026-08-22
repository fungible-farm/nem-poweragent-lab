//! Phase 3 -- the strategic-objective optimizer.
//!
//! One fixed, named contingency inside Lab 6's cluster (the real N-1 outage of
//! the 275 kV circuit `bus_4125`-`bus_4128`), three real candidate remedial
//! actions, each scored by the **same** `Satisfies<GridSecurityObjective>`
//! implementation Phase 1 uses -- i.e. by a real scryer-prolog query, not a
//! second, parallel scoring path.
//!
//! Every `post_action_rho` number in `fixtures/contingency_candidates.json`
//! comes from its own real grid2op what-if run (`generate_fixture.py` resets
//! the environment, applies the real trip, then applies the candidate action
//! and reads the resulting observation). None of them are authored by hand.
//!
//! The ranking is then wrapped in `ufo-types`' real DARE types --
//! `Decision`/`Alternative`/`Risk`/`ExecutiveDecision`/`DaredProposal` --
//! and driven through `OodaStateMachine` from `Decide` to `Act`. The field and
//! method names below were read out of the crate's own `src/dare.rs` at the
//! pinned rev, not guessed.

use serde::Deserialize;
use ufo_types::dare::{
    Alternative, DaredDocument, Decision, ExecutiveDecision, OodaEvent, OodaPhase,
    OodaStateMachine, DaredProposal, Risk, RiskSeverity,
};
use ufo_types::satisfies::{Satisfies, SatisfiesResult};

use crate::objectives::{GridSecurityObjective, MissionGridState};

#[derive(Debug, Clone, Deserialize, PartialEq)]
pub struct Contingency {
    pub name: String,
    pub tripped_line: String,
    pub description: String,
}

/// One candidate remedial action and the real post-action cluster loading it
/// produced in its own grid2op run.
#[derive(Debug, Clone, Deserialize, PartialEq)]
pub struct CandidateAction {
    pub name: String,
    pub description: String,
    pub post_action_rho: Vec<(String, f64)>,
}

impl CandidateAction {
    pub fn grid_state(&self) -> MissionGridState {
        MissionGridState {
            lines: self.post_action_rho.clone(),
        }
    }

    pub fn rho_max(&self) -> f64 {
        self.post_action_rho
            .iter()
            .map(|(_, r)| *r)
            .fold(f64::NEG_INFINITY, f64::max)
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq)]
pub struct ContingencyScenario {
    pub contingency: Contingency,
    pub rho_limit: f64,
    pub post_contingency_rho: Vec<(String, f64)>,
    pub candidates: Vec<CandidateAction>,
}

impl ContingencyScenario {
    pub fn load() -> Result<Self, String> {
        let path = crate::paths::contingency_candidates_json();
        let raw =
            std::fs::read_to_string(&path).map_err(|e| format!("{}: {e}", path.display()))?;
        serde_json::from_str(&raw).map_err(|e| format!("{}: {e}", path.display()))
    }

    pub fn objective(&self) -> GridSecurityObjective {
        GridSecurityObjective {
            rho_limit: self.rho_limit,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct RankedCandidate {
    pub candidate: CandidateAction,
    pub result: SatisfiesResult,
}

/// Rank candidates by `is_satisfied()`, then `confidence` descending.
///
/// Two further, fully deterministic tiebreaks are applied after those, because
/// this scenario really does produce a tie on both primary keys: two of the
/// three candidates leave exactly 2 of 19 branches over the limit, so both
/// score `violated(confidence = 1 - 2/19)`. Lower post-action `rho_max` wins
/// next (a real, measured difference), then name, so the ordering is stable
/// and testable rather than dependent on input order.
pub fn rank(scenario: &ContingencyScenario) -> Vec<RankedCandidate> {
    let objective = scenario.objective();
    let mut ranked: Vec<RankedCandidate> = scenario
        .candidates
        .iter()
        .map(|candidate| RankedCandidate {
            result: candidate.grid_state().satisfies(&objective),
            candidate: candidate.clone(),
        })
        .collect();

    ranked.sort_by(|a, b| {
        b.result
            .is_satisfied()
            .cmp(&a.result.is_satisfied())
            .then(
                b.result
                    .confidence
                    .partial_cmp(&a.result.confidence)
                    .unwrap_or(std::cmp::Ordering::Equal),
            )
            .then(
                a.candidate
                    .rho_max()
                    .partial_cmp(&b.candidate.rho_max())
                    .unwrap_or(std::cmp::Ordering::Equal),
            )
            .then(a.candidate.name.cmp(&b.candidate.name))
    });
    ranked
}

/// Wrap a completed ranking in `ufo-types`' DARE proposal types.
pub fn to_dare_proposal(
    scenario: &ContingencyScenario,
    ranked: &[RankedCandidate],
) -> DaredProposal {
    let top = ranked.first().expect("at least one candidate");

    let decision = Decision {
        what: format!(
            "Apply remedial action `{}` to clear {}",
            top.candidate.name, scenario.contingency.name
        ),
        who: "cim-gridy mission operator".into(),
        when: "this mission step".into(),
        scope: vec![
            "Lab 6's 15-bus snemSA.m cluster".into(),
            format!("branch security at rho <= {:.3}", scenario.rho_limit),
        ],
        explicitly_out_of_scope: vec![
            "the other ~484 buses of the snemSA.m network".into(),
            "redispatch and load shedding (topology actions only)".into(),
        ],
    };

    let alternatives = ranked[1..]
        .iter()
        .map(|r| Alternative {
            name: r.candidate.name.clone(),
            viable: r.candidate.description.clone(),
            rejected_because: format!(
                "{} (post-action rho_max {:.6}, confidence {:.6})",
                r.result.disposition,
                r.candidate.rho_max(),
                r.result.confidence
            ),
        })
        .collect::<Vec<_>>();

    let executive_decision = ExecutiveDecision {
        summary: "BranchSecurityRemediation ⊆ GridOperatorMission ⊆ StrategicObjective".into(),
        artifacts: vec![
            "labs/09-cim-gridy-phase1-3-vertical-slice/fixtures/contingency_candidates.json".into(),
        ],
        removed: Vec::new(),
        acceptance_criteria: vec![format!(
            "no cluster branch above rho {:.3} after the action",
            scenario.rho_limit
        )],
    };

    let mut proposal = DaredProposal::new(
        format!("DARED-{}", scenario.contingency.name),
        scenario.contingency.description.clone(),
        decision,
        executive_decision,
    )
    .with_risk(Risk {
        name: "synthetic-case branch ratings".into(),
        severity: RiskSeverity::Medium,
        description: "snemSA.m's ratings are effectively unconstrained, so the rho limit \
                      is a mission threshold (0.030), not a real thermal rating."
            .into(),
        mitigation: "Limit is stated explicitly in the lab README and sourced to a measured \
                     sweep of all 19 cluster N-1 outages."
            .into(),
    });
    for alternative in alternatives {
        proposal = proposal.with_alternative(alternative);
    }
    proposal
}

/// Run the ranked proposal through the real OODA state machine, `Decide` ->
/// `Act`, and report whether it was accepted.
pub fn dispatch_to_act(proposal: DaredProposal) -> (OodaPhase, bool) {
    let ready = proposal.is_ready_to_act();
    let mut machine = OodaStateMachine::new(proposal);
    let transition = machine
        .dispatch(OodaEvent::Execute)
        .expect("Execute is a legal event from Decide");
    (machine.current_phase(), transition.accepted && ready)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scenario_fixture_loads_with_three_real_candidates() {
        let scenario = ContingencyScenario::load().unwrap();
        assert_eq!(scenario.contingency.tripped_line, "line_4125_4128");
        assert_eq!(scenario.candidates.len(), 3);
        for c in &scenario.candidates {
            assert_eq!(c.post_action_rho.len(), 19);
        }
    }
}
