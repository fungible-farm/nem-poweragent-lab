//! PRD-0009 Phase 0d spike: build/link smoke test for `ufo-types` +
//! `scryer-prolog` coexisting in one Rust binary.
//!
//! Scope (per PRD-0009, Phase 0d): prove the two crates can be linked
//! together and each do something minimally real. This does NOT wire
//! `Satisfies<C>` to call into scryer-prolog for real proof-search --
//! that is future integration work (PRD-0009 Phase 3), explicitly out of
//! scope here. The two halves below run independently, back to back, in
//! the same process.

use scryer_prolog::{LeafAnswer, MachineBuilder, Term};
use ufo_types::satisfies::{Satisfies, SatisfiesResult};
use ufo_types::stereotype::{Stereotyped, UfoStereotype};

// ---------------------------------------------------------------------
// Part (a): ufo-types -- UfoStereotype + Satisfies<C>
//
// Mirrors the pattern in ufo-types' own src/satisfies.rs test module
// (TestCompany / LeiRequired) -- a domain entity implementing both
// `Stereotyped` and `Satisfies<C>` for a constraint type.
// ---------------------------------------------------------------------

/// A grid substation -- our stand-in domain entity for this smoke test.
struct Substation {
    n1_contingency_clear: bool,
}

/// A constraint: the substation must clear N-1 contingency analysis.
struct N1Contingency;

impl Stereotyped for Substation {
    fn ufo_stereotype(&self) -> UfoStereotype {
        // UFO-A rigid Kind: a substation doesn't stop being a substation.
        UfoStereotype::Kind("Substation".into())
    }
}

impl Satisfies<N1Contingency> for Substation {
    fn satisfies(&self, _c: &N1Contingency) -> SatisfiesResult {
        if self.n1_contingency_clear {
            SatisfiesResult::satisfied(0.97)
        } else {
            SatisfiesResult::violated("N-1 contingency analysis failed", 1.0)
        }
    }
}

fn run_ufo_types_smoke_test() {
    println!("== ufo-types smoke test ==");

    let sub = Substation {
        n1_contingency_clear: true,
    };
    let stereotype = sub.ufo_stereotype();
    println!("Substation UfoStereotype: {stereotype}");
    assert_eq!(stereotype.to_string(), "Kind:Substation");

    let result = sub.satisfies(&N1Contingency);
    println!(
        "Satisfies<N1Contingency>: disposition={:?} confidence={}",
        result.disposition, result.confidence
    );
    assert!(result.is_satisfied());

    let failing_sub = Substation {
        n1_contingency_clear: false,
    };
    let failing_result = failing_sub.satisfies(&N1Contingency);
    println!(
        "Failing case: disposition={:?} confidence={}",
        failing_result.disposition, failing_result.confidence
    );
    assert!(failing_result.is_violated());

    println!("ufo-types: OK\n");
}

// ---------------------------------------------------------------------
// Part (b): scryer-prolog -- Machine + a trivial fact/rule query
//
// API shape confirmed against scryer-prolog's own
// src/machine/lib_machine/{mod.rs,tests.rs} (MachineBuilder::default()
// .build(), Machine::load_module_string, Machine::run_query returning an
// iterator of Result<LeafAnswer, _>).
// ---------------------------------------------------------------------

const GRID_TOPOLOGY: &str = r#"
    feeds(bus_a, bus_b).
    feeds(bus_b, bus_c).
    feeds(bus_c, bus_d).

    energized(X, Y) :- feeds(X, Y).
    energized(X, Y) :- feeds(X, Z), energized(Z, Y).
"#;

fn run_scryer_prolog_smoke_test() {
    println!("== scryer-prolog smoke test ==");

    let mut machine = MachineBuilder::default().build();
    machine.load_module_string("grid", GRID_TOPOLOGY);

    // Trivial ground query.
    let ground_answers: Vec<_> = machine
        .run_query("feeds(bus_a, bus_b).")
        .collect::<Result<Vec<_>, _>>()
        .expect("ground query should execute");
    println!("feeds(bus_a, bus_b). -> {ground_answers:?}");
    assert_eq!(ground_answers, [LeafAnswer::True]);

    // Query with a variable binding, plus transitive-closure rule use.
    let bound_answers: Vec<_> = machine
        .run_query("energized(bus_a, X).")
        .collect::<Result<Vec<_>, _>>()
        .expect("bound query should execute");
    println!("energized(bus_a, X). -> {bound_answers:?}");
    // The query iterator yields one LeafAnswer per solution followed by a
    // trailing `False` once backtracking is exhausted (confirmed empirically
    // -- not documented in the doc comments read from source).
    assert_eq!(
        bound_answers,
        [
            LeafAnswer::from_bindings([("X", Term::atom("bus_b"))]),
            LeafAnswer::from_bindings([("X", Term::atom("bus_c"))]),
            LeafAnswer::from_bindings([("X", Term::atom("bus_d"))]),
            LeafAnswer::False,
        ]
    );

    println!("scryer-prolog: OK\n");
}

fn main() {
    run_ufo_types_smoke_test();
    run_scryer_prolog_smoke_test();
    println!("Phase 0d smoke test: both crates built, linked, and ran in one binary.");
}
