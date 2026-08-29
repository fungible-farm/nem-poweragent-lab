# Requirements: `systhread` — a b00t-installable MBSE vendor capability

**Status:** Draft v0.5 — end-state spec, not a sprint plan. Amends v0.1 after reconciling with this
repo's own current state (see §7, Amendments from v0.1); amended again after Phase 1 shipped (see
§8, Amendments from Phase 1); amended again to record a long-term, explicitly-unphased direction
(see §9); amended again to point FR7 at a dedicated design doc for the Bevy-native 2D/3D explorer
(`2026-08-26-systhread-3d-explorer-design.md`), which itself carries its own v1/v2 scope split.

**Relationship to prior work:** generalizes Lab 6 (`nem-poweragent-lab`, PRD-0006) from a two-track
evaluation lab into a standalone, reusable capability. Lab 6 stays as-is; this is what it becomes if
promoted out of the evaluation repo.

## 1. Vision (one line)

A project's SysML v2 model lives in the project's own git history, at the project's own commit
granularity — one Rust binary, no database, no second language toolchain for new logic, callable by
`b00t`, `just`, CI, or `ledgrrr`, that keeps that model honest against the actual codebase shape.

## 2. Design principles

- **RFC 2119 word precision throughout this doc and the tool's own error messages.**
- **Don't reinvent the wheel; don't invent the universe to bake an apple pie.** SysML v2 is the
  notation — not negotiable, not replaced. No new metamodeling platform, no new visual DSL, no new
  UFO taxonomy (see §2's "UFO taxonomy" principle below). Extend or fork permissively-licensed
  components; do not rebuild a parser, a renderer, a graph engine, or an ontology enum that already
  exists MIT/BSD/Apache-licensed in this org.
- **Git is the database.** No PostgreSQL, no sync server, no proxy — this is the one architectural
  bet three independent projects (this repo's own Lab 6, SysGit.io, OpenKer Modeler) have now
  converged on separately. Treat that convergence as validation, not coincidence.
- **UFO taxonomy: reuse, don't reinvent.** `promptexecution/ufo-types` (MIT, git dependency —
  `github.com/promptexecution/ufo-types`, already pinned by `rust/mission-engine` in this repo) was
  reconciled into the single source of truth for `UfoStereotype` across `ledgrrr` and `cim-gridy` on
  2026-08-24 (`docs/prd/0009-cim-gridy-incose-v-plan.md`). `systhread` depends on it directly rather
  than defining its own UFO category enum. New `UfoStereotype` variants MAY be added only when a
  genuine gap exists and the addition is ontologically well-composed (correctly placed in the
  existing endurant/perdurant lattice) — not for convenience. Energy/standards-specific ontology
  content (CIM/IEC 61970/61968/CGMES, IETF protocol ontologies, alignment with the
  [OpenEnergyPlatform ontology](https://github.com/openenergyplatform/ontology)) MUST live in its own
  separate, BFO-aligned domain crate — never folded into generic `ufo-types` or into systhread's core.
  This connects to, rather than duplicates, PRD-0007's already-scoped CIM class-URI mapping work.
- **Rust-first, polyglot-sensible.** New capability logic MUST be written in Rust, matching
  `forge`/SPARTAN/`_b00t_`'s existing implementation-language discipline. Python remains acceptable
  only in narrow, explicitly justified spots — LinkML schema-tooling glue (carried over from Lab 6's
  own scoping) is the standing example — and where Python needs systhread's functionality, it calls
  into the Rust library (e.g. via PyO3/maturin bindings), never the reverse for core logic. Any such
  exception MUST be named explicitly, not silently assumed. No Node/TypeScript runtime dependency in
  the core binary — both real prior-art candidates (OpenKer, MM-AR) are Node/TS; that is a reason to
  hold them at MCP arm's length, not a reason to adopt their language. The one sanctioned JS output is
  FR7's static explorer artifact (an *output* layer, not the tool's own implementation language).
- **Deterministic, CI-diffable output.** Every generated artifact (`.sysml`, SVG, iso-IR JSON) MUST
  be byte-identical across runs on unchanged input — carried over from Lab 6's own kill check, now a
  hard requirement rather than a nice-to-have.
- **Kill-gate phased delivery.** No phase ships until its own acceptance criteria pass; a later phase
  never patches over an earlier phase's unresolved finding.

## 3. Functional Requirements

### FR1 — b00t vendor capability packaging
The capability MUST ship as a `b00t stack` definition, installable via `b00t stack install` — the
actual installable-capability mechanism in b00t today (docker-compose/CRD generation,
activate/deactivate), not `b00t learn` (b00t's docs/RAG subsystem). `b00t learn systhread` MUST still
surface the rendered README for discovery, per `_b00t_` convention (a rendered doc, not a raw
template read directly) — but discovery and install are two different b00t subsystems and FR1 targets
both correctly. The capability is a self-contained Rust crate/binary set (§6). MUST be installable
and runnable with zero dependency on the `nem-poweragent-lab` repo or any other specific project.

### FR2 — dual deployment mode, one binary family
The same core logic MUST run in two transport modes with no logic fork between them:
- **Local**: CLI invocation (`systhread check`, `systhread render`, `systhread explore`), stdio MCP
  transport for agent tool-calls — `systhread-cli`.
- **Remote**: containerized service, HTTP/SSE MCP transport — `systhread-service`.

Both are thin wrappers over the shared `systhread-core` crate (§6); only transport selection differs,
matching the existing `forge`/promptexecution MCP server's multi-transport pattern. Remote mode is
Phase 5, contingent (§6).

### FR3 — project-level `.sysml` as the schema of record
Each adopting project MUST hold exactly one canonical `.sysml` model root (or a defined package tree
under one root) committed to that project's own git repository — not a separate model repo, not a
database. `systhread` operates against the project's working tree and its git history directly.

### FR4 — justfile / CI-ready tooling
MUST ship as a `just` module (not copy-pasted recipe text) importable into any adopting project's own
`Justfile`, exposing thin wrappers — no logic in the `just` recipes themselves, all logic lives in
`systhread-cli`:
- `just sysml-check` — syntax + (once available) semantic validation, exit-code gated.
- `just sysml-render` — regenerate all image artifacts from current model state.
- `just sysml-explore` — build the embeddable interactive explorer artifact (FR7).
- `just sysml-drift` — per-commit drift check (FR10).

All four MUST run in stock GitHub Actions/GitLab CI runners with no external service dependency,
per the Git-is-the-database principle in §2.

### FR5 — image artifact generation
MUST generate deterministic diagram artifacts (SVG at minimum) from the current `.sysml` model,
reusing Lab 6's iso-IR translation approach (Part/containment → isometric layout) as the baseline
renderer, re-derived in Rust (§6, Phase 0). SHOULD support standard SysML v2 diagram kinds (BDD/IBD)
as a later phase, not a blocking requirement for v1.

### FR6 — ledgrrr-callable artifact contract
`systhread render` output MUST be consumable by `ledgrrr` as an embeddable image/page source with no
custom glue code per project: a documented output directory plus a small JSON manifest (artifact
paths, kind, content hash) is the integration surface — `ledgrrr` reads the manifest; it has no
knowledge of systhread's internals, and systhread has no bespoke per-consumer API.

### FR7 — embeddable interactive model explorer
MUST produce a self-contained (no server dependency) HTML/JS artifact that lets a reader of a
generated document click through the model graph — the *capability* MM-AR demonstrates (3D/graph
exploration of a metamodel instance), deliberately without MM-AR's *infrastructure* (no Postgres, no
Express API server, no Aurelia2/WebXR client stack). Built from `systhread-core`'s graph model as a
`systhread-explorer` output artifact, not a Rust crate. Static-embeddable-widget scope only; live
collaborative editing is explicitly out of scope (§5).

**Sourcing amended 2026-08-26:** the Bevy-native path in
[`2026-08-26-systhread-3d-explorer-design.md`](2026-08-26-systhread-3d-explorer-design.md)
supersedes §5's Cytoscape.js/d3-only sourcing pick (that pick was to avoid forking MM-AR's AGPL
code, not a rejection of 3D — FR7's own text above already named 3D exploration as the target
capability). That document also resolves this entry's "output artifact, not a Rust crate" wording
against §7 amendment 6's crate-layout list — see its §5.

### FR8 — UFO/KerML base-type representation via `ufo-types`
Every domain class modeled through systhread MUST declare which `ufo_types::UfoStereotype` variant it
specializes (Kind/SubKind/Role/Relator/Mode plus the endurant/perdurant substereotypes reconciled
2026-08-24) — no separate systhread-owned taxonomy. This is what makes "model the promptexecution
UFO types" a schema requirement, not a one-off diagram. New variants follow the ontological-necessity
gate in §2; energy/standards-domain stereotyping lives in a separate domain crate, per §2.

### FR9 — Rust trait lowering, built on `ufo-types`/`sysml-derive`
Rust → SysML v2 generation is systhread's owned capability, but the mechanism extends existing prior
art rather than competing with it:

```rust
trait ToSysml {
    fn sysml_kind() -> &'static str;      // "part def" | "port def" | "item def" | "action def"
    fn sysml_name() -> &'static str;
    fn sysml_ufo_stereotype() -> ufo_types::UfoStereotype; // FR8 linkage, no new enum
    fn to_sysml_source() -> String;
}
```

Before this trait is implemented, Phase 2 MUST start with a dedicated look at `ufo-types`' existing
`sysml.rs` module and `ledgrrr`'s `sysml-derive` crate (currently dev-dependency-only, per
PRD-0009's MECE table) and choose one of: (a) extend `sysml-derive` in place, with its owner's
agreement, or (b) wrap/re-export it from systhread. **This choice is an open item, not decided in
this spec** — flagged for whoever owns `ledgrrr`/`ufo-types`, same posture as PRD-0009's own
unresolved "should `ufo-types` own all SysML capability" question. String-emit target,
`sysml-v2-parser` round-trip validation before acceptance (already the decision made for Lab 6, now
formalized as this tool's actual macro). This is the mechanism for representing `forge`/
promptexecution's own types:

| promptexecution concept | UfoStereotype | SysML lowering |
|---|---|---|
| a crate/module (e.g. `mistral.rs` binding) | (structural — nearest existing Kind/SubKind) | `part def` |
| an inference call, a DSL rule firing | (perdurant/Process or Event, per existing substereotypes) | `action def` |
| a `.tomllm` document, an embedding vector | (Mode or Relator, whichever fits existing semantics) | `item def` |
| an MCP tool registration, a sink route | (Relator) | `interface def`/`connection def` |

The exact variant mapping above MUST be confirmed against `ufo-types`' actual current enum (not
assumed) when Phase 2 starts — the table states intent, not a verified mapping.

**Update (2026-08-29, b00t SysML v2 spine consolidation epic, `elasticdotventures/_b00t_#1177`):**
the "open item" above is now resolved as choice (b) — `sysml-derive` was extracted out of `ledgrrr`
into its own standalone crate (`PromptExecution/sysml-derive`, `ledgrrr#210`/#211) specifically so
`systhread-core` and other consumers can depend on the derive directly, without either forking it or
pulling in the whole `ledgrrr` workspace. Separately, this crate's own `iso_ir.rs` (the generic
`Node`/`Edge` graph vocabulary, not the lab-specific extraction/layout/render logic that stays here)
was promoted into `ufo-types` (`PromptExecution/ufo-types#4`/#5) as the "non-visualization sysml-v2
type interface" home the user named directly. `systhread-core` now re-exports `Node`/`Edge` from
`ufo-types::iso_ir` (see `src/iso_ir.rs`) instead of defining them locally — verified behavior-
preserving via `cargo test` (all fixture-reproduction tests, including the three byte-identical
`iso_ir_full_test`/`render_test`/`sysml_gen_test` suites, pass unchanged). The `ToSysml` trait itself
and its variant-mapping table above remain open Phase 2 work; only the crate-ownership question is
now settled.

### FR10 — per-commit modelled-shape tracking
This is the requirement with no existing prior art among the tools evaluated so far — the
differentiator, not a reuse target:

- An extraction step MUST infer structural facts from the actual codebase at a given commit (crate
  manifests, module boundaries, MCP tool registrations — reusing FR9's `ToSysml` output as the
  extraction mechanism where types already derive it).
- `just sysml-drift` MUST diff extracted structure against the committed `.sysml` model and report
  additions/removals/renames — modeled-but-absent and present-but-unmodeled, the same drift-detection
  shape Lab 6 already applied to SBOM, now generalized to the whole project.
- MUST start as a non-blocking CI warning (kill-gate discipline: prove the signal is trustworthy
  before making it a merge gate) with a documented path to promotion once false-positive rate is
  acceptable.
- Each commit's drift result SHOULD be queryable (`systhread drift --at <sha>`), giving "the modelled
  shape of the project over time" as a real, git-log-walkable history, not just a point-in-time check.

## 4. Non-goals

- **Not a new modeling notation or metamodeling platform.** SysML v2 only; do not build MM-AR's
  meta2-model equivalent.
- **Not a database-backed model server.** No PostgreSQL, no sync service — violates §2's Git-is-the-
  database principle outright.
- **Not live collaborative model editing.** The explorer (FR7) is read-only; editing happens in the
  `.sysml` text file, in the project's normal git workflow.
- **Not a semantic/type-checking engine of its own.** Continue treating `mercurio-sysml` (or the
  eventual fixed Pilot Implementation path) as an external validation oracle, never as a dependency
  this tool's core logic is written against — same boundary Lab 6 already drew.
- **Not committing to full CIM/CGMES RDF-OWL support in v1.** FR8's UFO base types are notation-
  agnostic; CIM-specific class mapping (the separately-scoped `cim-gridy`/PRD-0007 work) is a
  consumer of this tool, connecting through the separate energy-domain crate named in §2 — not
  something this tool implements itself.
- **Not a second UFO taxonomy.** systhread does not define its own UFO category enum; see §2.

## 5. Build / fork / extend — sourcing decision per component

| Component need | Candidate | License | Verdict |
|---|---|---|---|
| SysML v2 syntax parse | `sysml-v2-parser` (`elan8/sysml-v2-parser`, crates.io v0.54.0) | **MIT — confirmed** (checked cached crate manifest directly) | Use. Already spiked in this repo (`labs/08-cim-gridy-phase0-spikes/0b-sysml-v2-parser/`) with real numbers against 36 real GfSE fixtures + Lab 6's own generated output: 26/39 pass. Not fully spec-conformant — expect real parse failures on some constructs; `syster-base` scored 28/39 on the same fixtures but pulls in an 82-package rust-analyzer-style stack (logos/rowan/salsa/tokio/rayon/wasm-bindgen) versus `sysml-v2-parser`'s 17-package `nom`-based footprint. Default to `sysml-v2-parser` for the smaller footprint; re-evaluate `syster-base` only if its extra ~2/39 conformance becomes load-bearing. |
| UFO/KerML taxonomy | `promptexecution/ufo-types` (git dep, MIT) | **MIT — confirmed**, already pinned by `rust/mission-engine` | Use directly, per §2. Do not re-implement. |
| Rust → SysML derive | `ledgrrr`'s `sysml-derive` | unverified — needs the Phase 2 "dedicated look" named in FR9 | Extend or wrap, per FR9's open item — do not build a competing derive macro without first checking this. |
| Semantic validation oracle | `mercurio-kerml`/`mercurio-sysml` | **unverified — confirm before depending** | Arm's-length oracle only regardless of license outcome, per non-goals. Still an open action item — no artifact found locally to check against. |
| Isometric diagram render | `isoflow`/`FossFLOW` (successor), `DaanV2/isometric-diagrams` | MIT | Reuse wholesale for the *rendering math reference*; Lab 6's own pure-Python writer (`render_diagram.py`, Cassowary layout via `kiwisolver`) is the actual logic to re-derive in Rust for Phase 0 — this is a solved problem, port it, don't re-architect it. |
| MCP graph traversal / impact analysis | OpenKer Modeler | **GPL-3.0** | **Do not fork or statically depend.** Not permissive. If used at all, arm's-length MCP sidecar process only (separate binary, protocol boundary, no linking) — flag explicitly to whoever owns license governance before any adoption, even at arm's length. |
| Interactive 3D/graph explorer concept | MM-AR | **AGPL-3.0** | **Do not fork.** Network-use clause is the sharpest possible copyleft trigger for a tool whose entire point is a running network service. Take the *concept* (FR7), build the static-embeddable version from scratch or from an MIT-licensed graph-viz library (e.g. `d3`, `cytoscape.js`, output layer only). |
| Per-commit drift tracking | none found | n/a | Build (FR10) — confirmed gap, the actual novel contribution of this tool. |

**Remaining open action item:** confirm `mercurio-sysml`'s actual license before treating it as even
an arm's-length oracle dependency — `sysml-v2-parser` and `ufo-types` are now both confirmed MIT,
closing the other two cells that were open in v0.1.

## 6. Phasing

- **Phase 0 — Core Rust crate, fixture-parity acceptance.** Not "extraction" (Lab 6's
  generator/validator/translator/renderer are 100% Python — there is no Rust code to extract).
  Build `systhread-core` from scratch in Rust: parse (`sysml-v2-parser`), validate, iso-IR translate,
  render (SVG, porting Lab 6's Cassowary/`kiwisolver` layout logic to a Rust constraint-solver
  equivalent), depending on `ufo-types` for stereotyping. Lab 6's committed Python outputs
  (`fixtures/expected_*.sysml`, rendered SVGs) are the **acceptance oracle** — Phase 0 is done when
  `systhread-core` reproduces them byte-identical — not code that keeps running. Lab 6 itself stays
  untouched in `nem-poweragent-lab`. This is real engineering effort, not a short decoupling step.
- **Phase 1 — FR1–FR6 (packaging, dual-mode local transport, justfile/CI, ledgrrr contract).** Ship
  something `b00t stack install`-able and `just`-callable in any project, still Part/containment-only
  (matches Lab 6's own non-goal carryover), still no Port/Flow syntax. `systhread-cli` only;
  `systhread-service` (remote transport) is Phase 5.
- **Phase 2 — FR8–FR9 (ufo-types integration, `ToSysml` trait built on `sysml-derive`).** Starts with
  the FR9-mandated "dedicated look" at `ufo-types`' `sysml.rs` and `ledgrrr`'s `sysml-derive` before
  writing any new derive code. Dogfood on `forge`'s own crates first, since that's the richest
  available Rust codebase to validate the trait against.
- **Phase 3 — FR7 (interactive explorer).** Build the static embeddable widget once there's a real
  model (from Phase 2's dogfooding) worth exploring — content before infrastructure, per §2.
- **Phase 4 — FR10 (per-commit drift tracking), non-blocking mode.** The differentiator, deliberately
  last: needs Phases 1–3's extraction/generation machinery to already be trustworthy, or the drift
  signal itself can't be trusted.
- **Phase 5 (contingent) — `systhread-service` (FR2's remote half), promotion of drift-check to
  blocking CI gate.** Only after Phase 4's false-positive rate is measured acceptable.

**Implementation planning boundary:** this document is the full end-state design. The next
implementation plan (via the `writing-plans` skill) is scoped to **Phase 0 only** — a 5-phase,
multi-quarter arc is not a single implementation plan. Phases 1–5 each get their own plan when their
turn comes, informed by what Phase 0 actually learns.

## 7. Amendments from v0.1 (summary)

Reconciled against this repo's actual current state during brainstorming on 2026-08-25:

1. FR8/FR9 no longer define a new UFO taxonomy or a competing derive macro — both build on
   `promptexecution/ufo-types` and `ledgrrr`'s `sysml-derive`, reconciled just one day earlier
   (2026-08-24, `docs/prd/0009-cim-gridy-incose-v-plan.md`). `sysml-derive`'s exact extension path is
   an explicit open item for Phase 2, not decided here.
2. Added the domain-ontology-separation rule (§2): energy/standards ontology content (CIM, IETF,
   OpenEnergyPlatform) lives in its own separate BFO-aligned crate, connecting to but not duplicating
   PRD-0007's CIM class-URI work.
3. Phase 0 re-scoped from "extraction" to a from-scratch Rust port with Lab 6's Python output as the
   acceptance oracle — Lab 6 has no Rust code to extract, and the "(short)" label was dropped as
   inaccurate.
4. FR1 retargeted from `b00t learn` (docs/RAG subsystem) to `b00t stack install` (the actual
   installable-capability subsystem); `b00t learn systhread` remains the discovery/README surface.
5. §5's two open license cells are now one: `sysml-v2-parser` and `ufo-types` are both confirmed MIT
   (checked directly against cached/pinned manifests in this repo); `mercurio-sysml` remains the one
   unverified item.
6. Crate layout made explicit (§3 FR2, §6): `systhread-core` / `systhread-cli` / `systhread-service`
   / `systhread-explorer`, chosen over a single feature-flagged binary for isolation and independent
   testability of the pure logic core.

## 8. Amendments from Phase 1 (2026-08-26)

Phase 1 (`systhread-cli`, PR [nem-poweragent-lab#36](https://github.com/fungible-farm/nem-poweragent-lab/pull/36))
shipped FR1–FR6. Its final whole-branch review surfaced one process gap and one real bug worth
making binding for every phase from here on, not just noting once and forgetting:

1. **Any task that adds an RPC/protocol surface MUST ship a protocol-level test as part of its own
   completion criteria — not something a later whole-branch review has to catch.** Phase 1's MCP
   stdio server printed a bare `PASS`/`FAIL` line to stdout from `commands::check::run` — a real
   bug, since stdout **is** the JSON-RPC transport in `--stdio` mode, corrupting every
   `systhread_check` tool call for any spec-compliant MCP client. It survived twelve independent
   per-task reviews because every existing MCP test checked `get_info()` or that the process stayed
   alive — none actually invoked a tool over the wire. A test that spawns the binary, speaks the
   real protocol, and asserts every line of stdout parses is the only thing that would have caught
   it, and the only thing that reliably catches this class of bug going forward. Binding for Phase 5
   (FR2's HTTP/SSE remote transport) especially: a bare-diff review will not see a framing
   corruption bug; only a protocol-level test or a whole-diff review run with real command
   execution will.
2. **FR9's "dedicated look" at `sysml-derive` (§6, Phase 2) found real, current facts worth
   recording before Phase 2 planning starts, rather than re-deriving them:** `ledgrrr`'s
   `crates/sysml-derive` is `#[derive(SysmlBlock)]`, a proc-macro mapping Rust struct fields
   (`Vec<T>`/`Option<T>`/numeric primitives/`chrono::DateTime`/opaque domain types) to SysML v2
   `part def` text and `ScalarValues` scalar types — it does **not** touch `UfoStereotype` at all
   today, so FR8's stereotype-aware mapping is genuinely new ground, not an extension of existing
   logic. It's real-grammar-validated (`ufo_types::sysml::validate_sysml_v2`), not just visually
   inspected. Both `sysml-derive` and `holon-viz` already pin `ufo-types` at PR #3's unmerged
   branch tip as a dev-dependency workaround — that PR merging is a shared prerequisite for Phase 2
   regardless of which extension path is chosen. Decision-request filed:
   [ledgrrr#202](https://github.com/PromptExecution/ledgrrr/issues/202).
3. **FR6's manifest.json schema was designed unilaterally in Phase 1 and has not been reviewed by
   `ledgrrr`.** It currently supports one track per output directory (no `track` field); review
   requested before Phase 2 planning locks in a shape ledgrrr writes a real consumer against:
   [nem-poweragent-lab#39](https://github.com/fungible-farm/nem-poweragent-lab/issues/39).
4. The SVG label-escaping gap noted as a Phase 0→1 entry condition (Lab 6's `render_diagram.py`
   and its Rust port both interpolate project-supplied instance names into SVG `<text>` content
   unescaped) was fixed in
   [nem-poweragent-lab#38](https://github.com/fungible-farm/nem-poweragent-lab/pull/38), closing
   [nem-poweragent-lab#37](https://github.com/fungible-farm/nem-poweragent-lab/issues/37). Not an
   open item for Phase 2 anymore — recorded here only so a future reader doesn't have to
   re-establish that it was resolved.

## 9. Long-term direction: whole-crate structural extraction (not phased, no target date)

**Deliberately outside §6's Phase 0–5 sequence.** This is a stated goal, not a commitment — it
does not get its own phase number, is not blocking anything above, and MUST NOT be started before
Phase 2–4 (FR8–FR10) are real and dogfooded. Recorded now, while the idea is fresh, so a future
session doesn't have to reconstruct the reasoning from scratch — the opposite failure mode from
inventing false urgency.

**The idea:** FR9's `ToSysml` trait (built on `sysml-derive`) is a procedural macro — it sees only
the syntax of the one struct it's attached to, at macro-expansion time, with no type information
and no view of the rest of the crate. That's the right starting mechanism (stable Rust, already
real, already validated — see §8 item 2) but it has a ceiling: every type that wants SysML
representation needs its own `#[derive(...)]` annotation, and FR10's per-commit drift tracking
(§3 FR10) inherits that ceiling, since it extracts structure by reusing FR9's output.

The long-term alternative is a `rustc_driver`-based tool: a custom `rustc_driver::Callbacks`
implementation that hooks rustc's own frontend and walks the **type-checked HIR/MIR across the
whole crate graph**, with no per-item annotation required. This is not a novel or speculative
architecture — it is the same shape `clippy`, `rust-analyzer`, and `miri` already use, and
concretely, **Kani's own compiler** (`kani-compiler`) already does exactly this for a different
target: a custom `rustc_driver` + `Callbacks` that lowers MIR to GOTO-C for the CBMC model checker
instead of lowering it to machine code. Retargeting that same architecture to lower MIR to SysML
v2 text instead of GOTO-C is the concrete long-term goal — real precedent, not an invented one.

**What it would buy, beyond FR9/FR10 as currently scoped:** automatic whole-crate structural
extraction with real type information (not syntax-only), removing the requirement that every type
needing SysML representation carry its own derive annotation — a plausible eventual replacement
for FR10's "infer structural facts from the actual codebase" extraction step, not an addition
alongside it.

**Why this is explicitly not near-term, and not given a phase number:**
- `rustc_private` (the API surface this requires) carries no stability guarantee and is
  nightly-only forever — every rustc release is a potential breaking change, requiring ongoing,
  dedicated maintenance this project has not budgeted for.
- It is a multi-month compiler-engineering undertaking, not a task-sized or even plan-sized unit
  of work — nothing this spec's existing phasing assumes about task granularity applies to it.
- Starting it before FR9/FR10 (Phase 2–4) are real and in use would mean designing the
  whole-crate extractor's output shape against a hypothetical consumer instead of a working one —
  exactly the "invent the universe to bake an apple pie" failure §2 already warns against.

**Revisit trigger, not a date:** reconsider this once Phase 4 (FR10) has shipped and the
per-type-annotation cost of FR9's proc-macro approach is a real, felt pain point in practice —
not on a calendar schedule.
