<!--
Draft GitHub issue / concept note. Not yet filed, not yet synced anywhere. Local only, per
instruction, until this is ready to move further.
-->

**Suggested title:** SIM-GRIDY: a SimCity/Civilization-style power-grid game, built on app4dog +
this repo's existing engines

**Suggested labels:** `enhancement`, `game`, `app4dog`, `sim-gridy`

---

## Summary

A separate project — **SIM-GRIDY**, working name — a person-vs-computer, configurable-difficulty,
configurable-speed civilization/city-builder game centered on running a power grid, built for the
author's 10-year-old niece Sara. Hosted (eventually) at `sim-gridy.promptexecution.com`, on the same
TypeScript/WASM pattern this repo already ships (`rust/phase-model`'s WASM-ready waveform state
machine, the Dioxus/WASM power-sim app), and on **app4dog**'s existing Bevy-engine-to-web-interface
patterns — reusing app4dog's abstract/shared libraries and its compositional testing patterns
(transfer the *patterns*, not IP or property), not reinventing them.

**Kept as its own separate module for now, deliberately not integrated into `labs/`** — this repo's
labs are an AEMO training curriculum with their own Definition of Done; SIM-GRIDY is a different
audience (a 10-year-old, playing a game) and a different program (a from-scratch build against
app4dog), and shouldn't get tangled into the labs' own scope or self-checking conventions until
there's a real reason to share code, not just adjacency.

## The game, as described

- **Progression arc**: begins in the industrial age as tower-defense-style grid-building (build your
  network, mine coal, generate steam) → pollution compounds as the civilization expands → global
  warming, fires, changing seasons become live mechanics → renewables get invented, forcing a
  research-spending/transmission-buildout/CER-DER-progression balance → eventually a space
  elevator/power conduit, space solar farms, plasma fusion.
- **Role progression**: the player's role changes at each phase, ending as head of the national power
  grid, on a generative map/topology that grows over the course of a playthrough (not a fixed map).
- **Sequel**: a Kardashev-scale successor, once SIM-GRIDY itself is real and playable.
- Person-vs-computer, with configurable difficulty and configurable speed.

## What already exists in this repo that plausibly transfers (patterns, not code as-is)

Flagged here so a future planning pass starts from what's real, not from scratch:

- `rust/phase-model` — the oxidized waveform state machine, already WASM-ready
  (`docs/PSCADOSSE.md`'s "one waveform state machine generates every view" principle) — the same
  TypeScript/WASM pattern the author wants to recycle for SIM-GRIDY's own hosting.
- `labs/_shared/scenario_engine` (PRD-0001's `Generator`/`Detector` platform) — a composable,
  causally-linked event-timeline engine with a scoring harness. Structurally close to what a
  civilization-game difficulty/disaster system needs (scripted cascading failures, scored outcomes),
  though built for AEMO-training self-checking, not for a game loop — would need real adaptation,
  not a drop-in reuse.
- Lab 5's `chaosnet.py` — procedural topology generation (NetworkX Watts-Strogatz perturbation of a
  seed grid) is already "a generative map/topology that grows," the same shape SIM-GRIDY's map
  generator needs.
- The GridSFM/GENCO screen-then-verify pattern (see `docs/backlog/0006`-adjacent conversation,
  not yet its own backlog item) — relevant here for a completely different reason than the AEMO labs:
  a real physics solve every game tick won't hold interactive framerate at civilization scale, so a
  fast learned surrogate, screened and spot-verified, is the legitimate way to keep "real power flow"
  as a difficulty setting rather than dropping physical accuracy entirely.

## Explicitly not decided yet

- Whether SIM-GRIDY lives as a subdirectory of this repo, a git submodule pointing at a real separate
  repo, or a fully independent repo from day one. "Its own sub-module, kept separate, for now" is the
  instruction this note follows; the permanent shape is an open question.
- app4dog's actual current code/patterns were not read for this note — nothing here should be taken
  as a claim about what app4dog already provides; that's the first real research step before any
  build begins.
- Nothing about this has been synced to GitHub or any web service yet, per instruction.

## Suggested next step, when picked back up

A proper PRD (`docs/prd/000X-sim-gridy...md`, matching how 0001–0004 already work in this repo) once
app4dog's real patterns have actually been read and the "sub-module vs. submodule vs. separate repo"
question is resolved — not before.
