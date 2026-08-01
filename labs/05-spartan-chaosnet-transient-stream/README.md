# Lab 5 — SPARTAN Chaos-Net: Transient Streams via DPsim + VILLASnode

> Status: **spec only** — full concept, architecture, and Definition of Done live in
> [`docs/LAB5_SPARTAN_CHAOSNET.md`](../../docs/LAB5_SPARTAN_CHAOSNET.md). This README is the
> lab-local summary.

## What you'll do (summary)

- Procedurally generate a new "chaos-net" grid topology each run (SimBench seed grids + NetworkX
  graph perturbation).
- Run a network-wide EMT-domain transient solve in [DPsim](https://github.com/sogno-platform/dpsim)
  at a 4kHz-class timestep, driven by a scheduled fault/switching-event file that counts down
  before each event fires.
- Stream each tagged substation's voltage/current samples out via a
  [VILLASnode](https://github.com/VILLASframework/node) pod (one per substation, native IEC 61850
  Sampled Values — the same lineage OpenPMU's own transport speaks), toward SPARTAN's data
  recorder.

**Definition of Done is split**: the full pipeline must run on a laptop with no physical hardware
(a stub receiver stands in for SPARTAN), and validation against the real Radxa Dragon Q8B is a
separate, optional, hardware-gated extension — see the design doc for why.

**Two things this lab does not claim**: it does not implement or reproduce SPARTAN's
anomaly-detection logic (a subsequent phase, out of scope here), and none of the generated
topologies correspond to a real substation network — they're procedurally generated stress
scenarios.

## Why an AEMO modeller should care

Every other lab in this repo works at the dispatch-interval timescale. This one is the waveform
timescale — the level actual protection and PMU-based monitoring systems operate at — and it shows
the same "deterministic scripting" discipline (a readable fault schedule, not a random crash;
composed, not hand-built, tooling) applied to generating labeled stress-test data for an edge
anomaly detector, rather than to an LLM-agent workflow.

## Step-by-step walkthrough (presenter / backup script)

See `docs/LAB5_SPARTAN_CHAOSNET.md` §"Step-by-step walkthrough" for the full numbered sequence
(topology generation → DPsim EMT solve with a live fault countdown → VILLASnode tap →
stream verification), including the backup fixtures to narrate from if a live run isn't available.
