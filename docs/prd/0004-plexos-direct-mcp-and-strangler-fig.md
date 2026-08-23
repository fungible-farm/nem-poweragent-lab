# 0004 — PLEXOS direct-access MCP + open-source strangler fig (plexosdb, R2X, Sienna)

- **Status:** proposed
- **Depends on:** none
- **Touches:** new `kube/plexosdb-mcp-pod.yaml` (adopts upstream `plexosdb-mcp`, no rebuild), new
  `kube/r2x-translate-pod.yaml` (wraps `r2x-cli` + Sienna), `docs/VISION.md` §3 ecosystem table
  (proposed additions), `docs/prd/README.md` index

## Problem

PowerAgent needs a direct interface to the PLEXOS model format itself — not a vendor's job-queue
API, a license-gated CLI, or billed remote compute. That interface already exists, is open-source,
and is maintained by the same national lab whose other tools this repo already builds on:

- **[`plexosdb`](https://github.com/NatLabRockies/plexosdb)** (PyPI, BSD-3, "Production/Stable",
  v1.6.0 as of this session) is a Python/SQLite library that parses a PLEXOS XML model into a
  queryable, typed, in-memory (or on-disk) database, and writes it back out to XML. No license
  gate, no network call — the same trust boundary this repo already crosses for the CSIRO `.m`
  case files via `powerio`. It reads objects, memberships, properties, scenarios, categories, and
  reports, and separately ships a `PlexosSolution` reader for solution ZIP output that already sits
  on disk.
- **[`plexosdb-mcp`](https://github.com/NatLabRockies/plexosdb/tree/main/src/plexosdb-mcp)**
  (**correction, Phase 0**: source-only, *not* a published PyPI package — `pypi.org/pypi/plexosdb-mcp/json`
  returns 404; see `0004-phase0-findings.md`. Installable directly from its GitHub subdirectory) is
  a *complete, already-built* MCP server over `plexosdb` — a `FastMCP`-based server (the same
  `mcp`/`fastmcp` stack `kube/powermcp_serve_http.py` already wraps in this repo), stdio transport
  by default, ~28 tools across session management, object/membership CRUD, property authoring,
  scenario tagging, discovery/catalog queries, read-only SQL, and XML/CSV export. It ships a
  `--read-only` safety flag and `health`/`doctor`/`capabilities` diagnostic subcommands
  (Phase 0-confirmed, all four run and return real JSON). This is "PowerAgent becomes a universal
  interface to PLEXOS" **already solved upstream** — the work here is composition, the same
  discipline `docs/VISION.md` §3 already applies to pandapower/powerio/PowerMCP ("Everything in
  this table already exists. This repo's job is the glue.").

Separately, the same organization publishes the **[R2X](https://github.com/NatLabRockies/R2X)**
ecosystem — a real, versioned, CI-tested model-translation framework between **ReEDS** (capacity
expansion), **PLEXOS**, and **[Sienna](https://github.com/Sienna-Platform)** (NREL's own
open-source Julia power-systems platform — PowerSystems.jl for the data model, PowerSimulations.jl
for production-cost/unit-commitment optimization). Two of R2X's four translation plugins are
directly relevant: `r2x-plexos-to-sienna` (21 mapping rules) and `r2x-sienna-to-plexos` (44 rules)
— both published, both bidirectional. This is the concrete mechanism for a strangler fig: translate
an existing PLEXOS study to Sienna, run the *equivalent* study through Sienna's open-source solver,
score the deviation against the PLEXOS study's own already-reported result, and once a study class
clears a documented tolerance, stop depending on PLEXOS for that class going forward.

## Confirmed source facts

This session read directly:

- **Conference deck**: "*plexosdb: A Modular Library for Programmatic PLEXOS Model Construction*",
  Pedro Andres Sanchez Perez & Marck Llerena-Velasquez, National Laboratory of the Rockies, May
  12–15 2026 (`docs.nlr.gov/docs/fy26osti/100294.pdf`, report NLR/PR-6A40-100294). Slide 12 names
  the MCP server explicitly: "Enable users to query, filter, and manage PLEXOS database schemas
  using plain text," "Provides agents with direct tools to fetch specific context parameters or
  simulation results," "Universal interface creation that allows any MCP application to connect
  and manipulate `plexosdb` without custom API development." Slides 19–20 cite two production use
  cases: TVA pumped-storage hydro representation (translating ReEDS capacity-expansion buildouts
  into PLEXOS via R2X, then bulk-editing with `plexosdb`, 48 translations × 1–2 min total) and
  large nodal-dataset editing for Southeastern-U.S. transmission-value studies.
- **`plexosdb` repo**: `pyproject.toml` confirms `name = "plexosdb"`, version `1.6.0`, `License ::
  OSI Approved :: BSD License`, `Development Status :: 5 - Production/Stable`, Python 3.11–3.14,
  dependency on `plexos2duckdb`. Its `src/` contains a sibling package `plexosdb-mcp` (own
  `pyproject.toml`, `server.py`, tests) and a `skills/plexosdb/SKILL.md` agent-skill bundle
  (references, eval trigger prompts, an `xmllint`-based sanity-check script) — explicitly scoped as
  "input authoring," not solver behavior ("Avoid when... User is asking for PLEXOS solver/runtime
  behavior instead of input authoring").
- **`plexosdb-mcp` source** (`src/plexosdb-mcp/src/plexosdb_mcp/server.py`, read in full this
  session): single-active-session `MCPServerState`; tools registered in six groups — session
  (`health`, `create_empty_session`, `open_xml_session`, `close_session`), object
  (`list_objects_by_class`, `add_object`, `add_membership`, `list_object_memberships`,
  `list_child_objects`, `list_parent_objects`), edit (`add_property`, `add_scenario`,
  `update_object`, `delete_object`, `delete_property`, `get_object_properties`),
  discovery/catalog (`list_classes`, `list_collections`, `list_scenarios`, `list_models`,
  `list_scenarios_by_model`, `list_valid_properties`, `list_reports`, `list_units`),
  discovery/query (`query_readonly`, `iterate_properties`), export (`save_xml`, `to_csv`), admin
  (`get_server_config`). A module-level `_ensure_writable()` guard gates every mutating tool behind
  the server's `read_only` flag.
- **R2X repo**: README confirms four translation plugins (`r2x-reeds-to-plexos` 34 rules,
  `r2x-reeds-to-sienna`, `r2x-plexos-to-sienna` 21 rules, `r2x-sienna-to-plexos` 44 rules), a Rust
  `r2x-cli` orchestrator, `r2x-core` shared framework, model packages `r2x-reeds` / `r2x-plexos`
  (built on `plexosdb`) / `r2x-sienna` (PowerSystems.jl-compatible), and a foundational `infrasys`
  System container. Model-compatibility table: inputs ReEDS v2024.8.0, Sienna PSY 4.0, PLEXOS
  9.0/9.2/10/11; outputs PLEXOS 9.0/9.2/10/11 and Sienna PSY 4.0/5.0. All packages BSD-3-Clause,
  active (`pushed_at` within days of this session for `r2x-cli`/`r2x-plexos`/`r2x-reeds`/`infrasys`).

## Composition strategy: separate upstream, shared adapter layer — not native, not forked

Three options were weighed for how `plexosdb-mcp`, `R2X`, and Sienna relate to PowerAgent:

1. **Native** — absorb their code into this repo. Rejected: it breaks the one architectural rule
   `docs/VISION.md` §3 holds every other dependency to ("Everything in this table already exists.
   This repo's job is the glue"), and it means manually backporting every upstream fix to
   independently-versioned, actively-developed projects with their own CI and release cadence.
2. **Fully separate, no shared layer** — this repo depends on pinned upstream versions directly,
   the way `kube/powermcp_serve_http.py` already wraps PowerMCP. Correct in spirit, but leaves the
   NEM-specific pieces (translation-rule overrides for AEMO's own PLEXOS modelling conventions, the
   comparison/scoring harness, pod manifests, agent Skills) scattered as one-offs inside a repo
   whose own `AGENTS.md` calls it a **training lab** — not the natural home for tooling other AEMO
   teams would want to depend on without buying into Labs 1–5's CSIRO/pandapower training content.
3. **Shared superproject (recommended)** — a small, separately-versioned adapter repo (working
   name: `poweragent-plexos-bridge`) that depends on pinned `plexosdb`/`plexosdb-mcp`/`R2X`/Sienna
   releases and contains only the glue: pod/subprocess wiring, AEMO-specific R2X rule overrides (if
   any prove necessary — none identified yet), the comparison/scoring harness from Phase 4 below,
   and a Skills bundle. This repo (`nem-poweragent-lab`) becomes one consumer of that bridge
   (a Lab 6), the same relationship it already has with PowerMCP, but the bridge itself is reusable
   by any other AEMO-adjacent project that wants agent-driven PLEXOS interoperability without
   adopting this repo's training-lab framing. This is the shape that lets AEMO "adopt the
   technologies, share context" across projects, per the actual ask — a lab-scoped fork would not.

This PRD proceeds on option 3, but Phase 0/1 below can be built directly in this repo first and
extracted once the pattern is proven — extracting working code is safer than designing a
superproject's boundaries before anything has run.

## Is PLEXOS a first-class PowerAgent capability?

"First-class" and "separately maintained" are two different axes, not opposites — this repo
already proves it with pandapower. pandapower is not native code here; it's a pinned upstream
dependency wrapped by `kube/powermcp_serve_http.py`, versioned and released entirely outside this
repo. It is unambiguously first-class anyway: the default power-flow engine, wired into every lab,
documented as a peer in `docs/VISION.md`'s ecosystem table. First-class describes PowerAgent's
*capability surface* — whether something is a standard, always-assumed peer tool server a workflow
can depend on, versus an ad hoc extension bolted on per-workflow. It says nothing about where the
code physically lives. `plexosdb-mcp` and the R2X/Sienna path should get exactly that status:
documented in `docs/VISION.md` as peers to pandapower/PowerMCP, the standard tool server for
PLEXOS-model interop and open-engine solves — while the code stays out of this repo, pinned via the
`poweragent-plexos-bridge` superproject the same way pandapower is pinned via PyPI. First-class
does not mean mandatory for every lab, either — Lab 3's provider bake-off and Lab 5's
hardware-validated extension are already optional pieces of a first-class lab set; it means *when*
a workflow needs this capability, this is *the* standard path to it, not one of several options.

Separately, "PLEXOS" itself names two different things worth splitting:

- **PLEXOS the model format** (what `plexosdb` reads/writes) — **yes, first-class**, at the same
  tier as pandapower. It is how PowerAgent talks to every study the organization already has, it is
  open-source to interoperate with, and treating it as a peer MCP tool server (not a bolt-on) is
  what makes the "universal interface" framing true rather than aspirational.
- **PLEXOS the proprietary solve engine** — **not first-class, and deliberately not depended on**.
  Making PowerAgent require a PLEXOS license or any vendor's remote compute to function would
  reintroduce exactly the lock-in this PRD exists to reduce. Sienna (open-source, local, free)
  should be the engine PowerAgent depends on by default; PLEXOS-format import/export stays
  available purely as an interoperability path for legacy studies and any downstream consumer that
  still expects PLEXOS output — never as a required runtime dependency.

Concretely: `plexosdb`/`plexosdb-mcp` sit in the same tier as `powermcp-pandapower` in
`docs/VISION.md`'s architecture (peer MCP tool servers, Goal 1 below). `R2X` + Sienna sit beside
them as the open engine path (Goal 4). Nothing in this design requires a PLEXOS license, a PLEXOS
installation, or any network call to a PLEXOS vendor to run end to end — the only thing PLEXOS
contributes is the XML files the organization already has sitting on disk from prior studies.

## Goals

1. **Adopt, don't rebuild.** Wire `plexosdb-mcp` into this repo's pod pattern as-is — pin an exact
   version, do not fork it. **Correction (Phase 0, see `docs/prd/0004-phase0-findings.md`):**
   `plexosdb-mcp` is not published to PyPI, so "pin the PyPI version" isn't available as written —
   pin a git subdirectory + commit/tag instead (`plexosdb-mcp @
   git+https://github.com/NatLabRockies/plexosdb#subdirectory=src/plexosdb-mcp`). Same discipline
   this repo already holds itself to for pandapower/PowerMCP, adapted to this dependency's real
   distribution shape.
2. **Read-only by default.** Any workflow that only inspects or compares models runs the server
   with `--read-only`; write sessions (`add_object`, `update_object`, `delete_object`, `save_xml`,
   ...) require an explicit opt-in — matches this repo's existing no-destructive-default posture
   and `plexosdb-mcp`'s own built-in `_ensure_writable()` gate.
3. **Resolve the transport question before building a pod.** `plexosdb-mcp` is stdio-native.
   **Correction (Phase 0):** the PRD originally assumed a standalone `uvx plexosdb-mcp` CLI — that
   command fails (`plexosdb-mcp` isn't on PyPI); the confirmed-working invocation is `uv run
   plexosdb-mcp` from a project that has installed it via the git-subdirectory pin above, which does
   behave as a standard stdio MCP server (verified with a real `initialize` JSON-RPC handshake in
   Phase 0). Determine whether Microsoft Agent Framework's MCP client can launch that `uv run`
   invocation directly as a stdio subprocess — if so, no HTTP-wrapper pod
   (`powermcp_serve_http.py`'s whole reason for existing) is needed for this server at all.
4. **Stand up R2X + Sienna as the strangler-fig engine**, not just a translator: wrap `r2x-cli`
   (a single Rust binary — easiest thing in this ecosystem map to containerize) running a
   `plexos-to-sienna` / `sienna-to-plexos` pipeline, and, once a translated system loads correctly,
   drive an actual Sienna/PowerSimulations.jl solve as the open-source engine. Expose the
   translation step as MCP tools mirroring `plexosdb-mcp`'s shape (`translate_plexos_to_sienna`,
   `translate_sienna_to_plexos`) so an agent can call it the same way.
5. **Migrate per study class, not in one cutover.** Pick one bounded PLEXOS study class, translate
   it, run it on Sienna, score deviation against that same study's own already-reported result (via
   `plexosdb`'s `PlexosSolution.from_zip()` against a solution ZIP already on disk, or a published
   study result — never a fresh vendor-run comparison), and only then flip that class's default
   engine.
6. **Track the actual success metric**: which study classes now run on Sienna by default versus
   which still require PLEXOS-format interoperability only. That list *is* the
   dependence-reduction result — not a one-time migration announcement.

## Non-goals

- Not claiming numeric parity across every study type on day one. R2X's own rule counts differ by
  direction and plugin (21 vs. 44 rules) — coverage is real but asymmetric and evolving; each study
  class needs its own deviation check before being trusted, not a blanket "Sienna replaces PLEXOS"
  claim.
- Not building new MCP servers for `plexosdb` or `R2X` from scratch — both already exist, are
  versioned and CI-tested upstream. The work is composition: pods (or subprocess wiring), an Agent
  Framework workflow, and the comparison/scoring harness.
- Not vendoring or forking `plexosdb`/`R2X`/`r2x-*` into this repo. Pin exact versions
  (`plexosdb-mcp==`, an `r2x-cli` release tag) the same way `docs/VISION.md` already asks of every
  ecosystem dependency.
- Not a claim that Sienna/Julia is "free" in the infrastructure sense this repo otherwise expects —
  it is open-source and license-free, but it is a **new runtime dependency** (Julia + package
  precompilation) this repo has never carried before; name that cost explicitly, don't bury it.
- Not requiring a PLEXOS license, installation, or vendor network call anywhere in this design —
  see "Is PLEXOS a first-class capability?" above. If a future need genuinely requires running
  PLEXOS's own proprietary engine, that is a separate PRD with its own explicit license/cost
  tradeoff, not a silent dependency introduced here.

## Architecture

```
┌────────────────────────────────────────────────────────────────────────────────┐
│ podman kube play  (same pod-network as the rest of this repo)                  │
│                                                                                  │
│  ┌─────────────────┐   MCP (stdio, or streamable-HTTP if a pod proves needed)  │
│  │ plexosdb-mcp     │◄──────────────────────────────┐                          │
│  │ (adopted verbatim,│                               │                          │
│  │ upstream package) │                               │                          │
│  └─────────────────┘                                 │      ┌─────────────────┐│
│         reads/writes local .xml / SQLite               ├─────►│ agent-framework ││
│                                                        │      │ orchestrator    ││
│  ┌─────────────────┐   MCP (translate_* tools)         │      │ (Lab 2's own    ││
│  │ r2x-translate    │◄──────────────────────────────┘      │ driver process) ││
│  │ (wraps r2x-cli   │                                              └────────┬────────┘│
│  │ + Sienna solve)  │                                                       │         │
│  └────────┬─────────┘                                                       │         │
│           │ writes Sienna PSY JSON, invokes PowerSimulations.jl (new Julia   │         │
│           │ runtime dependency)                                             │         │
│           ▼                                                                 │         │
│  ┌─────────────────┐                                                        │         │
│  │ powermcp-pandapower│◄───────────────────────────────────────────────────┘         │
│  │ (existing, unchanged)                                                              │
│  └─────────────────┘                                                                  │
└────────────────────────────────────────────────────────────────────────────────┘
```

`plexosdb-mcp` needs no `powermcp_serve_http.py`-style reflection hack — `build_mcp_server()` is
already a clean public constructor in the upstream package, so an HTTP wrapper (if one turns out
to be needed at all — see Goal 3) would be a straight `server.run(transport="streamable-http")`
call, simpler than the PowerMCP precedent.

## Tool surface

### `plexosdb-mcp` (adopted verbatim, grouped by the source's own registration order)

| Group | Tools |
|---|---|
| Session | `health`, `create_empty_session`, `open_xml_session`, `close_session` |
| Object | `list_objects_by_class`, `add_object`, `add_membership`, `list_object_memberships`, `list_child_objects`, `list_parent_objects` |
| Edit (write-gated) | `add_property`, `add_scenario`, `update_object`, `delete_object`, `delete_property`, `get_object_properties` |
| Discovery/catalog | `list_classes`, `list_collections`, `list_scenarios`, `list_models`, `list_scenarios_by_model`, `list_valid_properties`, `list_reports`, `list_units` |
| Discovery/query | `query_readonly`, `iterate_properties` |
| Export (write-gated) | `save_xml`, `to_csv` |
| Admin | `get_server_config` |

### `r2x-translate` (proposed — new thin wrapper around `r2x-cli`)

| MCP tool | Underlying call | Notes |
|---|---|---|
| `translate_plexos_to_sienna` | `r2x run pipeline.yaml` with `r2x-plexos.plexos-exporter` → `r2x-plexos-to-sienna.translation` | takes a PLEXOS XML path, returns a Sienna PSY JSON path |
| `translate_sienna_to_plexos` | inverse pipeline (`r2x-sienna-to-plexos.translation`) | for round-tripping strangled study results back into PLEXOS format for downstream consumers that still expect it |
| `run_sienna_solve` | invokes PowerSimulations.jl against the translated system | the open-source engine call — new Julia runtime dependency, named explicitly |
| `compare_solutions` | reads a PLEXOS solution (via `plexosdb.PlexosSolution.from_zip`) already on disk and the Sienna solve output, scores deviation | the harness from Goal 5, same "deterministic script, agent drives it" pattern as this repo's other labs |

## Strangler-fig phasing

- **Phase 0 — env verification. Done.** See
  [`0004-phase0-findings.md`](0004-phase0-findings.md) for the full evidence trail. Summary:
  `plexosdb` (the library) installs cleanly via `uv add plexosdb` — pure-Python/OSS, no license
  gate, confirmed. `plexosdb-mcp` is **not** published to PyPI (`pypi.org/pypi/plexosdb-mcp/json`
  returns 404, and the PRD's literal `uvx plexosdb-mcp ...` command fails as written — a real
  correction to this PRD's original "own PyPI package" claim above), but its real source in
  `NatLabRockies/plexosdb`'s `src/plexosdb-mcp/` installs and runs cleanly from GitHub
  (`uv add "plexosdb-mcp @ git+https://github.com/NatLabRockies/plexosdb#subdirectory=src/plexosdb-mcp"`
  then `uv run plexosdb-mcp {health,version,doctor,capabilities}`), all four diagnostic subcommands
  returning real JSON matching this PRD's tool-surface table. A real MCP `initialize` handshake
  piped over stdio to `uv run plexosdb-mcp` (no subcommand) returned a spec-correct response on
  stdout with all logging on stderr — confirming it behaves as a normal stdio MCP server (see Goal
  3 / Open questions below for what this does and doesn't settle).
- **Phase 1 — direct-access workflow, standalone value.** Wire `plexosdb-mcp` into an Agent
  Framework workflow (Lab 2's own shape) doing something useful on its own, independent of the
  strangler-fig ambition: load a PLEXOS study, list its generators/nodes, diff two versions of a
  model. This alone delivers the direct-interface goal.
- **Phase 2 — translation only.** Stand up `r2x-cli` + `r2x-plexos-to-sienna`; translate one real
  PLEXOS study to Sienna PSY JSON; confirm it loads in Sienna's own tooling. No solve yet.
- **Phase 3 — Sienna solve.** Run the translated study through PowerSimulations.jl. Name the new
  Julia runtime dependency explicitly in `docs/VISION.md`'s ecosystem table (this repo has never
  carried a Julia dependency before — a genuinely new axis, not a variant of an existing one).
- **Phase 4 — comparison harness.** Score Sienna's result against that same study's own
  already-reported PLEXOS solution (a solution ZIP already on disk, or a published result). Anchor
  the deviation tolerance to that named, real source — same discipline `docs/prd/0002`/`0003`
  already apply to their own scoring tolerances.
- **Phase 5 — flip the default, per class.** Once a study class clears its tolerance, make Sienna
  the default engine for it in the workflow; keep `translate_sienna_to_plexos` available so
  PLEXOS-format output can still be produced for any downstream consumer expecting it.
- **Phase 6 — ongoing tracking.** Maintain a visible strangled/not-strangled table (in this PRD's
  future revision or a follow-up doc) — the actual measure of reduced PLEXOS dependency.
- **Phase 7 — extract the bridge (optional, once Phases 1–2 prove the pattern).** Pull the pod
  manifests, translation wrappers, and comparison harness out into the shared
  `poweragent-plexos-bridge` superproject described above, so other AEMO projects can depend on it
  without adopting this repo's training-lab scope.

## Where this lives (proposal, not final)

- `kube/plexosdb-mcp-pod.yaml` (or, pending Phase 0/Goal 3, a documented stdio-subprocess wiring
  that skips a pod entirely)
- `kube/r2x-translate-pod.yaml`, `Containerfile.r2x-translate` (Rust `r2x-cli` binary + Julia
  runtime for the Sienna solve step)
- `labs/10-plexos-direct-and-strangler-fig/` (proposed new lab, Phase 1 onward — renumbered twice
  now: originally proposed as `labs/06-...`, then `labs/07-...` after PRD-0006 claimed Lab 6 for the
  SysML v2 digital-thread MVP; now `labs/10-...` since Labs 07/08/09 were subsequently claimed by
  `rust-comtrade-fft-detector` and the two cim-gridy labs, per Phase 0's findings doc), following
  Labs 1–5's fetch→run→check/README-with-Sandbox-notes shape. Not created yet — Phase 0 is
  verification only; see `0004-phase0-findings.md`.
- `docs/VISION.md` §3: proposed new ecosystem rows for `plexosdb`, `plexosdb-mcp`, `R2X`
  (`r2x-cli`/`r2x-core`/`r2x-plexos`/`r2x-sienna`/`infrasys`), and Sienna
  (PowerSystems.jl/PowerSimulations.jl) — all open-source, all free to run locally

## Acceptance criteria for this PRD

- [x] `plexosdb-mcp` confirmed runnable in this sandbox (Phase 0), exact commands cited. See
      `0004-phase0-findings.md` — runnable via `uv add "plexosdb-mcp @
      git+https://github.com/NatLabRockies/plexosdb#subdirectory=src/plexosdb-mcp"` + `uv run
      plexosdb-mcp {health,version,doctor,capabilities}`; the PRD's originally-cited bare `uvx
      plexosdb-mcp ...` command does not work as written (package not on PyPI — corrected above).
- [ ] A real (or CSIRO-adjacent placeholder) PLEXOS XML study has been loaded and inspected via
      `plexosdb-mcp` tools end-to-end from an Agent Framework workflow.
- [ ] The stdio-vs-pod transport question (Goal 3) is answered with a cited finding, not assumed
      either way.
- [ ] At least one PLEXOS→Sienna translation has been run via `r2x-cli` and the output confirmed
      loadable, before any claim about a working Sienna solve path.
- [ ] The Julia/Sienna runtime dependency is named in `docs/VISION.md`'s ecosystem table if Phase 3
      work begins — never silently added.

## Open questions

- **Stdio-direct vs. pod+HTTP** (Goal 3): does Agent Framework's MCP client support launching a
  stdio child process directly? This determines whether `plexosdb-mcp` needs a pod at all.
- **Single-session constraint**: `plexosdb-mcp`'s `MCPServerState` holds exactly one active
  `PlexosDB` session at a time. Fine for one workflow at a time; a concurrency limit to note, not
  solve, in this PRD.
- **Sienna/Julia feasibility in this sandbox**: this repo has zero Julia today. Confirm a CPU-only
  `PowerSimulations.jl` solve is actually runnable here before Phase 3 proceeds — if blocked, name
  the blocker the same way Lab 5's IEC 61850 gap is named, don't silently skip it.
- **Deviation-tolerance source** for Phase 4: needs a real, citable anchor (a published study, or a
  solution ZIP already held from a prior study) rather than an arbitrary number.
- **`r2x-sienna` maturity flag**: its own README carries a warning — "optimized for internal R2X
  workflows... APIs and behavior may continue to evolve" — worth re-checking at Phase 2 start
  rather than assuming stability from this session's read.
- **When (if ever) to cut Phase 7's superproject.** Extracting too early designs boundaries no one
  has tested; extracting too late lets NEM-specific glue calcify inside a training-lab repo other
  AEMO teams won't want to depend on. Revisit once Phase 1/2 are real and running.
