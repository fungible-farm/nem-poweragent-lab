# Phase 0b spike — native-Rust SysML v2 parsers vs. real fixtures

PRD-0009's Phase 0b: does either of the two real, actively-maintained native-Rust SysML v2/KerML
parser crates found this session (`sysml-v2-parser`, `syster-base`) actually parse real SysML v2
text? Not researched — run for real, against (a) 36 real model files from `GfSE/SysML-v2-Models`
and (b) this repo's own three already-generated `.sysml` outputs from Lab 6
(`labs/06-sysml-digital-thread/output/*.sysml`). This directory is a standalone Rust crate, not a
member of `rust/`'s workspace — throwaway spike, `rust/Cargo.toml`/`rust/Cargo.lock` untouched.

## Setup

```
cargo add sysml-v2-parser   # resolved to 0.54.0
cargo add syster-base       # resolved to 0.5.1-alpha, package name "syster-base", lib crate name "syster"
```

Both added cleanly from crates.io, no yanked/missing-version issues. Dependency footprint is
**very** different:

- `sysml-v2-parser` v0.54.0 — small, `nom`-based recursive-descent parser. Real dependency tree:
  `log`, `nom`, `nom_locate`, `stacker` (+ their own transitive deps) — 17 packages total in the
  lockfile including itself.
- `syster-base` v0.5.1-alpha — a full rust-analyzer-style stack: `logos` (lexer), `rowan`
  (lossless CST), `salsa` (incremental query engine), plus `tokio`, `rayon`, `dashmap`,
  `wasm-bindgen`, `uuid`, `borsh`... 82 packages pulled in by `cargo add` alone, 112 lines in
  `cargo tree -p syster-base`.

Both compiled and ran with `cargo build`/`cargo run` on stable Rust 1.96.0, no feature flags
needed beyond the crates' own defaults (`syster-base` defaulted `interchange` on, unused by this
spike).

## What was tried

`src/main.rs` walks `fixtures/` recursively, and for every `.sysml` file calls:

- `sysml_v2_parser::parse(src)` (strict) — on failure, also calls `parse_for_editor(src)` to show
  how far the resilient path gets.
- `syster::parser::parse_sysml(src)` (always resilient; `Parse.errors` is empty on success).

Fixture set (39 files, `fixtures/`):

- `fixtures/gfse-models/` — a full `git clone --depth 1` of `https://github.com/GfSE/SysML-v2-Models`
  (its own README confirms: no commits since 2025-06-04, stale but real), `models/` copied in —
  36 real `.sysml` files: use-case models, a family-law adoption example, a drone, a lawnmower, a
  mining-frigate system-of-systems model, HVAC requirements, an EVE Online domain model, etc.
- `fixtures/digital_thread.sysml`, `fixtures/grid_topology.sysml`, `fixtures/pipeline_phases.sysml`
  — copied directly from this repo's own `labs/06-sysml-digital-thread/output/*.sysml` (freshly
  regenerated, `--step run` for all three tracks, matches the committed `fixtures/expected_*.sysml`
  in Lab 6).

Full raw run captured in `run_output.txt` in this directory (`cargo run --quiet > run_output.txt`).

## Results — real numbers, not estimated

```
sysml-v2-parser : 26 pass / 39 total (13 fail)
syster-base     : 28 pass / 39 total (11 fail)
```

Split by fixture source:

| Fixture set | sysml-v2-parser | syster-base |
|---|---|---|
| This repo's own Lab 6 output (3 files: digital-thread, grid-topology, pipeline-phases) | **3/3 PASS** | **3/3 PASS** |
| Real `GfSE/SysML-v2-Models` fixtures (36 files) | 23/36 pass (63.9%) | 25/36 pass (69.4%) |

**This repo's own generated `.sysml` parses cleanly on both parsers, no surprise**: Lab 6's
`generate_sysml.py` deliberately emits only `package`/`part def`/`part`/`attribute` — the
"straight boxes are enough" MVP subset (see `labs/06-sysml-digital-thread/README.md`). Both real
parsers trivially cover that subset; this datapoint says nothing about how they'd perform if Lab
6's schema ever grows past that subset (ports, connections, states, requirements, actions), which
the GfSE fixtures below actually probe.

**Real GfSE fixtures are the interesting result.** Of 36 real files: 19 pass on both parsers, 7
fail on both, 6 fail only on `sysml-v2-parser`, 4 fail only on `syster-base`. The failure sets
barely overlap — each parser has real gaps the other doesn't:

| File | sysml-v2-parser | syster-base |
|---|---|---|
| `SE_Models/DroneModelLogical.sysml` | FAIL | FAIL |
| `SE_Models/EIT_System_Use_Cases.sysml` | FAIL | FAIL |
| `SE_Models/ForestFireDetectionSystemModel.sysml` | FAIL | FAIL |
| `SE_Models/InternetModel_v1.sysml` | FAIL | FAIL |
| `SE_Models/VehicleModel.sysml` | FAIL | FAIL |
| `.../DomainModel/Domain.sysml` | FAIL | FAIL |
| `example_family/family.sysml` | FAIL | FAIL |
| `SE_Models/Drone_BaseArchitecture.sysml` | FAIL | pass |
| `SE_Models/MPLEExample_DirectCleanApproach_Vehicle.sysml` | FAIL | pass |
| `SE_Models/StopWatchStates.sysml` | FAIL | pass |
| `.../LogicalArchitecture/ActionsHull.sysml` | FAIL | pass |
| `.../LogicalArchitecture/COTS.sysml` | FAIL | pass |
| `example_contribution/example_nested/Boeing.sysml` | FAIL | pass |
| `SE_Models/HVACSystemRequirements.sysml` | pass | FAIL |
| `.../DomainModel/MiningFrigate.sysml` | pass | FAIL |
| `.../LogicalArchitecture/UseCasesHull.sysml` | pass | FAIL |
| `.../UseCases/UseCasesFrigate.sysml` | pass | FAIL |

## Real error text (verbatim, not paraphrased)

`sysml-v2-parser` on `SE_Models/StopWatchStates.sysml` (real `action def` without a body, valid
SysML v2 per the spec's forward-declaration form):

```
parse() FAILED: expected ';' or '{' after declaration header (found 'action def VehicleStartSignal;')
Use `action def Run;` or `action def Run { ... }`. at line 7, column 11
parse_for_editor(): 2 diagnostic(s), first: Some(ParseError { message: "expected ';' or '{' after
action definition header", offset: Some(114), line: Some(7), column: Some(11), length: Some(41),
severity: Some(Error), code: Some("missing_body_or_semicolon"), ... })
```

That one is a real parser bug/gap, not a bad fixture — `action def Foo;` (bare declaration,
semicolon only) is exactly the form the crate's own suggestion text says to use, and the fixture
uses that exact form; `syster-base` parses it with 0 errors.

`syster-base` on `SE_Models/HVACSystemRequirements.sysml` (real boolean-logic requirement
constraint expression):

```
parse_sysml() 6 error(s). First up to 3:
SyntaxError { message: "expected '}', found '&&'", range: 1918..1920 }
SyntaxError { message: "unexpected '&&' in namespace body", range: 1918..1920 }
SyntaxError { message: "expected '}', found '&&'", range: 3110..3112 }
```

`syster-base`'s expression grammar doesn't yet handle `&&` inside a requirement body in this
position; `sysml-v2-parser` parses the same file cleanly.

Both fail on `example_family/family.sysml` but on genuinely different constructs —
`sysml-v2-parser` chokes on `snapshot birth;` (an occurrence-usage keyword inside a connection
definition body):

```
parse() FAILED: expected valid connection definition body element (found 'snapshot birth;')
Replace `snapshot` with a valid connection definition body member or remove it. at line 103, column 3
```

`syster-base` gets further into the same file but then fails on different tokens entirely
(`done`, `start`, a stray `=`):

```
parse_sysml() 12 error(s). First up to 3:
SyntaxError { message: "expected ';' to end declaration or '{' to start body, found 'done' ('done')", range: 3594..3598 }
SyntaxError { message: "expected ';' to end declaration or '{' to start body, found 'start' ('start')", range: 4240..4245 }
SyntaxError { message: "expected '}', found '='", range: 5851..5852 }
```

Full text for every file, both parsers, is in `run_output.txt`.

## Analysis

- **Neither parser is spec-complete against real-world SysML v2 text today.** ~64-69% of real
  GfSE fixtures pass per-parser; ~53% (19/36) pass on *both*. These are curated example models
  from the SysML working group's own reference repo, not adversarial or malformed input — genuine
  gaps, not bad fixtures.
- **The two parsers' gaps are largely disjoint** (6 sysml-v2-parser-only failures, 4
  syster-base-only failures, only 7 files both reject). That's a real signal this repo could use:
  a "parses if either accepts it" OR gate would cover 32/36 (88.9%) instead of either alone.
  Recorded here as an option, not implemented — out of this spike's scope.
- **This repo's own current `.sysml` emission is not a real stress test for either parser** — Lab
  6's deliberately minimal grammar subset (`package`/`part def`/`part`/`attribute` only) is
  trivial for both. The real GfSE fixtures are what actually exercises the parsers' coverage.
- **Dependency cost is a real, not cosmetic, differentiator.** `sysml-v2-parser` pulls 17 packages
  total (a `nom` parser plus `stacker` for deep-recursion safety); `syster-base` pulls 82+
  (`salsa`, `rowan`, `tokio`, `rayon`, `dashmap`, `wasm-bindgen`, ...) because it's architected as
  a full incremental-compiler/IDE backend, not just a parser. For "parse this file, check it's
  valid," that's a materially heavier build for the win it doesn't need yet — `syster-base`'s
  extra weight buys IDE features (hover, goto-def, completion, semantic tokens — all real modules
  under `src/ide/`) this repo doesn't currently have a use for.
- **Neither crate crashed, panicked, or hung on any of the 39 real files** — every failure was a
  clean `Result::Err`/non-empty `errors` Vec with real line/column (or byte-range) diagnostics.
  That's a genuinely different failure mode than Lab 6's original JVM/Maven
  `UnsatisfiedLinkError` dead end (`labs/06-sysml-digital-thread/README.md`'s Design notes §1) —
  these are real, working, native-Rust binaries that parse correctly ~2/3 of the time and fail
  cleanly and diagnosably the rest of the time, not a build-time or link-time blocker.

## Verdict

**`sysml-v2-parser` is the better default pick for this repo's static-type parsing layer going
forward, not because it parses more (it parses slightly less: 23/36 vs. syster-base's 25/36 on
real fixtures) but because of what it costs to adopt**: a small, focused `nom`-based parser with
an explicit strict/lenient API split (`parse()`/`parse_for_editor()`) that matches this repo's own
"syntax gate" use case in `validate_sysml.py` directly, 17 total dependencies, and (per PRD-0009's
research) a conformance suite tied to the real `SysML-v2-Release` repo — i.e. it's already being
tested against the same class of fixtures this spike used.

**`syster-base` is not disqualified** — it parsed more of the real GfSE corpus in this run, and
its rust-analyzer-shaped architecture (Salsa incremental engine, lossless CST, HIR, IDE-feature
modules already implemented) is the more architecturally serious long-term bet *if* this repo ever
wants IDE/LSP-grade tooling (hover, goto-definition, live diagnostics as a user types) rather than
just a build-time syntax gate. It's flagged alpha (0.5.1-alpha) for a real reason: `parse_sysml`
on `family.sysml` and `Domain.sysml` both show its own error recovery cascading into unrelated
follow-on errors once it desyncs, a rougher edge than `sysml-v2-parser`'s more localized failures.

**Recommendation for Phase 1+**: adopt `sysml-v2-parser` as the primary static-type/syntax-gate
parser — a direct, lower-cost replacement for `validate_sysml.py`'s hand-rolled structural
stand-in, and a real upgrade path over the JVM/Maven dead end. Do not adopt `syster-base` yet;
revisit it specifically if/when this repo wants editor tooling (LSP server, live validation in an
IDE), which is the actual problem its extra weight is solving. Neither should be treated as
"replaces the normative SysML v2 spec checker" — both have real, demonstrated gaps against
official example models, so any future gate built on either should keep reporting real
line/column errors on failure (as both already do) rather than silently accepting or silently
rejecting input.

## Files

- `Cargo.toml` / `Cargo.lock` — standalone crate, not a member of `rust/`'s workspace.
- `src/main.rs` — the spike program (recursive fixture walk, both parsers, real pass/fail + error
  text per file).
- `fixtures/gfse-models/` — full clone of `GfSE/SysML-v2-Models`'s `models/` directory (36 `.sysml`
  files).
- `fixtures/{digital_thread,grid_topology,pipeline_phases}.sysml` — copied from this repo's own
  `labs/06-sysml-digital-thread/output/` (freshly regenerated for this spike).
- `run_output.txt` — full captured stdout of `cargo run`, every file's real result and error text.
