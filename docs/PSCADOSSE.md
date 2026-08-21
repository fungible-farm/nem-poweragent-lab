# PSCADOSSE — charter

**PSCADOSSE** = *PS/CAD and Open Systems Simulation Engineering*: the EMT /
phasor domain and capability set that commercial PS/CAD exemplifies, implemented
in this repo with the **open variants** it recommends. Using commercial PSCAD
(or any commercial engine) is a modeller's own choice; it is **never required**
on this repo's golden path (AGENTS.md non-goal: no commercial engines on the
golden path).

This repo assimilates that domain for Australian NEM capability: real CSIRO
Synthetic-NEM network models, real AEMO reconciliation, and 50 Hz NEM-domain
physics throughout.

## Golden-path licensing policy

The golden path prefers **foundational, OSI-approved, permissively licensed**
components — Apache-2.0, MIT, BSD — ideally foundation-backed. Where such a
component exists for a needed capability, this repo assimilates it rather than
reaching for a proprietary or novel re-implementation.

### Verified license map (checked from installed metadata / vendored files, not assumed)

| Component | Role on the golden path | License | Notes |
|---|---|---|---|
| pandapower | power-flow engine (Labs 1-4) | BSD | OSI-approved BSD (classifier-confirmed) |
| powerio | MATPOWER .m parsing | MIT OR Apache-2.0 | dual |
| networkx | graph (Lab 5) | BSD-3-Clause | |
| numpy / scipy / numba | numeric stack | BSD-3 / BSD-3 / BSD-2 | |
| matplotlib | charts/animations | PSF / BSD-style | |
| mcp | MCP SDK (smoke test) | MIT | |
| DPsim | EMT engine (Lab 5) | **MPL-2.0** | one of two documented MPL-2.0 exceptions (see pypowsybl below) — OSI-approved, file-level copyleft only, foundation-friendly; documented so nobody mistakes it for Apache |
| simbench | Lab 5 seed grid dataset | university license (Kassel / TU Dortmund / RWTH) | dataset attribution terms |
| just / uv | command runner / env | CC0 / MIT-or-Apache | |
| CSIRO Synthetic-NEM data | Labs 1-5 case files | CC-BY-4.0 | fetched by scripts/fetch_csiro_nem_data.py |
| AEMO NEM constraints | Lab 4 constraint decode | MIT (vendored, LICENSE-NEM_constraints) | |
| mpv / chafa / ffmpeg / fzf | demo display/render/launcher (CLIs) | GPL-2.0+ / LGPL-3.0+ / LGPL-GPL / MIT | mpv, chafa, ffmpeg are copyleft but invoked as external CLIs — **not** part of the linked API surface; fzf (MIT) is permissive, used by the `just demo` launcher |
| jupytext / nbconvert / ipykernel | dev-only: `notebooks/lab_playbook.py` percent-format notebook + its `--execute` render (docs/backlog/0005) | MIT / BSD-3-Clause / BSD-3-Clause | `[dependency-groups].dev` only, never imported by lab code itself |
| pypowsybl | Lab 3 `spike_pypowsybl.py` (solver-comparison spike) + Lab 2 `pypowsybl_cross_check.py` (real N-1 second-opinion cross-check, via shared `labs/_shared/gridfit.py` helpers) | **MPL-2.0** | license-verified from installed metadata (`pypowsybl==1.16.1`); a genuine second MPL-2.0 component alongside DPsim, not spike-only anymore — full comparison write-up and conclusions: [`docs/POWERFLOW_ENGINE_SHOOTOUT.md`](POWERFLOW_ENGINE_SHOOTOUT.md) |

### The distinction that keeps the policy honest

- **Golden-path *library/API* surface**: permissive (BSD/MIT/Apache) with DPsim and pypowsybl as
  two documented MPL-2.0 exceptions (both file-level copyleft only, both foundation-backed —
  DPsim/RWTH Aachen, pypowsybl/RTE).
- **External CLIs used for display/rendering** (mpv, chafa, ffmpeg): copyleft,
  fine — they are subprocess-invoked tools, never linked into the deliverable.
- **Data**: CC-BY-4.0 (CSIRO) and MIT (AEMO constraints vendor) carry their own
  attribution terms, preserved in the fetch/vendoring paths.

New golden-path dependencies MUST satisfy the policy (foundational +
permissive OSI license, or a documented exception); record the license at the
point of adoption.

## One waveform state machine generates every view

The single source of truth for a fault event is the ordered 3-phase
instantaneous-voltage state sequence (`labs/05-.../phase_model.py`,
`ThreePhaseWaveform`). Raw 5 kHz, C37.118 phasors, positive sequence, SCADA
RMS, and the anomaly signal are all *generated* from that one model — no view
re-implements its own math, so they can never disagree about what the waveform
was. See `phase_model.py`'s docstring for the PSCADOSSE framing.

## Generative design & agent skills (ambition, adjacent to the open PowerAgent ecosystem)

High-level, domain-specific, idiomatic abstracts modeled on PSCAD-style
component/template patterns, expressed in the open stack (pandapower/DPsim),
accompanied by loadable agent skills — sitting adjacent to the open-source
PowerAgent ecosystem (PowerAgentBench is already referenced in
`benchmarks/README.md`). This is the stated direction; the concrete seeds so
far are `phase_model.py` (one-source-of-truth generation) and the telemetry
views that consume it.

## Local Grafana live dashboard (future direction)

The same feeds the animations render — raw 5 kHz, C37.118 100 Hz phasors +
positive sequence, SCADA/EMS 4 s — should ultimately appear as **live panels on
a local Grafana server** (deployed as a pod via `podman kube play`; not yet
installed). Planned shape:

```
phase_model (ThreePhaseWaveform) -> ingest bridge -> time-series store -> Grafana
```

- **Datasource** (all policy-compliant, per the license map): Prometheus
  (Apache-2.0, pull model) or InfluxDB (MIT, push model) for the live feeds;
  Postgres/TimescaleDB (PostgreSQL license / Apache-2.0) or SQLite if the
  stored-log replay view matters more than live.
- **Feed fit:** the phasor 100 Hz + SCADA 4 s feeds are the natural Grafana
  panels (light, live). The raw 5 kHz feed is heavy for a dashboard — plan to
  decimate or keep it in the scope animations, not Grafana.
- **Licensing note:** Grafana itself is **AGPL-3.0** (strong copyleft). It is
  an external service, not linked into the golden-path API surface — the same
  category as the display CLIs — so it does not change the golden-path posture,
  but it should be recorded at adoption like any other component.

## Distribution & performance: a common ring buffer, lock per consumer

Distribution of the live feeds is a **single common ring buffer** the producer
(a live DPsim solve, or the log replay) writes time-indexed samples into.
Every consumer — raw 5 kHz view, C37.118 phasor feed, SCADA/EMS, the anomaly
classifier, and the future Grafana bridge — holds **its own read cursor /
lock**, so one slow consumer lags on its own cursor without blocking the
producer or its peers. The derived feeds remain *transforms of the same ring*
(phasor = decimation + one-cycle DFT; SCADA = aggregation), preserving the
one-source-of-truth principle from the state machine.

## Rust preference & the oxidation roadmap

At some point the hot path **prefers Rust over Python** for performance and
hardware customization. The phase-model types currently in `phase_model.py`
(ThreePhaseWaveform, the per-consumer-cursor ring buffer, the C37.118 phasor /
positive-sequence transforms) are the intended first **oxidized** crates —
consumed from Python via PyO3, or directly by the classifier / Grafana bridge.

**Status:** the first oxidized crate is done — `rust/phase-model`
(MIT OR Apache-2.0) ports the Python state machine, ring buffer, and phasor
transforms; its `real_log_matches_python` test proves the numbers are
bit-consistent with Python on the real DPsim log, and it compiles to
`wasm32-unknown-unknown` (`just rust-test` / `just rust-wasm`).

**Dynamic browser dashboard (the "Vue-in-Rust" direction):** the static
`scripts/demo_index.html` page is a stopgap. The target is a **Dioxus** app
(rsx DSL, WASM target, canvas/WebGL rendering; MIT/Apache-2.0 — golden-path
compliant) that loads the `phase-model` WASM and runs the simulation
client-side: it fetches the real log JSON, computes phasors/sequence/SCADA in
the browser, and streams the feeds to canvas — dynamic, not static. The
static page stays until the Dioxus bundle replaces it.

**Revision of VISION §8 ("We are **not** writing a new Rust crate"):** that
stance was written for the parsing layer — `powerio` already covers it, so the
golden path still consumes `powerio` and does not fork it. The oxidation
roadmap **supersedes §8 for the ring-buffer / hot-path layer**: a first-party
Rust crate (e.g. `phase-model-rs`) is the intended future there. This is an
explicit revision decision, not a silent change.
