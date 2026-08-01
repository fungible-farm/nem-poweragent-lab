# Lab 5 — SPARTAN Chaos-Net: Transient Streams via DPsim + VILLASnode

Status: **spec only**. Own file, same reason as Lab 4: this lab has a different risk/dependency
profile from Labs 1–3 (it's about EMT-domain transient simulation and real-time streaming
infrastructure for an external edge-ML project, not steady-state power-flow agent orchestration),
and its Definition of Done is deliberately split into a laptop-portable core and an
optional-hardware extension — see §6.

## Why this lab, and why it's different from Labs 1–4

Labs 1–4 are all steady-state (power-flow / OPF / contingency) exercises, and their inputs are
either fully synthetic or, for Lab 4, real market data reconciled against a synthetic topology —
but always at the dispatch-interval timescale (5 minutes), never the waveform timescale. SPARTAN
is an edge PMU anomaly-detection system (Radxa Dragon Q8B, DirectML — that board is Qualcomm
Snapdragon 8cx Gen 3 silicon, the same chip family Windows-on-ARM devices use, which is why
DirectML is the natural inference path there) that needs realistic 4kHz-class raw waveform
streams — voltage/current sampled values, not phasor reports — from many independent substation
nodes in network topologies that are deliberately, continuously breaking. This lab exists to
generate that: a "chaos-net" of procedurally generated grid topologies, each running a continuous
schedule of faults and switching events, streamed out per-substation at ADC-rate fidelity to
SPARTAN's data recorder. It is also the lab that most directly demonstrates the cited paper's
"rising frequency of extreme weather events... escalating demands on power grids" framing
(`docs/VISION.md` §1) — not as a retrospective case study (Lab 4, Part C) but as a live, endlessly
regenerating stress-test feed.

## Architecture

```
┌────────────────────────────────────────────────────────────────────────────────┐
│  Chaos-net topology generator (Python, uv)                                     │
│  SimBench seed grids ──▶ NetworkX procedural graph perturbation ──▶ pandapower/ │
│  DPsim network build — a new topology instance per run, not a fixed case        │
└───────────────────────────────────┬──────────────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│  DPsim (C++/Python, MPL 2.0) — one network-wide EMT solve, 50µs-class timestep  │
│  Fault/event schedule (line trip, fault, load step: target, trigger time,      │
│  duration — a "countdown" the schedule file states explicitly) drives DPsim's  │
│  switch/breaker components at runtime                                          │
└───────────────────────────────────┬──────────────────────────────────────────────┘
                                    ▼  (per-substation V/I taps, one network-wide solve)
┌────────────────────────────────────────────────────────────────────────────────┐
│  VILLASnode (C/C++, Apache-2.0) — one pod per substation tap, podman kube play  │
│  Native IEC 61850 Sampled Values / GOOSE node-type — same SV lineage as         │
│  OpenPMU's own DAQ→PhasorEstimation transport, so no bespoke wire format        │
└───────────────────────────────────┬──────────────────────────────────────────────┘
                                    ▼
                     SPARTAN data recorder (Radxa Dragon Q8B)
        (Phase 2: becomes the detector — out of scope for this lab)
```

## Components (nothing hand-rolled that already exists)

| Need | Tool | Note |
|---|---|---|
| Procedurally varied substation topologies | [SimBench](https://github.com/e2nIEE/simbench) (seed grids, pandapower-native) + NetworkX random-graph generators (`watts_strogatz_graph`, `barabasi_albert_graph`) for the actual "chaos-net" variation | SimBench supplies realistic parameter distributions so procedurally generated topologies aren't arbitrary; NetworkX supplies the graph structure |
| EMT-domain transient simulation at 4kHz-class rates | [DPsim](https://github.com/sogno-platform/dpsim) (RWTH Aachen, MPL 2.0) | Real-time-capable power-flow / dynamic-phasor / EMT solver, deterministic time steps down to 50µs — well inside the 4kHz (250µs) requirement. One network-wide solve, not N independent per-node simulators. |
| Fault/event scheduling ("problems spawn and countdown") | DPsim's own switch/breaker components, driven by a plain schedule file (target, trigger time, duration) | Same "deterministic scripting" discipline as every other lab — the schedule is a committed, readable file, not implicit in code |
| Real-time multi-protocol streaming, per-substation fan-out | [VILLASnode](https://github.com/VILLASframework/node) (RWTH Aachen / FEIN Aachen, Apache 2.0) | ~18 supported protocols including **IEC 61850 Sampled Values/GOOSE**, ZeroMQ, MQTT, WebSockets, shared memory; ships as an OCI container; DPsim's own documentation names VILLASnode as its recommended external-interface path — this is not a novel integration, it's the documented one |
| SPARTAN-facing hop | VILLASnode's IEC 61850 SV node-type directly, if SPARTAN's recorder can consume it — check this **first** | Only if SPARTAN's recorder specifically requires gRPC or Cap'n Proto rather than accepting IEC 61850 SV/WebSocket/MQTT: VILLASnode's plugin architecture (`plugins/` in its own source tree) supports a custom node-type as the one, narrowly-scoped last-mile adapter — everything upstream of that hop still stays on VILLASnode's native routing, so the custom code is a thin edge, not a rebuilt gateway |
| Composition/runtime | `podman kube play`, same as every other lab | One VILLASnode pod per substation tap, one DPsim pod for the network-wide solve |

## Why VILLASnode over a hand-rolled Rust gRPC/Cap'n Proto bridge

The original sketch of this lab (see conversation leading here) proposed building a Rust `tonic`/
`capnp-rpc` adapter reading DPsim's output directly. VILLASnode replaces that plan outright:

- It's the tool DPsim's own documentation already names for external interfacing — using it isn't
  a new integration to validate, it's the documented path.
- Its native **IEC 61850 Sampled Values** node-type is the same SV lineage OpenPMU's own
  DAQ→Telecoms transport already speaks — meaning if SPARTAN's recorder was built against
  OpenPMU-shaped data, VILLASnode may require *no* custom node-type at all.
- It ships as an OCI container, which drops straight into this repo's existing `podman kube play`
  composition pattern rather than introducing a new one.
- The only place bespoke code might still be needed is a single, narrow last-mile node-type if
  SPARTAN's recorder insists on gRPC/Cap'n Proto specifically — check whether it can just consume
  IEC 61850 SV, WebSocket, or MQTT before writing that.

## Definition of Done for this lab (deliberately split — see rationale above)

**Laptop-portable core (required):**
- [ ] The chaos-net generator produces a new topology instance (SimBench seed + NetworkX
      perturbation) on each run, loadable by both pandapower (for a sanity power-flow check) and
      DPsim (for the EMT solve).
- [ ] DPsim runs the network-wide EMT solve at a 4kHz-class (≤250µs) timestep against at least one
      generated topology, with at least one scheduled fault/switching event firing mid-run and a
      "countdown" printed/logged before it fires.
- [ ] A VILLASnode pod (via `podman kube play`) receives DPsim's per-substation taps and re-emits
      them as IEC 61850 Sampled Values, verified by a stub/mock receiver (not real SPARTAN
      hardware) that confirms the stream's rate and field shape.
- [ ] This entire pipeline runs on a laptop with no Radxa hardware present — the "SPARTAN data
      recorder" endpoint is a stub for this DoD tier.

**Hardware-validated extension (optional, separately gated):**
- [ ] The same pipeline validated end-to-end against an actual Radxa Dragon Q8B running the real
      SPARTAN data recorder, confirming the stream is ingestible as-is (or documenting exactly
      what last-mile node-type was needed).

**Caveats, stated in this lab's own step-by-step section, not only here:** this lab does not
implement or claim to reproduce SPARTAN's anomaly-detection logic — that is explicitly a
subsequent phase and out of scope. It also does not claim any of the generated "chaos-net"
topologies correspond to a real substation network — they are procedurally generated stress
scenarios, not a model of any specific real asset.

## Step-by-step walkthrough (presenter / backup script)

1. **`uv run labs/05-spartan-chaosnet-transient-stream/generate_topology.py --seed 42`**
   — You should see: `Seeded from simbench code 1-MV-rural--0-sw, perturbed: 14 buses, 17 lines,
   3 substations tagged as tap points` — a different topology on a different seed.
   — *Backup if unavailable*: the committed `sample_topology.json` fixture, printed with the same
   framing.
2. **`uv run labs/05-spartan-chaosnet-transient-stream/run_dpsim.py --schedule chaos_schedule.yaml`**
   — You should see: `EMT solve running at 200us timestep` followed by, mid-run,
   `[T+00:42] fault scheduled at substation SUB-3 in 8s... 7... 6...` counting down, then
   `FAULT INJECTED: SUB-3 line-to-ground, clearing in 150ms`.
   — Why it matters: this is "problems spawn and countdown" made literal — a deterministic,
   readable schedule file driving a real physics solve, not a random crash.
3. **`podman kube play kube/villasnode-tap-pod.yaml --replace`** (one per tagged substation)
   — You should see: `villasnode: node 'sub-3-tap' active, IEC61850-SV output on <address>`.
   — Why it matters: this is the same "one pod per tap, scale with the topology" pattern as every
   other lab's fan-out, just applied to substations instead of contingencies or providers.
4. **`uv run labs/05-spartan-chaosnet-transient-stream/verify_stream.py --node sub-3-tap`**
   — You should see: a short summary — sample rate achieved, channel count, a plot of the fault
   transient's voltage sag and recovery — confirming the stream is what SPARTAN's recorder would
   receive, without needing the physical board present.
   — *Backup if the live pods aren't reachable*: the committed `sample_stream_summary.json` plus a
   pre-rendered plot, narrated the same way.
5. **(hardware-validated extension only)**: point the VILLASnode tap at the real Radxa Dragon Q8B
   endpoint and confirm SPARTAN's recorder ingests the stream unmodified — this step needs the
   physical board and is not part of the laptop-portable walkthrough above.
