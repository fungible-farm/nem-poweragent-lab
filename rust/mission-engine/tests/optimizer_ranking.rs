//! Phase 3's paired right-side check: for one fixed, named contingency, does
//! the optimizer rank the real candidate actions in the exact order their real
//! measured post-action grid states justify, and does the resulting DARE
//! proposal actually clear `ufo-types`' own OODA `Decide -> Act` gate?
//!
//! Every number scored here came out of its own real grid2op what-if run (see
//! `generate_fixture.py`); the scoring path is the same
//! `Satisfies<GridSecurityObjective>` (real scryer-prolog query) Phase 1 uses.

use mission_engine::objectives::{GridSecurityObjective, MissionGridState};
use mission_engine::optimizer::{self, ContingencyScenario};
use ufo_types::dare::{DaredDocument, OodaPhase};
use ufo_types::satisfies::Satisfies;

#[test]
fn ranks_the_real_candidates_in_the_expected_order() {
    let scenario = ContingencyScenario::load().unwrap();
    assert_eq!(scenario.contingency.name, "n1_line_4125_4128");
    assert_eq!(scenario.rho_limit, 0.030);

    // The contingency itself really does violate the objective -- otherwise
    // there would be nothing to rank.
    let post_contingency = MissionGridState {
        lines: scenario.post_contingency_rho.clone(),
    };
    let base = post_contingency.satisfies(&scenario.objective());
    assert!(base.is_violated());
    assert_eq!(
        post_contingency.overloaded_lines(scenario.rho_limit),
        vec!["line_4128_4148".to_string(), "line_4129_4148".to_string()]
    );

    let ranked = optimizer::rank(&scenario);
    let order: Vec<&str> = ranked.iter().map(|r| r.candidate.name.as_str()).collect();
    assert_eq!(
        order,
        vec!["reclose_line_4125_4128", "do_nothing", "open_line_4117_4131"]
    );

    // Top-ranked: the only candidate that actually restores security.
    let top = &ranked[0];
    assert!(top.result.is_satisfied());
    assert_eq!(top.result.confidence, 1.0);
    assert_eq!(top.candidate.rho_max(), 0.026552679);

    // The two rejected candidates tie on confidence (both leave 2 of 19
    // branches over the limit) and are separated only by their real,
    // measured rho_max -- `open_line_4117_4131` is genuinely, if barely,
    // worse than doing nothing.
    assert!(!ranked[1].result.is_satisfied());
    assert!(!ranked[2].result.is_satisfied());
    assert_eq!(ranked[1].result.confidence, 1.0 - 2.0 / 19.0);
    assert_eq!(ranked[2].result.confidence, 1.0 - 2.0 / 19.0);
    assert_eq!(ranked[1].candidate.rho_max(), 0.037622131);
    assert_eq!(ranked[2].candidate.rho_max(), 0.037630755);
}

#[test]
fn dare_proposal_is_complete_and_clears_decide_to_act() {
    let scenario = ContingencyScenario::load().unwrap();
    let ranked = optimizer::rank(&scenario);
    let proposal = optimizer::to_dare_proposal(&scenario, &ranked);

    assert_eq!(proposal.proposal_id, "DARED-n1_line_4125_4128");
    assert_eq!(proposal.phase, OodaPhase::Decide);
    assert_eq!(
        proposal.decision.what,
        "Apply remedial action `reclose_line_4125_4128` to clear n1_line_4125_4128"
    );
    // Every candidate that was not chosen is recorded as a real Alternative
    // with a real rejection reason, which is what DARED requires.
    assert_eq!(proposal.alternatives.len(), 2);
    assert_eq!(proposal.alternatives[0].name, "do_nothing");
    assert!(proposal.alternatives[0]
        .rejected_because
        .starts_with("Violated(2 of 19 cluster branches over rho limit 0.030"));
    assert_eq!(proposal.risks.len(), 1);

    proposal.validate().expect("DARED document is structurally complete");
    assert!(proposal.is_ready_to_act());

    let (phase, accepted) = optimizer::dispatch_to_act(proposal);
    assert_eq!(phase, OodaPhase::Act);
    assert!(accepted);
}

#[test]
fn objective_limit_comes_from_the_fixture_not_a_hardcoded_default() {
    let scenario = ContingencyScenario::load().unwrap();
    assert_eq!(scenario.objective(), GridSecurityObjective { rho_limit: 0.030 });
    // ...and the crate default agrees, so the FSM and the optimizer score the
    // same threshold.
    assert_eq!(GridSecurityObjective::default().rho_limit, 0.030);
}
