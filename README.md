# nem-poweragent-lab

**PowerAgent Tutorial.** Six hands-on labs that use AI agents to do the kind of thing a power-grid
engineer does by hand: load a model of the grid, run a simulation, check whether anything is
overloaded, write a report. Every number in every lab comes from a real calculation against real
(or realistically synthetic) grid data — nothing is faked to look plausible.

## Concepts, in plain terms

You don't need a power-systems background to follow these labs. Here's everything you need, in
one place, so each lab doesn't have to re-explain it:

- **Grid / network** — generators, transformers, and loads (homes, factories) connected by
  transmission lines. A **bus** is just a connection point, like an intersection in a road network.
- **Power flow (a.k.a. load flow)** — the calculation of how much current flows on every line and
  what the voltage is at every bus, given how much power each generator is producing and each load
  is consuming. This is the single most common calculation in power engineering; every lab here
  runs it via [pandapower](https://www.pandapower.org/), a real open-source power flow solver.
- **Per-unit (pu) voltage** — voltage expressed as a fraction of what's normal for that point in
  the grid, so `1.00 pu` means "exactly nominal," `0.95 pu` means "5% low." Grids are normally kept
  within a narrow band (typically 0.90–1.10 pu) — outside that, equipment can misbehave or trip
  offline.
- **MW vs. MVA** — MW (megawatts) is real power, the kind that actually does work (spins a motor,
  lights a bulb). MVA (megavolt-amps) is total electrical capacity, including a "reactive"
  component that flows back and forth without doing useful work but that cables and transformers
  still have to be sized to carry.
- **N-1 contingency screening** — checking "if any single line or generator suddenly dropped out
  right now, would anything else overload?" Grid operators require the answer to always be no —
  a single failure should never cascade. Lab 2 runs a real one.
- **Interconnector** — a major transmission line joining two separate grid regions (e.g. South
  Australia to Victoria), so power can flow between them.
- **Transient vs. steady-state** — most of these labs assume the grid has already settled into a
  stable state and just solve for the numbers there ("steady-state"). Lab 5 instead looks at
  **transients**: the physics in the first fraction of a second after something goes wrong (a
  fault), sampled thousands of times per second, before the grid settles back down or protection
  equipment intervenes.
- **MCP (Model Context Protocol)** — a standard way for an AI agent to call an external tool over
  a network connection, conceptually similar to a REST API but designed for AI agents. One of the
  three pillars this repo's [source paper](#citation) is built around.

## The seven labs

Every lab uses real public data (CSIRO's Synthetic-NEM-2000-Bus grid model, real historical AEMO
market data, or a real physics solver), checks its own result against a known-good answer, and has
its own tutorial `README.md` plus a `Containerfile` to run it with zero local setup.

| Lab | What it shows | Real data / physics |
| --- | --- | --- |
| [`01-simple-loadflow-fit`](labs/01-simple-loadflow-fit/) | fitting a model parameter to match a field measurement | real `pandapower.runpp()` against CSIRO `snemSA.m` |
| [`02-medium-interconnection-screening`](labs/02-medium-interconnection-screening/) | N-1 contingency screening + a human approval gate | real `pandapower.runpp()` against CSIRO `snem1803.m` |
| [`03-advanced-provider-bakeoff`](labs/03-advanced-provider-bakeoff/) | scoring different AI "providers" against the same tasks | 3 task families, real scored comparison |
| [`04-aemo-digital-twin-reconciliation`](labs/04-aemo-digital-twin-reconciliation/) | comparing a model's prediction against what the real grid actually did | real live AEMO market-data pull, real `pandapower.runpp()` |
| [`05-spartan-chaosnet-transient-stream`](labs/05-spartan-chaosnet-transient-stream/) | millisecond-scale fault physics + a real corrective controller | real 200µs-timestep physics solve (DPsim), real streaming pipeline |
| [`06-sysml-digital-thread`](labs/06-sysml-digital-thread/) | evaluating SysML v2/MBSE for AI-workflow and grid-topology modelling | real repo inventory (Track A) + a real bus/generator/line cluster from CSIRO `snemSA.m` (Track B) |
| [`07-rust-comtrade-fft-detector`](labs/07-rust-comtrade-fft-detector/) | an independent Rust FFT detector reading back a real relay/DFR file format | real `realfft`/`rustfft` FFT, real COMTRADE (IEEE C37.111) file round trip |
| [`08-cim-gridy-phase0-spikes`](labs/08-cim-gridy-phase0-spikes/) | five real-tool spikes answering cim-gridy's Phase-0 technology questions | real Grid2Op episode on CSIRO `snemSA.m`, real SysML v2 parsers, real `ufo-types`/`scryer-prolog` build |
| [`09-cim-gridy-phase1-3-vertical-slice`](labs/09-cim-gridy-phase1-3-vertical-slice/) | one minimal grid-operator mission end to end: Grid2Op → Bevy → SysML v2 → ontology/constraint → mission FSM → DARE optimizer | real Grid2Op N-1 trip/reclose on CSIRO `snemSA.m`, real `scryer-prolog` proof search |

Start with [`docs/VISION.md`](docs/VISION.md) for the full architecture and the reasoning behind
each technology choice. [`docs/DEFINITION_OF_DONE.md`](docs/DEFINITION_OF_DONE.md) is the checklist
this repo is built against, and [`docs/PSCADOSSE.md`](docs/PSCADOSSE.md) covers the open-source
licensing policy.

**Solver evaluation: [`docs/POWERFLOW_ENGINE_SHOOTOUT.md`](docs/POWERFLOW_ENGINE_SHOOTOUT.md)** —
cross-validates pandapower (this repo's golden-path solver) against PowSyBl/pypowsybl on the same
real CSIRO case and the same real N-1 screen (Labs 2/3): both engines agree, and two real
pypowsybl import defects were found and fixed along the way.

## Install

```
./install.sh
```

One command: installs `uv` if missing (requires `podman` to already be present — installs
distro-specific instructions if it isn't), fetches the CSIRO case data, syncs dependencies, brings
up two local support services, and finishes with a pass/fail smoke test. A cached re-run takes well
under a minute; a fully cold run (dominated by a one-time ~2.3GB model download) takes a few
minutes.

`just --list` is the full command index (install, sync, fetch, per-lab checks, per-lab walkthrough
steps, and a few in-terminal chart/animation viewers for SSH-only sessions).

## Running the labs in a container

If you'd rather not install this repo's toolchain natively — or you're on Windows — every lab has
its own `Containerfile`, built on one shared base image so the (fairly large) dependency install
only happens once:

```
podman build -t nem-poweragent-base:local -f Containerfile.base .
podman build -t lab1:local -f labs/01-simple-loadflow-fit/Containerfile .
podman run --rm lab1:local
```

Repeat the last two lines per lab — each lab's own README has its exact image name and commands.
`docker` works identically anywhere this doc says `podman`; a `Containerfile` is plain OCI build
syntax, read the same way by either tool.

**On Windows**, Docker Desktop and Podman Desktop both run these `Containerfile`s exactly as shown
above via a WSL2 backend. This is the recommended path for **Lab 5** specifically — its physics
engine (DPsim) only ships Linux wheels at the version this repo uses, so the container is the
simplest way to run it on Windows. Labs 1–4 have no such restriction and also work with a native
`uv sync` on Windows.

## Connecting to the MCP servers

Two MCP servers exist in this repo:

**`codebase-memory`** — a tool for exploring this codebase's own structure (which function calls
what, etc.), registered in `.mcp.json` for any MCP-aware coding assistant. Not part of any lab.

**`powermcp-pandapower`** — the lab's own power-flow tool server, exposing `run_power_flow`,
`run_contingency_analysis`, `load_network_from_any`, and more over the network (streamable-HTTP).
`./install.sh` brings it up automatically; standalone:

```
podman build -t powermcp-pandapower:local -f Containerfile.powermcp .
podman kube play kube/powermcp-pandapower-pod.yaml   # mounts data/ at /data (read-only), port 8001
```

Then connect with any MCP client:

```python
import asyncio, json
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    async with streamablehttp_client("http://127.0.0.1:8001/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            print([t.name for t in (await s.list_tools()).tools])
            await s.call_tool("load_network_from_any", {"file_path": "/data/snemSA.m"})
            res = await s.call_tool("run_power_flow", {})
            print(json.loads(res.content[0].text)["status"])

asyncio.run(main())
```

Tear down with `podman kube play --down kube/powermcp-pandapower-pod.yaml`. Full details, including
the one transport limitation (this MCP server's own CLI only speaks the older stdio transport, so
this pod runs a small wrapper on top — see `kube/README.md`), are in `kube/README.md`.

Note that Labs 1–3's own scripts don't call this pod yet — they compute their power flow results by
calling `pandapower` directly in-process. The pod exists and works; wiring the labs to call it over
the network instead is a real, documented follow-up, not done here (see each lab's own README).

## Status

| Lab | Status | Real data |
| --- | --- | --- |
| `01-simple-loadflow-fit` | implemented | CSIRO `snemSA.m` |
| `02-medium-interconnection-screening` | implemented | CSIRO `snem1803.m` |
| `03-advanced-provider-bakeoff` | implemented | 3 task families, real scoring |
| `04-aemo-digital-twin-reconciliation` | implemented (Parts A, B, optional C) | live AEMO NEMWeb pull via NEMOSIS |
| `05-spartan-chaosnet-transient-stream` | implemented (laptop-portable core) | real DPsim EMT solve, real VILLASnode pod |
| `06-sysml-digital-thread` | implemented (both tracks) | real repo inventory + real CSIRO `snemSA.m` cluster |

All four `kube/` pod manifests (`llamacpp-phi-pod.yaml`, `powermcp-pandapower-pod.yaml`,
`villasnode-tap-pod.yaml`, `benchmark-runner-job.yaml`) are real and have been run with
`podman kube play` — see `kube/README.md` for each one's notes, including the one `podman kube play`
limitation found along the way (v5.4.2 doesn't implement Kubernetes Job's `completions`/
`parallelism` fields, so `benchmark-runner-job.yaml` runs as a single pod rather than a
partitioned matrix — worked around with directly-launched containers instead).

`labs/03-advanced-provider-bakeoff/expected_scorecard.json` is the committed, diffable result
fixture; `benchmarks/power-agent-bench-lite/results/` holds the regenerated (gitignored) output
from actually running it.

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
golden path.

## Citation

This lab is a runnable implementation of the roadmap in:

> Q. Zhang and L. Xie, "PowerAgent: A Road Map Toward Agentic Intelligence in Power Systems:
> Foundation Model, Model Context Protocol, and Workflow," *IEEE Power and Energy Magazine*,
> vol. 23, no. 5, pp. 93–101, Sept.–Oct. 2025.
> [IEEE Xplore](https://ieeexplore.ieee.org/document/11131348/) ·
> [open-access preprint](https://www.techrxiv.org/doi/full/10.36227/techrxiv.174918210.07854858/v1) ·
> [poweragent.seas.harvard.edu](https://poweragent.seas.harvard.edu/)

The paper names three pillars — Foundation Model, Model Context Protocol, and Workflow — which map
onto PowerFM, PowerMCP, and PowerWF/PowerSkills respectively, and onto this repo's labs. See
`docs/VISION.md` §1 for the full mapping.
