# nem-poweragent-lab

PowerAgent Tutorial — AEMO Labs

A training lab (not a product pitch) demonstrating deterministic, agent-driven power-system
workflows against a real NEM network model, running entirely on local, open-source components.

## Summary

Five runnable labs, each against real public data (CSIRO's Synthetic-NEM-2000-Bus MATPOWER case,
real historical AEMO NEMWeb market data, or a real DPsim EMT solve), each self-checking (a
`--step check` that diffs against a committed fixture, plus a `test_labN.py`), and each with its
own tutorial `README.md` and its own `Containerfile`:

| Lab | What it shows | Real data / physics |
| --- | --- | --- |
| [`01-simple-loadflow-fit`](labs/01-simple-loadflow-fit/) | single-agent load-flow parameter fit | real `pandapower.runpp()` against CSIRO `snemSA.m` |
| [`02-medium-interconnection-screening`](labs/02-medium-interconnection-screening/) | concurrent N-1 contingency screen + human-in-the-loop memo gate | real `pandapower.runpp()` against CSIRO `snem1803.m` |
| [`03-advanced-provider-bakeoff`](labs/03-advanced-provider-bakeoff/) | provider × task-family scoring harness | 3 task families, real scored comparison |
| [`04-aemo-digital-twin-reconciliation`](labs/04-aemo-digital-twin-reconciliation/) | digital-twin reconciliation against live AEMO market data | real live NEMWeb pull via NEMOSIS, real `pandapower.runpp()` |
| [`05-spartan-chaosnet-transient-stream`](labs/05-spartan-chaosnet-transient-stream/) | EMT-domain transient streaming + a real grid-forming stabilizer | real DPsim 200µs-timestep EMT solve, real VILLASnode pod |

Every lab is runnable two ways, documented in that lab's own `README.md`: natively via `uv run`
(fastest, needs this repo's own toolchain — see Install below), or in a container via that lab's
own `Containerfile` (no local Python/DPsim/pandapower install at all — see "Running the labs in a
container" below, and especially the note there for Windows users).

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

**Governance: [`docs/PSCADOSSE.md`](docs/PSCADOSSE.md)** — the golden-path licensing policy and the
"one waveform state machine generates every view" principle for Australian NEM capability.

**Solver evaluation: [`docs/POWERFLOW_ENGINE_SHOOTOUT.md`](docs/POWERFLOW_ENGINE_SHOOTOUT.md)** —
cross-validates pandapower (this repo's golden-path solver) against PowSyBl/pypowsybl on the same
real CSIRO case and the same real N-1 screen (Labs 2/3): both engines agree, and two real
pypowsybl import defects were found and fixed along the way.

## Install

```
./install.sh
```

One command, checks-then-acts (never silently reinstalls `uv`/`cargo`/`podman` if already
present): installs `uv` if missing, requires `podman` to already be present (prints distro
install instructions and stops otherwise — this script does not install a container runtime with
root on your behalf), `uv sync`, fetches the CSIRO case data and the Phi-4-mini-instruct GGUF,
brings up the `llamacpp-phi-pod` and `powermcp-pandapower-pod` pods via `podman kube play`, and
finishes with `scripts/install_smoke_test.py` — a real chat completion through the LLM pod and a
real `pandapower.runpp()` through the MCP pod, printing a final `PASS`/`FAIL` line. Measured on
this build machine: **~43s on a re-run** with everything already cached, **~4m30s** on a fully
cold run (dominated by the one-time ~2.3GB GGUF download over this machine's link — see
`docs/VISION.md` §10 for the full step list).

`install.sh` also best-effort installs the demo/display tools `mpv` + `chafa` (step 7; non-fatal —
the labs don't need them). The canonical per-command path is the scoped-sudoers authorized-script
boundary: `scripts/deploy_demo_tools.sh` is the only NOPASSWD root surface (granted by
`scripts/sudoers.d/nem-poweragent-lab` via `just authorize`), and `just deploy` runs it as root
with no password anywhere.

**`just --list` is the canonical command index** — `just sync`, `just fetch`, `just test`,
`just proof`, `just check`, per-lab walkthrough steps, `just render` (the MP4 animations), and
the zero-file-transfer display recipes `just peek <chart>` (chafa, in-terminal) and
`just watch <anim>` (mpv, windowed over WSLg/ssh -X, or `just watch-tct` in-terminal).

## Running the labs in a container

`./install.sh` above is the fastest path if your host is Linux/macOS (or WSL2) and you don't mind
a real `uv`/`podman` install. If you'd rather not install this repo's toolchain at all — or you're
on **Windows without WSL2** — every lab has its own `Containerfile` (`labs/0N-.../Containerfile`),
built on one shared base layer so the (large: DPsim, pandapower, nemosis, numba) dependency install
only happens once, not five times:

```
podman build -t nem-poweragent-base:local -f Containerfile.base .
podman build -t lab1:local -f labs/01-simple-loadflow-fit/Containerfile .
podman run --rm lab1:local
```

Repeat the last two lines per lab (`lab2`/`labs/02-.../Containerfile`, etc. — each lab's own
README has the exact commands and image name). `docker` works identically wherever this doc says
`podman` — a `Containerfile` is plain OCI build syntax, read the same way by either tool.

**Windows note.** Docker Desktop and Podman Desktop both run on Windows via a WSL2 backend and
build/run these `Containerfile`s exactly as shown above — this is the recommended Windows path,
especially for **Lab 5**: this repo's pinned `dpsim==1.2.1` ships Linux (`manylinux`) wheels only,
no native Windows wheel, so Lab 5's container is the only way to run it on Windows without setting
up WSL2 directly. Labs 1-4 have no such constraint (pandapower/nemosis/numpy/scipy all ship
Windows wheels), so a native `uv sync` on Windows works for those — but `install.sh`/`Justfile`
are POSIX shell either way, so the container path (or WSL2) is still the smoothest route for the
whole repo, not just Lab 5.

Each lab's own `README.md` has a "Running in a container" section with that lab's exact build/run
commands and what to expect.

## Connecting to the MCP servers

Two MCP servers exist in this repo, for two different consumers. If you're a codeworker (human or
agent) picking this repo up cold, read this section before either one.

**`codebase-memory` — for you, the codeworker, to explore this repo.** Registered in `.mcp.json`,
launched over stdio by any MCP-aware client (Claude Code and similar) from `codebase-memory-mcp`
on `PATH`. It's dev tooling for working *on* this codebase, not part of any lab: use its
`search_graph` / `trace_path` / `get_code_snippet` / `query_graph` tools for structural questions
("who calls this function", "what does Lab 2's workflow import") instead of grepping cold. See the
`codebase-memory` skill for query syntax. If `list_projects` fails, the handshake env is wrong —
see `AGENTS.md`'s troubleshooting table.

**`powermcp-pandapower` — the lab's own MCP tool server**, the "Model Context Protocol" pillar the
PowerAgent paper (see Citation, below) names — pandapower power-flow tools (`run_power_flow`,
`run_contingency_analysis`, `load_network_from_any`, …) exposed over streamable-HTTP, not stdio.
`./install.sh` brings it up automatically; standalone:

```
podman build -t powermcp-pandapower:local -f Containerfile.powermcp .
podman kube play kube/powermcp-pandapower-pod.yaml   # mounts data/ at /data (read-only), port 8001
```

Then connect with any MCP client — here, the official `mcp` Python SDK:

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

Tear down with `podman kube play --down kube/powermcp-pandapower-pod.yaml`. Full verified session
(real tool list, real solve output) and the one named transport limitation
(`powermcp run pandapower`'s shipped CLI only speaks stdio, so this pod runs a small committed
wrapper instead — no upstream PowerMCP source modified) are in `kube/README.md`.

**Honesty check before you assume a lab calls this pod: it doesn't, yet.** The pod is real,
built, and independently verified reachable (`kube/README.md`), but Labs 1-3's own scripts still
use in-process pandapower calls as their MCP-tool-call stand-in — rewiring them to dial the pod
above is a named, undone follow-up (see "Status" below), not a hidden gap.

**Every lab has its own case data and its own real-vs-stand-in pattern** — don't assume Lab 1's
shape generalizes. Skim the table, then read that lab's own README "Sandbox notes" section before
working in it:

| Lab | Case data | MCP / demo pattern |
| --- | --- | --- |
| `01-simple-loadflow-fit` | CSIRO `snemSA.m` | in-process `pandapower` calls stand in for the MCP tool call |
| `02-medium-interconnection-screening` | CSIRO `snem1803.m` | same stand-in, plus a real concurrent N-1 contingency screen |
| `03-advanced-provider-bakeoff` | CSIRO `snem1803.m` | 3 deterministic local policies stand in for LLM providers; scoring is real |
| `04-aemo-digital-twin-reconciliation` | CSIRO `snemSA.m` + a real live NEMWeb MMS pull via NEMOSIS | real `pandapower.runpp()` reconciliation, no stand-ins |
| `05-spartan-chaosnet-transient-stream` | procedurally generated SimBench chaos-net topology | real DPsim EMT solve + real VILLASnode pod, no stand-ins |

## Status

**Labs 1-3 are implemented and self-checking.** Run the whole thing end to end, with proof:

```
./scripts/run_labs_1_3.sh
```

That one committed script — not a transcript of anyone running commands by hand — is the proof
these labs work: it fetches the real CSIRO case data, runs every step of Labs 1-3, runs the pytest
suite, and prints a final PASS/FAIL summary. `podman`, a real Phi-4-mini-instruct pod, and a real
PowerMCP pandapower pod all now genuinely exist and run in this build environment (`./install.sh`,
`kube/llamacpp-phi-pod.yaml`, `kube/powermcp-pandapower-pod.yaml` — see `kube/README.md`), but
Labs 1-3's own scripts were not rewired this round to call them instead of their original
in-process stand-ins (a deterministic bisection policy standing in for the LLM's "propose next
trial" role, direct pandapower calls standing in for an MCP tool call) — `docs/VISION.md` §9
itself names Lab 1 as the one case where wiring in a container is intentionally *not* worth it;
Labs 2-3 rewiring to the now-real pods is a named, undone follow-up, not a sandbox impossibility.
See each lab's own `README.md` "Sandbox notes" section for exactly what stands in for what today,
and why.

- `labs/01-simple-loadflow-fit/` — **implemented.** Single-agent load-flow parameter fit against
  real CSIRO `snemSA.m` data.
- `labs/02-medium-interconnection-screening/` — **implemented.** Sequential + genuinely-concurrent
  N-1 contingency screen against real CSIRO `snem1803.m` data, a committed
  `sample_contingency_chart.png` rendering the limit checks, and a human-in-the-loop memo gate
  that actually blocks.
- `labs/03-advanced-provider-bakeoff/` — **implemented.** 3 task families × 3 provider stand-ins +
  a non-agentic forecasting-baseline row, scored into a diffable `expected_scorecard.json` fixture.
- `labs/04-aemo-digital-twin-reconciliation/` — **implemented** (Part A + Part B required, Part C
  optional — also implemented). Real `NEMOSIS` pulls of AEMO's live NEMWeb MMS archive (no fixture
  fallback needed — the live pull worked), a committed auditable DUID→synthetic-generator mapping,
  a real `pandapower.runpp()` reconciliation against real interconnector flow (honestly scored
  FAIL against its own stated tolerance, with a memo that quantifies why), and a real binding
  constraint decoded via a vendored `NEM_constraints` (not hand-rolled) into plain English. See its
  own `README.md`.
- `labs/05-spartan-chaosnet-transient-stream/` — **implemented** (laptop-portable core Definition
  of Done; the hardware-validated extension against a real Radxa Dragon Q8B is optional and out of
  scope, not attempted). A real SimBench + NetworkX chaos-net topology, a real DPsim EMT solve
  (200µs timestep, a real scheduled `SwitchEvent3Ph` fault with a live countdown), and a real
  VILLASnode pod actually run via `podman kube play`, verified by a real UDP capture. See its own
  `README.md` for exactly which node-type (`socket`/UDP/JSON, not `iec61850-9-2` — compiled into
  the image but fails to actually start in this sandbox even under `--privileged`) and transport
  (file, not a live `dpsimpyvillas` socket) had to be substituted, and why.
- `kube/` — all four manifests are written **and real-podman-executed**: `llamacpp-phi-pod.yaml`,
  `powermcp-pandapower-pod.yaml`, `villasnode-tap-pod.yaml` (Lab 5), and `benchmark-runner-job.yaml`
  (Lab 3 — with one documented `podman kube play` limitation: v5.4.2 doesn't implement Kubernetes
  Job's `completions`/`parallelism` fields, so it runs as a single pod rather than 3; the actual
  matrix-partitioning logic was verified for real via 3 directly-launched `podman run` containers
  instead — see the manifest's own header). See `kube/README.md` for the full status of each.
- `benchmarks/` — `power-agent-bench-lite/results/scorecard.json` is Lab 3's real, regenerated
  (gitignored) output; the committed, diffable fixture is
  `labs/03-advanced-provider-bakeoff/expected_scorecard.json`.
- `scripts/` — `fetch_csiro_nem_data.py`, `fetch_phi4_model.py`, `install_smoke_test.py`,
  `record_asciinema_demo.sh`, and `run_labs_1_3.sh` are real.

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
