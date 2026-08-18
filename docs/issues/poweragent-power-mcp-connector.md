<!--
Draft GitHub issue. Not yet filed. Written to `gh issue create --body-file` verbatim once
reviewed — everything below the "---" is the intended issue body; this comment block is not.
-->

**Suggested title:** PowerMCP connector: an idiomatic, loosely-coupled wrapper for plexosdb, R2X,
and Sienna

**Suggested labels:** `enhancement`, `mcp`, `plexos`

---

## Summary

Add a PowerMCP-family tool server — working name **`power-mcp-plexos`** — that exposes PLEXOS and
Sienna support **together, from the same foundation**, rather than staged as "PLEXOS first, Sienna
later." [R2X](https://github.com/NatLabRockies/R2X) already treats both as peer formats onto one
in-memory model: `r2x-plexos` (built on
[`plexosdb`](https://github.com/NatLabRockies/plexosdb)) and `r2x-sienna` are parser/exporter
pairs onto `r2x-core`'s shared `System` container, with `r2x-plexos-to-sienna` /
`r2x-sienna-to-plexos` translating between them. The connector should preserve that symmetry: build
on R2X as the shared foundation, add `plexosdb-mcp`'s fine-grained object/property CRUD tools for
direct PLEXOS editing, and add a Sienna (PowerSimulations.jl) solve step — all as one connector,
shipped together, as **peer** MCP tool servers alongside PowerMCP's existing pandapower server. The
connector wraps these upstream, independently-maintained projects idiomatically — matching
PowerMCP's own tool-server conventions — without forking, vendoring, or otherwise tightly binding
the poweragent-mcp ecosystem's core to any of them.

## User story

> As an agent workflow speaking MCP to PowerMCP's tool servers, I want to call a standard set of
> MCP tools to inspect, edit, and translate a PLEXOS study, and to run the translated study on an
> open-source solve engine — the same way I already call `run_power_flow` against pandapower —
> **without** needing a PLEXOS license, a PLEXOS installation, or any vendor network call to do it.

## Logical goals of the integration

1. **Symmetric, simultaneous format support.** Add PLEXOS and Sienna support together, both
   grounded in R2X's own plugin ecosystem, rather than staging "PLEXOS now, Sienna later." R2X
   already treats both as peer input/output formats onto one `System` container — the connector
   should preserve that symmetry, not re-introduce a sequencing R2X itself doesn't have.
2. **Direct model access and translation, from one foundation.** Because `r2x-plexos` is itself
   built on `plexosdb`, the connector's PLEXOS object/property/membership editing tools
   (`plexosdb-mcp`, adopted as-is, for fine-grained CRUD no translation-level API needs to cover)
   and its PLEXOS↔Sienna translation tools (R2X's own versioned, tested rules — not a bespoke
   converter this connector would build itself) share the same underlying model rather than being
   two independently-timed capabilities.
3. **Open engine access.** Give agents a path to an actual open-source production-cost /
   unit-commitment solve (Sienna/PowerSimulations.jl) as a peer to pandapower's steady-state
   power-flow solve — a study class pandapower does not cover today.
4. **Idiomatic tool surface.** The connector's tools should read like PowerMCP's pandapower tools
   already do: consistent naming, predictable session/error semantics, the same MCP transport
   conventions — so an agent doesn't need special-casing per tool server. "Idiomatic" here means
   *conforms to PowerMCP's existing conventions*, not *reimplements upstream behavior*.
5. **Loose coupling, by design.** Pin exact upstream versions as a set — `plexosdb-mcp==`,
   `r2x-core`/`r2x-plexos`/`r2x-sienna` at a compatible `r2x-cli` release tag, following R2X's own
   published model-compatibility table rather than pinning PLEXOS and Sienna support
   independently. No forking, no vendoring. The connector is thin adapter code only — tool-naming
   glue, transport wiring, a comparison harness — extractable into its own standalone project
   without breaking how PowerMCP consumers reach it.
6. **A measurable dependence-reduction path.** Once translation + open-engine solve are wired up,
   individual PLEXOS study classes can be validated against Sienna and migrated one at a time — a
   strangler fig, not a big-bang cutover, with a visible strangled/not-strangled record.

## Why Sienna, R2X, and PLEXOS belong in the poweragent-mcp ecosystem

- **It's the paper's own architecture, extended, not reinvented.** PowerAgent's Model Context
  Protocol pillar (Zhang & Xie, "PowerAgent: A Road Map Toward Agentic Intelligence in Power
  Systems," IEEE Power and Energy Magazine, 2025) is explicitly a *tool layer*: multiple engines
  exposed as peer MCP servers an orchestrator picks between. PowerMCP's existing pandapower server
  fills the steady-state power-flow slot; nothing today fills the production-cost/capacity-class
  slot PLEXOS and Sienna occupy. Adding it fills a named gap in the same architecture, not a new
  one.
- **The hard part is already built, and built for exactly this.** `plexosdb-mcp` isn't a library
  this connector would wrap for the first time — its own publication (a May 2026 conference
  presentation from its maintaining lab) names "agentic integration" and a "universal interface...
  without custom API development" as its explicit design goal. Adopting it is the same
  compose-don't-rebuild discipline PowerMCP itself already applies to pandapower — applied to
  another real, versioned, open-source project, not a departure from it.
- **It's the first connector here that pairs a closed-source engine with a tested way off it.**
  PowerMCP already wraps several closed-source, locally-licensed engines — PSS/E, PowerWorld,
  PSLF, PowerFactory, PSCAD — each purely as an interface to the paid tool itself, with no
  translation or open-source path offered alongside it. PLEXOS joining that list isn't a new
  category. What's new is pairing the closed-source interface with R2X's tested, versioned,
  bidirectional translation to Sienna (open, local, license-free) for the *same class of study* —
  giving adopters an actual, incremental way to reduce dependency on the licensed tool, not just
  another wrapper around one.
- **Organizations adopting PowerMCP already have the artifacts.** Existing PLEXOS studies (XML
  files, solution ZIPs) sit on disk today for any org with an existing PLEXOS practice. `plexosdb`
  reads them with no additional access requirement — this connector makes that existing asset
  usable by an agent immediately, independent of whether a strangler-fig migration to Sienna ever
  completes for a given study class.

## Proposed shape (non-binding)

Both groups below ship together, in the same release — neither is a prerequisite phase for the
other, since both sit on the same R2X foundation:

- `power-mcp-plexos` tool group: session + object/membership/property/scenario CRUD +
  discovery/query/export, mirrored 1:1 from `plexosdb-mcp`'s own ~28 tools, read-only by default.
- `power-mcp-translate` tool group: `load_system` (PLEXOS XML or Sienna PSY JSON, via `r2x-plexos`
  / `r2x-sienna`), `translate_plexos_to_sienna`, `translate_sienna_to_plexos`, `run_sienna_solve`,
  `compare_solutions` — thin wrappers around `r2x-cli` pipelines and a Sienna solve invocation.
- Both registered as standard peers to PowerMCP's existing pandapower server and to any MCP-capable
  agent workflow that needs them — not an experimental/opt-in extension, and not sequenced as one
  released ahead of the other.

## Non-goals

- Not forking or vendoring `plexosdb`, `R2X`, or Sienna.
- Not requiring a PLEXOS license, installation, or vendor network call anywhere in the connector.
- Not claiming solve parity with PLEXOS across every study type on day one — coverage should be
  validated and tracked per study class, not asserted as a blanket replacement.
- Not deciding upfront whether this connector ships inside PowerMCP itself or as a standalone
  sibling project — an open question to resolve once a working prototype exists, not before.

## Acceptance criteria (scoped to starting this work, not full parity)

- [ ] `plexosdb-mcp` and `r2x-cli` (with the `r2x-plexos` and `r2x-sienna` plugins installed)
      confirmed installable and runnable together in a target deployment environment, commands
      cited.
- [ ] A real PLEXOS XML study loads and is inspectable end-to-end through the connector (list
      objects, list memberships, read properties) **and** the same study translates to Sienna PSY
      JSON and loads there — both proven in the same pass, not one gated behind the other.
- [ ] The stdio-vs-HTTP transport question is answered with a cited finding for at least one
      target MCP client (does it support a direct stdio subprocess, or is an HTTP wrapper
      required).
- [ ] A Sienna solve has been run against the translated system, since a solve is genuinely
      downstream of a working translation — but PLEXOS-side and Sienna-side tool availability
      themselves ship together, not staged.

## References

- [`plexosdb`](https://github.com/NatLabRockies/plexosdb) /
  [`plexosdb-mcp`](https://github.com/NatLabRockies/plexosdb/tree/main/src/plexosdb-mcp)
- [`R2X`](https://github.com/NatLabRockies/R2X) and its `r2x-plexos-to-sienna` /
  `r2x-sienna-to-plexos` translation plugins
- [Sienna](https://github.com/Sienna-Platform) (PowerSystems.jl / PowerSimulations.jl)
- Zhang, Q. & Xie, L., "PowerAgent: A Road Map Toward Agentic Intelligence in Power Systems:
  Foundation Model, Model Context Protocol, and Workflow," IEEE Power and Energy Magazine, vol. 23,
  no. 5, pp. 93–101, Sept.–Oct. 2025 — the architecture this connector's MCP tool layer extends.
