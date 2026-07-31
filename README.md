# nem-poweragent-lab

PowerAgent Tutorial — AEMO Labs

A training lab (not a product pitch) demonstrating deterministic, agent-driven power-system
workflows against a real NEM network model, running entirely on local, open-source components.

**Start here: [`docs/VISION.md`](docs/VISION.md)** for the full plan — ecosystem map, architecture,
Labs 1–3 (simple/medium/advanced), and the reasoning behind every technology choice.

**Real data: [`docs/LAB4_AEMO_REAL_DATA.md`](docs/LAB4_AEMO_REAL_DATA.md)** — Lab 4, the one lab
that pulls actual historical AEMO market data instead of synthetic inputs, in its own file since
it carries its own risk profile and caveats.

**Transient/edge: [`docs/LAB5_SPARTAN_CHAOSNET.md`](docs/LAB5_SPARTAN_CHAOSNET.md)** — Lab 5,
EMT-domain 4kHz-class transient streams from procedurally generated grid topologies, feeding
SPARTAN (an external edge PMU anomaly-detection project) via DPsim + VILLASnode. Its own file for
the same reason as Lab 4 — different risk profile, and a Definition of Done split between a
laptop-portable core and an optional hardware-validated extension.

**Then: [`docs/DEFINITION_OF_DONE.md`](docs/DEFINITION_OF_DONE.md)** for the checklist this repo
is being built against.

## Status

**Labs 1-3 are implemented and self-checking.** Run the whole thing end to end, with proof:

```
./scripts/run_labs_1_3.sh
```

That one committed script — not a transcript of anyone running commands by hand — is the proof
these labs work: it fetches the real CSIRO case data, runs every step of Labs 1-3, runs the pytest
suite, and prints a final PASS/FAIL summary. Every lab's `README.md` documents where this sandbox's
implementation deviates from `docs/VISION.md`'s full spec (no `podman`, no live local LLM server —
see each lab's "Sandbox notes" section for exactly what stands in for what, and why).

- `labs/01-simple-loadflow-fit/` — **implemented.** Single-agent load-flow parameter fit against
  real CSIRO `snemSA.m` data.
- `labs/02-medium-interconnection-screening/` — **implemented.** Sequential + genuinely-concurrent
  N-1 contingency screen against real CSIRO `snem1803.m` data, with a human-in-the-loop memo gate
  that actually blocks.
- `labs/03-advanced-provider-bakeoff/` — **implemented.** 3 task families × 3 provider stand-ins +
  a non-agentic forecasting-baseline row, scored into a committed, diffable scorecard.
- `labs/04-aemo-digital-twin-reconciliation/` — spec only, not yet built (see its own `README.md`).
- `labs/05-spartan-chaosnet-transient-stream/` — spec only, not yet built (see its own `README.md`).
- `kube/` — `benchmark-runner-job.yaml` is a written, valid (not yet podman-executed in this
  sandbox) Job manifest for Lab 3; the LLM-server/PowerMCP pods remain spec only.
- `benchmarks/` — `power-agent-bench-lite/results/scorecard.json` is Lab 3's real, committed output.
- `scripts/` — `fetch_csiro_nem_data.py` and `run_labs_1_3.sh` are real; `record_asciinema_demo.sh`
  is not yet built.

## What this is built from (all upstream, none of it written here)

[pandapower](https://www.pandapower.org/) ·
[powerio](https://github.com/eigenergy/powerio) (Rust) ·
[PowerFM](https://github.com/Power-Agent/PowerFM) ·
[PowerMCP](https://github.com/Power-Agent/PowerMCP) ·
[PowerSkills](https://github.com/Power-Agent/PowerSkills) ·
[PowerWF](https://github.com/Power-Agent/PowerWF) ·
[Microsoft Agent Framework](https://github.com/microsoft/agent-framework) ·
[llama.cpp](https://github.com/ggml-org/llama.cpp) ·
[CSIRO Synthetic-NEM-2000-Bus](https://github.com/csiro-energy-systems/Synthetic-NEM-2000bus-Data) ·
[NEMOSIS](https://github.com/UNSW-CEEM/NEMOSIS) ·
[NEM_constraints](https://github.com/susantoj/NEM_constraints) ·
[DPsim](https://github.com/sogno-platform/dpsim) ·
[VILLASnode](https://github.com/VILLASframework/node) ·
[SimBench](https://github.com/e2nIEE/simbench)

Package management: `uv` only. No cloud LLM keys. No commercial power-system engines on the
golden path. No `b00t`.

## Citation

This lab is a runnable implementation of the roadmap in:

> Q. Zhang and L. Xie, "PowerAgent: A Road Map Toward Agentic Intelligence in Power Systems:
> Foundation Model, Model Context Protocol, and Workflow," *IEEE Power and Energy Magazine*,
> vol. 23, no. 5, pp. 93–101, Sept.–Oct. 2025.
> [IEEE Xplore](https://ieeexplore.ieee.org/document/11131348/) ·
> [open-access preprint](https://www.techrxiv.org/doi/full/10.36227/techrxiv.174918210.07854858/v1) ·
> [poweragent.seas.harvard.edu](https://poweragent.seas.harvard.edu/)

See `docs/VISION.md` §1 for how the paper's three named pillars (Foundation Model / Model Context
Protocol / Workflow) map onto PowerFM / PowerMCP / PowerWF-and-PowerSkills, and onto this repo's
labs.
