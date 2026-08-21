# 0008 — cim-gridy Phase 0: mission/calendar-step engine prerequisites

- **Status:** proposed
- **Depends on:** 0006 (Lab 6 SysML v2 digital-thread MVP), 0007 (Lab 6 Phase 4a CIM class-URI
  traceability) — both become the static grid-model type layer this PRD's dynamic mission layer
  sits on top of, not something rebuilt here
- **Touches:** this PRD file only, plus `docs/prd/README.md`'s index row — no code, no tool
  installs, no rename in this pass

## Problem

The stated long-term direction: rename this repo to **cim-gridy**, rewrite its narrative as an
interactive grid-operator "video game" (a SimCity-style isometric signature, an Oregon-Trail-style
card mechanic, missions generated in calendar steps), model it with a unified ontology
(RDF/OWL/SHACL) driving constraint optimizers that rank candidate actions against a growing list of
stakeholder-defined strategic objectives, with standardized simulation iconography and real
geographic positions, starting with Australia and expanding globally.

That is too large to plan or build in one pass. Asked which piece to tackle first, the answer was
explicit: **focus on prerequisite requirements, focus on planning the steps** — not the rename, not
a code spike, not a full vision document. This PRD is that planning document: a real-tool-grounded
inventory of prerequisites and a phased sequence, with zero code, installs, or renaming attempted
here.

## What was checked this session, not assumed

**Real LF Energy project landscape, fetched live from lfenergy.org/our-projects/ (39 named
projects), not guessed.** Two are near-perfect, real fits for the core mission/calendar-step ask:

- **[Grid2Op](https://github.com/Grid2op/grid2op)** — MPL-2.0, an LF Energy member project, a
  mature MDP-style `Environment`/`Agent`/`Action`/`Observation`/**chronics** framework for
  sequential grid-operation decision-making. Confirmed directly from its own repo: the **default
  backend is pandapower** — this repo's own golden-path power-flow engine (Labs 1-5) — and a
  **PowSyBl backend is also in active development**, the exact second engine this repo already
  integrates and cross-validates against pandapower (PRD-0007,
  `docs/POWERFLOW_ENGINE_SHOOTOUT.md`). Grid2Op's "chronics" — the time-series scenario data
  driving one episode — is structurally the same concept as "missions generated in calendar
  steps." This is not a tool to evaluate from a cold start; it's built to consume exactly the kind
  of case data (`data/snemSA.m`, `data/snem1803.m`) this repo already has loaded and solved.
- **[OperatorFabric](https://github.com/opfab/operatorfabric-core)** — MPL-2.0, an LF Energy
  project, a real production operator-console platform (Java/Spring Boot/Angular, Docker-packaged).
  Confirmed directly: its own native UI concept is **"cards" sorted in a feed by severity, date,
  and process** — a near-exact real-world match for "Oregon-Trail type card," not a metaphor that
  needs inventing from scratch.
- Secondary real finds from the same fetch, not pursued in this PRD but worth naming: **Dynawo**
  (RTE, sibling project to PowSyBl — an alternate C++/Modelica dynamics engine), **SOGNO**
  (cloud-native monitoring/control — DPsim's own GitHub org, `sogno-platform`, is this project;
  this repo already indirectly uses an LF Energy-family tool via Lab 5's DPsim without having
  named it as such), **Semantic Energy Framework (SEF)** ("open, ontology-driven interoperability
  framework... across the energy ecosystem" — worth checking against the ontology direction below
  before assuming a from-scratch RDF/OWL/SHACL build is the only path), **CoMPAS** (IEC 61850 model
  implementation — ties to Lab 5's existing VILLASnode/IEC 61850 investigation).

**`promptexecution/ufo-types` confirmed real, public, and read directly (`gh repo view`), not
assumed from `b00t learn`'s search snippets alone.** `b00t learn ufo,ontology` initially found no
cached knowledge and queued background research; the user then pointed directly at
`github.com/promptexecution/ufo-types`, confirmed public. Fetched and read in full: **MIT
licensed**, extracted with git history preserved from `elasticdotventures/_b00t_`
(`crates/ufo-types`), already consumed by `ledger-core`/`ledgrrr` — **the same codebase Lab 6's
Cassowary layout solver already cites as its own reference implementation** (`translate_iso_ir.py`
Design notes §5) — and by `critter-keeper` in `app4dog`. It is a real, working foundation for
exactly what "unified common ontology... constraint optimizers... graded ranking outcome...
strategic organizational objectives" asks for, not a system to design from first principles:

- `UfoStereotype` (Guizzardi's Unified Foundational Ontology stereotypes — Kind/SubKind/Role/etc.)
  + the `Satisfies<C>` trait (deterministic, audit-ready constraint evaluation) — the
  ontology/constraint layer itself.
- `Task`/`Attempt`/`ActionRecord`/`Episode` (generic capability/OODA types) — `Episode` is also
  Grid2Op's own term for one calendar-step run; a real conceptual seam between the two projects.
- `Decision`/`Alternative`/`Risk`/`ExecutiveDecision`/`OodaStateMachine` (the "DARE" proposal
  types) — map directly onto "explore the opportunity space and graded ranking outcome for meeting
  an ever-increasing list of strategic organizational objectives."

**Geographic positioning is a confirmed real gap, checked directly against this repo's own code,
not assumed.** `labs/01-simple-loadflow-fit/run.py`'s own docstring states plainly: "`net` carries
no real geographic coordinates (`snemSA.m` has none)." CSIRO's Synthetic-NEM case data — this
repo's only grid dataset today — has no lat/lon. A geo-positioned mission map needs either a real
geocoded dataset (swapped in or layered on top) or a documented synthetic stand-in; neither is
identified yet.

**Lab 6 (PRD-0006) and PRD-0007 already give this repo a real, working static-schema pipeline** —
LinkML instance data → `.sysml` text → a syntax gate → an isometric SVG diagram, now gaining real
CIM class-URI annotations. This is the natural home for the *static* grid-model type layer a
mission operates on; nothing here needs to be rebuilt, only connected to the *dynamic* layer this
PRD scopes.

## Architecture sketch (for later phases — documented here, not built)

```
Grid2Op (dynamic episode/chronics loop)
    -- wraps --> existing pandapower/PowSyBl case data (data/snemSA.m, data/snem1803.m)

OperatorFabric, or a named honestly-evaluated stand-in (card-feed operator console UI)
    -- surfaces --> each episode's events as real "cards"

ufo-types, via a to-be-decided Rust/Python integration shape
    -- scores --> candidate actions (Decision/Alternative/Risk) against stakeholder objectives
    -- grounds --> every domain type in a real UFO stereotype (Satisfies<C>)

Lab 6 / PRD-0007's SysML + LinkML + CIM pipeline
    -- describes --> the static grid-model types every layer above operates on
```

## Prerequisites identified — none satisfied yet

1. **Real-tool evaluation: does Grid2Op wrap this repo's own case data cleanly** via its
   pandapower or in-progress PowSyBl backend? What's the minimal action-space/chronics
   configuration for a first episode? Not yet attempted.
2. **Real-tool evaluation: does OperatorFabric run as a real service in this environment**
   (Java/Spring/Angular/Docker)? This repo has precedent both ways — VILLASnode, llamacpp, and
   powermcp pods all succeeded (`kube/README.md`); the SysML v2 Pilot Implementation container
   attempt hit a genuine, precisely root-caused dead end (PRD-0006 Design notes §1). Must be
   attempted with the same honesty, not assumed to work or assumed to fail.
3. **Undecided: how `ufo-types` enters this repo's toolchain** — a direct Cargo dependency in a new
   Rust crate (matching the existing oxidation-roadmap precedent, `rust/phase-model`, per
   `docs/PSCADOSSE.md`), PyO3 bindings consumed from Python, or a lighter Python-only
   re-implementation of just the stereotype/constraint concepts actually needed. Not decided here.
4. **No geocoded data source identified** for "geographic positions" — real dataset vs. documented
   synthetic stand-in, not yet chosen.
5. **The rename itself is mechanical but hard to reverse** — it touches the GitHub remote and every
   existing PR/issue link. Should be sequenced deliberately once the technical spikes below have
   de-risked the concept, not done incidentally alongside a code spike.

## Goals

1. Establish, with real evidence rather than assumption, whether Grid2Op and OperatorFabric are
   viable foundations for the mission/calendar-step/card mechanic — before any narrative or rename
   work depends on them.
2. Decide how `ufo-types` — a real, already-built ontology/constraint foundation in the user's own
   ecosystem — integrates with this repo's Python-centric toolchain.
3. Sequence every remaining piece (schema-layer connection, strategic-objective optimizer,
   iconography, geography, rename, global expansion) so each phase has a real, checkable
   prerequisite satisfied before it starts.

## Non-goals

- No code written, no tools installed, no rename executed in this PRD.
- Not deciding the Rust-vs-Python integration shape for `ufo-types` — that's Phase 0c's own
  question.
- Not attempting an RDF/OWL/SHACL implementation. `ufo-types` is Rust-native typed constraints, not
  RDF/OWL/SHACL directly — whether and how those map onto each other (or whether `ufo-types`
  supersedes the need for a separate RDF/OWL/SHACL layer entirely) is an open question for a later
  phase, not resolved here.
- Not evaluating Semantic Energy Framework (SEF) in depth — named as a candidate worth checking,
  not checked.

## Phasing

- **Phase 0a (not started):** Grid2Op real-tool spike against this repo's own CSIRO case data,
  timeboxed, written up honestly whichever way it lands — matching this repo's own established
  discipline (Lab 5's VILLASnode investigation, Lab 6's SysML Pilot Implementation attempt).
- **Phase 0b (not started):** OperatorFabric real-tool spike as a running card-feed console, same
  discipline.
- **Phase 0c (not started):** `ufo-types` integration-shape decision, plus a minimal build/link
  smoke test (not a full integration).
- **Phase 1 (not started, depends on 0a-0c):** one minimal end-to-end mission — one Grid2Op episode
  over existing case data, one generated card (via OperatorFabric if 0b lands, else a named
  stand-in), one `ufo-types`-scored Decision/Alternative/Risk outcome — proving the full loop once,
  small, before building it out.
- **Phase 2 (not started, depends on 1):** connect Lab 6/PRD-0007's static schema layer to Phase
  1's dynamic mission state.
- **Phase 3 (not started, depends on 2):** the strategic-objective constraint optimizer — multiple
  objectives, graded ranking across candidate actions — built on `ufo-types`' DARE types.
- **Phase 4 (not started, depends on 1):** geographic positioning and standardized simulation
  iconography.
- **Phase 5 (not started, depends on 0a/0b/1 landing well enough to justify it):** the rename and
  narrative rewrite — cim-gridy, the Oregon-Trail-card framing — sequenced after the technical
  spikes de-risk the concept, not before.
- **Phase 6 (not started, depends on 5):** expansion beyond Australia to a global scope.

## Acceptance criteria for this PRD

- [x] Real LF Energy project landscape checked against the live `lfenergy.org` project list, not
      guessed.
- [x] Grid2Op's real backend (pandapower, with a PowSyBl backend in progress) confirmed directly
      from its own repository, not assumed to be a generic RL toolkit unrelated to this repo's
      stack.
- [x] OperatorFabric's real "cards in a feed" UI concept confirmed directly, not invented as an
      analogy.
- [x] `ufo-types` confirmed real, public, and its actual module/type shape read from its own
      README, not assumed from a search snippet.
- [x] The geographic-data gap confirmed against this repo's own existing code comment, not
      assumed.
- [ ] Reviewed and approved by the user before any Phase 0 spike work begins.

## Open questions

- **CIM16 vs. CIM100** carries forward unresolved from PRD-0007 — still open.
- **Can OperatorFabric's real card/feed model host grid-mission content unmodified**, or does it
  need a thin domain adapter layer? Not checked — a Phase 0b question.
- **Does `ufo-types`' Rust-native `Satisfies<C>` constraint model supersede the need for a separate
  RDF/OWL/SHACL semantic layer**, or is RDF/OWL/SHACL still wanted in parallel (e.g. for
  interoperability with external CIM/CGMES tooling per PRD-0007)? Genuinely open.
- **Is Semantic Energy Framework (SEF) a stronger real anchor for "unified common ontology"** than
  a from-scratch RDF/OWL/SHACL build, given it's an LF Energy project specifically about
  ontology-driven energy-data interoperability? Named, not evaluated.
- **Does Dynawo (RTE, sibling to PowSyBl) belong in the engine lineup alongside pandapower/PowSyBl**
  once dynamics-timescale missions are in scope, or does DPsim (already integrated, Lab 5) already
  cover that role well enough? Not evaluated.
