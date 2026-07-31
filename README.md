# nem-poweragent-lab

PowerAgent Tutorial — AEMO Labs

A training lab (not a product pitch) demonstrating deterministic, agent-driven power-system
workflows against a real NEM network model, running entirely on local, open-source components.

**Start here: [`docs/VISION.md`](docs/VISION.md)** for the full plan — ecosystem map, architecture,
Labs 1–3 (simple/medium/advanced), and the reasoning behind every technology choice.

**Real data: [`docs/LAB4_AEMO_REAL_DATA.md`](docs/LAB4_AEMO_REAL_DATA.md)** — Lab 4, the one lab
that pulls actual historical AEMO market data instead of synthetic inputs, in its own file since
it carries its own risk profile and caveats.

**Then: [`docs/DEFINITION_OF_DONE.md`](docs/DEFINITION_OF_DONE.md)** for the checklist this repo
is being built against.

## Status

Planning complete, implementation not yet started. Every directory below currently contains a
`README.md` describing what will go there — see each for its spec, including a step-by-step
walkthrough written to double as a presenter/backup script if a live run isn't available:

- `labs/01-simple-loadflow-fit/` — single-agent load-flow parameter fit
- `labs/02-medium-interconnection-screening/` — Agent Framework Sequential+Concurrent asset
  provisioning screen
- `labs/03-advanced-provider-bakeoff/` — multi-provider, Podman-scaled benchmark bake-off
- `labs/04-aemo-digital-twin-reconciliation/` — real AEMO dispatch data reconciled against the
  synthetic network, plus a constraint-equation literacy exercise
- `kube/` — `podman kube play` manifests for the local LLM server and PowerMCP tool server
- `benchmarks/` — deterministic scoring harness
- `scripts/` — data fetch + asciinema recording

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
[NEM_constraints](https://github.com/susantoj/NEM_constraints)

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
