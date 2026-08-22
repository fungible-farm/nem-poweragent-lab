# 0009 — cim-gridy: INCOSE-V prioritized plan, Rust/Bevy-first

- **Status:** Phase 0 (a-e) complete, real evidence for every spike (Lab 8,
  `labs/08-cim-gridy-phase0-spikes/`); Phase 1 not started
- **Depends on:** 0006 (Lab 6 SysML v2 digital-thread MVP), 0007 (Lab 6 Phase 4a CIM class-URI
  traceability), 0008 (cim-gridy Phase 0 prerequisites)
- **Touches:** this PRD file + `docs/prd/README.md`'s index row only — no code, no installs, no
  rename in this pass, same boundary PRD-0008 already set

## Problem

PRD-0008 surveyed real prerequisites for the "cim-gridy" pivot (grid-operator missions in calendar
steps, featuring LF Energy tools) at a high level. A follow-on planning pass sharpened the mandate
significantly: **prioritize using an INCOSE "V" systems-engineering model**, **use sub-agents
heavily**, **source crates from blessed.rs — do not reinvent the wheel**, **prefer Rust over
Python**, **use Bevy as the game engine**, and re-investigate SysML v2 tooling against the official
`systems-modeling/sysml-v2-release` repo and GfSE's `SysML-v2-Models`. This PRD turns that research
into a prioritized, INCOSE-V-shaped plan — still no code, no installs, no rename; that's Phase 0's
job, not this PRD's.

## What was checked this session, not assumed

**Crate stack — blessed.rs picks where it has an opinion, verified-current alternatives where it
doesn't:**

| Need | Pick | Why |
|---|---|---|
| Game engine / ECS | **Bevy 0.19** (MIT/Apache-2.0) | blessed.rs's own pick; confirmed healthy (47.8k stars, 261 contributors last release cycle, ~3-month cadence, June 2026 release) |
| Async runtime | **Tokio** | blessed.rs default |
| Serialization | **serde / serde_json / toml / prost** | blessed.rs default |
| CLI | **clap** | blessed.rs default |
| Horn-clause/FOHH constraint solving | **`scryer-prolog`** (BSD-3-Clause) | blessed.rs has no logic-programming section, but direct crates.io checks show `chalk` is being phased out of rustc itself and `datafrog` is unmaintained since 2019 — this **corrects this project's own `b00t learn rust` house doc**, which still names chalk/datafrog as the picks; scryer-prolog (released 2025-09, active) is the one safe live dependency of the three |
| WASM | no blessed.rs section; use the official wasm-bindgen/rustwasm toolchain directly | confirmed real, working path for Bevy specifically, but browser builds lose ECS multithreading and not every plugin is WASM-compatible |
| Geospatial | no blessed.rs section, no pick made | real gap — `georust` exists outside blessed.rs's scope, not yet evaluated; CSIRO's own case data also carries no lat/lon (PRD-0008), so a geocoded source is needed regardless of crate choice |
| RDF/OWL/SHACL | no blessed.rs section at all | reinforces PRD-0008's own open question — `ufo-types`'s Rust-native `Satisfies<C>` model is the more practical foundation than a from-scratch RDF/OWL/SHACL layer |

**SysML v2 tooling — the landscape has materially changed since Lab 6's original 2026-08-18
investigation, checked directly against crates.io/GitHub/GitLab APIs, not assumed stale:**

- `Systems-Modeling/SysML-v2-Release` is a **sibling repo in the same org** as
  `SysML-v2-Pilot-Implementation`, not an alternative path — it ships spec PDFs, the normative
  textual/KPAR/XMI standard library, and Eclipse-IDE/Jupyter installers only. Its own README
  explicitly punts headless use back to the Pilot Implementation. No CLI, no jar, no Docker image.
  Actively maintained (latest release 2026-07-22).
- **The `sysand-maven-plugin` JNI bug from Lab 6's original investigation is still unfixed** as of
  2026-08-21 — the plugin's last publish was 2026-06-16 (v0.1.4); a JNI-adjacent fix landed on the
  upstream Rust `sysand` repo's `main` branch 2026-08-10 but has not been published to Maven
  Central. The JVM/Maven path remains genuinely blocked, not just untried.
- **Real native-Rust SysML v2/KerML parsers exist now, checked directly, not toy projects:**
  - **`sysml-v2-parser`** (elan8, MIT, crates.io) — actively maintained, last published
    2026-08-07 (14 days before this research). Strict `parse()` + resilient `parse_for_editor()`,
    640 textual productions implemented, and its own conformance suite pulls fixtures directly
    from the real `SysML-v2-Release` repo.
  - **`syster-base`** (jade-codes, MIT) — the architecturally serious find: a rust-analyzer-style
    stack (logos lexer, rowan lossless CST, Salsa incremental engine, HIR, name resolution, IDE
    features). Alpha (0.5.1-alpha), actively pushed 2026-07-07.
  - **`sensmetry/sysand`** itself (dual MIT/Apache-2.0) — the Rust-based SysML v2/KerML package
    manager whose *Maven wrapper* has the JNI bug; its own native Rust CLI (`sysand build`/
    `sysand publish`) may sidestep the JVM layer entirely — worth a direct spike rather than
    assuming the whole tool is blocked because its Maven plugin is.
  - `artob/sysml.rs` confirmed genuinely abandoned (~2 years stale) — correctly excluded.
  - `tree-sitter-sysml` (GitLab, active) — grammar-only (no semantics), useful for editor tooling.
- **`GfSE/SysML-v2-Models`** (BSD-3-Clause) — real, curated example models, good reference
  fixtures, but stale (no commits since 2025-06-04, 14+ months). Use as fixtures, don't expect
  upstream activity.
- **Syside (Sensmetry)** — free tier still editor-extension-only, no CLI/API. CLI/Automator/
  diagrams gated behind paid Solo/Business tiers. The same company controls both the buggy free
  `sysand-maven-plugin` and the paid, presumably-working Syside tooling — noted, not acted on.
- **This supersedes Lab 6's own "real parser vs. hand-rolled stand-in" framing.** The JVM path is
  still blocked, but it's no longer "real parser (blocked) vs. stand-in" — it's now "a real,
  actively-maintained native-Rust parser (`sysml-v2-parser` or `syster-base`) vs. the old
  hand-rolled stand-in," a materially better position that matches the Rust-first mandate.

**Bevy — external-simulation integration pattern confirmed via a real precedent, not
hypothesized:** `bevy_rapier` (dimforge) wraps the non-Bevy-native Rapier physics engine behind a
`Plugin` that registers a `Resource`/context, with a `System` stepping the external solver each
tick and writing results back into ECS state. This is the direct template for wrapping
pandapower/PowSyBl/Grid2Op grid-physics state inside a Bevy app — the same
Entity/Component/System/Resource/Plugin/World/App vocabulary applies throughout this plan. **No
existing open-source Bevy + power-grid/energy project was found** — confirmed by direct search;
this is a genuine first, not a reinvention.

**INCOSE V-model — real structure, used to shape this plan, not a paraphrase:** Left
(decomposition): Concept of Operations → System Requirements → Architecture (high-level design) →
Detailed Design. Bottom: Implementation & Coding. Right (integration/verification): Unit/Component
Test → Subsystem Integration & Test → System Verification & Validation → Operation & Maintenance.
**Core discipline: every left-side level has a paired right-side check at the same abstraction
level.** Best real free template: the NASA Systems Engineering Handbook (SP-2016-6105 Rev2, freely
downloadable); the INCOSE Handbook itself is paid; no maintained open-source V-model checklist repo
was found.

**Local b00t ecosystem — real, reusable, currently uncatalogued as `sysml`/`bevy`/`rdf`/`shacl`
datums (confirmed via `b00t datum search`, all empty):**
- `ledgrrr`'s real **TOML → Rhai FSM → Mermaid → Rust enum** pipeline ("code is source of truth
  for types") is a ready state-machine-with-diagram pattern for the mission/calendar-step loop.
- `ledgrrr`'s **`ontology-extractor`** (parses Rust AST via `syn`, emits an `OntologyGraph` JSON)
  is a real answer to "procedurally generate types from a Rust type."
- `ledgrrr`'s **`mdbook-rhai-mermaid`** ships a real `NodeVisualState` vocabulary
  (Idle/Active/Success/Warning/Error/Review) that maps naturally onto card severities.
- `promptexecution/ufo-types` (MIT, confirmed public) still stands as the ontology/constraint
  foundation from PRD-0008 — `UfoStereotype`/`Satisfies<C>` for the ontology layer,
  `Decision`/`Alternative`/`Risk`/`ExecutiveDecision`/`OodaStateMachine` for the strategic-objective
  ranking ask. `scryer-prolog` is the concrete engine `Satisfies<C>` should likely be built on for
  real proof-search, not `chalk`/`datafrog`.

## Goals

1. Structure cim-gridy's architecture explicitly as an INCOSE V, so every design decision has a
   named, paired verification step, not an implicit "we'll test it eventually."
2. Ground every technology choice in a real, currently-maintained, license-checked open-source
   project — blessed.rs where it has an opinion, direct crates.io/GitHub verification where it
   doesn't — never inventing a crate or assuming staleness/currency without checking.
3. Resolve the SysML v2 tooling question with the newly-available native-Rust parser options
   rather than carrying forward Lab 6's older JVM-blocked/hand-rolled-stand-in framing unexamined.
4. Sequence everything so each phase has a real, checkable prerequisite satisfied before it starts
   — same discipline as PRD-0008, now shaped explicitly by the V-model's paired-verification rule.

## Non-goals

- No code written, no tools installed, no rename executed in this PRD.
- Not committing to OperatorFabric vs. a Bevy-native card UI — a genuine open decision (Phase 0e).
- Not fully resolving RDF/OWL/SHACL vs. `ufo-types`-only — carried open from PRD-0008.
- Not evaluating `georust` yet — named as a real gap, not filled here.
- Not deciding `sysml-v2-parser` vs. `syster-base` as the primary parser — both get spiked in
  Phase 0b before a choice is made.

## Architecture (V-model left side, each level paired with its right-side check)

1. **Concept of Operations** — "operate a simulated grid via missions generated in calendar steps,
   featuring real LF Energy tools, Australia first" ↔ **Operation & Maintenance validation**: does
   a played mission still read as "the grid-operator game" originally described?
2. **System requirements** — derived from the growing stakeholder-objective list ↔ **System
   V&V**: does the Phase-1 minimal mission satisfy a real, named stakeholder objective, scored via
   `ufo-types`/`scryer-prolog`, not just "it ran"?
3. **Architecture** — a Bevy app (`Plugin`/`Resource`/`System`, `bevy_rapier`-pattern) wrapping
   Grid2Op's chronics/episode loop, which wraps existing pandapower/PowSyBl case data; a real
   native-Rust SysML v2 parser (`sysml-v2-parser` or `syster-base`) for the static type layer;
   `ufo-types` + `scryer-prolog` for the ontology/constraint layer; `ledgrrr`'s Rhai/Mermaid
   pipeline for the mission state machine ↔ **Subsystem integration & test**: does the full chain
   run end to end for one minimal mission (Phase 1)?
4. **Detailed design** — the crate table above, per-component ↔ **Unit/component test**: does each
   piece work in isolation first (Phase 0 spikes below)?

## Phasing (bottom of the V — implementation)

**Phase 0 (a-e) complete as of 2026-08-22** — all five spikes run for real (parallel sub-agents,
per this PRD's own "use sub-agents heavily" mandate), each with an honest, evidence-based verdict.
Full detail: `labs/08-cim-gridy-phase0-spikes/README.md` (synthesis) and each spike's own
subdirectory README.

- **Phase 0a (done):** Grid2Op spike against existing CSIRO case data (`data/snemSA.m`). **Real
  success, with real friction**: three independent bugs found and fixed by reading source, not
  docs — grid2op 1.12.5's published PyPI wheel is missing `typing_variables.py` (worked around with
  `--no-binary-package`), a pandapower 3.5.4 `to_json`/`from_json` round-trip bug for nets that
  already passed through `from_json_string` once (this repo's own `gridfit.load_case` does exactly
  that), and `PandaPowerBackend`'s dense-0..N-1-bus-index assumption (`snemSA.m`'s real IDs are
  non-sequential). One real episode ran end-to-end post-fix (503 buses, 698 lines, 186 loads, 57
  gens; `env.reset()`/`env.step(do_nothing)` both succeeded on the real converged power flow).
  Verdict: viable, but budget real engineering time — "wraps cleanly" is false as shipped.
  See `labs/08-cim-gridy-phase0-spikes/0a-grid2op/README.md`.
- **Phase 0b (done):** SysML v2 native-Rust parser spike. **Both `sysml-v2-parser` (63.9% of 36
  real `GfSE/SysML-v2-Models` fixtures) and `syster-base` (69.4%) parse cleanly, no crashes, real
  diagnostics on failures** (this repo's own Lab 6 `.sysml` output: 3/3 on both). Supersedes
  PRD-0006/0008's JVM-first framing entirely. **Recommendation: `sysml-v2-parser` as primary** —
  lighter dependency footprint (17 vs. 82+ packages), explicit strict/lenient API matching this
  repo's syntax-gate use case; `syster-base` not disqualified, better long-term bet if LSP/editor
  tooling is ever wanted. See `labs/08-cim-gridy-phase0-spikes/0b-sysml-v2-parser/README.md`.
- **Phase 0c (done):** `sensmetry/sysand` native Rust CLI spike. **Yes — works fully standalone,
  zero JVM/Maven/JNI anywhere** (`ldd` confirms only glibc/libgcc/libm linked). Real `init` →
  `include` → `build` pipeline produced a genuine spec-shaped KPAR (ZIP) archive from a real
  `.sysml` file (Lab 6's `grid_topology.sysml`); `include` does real lightweight syntax checking
  (rejects garbage input) but is not a semantic parser — pairs with Phase 0b's parser choice for
  that. Clears the exact `UnsatisfiedLinkError` dead end that blocked Lab 6's original toolchain.
  See `labs/08-cim-gridy-phase0-spikes/0c-sysand-cli/README.md`.
- **Phase 0d (done):** `ufo-types` + `scryer-prolog` integration-shape spike (build/link smoke test
  only, as scoped). **Both crates build, link, and run together with no dependency conflicts**
  (real `UfoStereotype`/`Satisfies<C>` example and a real Prolog transitive-closure query both
  produced correct output). Real caveat found: `scryer-prolog` panics on an internal UB-check
  inside its own `Heap::clear`/`dealloc`, **debug-profile builds only** — release builds
  unaffected, zero `ufo_types` involvement in the panic. Recommendation: proceed with this pairing
  for Phase 3, release builds (or `debug-assertions = false`) until upstream resolves it.
  See `labs/08-cim-gridy-phase0-spikes/0d-ufo-types-scryer-prolog/README.md`.
- **Phase 0e (done):** OperatorFabric real-tool spike, weighed against a Bevy-native card UI.
  **Real deployment footprint confirmed heavy**: light dev-mode is still 11 containers / ~1.9GB;
  a real bring-up attempt hit a precisely-diagnosed host policy blocker (short-name image
  resolution enforcement), fixed and confirmed, but a full `Running`+healthy stack would plausibly
  take 20-30+ minutes on this shared host. **Recommendation: build the card feed natively in
  Bevy** — `bevy_ui`'s flexbox layout, first-party scroll (`ScrollPosition`/`Overflow::scroll()`),
  and card styling (`BorderRadius`/`BackgroundColor`/`BoxShadow`) are all confirmed real and
  current via Bevy's own example suite; zero new dependency, since Bevy 0.19 is already this
  project's chosen engine. OperatorFabric's `Card` data model (severity/process/timestamp) kept as
  a design reference, not adopted as a runtime dependency.
  See `labs/08-cim-gridy-phase0-spikes/0e-operatorfabric-vs-bevy/README.md`.
- **Phase 1 (not started, depends on 0a-0e — all now satisfied):** one minimal end-to-end mission
  proving the full architecture chain above, now with real, evidence-grounded tool choices instead
  of proposed ones.
- **Phase 2:** connect Lab 6/PRD-0007's schema layer to Phase 1's dynamic state.
- **Phase 3:** the strategic-objective optimizer, built on `ufo-types`' DARE types +
  `scryer-prolog`.
- **Phase 4:** geographic positioning (real gap, `georust` not yet evaluated) + standardized
  iconography.
- **Phase 5:** the rename + narrative rewrite.
- **Phase 6:** global expansion beyond Australia.

## Housekeeping action worth doing alongside this PRD

`b00t learn rust`'s "Lowering Logic" doc's crate table is stale (still recommends `chalk`/
`datafrog` as live picks). Worth a `b00t learn rust --record` correction pointing at
`scryer-prolog` instead, sourced to this session's findings, once this PRD is committed — outside
this repo's own scope to execute directly, flagged for the user.

## Acceptance criteria for this PRD

- [x] Every crate/tool choice traces to a direct, sourced check this session (blessed.rs fetch,
      crates.io/GitHub/GitLab API checks, Maven Central metadata) — none invented or assumed
      current.
- [x] SysML v2 tooling re-investigated fresh rather than carrying forward Lab 6's 2026-08-18
      verdict unexamined — found materially changed (real native-Rust parsers now exist).
- [x] INCOSE V-model structure sourced accurately (reqi.io citing the INCOSE Handbook, Wikipedia,
      NASA SE Handbook) rather than paraphrased from general knowledge.
- [x] Bevy's external-simulation integration pattern grounded in a real precedent (`bevy_rapier`),
      not hypothesized.
- [x] Reviewed and approved by the user before any Phase 0 spike work begins (approved 2026-08-22 --
      "phase zero is completely approved"). Spikes 0a-0e proceed in the order listed below.

## Open questions

- ~~OperatorFabric vs. Bevy-native cards (Phase 0e).~~ **Resolved 2026-08-22**: build in Bevy — see
  Phasing above.
- ~~`sysml-v2-parser` vs. `syster-base` as the primary parser, once both are spiked (Phase 0b).~~
  **Resolved 2026-08-22**: `sysml-v2-parser` primary — see Phasing above.
- ~~Whether `sensmetry/sysand`'s Rust CLI alone is sufficient or the Maven-wrapped workflow is
  still needed for anything (Phase 0c).~~ **Resolved 2026-08-22**: native CLI alone is sufficient,
  Maven-wrapped path not needed for anything — see Phasing above.
- **New from Phase 0a**: does grid2op ship a fixed wheel (packaging the missing
  `typing_variables.py`) before Phase 1 pins a version? Not yet re-checked.
- **New from Phase 0d**: is `scryer-prolog`'s debug-profile `Heap::clear` panic already a known
  upstream issue, or worth filing? Not yet checked against their issue tracker.
- Everything PRD-0008 already left open — CIM16-vs-CIM100, Semantic Energy Framework as a possible
  ontology anchor, Dynawo vs. DPsim for dynamics-timescale missions — still open, not revisited
  this session.
