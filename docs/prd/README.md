# PRDs

Forward-looking capability specs — what to build next, broken into composable units with
acceptance criteria — as distinct from `docs/backlog/`, which records gaps found by auditing
already-committed code. A PRD here may cite a backlog item as motivation, but it is a build plan,
not a gap report.

Numbered in authoring order, never renumbered once merged. Each file states its own dependencies
on other PRDs explicitly (don't assume reading order from the number alone).

| # | Title | Depends on | Status |
|---|-------|------------|--------|
| [0001](0001-composable-generator-detector-platform.md) | Composable generator/detector simulation platform | — (foundation) | proposed |
| [0002](0002-sa-2016-black-system-cascade-scenario.md) | SA 2016 Black System — physically-grounded cascade reproduction | 0001 | proposed |
| [0003](0003-iberian-2025-blackout-scenario.md) | Iberian Peninsula 2025 blackout — new scenario | 0001 | proposed |
| [0004](0004-plexos-direct-mcp-and-strangler-fig.md) | PLEXOS direct-access MCP + open-source strangler fig (plexosdb, R2X, Sienna) | — (sibling to PowerMCP) | proposed |
| [0005](0005-grid-forming-stabilizer-and-renewable-models.md) | Grid-forming transient stabilizer + open renewable-generation models (Lab 5, SPARTAN's corrective-action testbed) | — (builds on Lab 5 + 0006) | in progress |
| [0006](0006-sysml-digital-thread-mvp.md) | SysML v2 digital-thread MVP: MBSE tooling evaluation (Lab 6) | — (reuses Labs 1/3/4/5 as seed data) | implemented |

## Why this shape

`docs/PSCADOSSE.md`'s "one waveform state machine generates every view" principle already gives
Lab 5 a single source of truth for a fault's *physics*. What Lab 5 does not yet have is a way to
compose more than one physical event into a causally-linked sequence (a network fault triggering a
protection response triggering a plant disconnection triggering a further protection response —
the actual shape of every real blackout this repo's docs already reference), or anything that
*consumes* the resulting stream to detect the precursor pattern before the collapse. 0001 names
that gap as two small, composable interfaces (`Generator`, `Detector`) and a scoring harness; 0002
and 0003 are the first two scenarios built on top of it, chosen because both are already named
in this repo (SA 2016 is Lab 4's optional Part C, explicitly caveated as *not* a root-cause
reproduction; Iberian 2025 is cited in `docs/VISION.md`/GPSRR-review discussion as the reference
international incident for voltage-control and oscillation risk) and because between them they
cover the two structurally different blackout mechanisms worth having reference implementations
of: a **weather/network-fault-initiated** cascade (SA) and a **control/oscillation-initiated**
cascade with no initiating network fault at all (Iberian).
