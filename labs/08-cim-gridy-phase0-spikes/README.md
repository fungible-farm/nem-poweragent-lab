# Lab 8 — cim-gridy Phase 0: real-tool spikes

PRD-0008/0009's Phase 0 (docs/prd/0008-cim-gridy-mission-engine-prerequisites.md,
docs/prd/0009-cim-gridy-incose-v-plan.md) named five prerequisite technology questions for the
"cim-gridy" pivot — a grid-operator missions game in calendar steps — and mandated real, timeboxed
spikes over research, plus "use sub-agents heavily." This lab is those five spikes, run in parallel,
each with its own honest, evidence-based verdict. No narrative/rename work depends on any of this
yet (that's Phase 5); this is purely "does the foundation actually work."

## Verdicts at a glance

| Spike | Question | Verdict | Detail |
|---|---|---|---|
| [0a](0a-grid2op/README.md) | Does Grid2Op wrap this repo's own CSIRO case data? | **Yes, with real friction** — 3 independent bugs found and fixed (grid2op's own broken PyPI wheel, a pandapower round-trip bug, a dense-bus-index assumption); one real episode ran end to end (503 buses, 698 lines) once fixed | `grid2op.make()` + `env.step()` both succeeded post-fix |
| [0b](0b-sysml-v2-parser/README.md) | Do real native-Rust SysML v2 parsers work? | **Yes** — `sysml-v2-parser` (63.9%) and `syster-base` (69.4%) both parse the real GfSE fixture corpus cleanly, no crashes; **`sysml-v2-parser` recommended primary** (lighter, purpose-fit API) | 36 real GfSE fixtures + this repo's own Lab 6 `.sysml` output (3/3 both) |
| [0c](0c-sysand-cli/README.md) | Does sysand's native CLI work without Maven/JVM? | **Yes, cleanly** — `ldd` confirms zero JVM/JNI linkage; `init`/`include`/`build`/`lock` all ran correctly, produced a genuine spec-shaped KPAR archive | Clears the exact `UnsatisfiedLinkError` blocker that stopped Lab 6's original JVM approach |
| [0d](0d-ufo-types-scryer-prolog/README.md) | Do `ufo-types` + `scryer-prolog` coexist? | **Yes** — build/link/run cleanly together, no dependency conflicts; real caveat found: `scryer-prolog` panics on a debug-profile internal UB check (release builds unaffected) | Recommend release builds for this pairing until upstream fixes the debug-mode issue |
| [0e](0e-operatorfabric-vs-bevy/README.md) | OperatorFabric or Bevy-native cards? | **Build in Bevy** — OperatorFabric's real footprint (11 containers, ~1.9GB, 20-30+ min bring-up) is disproportionate for a single-player card mechanic; `bevy_ui` confirmed to have every primitive needed (flexbox, first-party scroll, card styling) via a real Bevy example | OperatorFabric's `Card` data model kept as a design reference, not a dependency |

**Every spike reached a real, checkable verdict — none blocked outright.** The overall Phase 0
conclusion: the technology stack PRD-0009 proposed is viable end to end, with two real, load-bearing
findings that Phase 1 must carry forward (not silently assumed away):

1. **Grid2Op's stock `pandapower` integration path has three real bugs standing between "install it"
   and "it works"** (0a) — each has a documented fix, but Phase 1 must budget real engineering time
   for this, not treat it as a thin wrapper.
2. **`scryer-prolog` has a debug-build-only internal panic** (0d) — real, reproducible, unrelated to
   `ufo-types` — Phase 1's dev workflow for the ontology/constraint layer should default to release
   builds (or `debug-assertions = false`) until upstream resolves it.

## What Phase 1 should now do differently, given this evidence

- **SysML v2 parsing**: use `sysml-v2-parser`, not a hand-rolled stand-in and not the JVM/Maven
  path — both now retired as options (0b, 0c).
- **SysML v2 packaging**: `sysand`'s native CLI is a real, working `.sysml` → KPAR pipeline with
  zero JVM dependency — usable directly (0c).
- **Grid2Op**: plan for `--no-binary-package grid2op` (or a fixed future release) and the two other
  named fixes (0a) as a real, one-time integration cost, not a given.
- **Ontology/constraint layer**: `ufo-types` + `scryer-prolog` is a workable pairing for Phase 3's
  optimizer, release-build-only for now (0d).
- **Card feed UI**: build natively in Bevy — no new runtime dependency, and Bevy 0.19's own APIs
  already demonstrate the exact "scrollable severity-sorted card list" shape needed (0e).

## Process note

All five spikes ran as parallel sub-agents per PRD-0009's own "use sub-agents heavily" mandate, each
independently cloning/installing/building/running its target tool against real data already in this
repo (CSIRO case files, Lab 6's `.sysml` output) or real upstream fixtures (`GfSE/SysML-v2-Models`).
Each spike's own directory is self-contained (own `Cargo.toml`/scratch venv, not wired into this
repo's main `rust/` workspace or `pyproject.toml`/`uv.lock`) — these are throwaway spikes, not
production dependencies; adopting any of them for real is Phase 1+ work.

## Files

- `0a-grid2op/` — spike scripts + the real converted CSIRO dataset (`dataset_snemSA/`).
- `0b-sysml-v2-parser/` — standalone Rust crate, real GfSE + Lab 6 fixtures, `run_output.txt`.
- `0c-sysand-cli/` — findings + reproduction script (upstream cloned to scratch, not vendored).
- `0d-ufo-types-scryer-prolog/` — standalone Rust crate, build/link smoke test.
- `0e-operatorfabric-vs-bevy/` — findings only (upstream cloned to scratch, containers torn down).
