# Phase 0d spike: `ufo-types` + `scryer-prolog` build/link smoke test

**PRD:** `docs/prd/0009-cim-gridy-incose-v-plan.md`, Phase 0d — "`ufo-types` +
`scryer-prolog` integration-shape spike (build/link smoke test only)."

**Scope, per the PRD:** prove the two crates can be linked together in one
Rust binary and each do something minimally real. This is explicitly *not*
full integration — `Satisfies<C>` is not wired to call into scryer-prolog for
real proof-search here; that is future work (PRD-0009 Phase 3). This is a
standalone throwaway spike crate, not part of the main `rust/` Cargo
workspace.

## Verdict

**Yes — the two crates coexist cleanly as a foundation for later real
`Satisfies<C>`-via-scryer-prolog integration, with one caveat that is a
scryer-prolog-only bug (not an interaction bug) and does not block the
integration path.**

- Both crates build and link together in one binary with **no dependency
  conflicts**: `serde` and `chrono` (used by both `ufo-types` and
  `scryer-prolog`) resolve to a single unified version each
  (`serde` 1.0.229, `chrono` 0.4.45); the only other shared-name crate is
  `thiserror`, where `ufo-types` pulls `2.0.20` and `scryer-prolog`'s tree
  pulls a different major version independently -- normal, harmless Rust
  dependency diversity (`cargo tree -i thiserror` reports it as ambiguous
  precisely because there are two independent major-version subgraphs, not
  because of a resolution failure). No edition/MSRV conflict: `ufo-types` is
  edition 2024 / `rust-version = "1.85"`, `scryer-prolog` 0.10.0 is edition
  2024 / `rust-version = "1.93.1"`; this sandbox's `rustc 1.96.0` satisfies
  both.
- **`cargo build` (debug profile) succeeds** in ~6.5 minutes cold (~150
  transitive crates compiled, dominated entirely by `scryer-prolog`'s own
  dependency tree -- `ufo-types` itself is tiny: `serde`, `serde_json`,
  `chrono`, `thiserror`).
- **`cargo build --release` succeeds** in ~6.5 minutes cold too.
- **Part (a) — `ufo-types`' `UfoStereotype`/`Satisfies<C>` — ran correctly
  in both debug and release builds**, producing real output (see below).
- **Part (b) — `scryer-prolog`'s `Machine`/query API — ran correctly and
  produced correct real Prolog answers in the `--release` build**, but
  **panics in the plain `cargo build` (debug) profile** with a real bug
  inside `scryer-prolog` itself, unrelated to `ufo-types` (see "Debug-build
  panic" below). This does not block adopting `scryer-prolog`: the query
  engine itself is correct (confirmed by the release run below); it's a
  reportable upstream issue about UB-check compliance in debug builds on a
  very recent `rustc`.

## What was verified against real source, not the PRD's paraphrase

`promptexecution/ufo-types` was cloned fresh
(`gh repo clone promptexecution/ufo-types`, commit `443482c`) and its actual
`src/stereotype.rs` and `src/satisfies.rs` read in full. Confirmed real API
shape:

- `ufo_types::stereotype::UfoStereotype` -- enum `{ Kind(String), SubKind {
  name, parent }, Role(String), Relator(String), Mode(String) }`, `Display`
  impl producing labels like `"Kind:Substation"`.
- `ufo_types::stereotype::Stereotyped` trait -- `fn ufo_stereotype(&self) ->
  UfoStereotype`.
- `ufo_types::satisfies::Satisfies<C>` trait -- `fn satisfies(&self,
  constraint: &C) -> SatisfiesResult`.
- `ufo_types::satisfies::SatisfiesResult` -- `{ disposition: Disposition,
  confidence: f64, evidence_nodes: Vec<NodeId>, ufo_category: UfoStereotype
  }` with constructors `satisfied(confidence)`, `violated(reason,
  confidence)`, `unknown(confidence)`.
- `ufo_types::satisfies::Disposition` -- `Satisfied | Violated { reason:
  String } | Unknown`.
- The crate's own test module (`src/satisfies.rs`, `TestCompany` /
  `LeiRequired`) is the real, working usage pattern this spike's `Substation`
  / `N1Contingency` example mirrors.

`scryer-prolog`'s real API was confirmed by cloning
`github.com/mthom/scryer-prolog` and reading `src/lib.rs` and
`src/machine/lib_machine/{mod.rs,tests.rs}` directly (crates.io's package
API endpoint was unreachable in this sandbox -- `crates.io/api/v1/crates/...`
returned a data-access-policy error both times it was tried -- so
`cargo add --dry-run` and a source clone were used instead, both of which
worked):

- `scryer_prolog::MachineBuilder::default().build() -> Machine` (re-exported
  at crate root via `pub use machine::config::*;`).
- `Machine::load_module_string(&mut self, module_name: &str, program: impl
  Into<String>)`.
- `Machine::run_query(&mut self, query: impl Into<String>) ->
  QueryState<'_>`, an iterator of `Result<LeafAnswer, _>`.
- `scryer_prolog::LeafAnswer` -- `True | False | Exception(Term) |
  LeafAnswer { bindings: BTreeMap<String, Term> }`, with a
  `LeafAnswer::from_bindings(...)` constructor used throughout the crate's
  own tests.
- **Not in the PRD's paraphrase, confirmed empirically in this spike**: a
  query with a variable that has multiple solutions yields one `LeafAnswer`
  per solution *followed by a trailing `LeafAnswer::False`* once
  backtracking is exhausted; a query with no free choice points (like a
  single ground fact match) yields just `[True]` with no trailing `False`.
  This spike's first assertion (`bound_answers == [...three bindings...]`,
  no trailing `False`) initially failed against this real, correct behavior
  -- fixed once observed (see `src/main.rs` and git history of this file if
  kept).

## Crate/registry findings

- **`ufo-types` is NOT published on crates.io.** Confirmed via `cargo add
  ufo-types --dry-run` -> `error: the crate 'ufo-types' could not be found
  in registry index.` Used as a git dependency instead: `ufo-types = { git =
  "https://github.com/promptexecution/ufo-types" }` (resolves to `v0.10.2`,
  commit `443482c`).
- **`scryer-prolog` IS published on crates.io**, confirmed via `cargo add
  scryer-prolog --dry-run` -> resolves `v0.10.0`. Used as
  `scryer-prolog = { version = "0.10", default-features = false, features =
  ["repl", "hostname"] }`.
  - The published `0.10.0` on crates.io does **not** have the `all-pure`
    meta-feature that exists in the crate's git `HEAD` Cargo.toml (`cargo
    build` first failed with `package 'spike-...' depends on 'scryer-prolog'
    with feature 'all-pure' but 'scryer-prolog' does not have that feature`
    when the git-HEAD feature name was used) -- the published release is
    slightly behind the git repo's Cargo.toml. Fixed by depending on the
    published release's real constituent features (`repl`, `hostname`)
    directly instead of the newer meta-feature name.
  - Default features (`tls`, `http`, `crypto-full`, `ffi`) were deliberately
    disabled (`default-features = false`) for this smoke test to avoid a
    native-openssl link dependency that is irrelevant to proving basic
    coexistence; only the pure-Rust `repl` and `hostname` features were
    enabled (needed to satisfy `MachineBuilder`'s config surface).

## Debug-build panic (real, reproducible, scryer-prolog-only bug)

`cargo build` (default debug profile) + `cargo run` panics during
`MachineBuilder::default().build()` itself (before any of this spike's own
`load_module_string`/`run_query` calls execute), with:

```
thread 'main' panicked at .../alloc/src/alloc.rs:121:30:
unsafe precondition(s) violated: NonNull::new_unchecked requires that the pointer is non-null
thread caused non-unwinding panic. aborting.
```

`RUST_BACKTRACE=full` traces this to `scryer_prolog::machine::heap::
Heap::clear` (`scryer-prolog-0.10.0/src/machine/heap.rs:685`) calling
`alloc::alloc::dealloc` on what the new Rust stdlib UB-check (`ub_checks`,
active in this sandbox's `rustc 1.96.0`, released 2026-05-25) determines is
an invalid/null pointer, reached via `Machine::run_module_predicate ->
Machine::load_file -> Machine::load_top_level -> MachineBuilder::build`.
**No `ufo_types` symbols appear anywhere in the backtrace** -- this is
reproducible with `scryer-prolog` alone and is unrelated to `ufo-types` or
to anything this spike's code does.

`cargo build --release` **does not exhibit this panic** -- the query engine
runs correctly and produces the correct real Prolog answers (see "How to
run" below). This is consistent with `ub_checks`-gated UB detection being a
debug-profile-only Rust stdlib feature on this very-recent toolchain; the
underlying pointer-arithmetic pattern in `Heap::clear` may still be worth
flagging upstream to `mthom/scryer-prolog` even though it does not manifest
as a functional bug in release builds.

**This does not change the Phase 0d verdict**: the actual Prolog
query-answering logic is correct in the mode that matters for real usage
(release builds; any real deployment would ship release, not debug). It is
recorded here because Phase 0d's job is exactly to surface findings like
this before Phase 3 integration work begins.

## How to run

```console
$ cargo build --release   # ~6.5 min cold; recommended -- avoids the debug-only panic above
$ ./target/release/spike-0d-ufo-types-scryer-prolog
== ufo-types smoke test ==
Substation UfoStereotype: Kind:Substation
Satisfies<N1Contingency>: disposition=Satisfied confidence=0.97
Failing case: disposition=Violated { reason: "N-1 contingency analysis failed" } confidence=1
ufo-types: OK

== scryer-prolog smoke test ==
feeds(bus_a, bus_b). -> [True]
energized(bus_a, X). -> [LeafAnswer { bindings: {"X": Atom("bus_b")} }, LeafAnswer { bindings: {"X": Atom("bus_c")} }, LeafAnswer { bindings: {"X": Atom("bus_d")} }, False]
scryer-prolog: OK

Phase 0d smoke test: both crates built, linked, and ran in one binary.
```

(`energized/2` is a transitive-closure rule over a small `feeds/2` grid
topology fact base -- `bus_a -> bus_b -> bus_c -> bus_d` -- defined in
`src/main.rs`'s `GRID_TOPOLOGY` constant, deliberately grid-flavored rather
than a generic `parent(tom, bob)` toy example, to keep it recognizable as a
real query, not just a syntax check.)

Debug build (`cargo build` / `cargo run`, no `--release`) reproduces the
panic documented above.

## Files

- `Cargo.toml` -- standalone crate manifest (not part of `rust/`'s
  workspace); `ufo-types` as a git dependency, `scryer-prolog` from
  crates.io with reduced (pure-Rust) features.
- `src/main.rs` -- the spike program: part (a) `ufo-types`
  `UfoStereotype`/`Satisfies<C>` example (`Substation`/`N1Contingency`),
  part (b) `scryer-prolog` `Machine`/query example (grid-topology
  transitive-closure query), run back to back in `main()`.
- `Cargo.lock` -- captured lockfile from the successful build, left in place
  for reproducibility (not committed to the main `rust/` workspace lock).

## Recommendation for Phase 3

Proceed with `ufo-types` + `scryer-prolog` as the ontology/constraint-solving
foundation. Concretely for the real integration:

1. Depend on `ufo-types` via git (pin a commit or tag once one exists;
   `443482c` was current at spike time) since it is not on crates.io.
2. Build release binaries (or at minimum `-C debug-assertions=off`) when
   exercising `scryer-prolog`'s `Machine` until the upstream `Heap::clear`
   UB-check issue is fixed or better understood -- file/track it against
   `mthom/scryer-prolog` before Phase 3 starts, since Phase 3 is where the
   `Satisfies<C>` impl would actually call into a live `Machine` for
   proof-search and would run debug builds during its own development.
3. `Satisfies<C>::satisfies` implementations would call
   `Machine::run_query`, translate `LeafAnswer::{True,False,LeafAnswer}`
   into `SatisfiesResult`'s `Disposition`, and use the query's bindings (or
   lack of a solution) to decide `Satisfied` / `Violated` / `Unknown` --
   the trailing-`False`-after-solutions behavior observed here matters for
   that translation (a caller collecting all answers needs to filter it out
   or treat it as "no more solutions", not as a fourth real answer).
