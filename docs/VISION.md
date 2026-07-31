# PowerAgent NEM Lab — Vision & Architecture Plan

Status: **PLAN / PRE-BUILD**. Nothing in `labs/`, `kube/`, or `benchmarks/` is working code yet —
this document is the spec those directories will be filled against. Treat it as a training-guide
outline (MEA137A style: numbered steps, state what you did, state what you should observe, state
why it matters to an AEMO modeller), not a sales deck.

## 0. One paragraph, no adjectives

We are composing five existing open-source projects — **pandapower**, **powerio**, **PowerMCP**,
**PowerWF/PowerSkills** and **Microsoft Agent Framework** — around a real, public NEM network
model (CSIRO's Synthetic-NEM-2000-Bus dataset), run entirely on local compute (llama.cpp serving
Phi-4-mini on CPU, no cloud API keys), packaged as `podman kube play` pods so each piece can be
started, replaced and scaled independently. The deliverable is three runnable labs (simple,
medium, advanced) that show deterministic, scriptable agent workflows doing the kind of thing a
power modeller currently does by hand: load a case, run a study, check limits, produce a report —
and a benchmark harness that scores how well different *local* LLM providers perform simple
parameter-fitting/regression tasks against a public power-systems benchmark.

Nothing here requires PSS/E, PowerFactory, a cloud LLM subscription, or `b00t`.

## 1. Grounding: the paper this lab operationalises

This repo is not an original architecture — it is a runnable, laptop-scale implementation of the
roadmap laid out in:

> Q. Zhang and L. Xie, "PowerAgent: A Road Map Toward Agentic Intelligence in Power Systems:
> Foundation Model, Model Context Protocol, and Workflow," *IEEE Power and Energy Magazine*,
> vol. 23, no. 5, pp. 93–101, Sept.–Oct. 2025.
> [ieeexplore.ieee.org/document/11131348](https://ieeexplore.ieee.org/document/11131348/) ·
> open-access preprint: [doi.org/10.36227/techrxiv.174918210.07854858/v1](https://www.techrxiv.org/doi/full/10.36227/techrxiv.174918210.07854858/v1)
> · project site: [poweragent.seas.harvard.edu](https://poweragent.seas.harvard.edu/) (Qian Zhang
> and Le Xie, Harvard SEAS, Power and AI Initiative)

> "The operational resilience of electric power grids is facing growing challenges caused by aging
> infrastructure, increasing system complexity, and a rising frequency of extreme weather events.
> Traditional control paradigms, built around deterministic models and human-in-the-loop decision
> making, will become insufficient to manage the escalating demands on power grids. In response,
> recent advances in artificial intelligence (AI)—particularly the emergence of general-purpose AI
> agents capable of tool use, reasoning, and task orchestration—offer a new direction for
> enhancing grid flexibility and resiliency. This article introduces the concept of the Power
> Agent: an AI-enabled, context-aware assistant that leverages foundation models, standardized
> tool interfaces, and structured workflows to support grid operation and planning decisions. We
> discuss the conceptual architecture, implementation pathways, and system-level benefits of
> deploying Power Agents in power grid operations, with an emphasis on augmenting operator
> capabilities, improving situational awareness, and reducing operational bottlenecks."
> — abstract, Zhang & Xie 2025

The paper's own subtitle names its three architectural pillars — **Foundation Model, Model Context
Protocol, and Workflow** — and the Power-Agent GitHub organisation is that same triad, shipped as
code:

| Paper's pillar | Repo | Role in *this* lab |
|---|---|---|
| Foundation Model | [PowerFM](https://github.com/Power-Agent/PowerFM) | §7, Lab 3 — a domain-trained baseline sitting alongside the general-purpose LLM agents |
| Model Context Protocol | [PowerMCP](https://github.com/Power-Agent/PowerMCP) | Tool layer — pandapower exposed to any MCP client |
| Workflow | [PowerWF](https://github.com/Power-Agent/PowerWF) / [PowerSkills](https://github.com/Power-Agent/PowerSkills) | Orchestration pattern, reimplemented here on Microsoft Agent Framework |

So the "why compose these five projects" question in §3 has a one-line answer: **this is the
reference architecture from the IEEE paper, assembled from the org's own open-source
implementation of each of its three named pillars**, with a local-only inference stack and a real
NEM case substituted in for the demo. Everything downstream in this document is that
substitution made concrete and runnable.

## 2. Why (the actual problem, not the pitch)

Provisioning studies (new generator/load connection screening, N-1 contingency checks, model
validation before a planning submission) are currently a chain of manual steps: pull a case,
open it in a desktop tool, run a study, eyeball the output, write a memo. Every step is a place
where two engineers get different answers because they ran a slightly different version of the
tool, a slightly different case file, or forgot a step.

The pattern we want to demonstrate — not sell, demonstrate — is: **encode the steps as a
deterministic script, let an agent drive the script, containerise each tool so the exact version
is pinned, and get the same answer every time.** That's the entire thesis. Everything else in this
document is plumbing to make that demonstrable in an hour, on a laptop, with no vendor accounts.

## 3. Ecosystem map (what we're composing, not building)

| Project | Role in this lab | Language | Note |
|---|---|---|---|
| [pandapower](https://www.pandapower.org/) | The power-flow / OPF / contingency engine | Python | Wraps PYPOWER + pandas; solves AC/DC PF, OPF, short-circuit, topological search |
| [powerio](https://github.com/eigenergy/powerio) | Fast MATPOWER `.m` / PSS/E `.raw` / PyPSA-CSV parser + format converter, Python bindings over Rust | **Rust**, Python bindings | This is our Rust requirement — it reads CSIRO's `.m` files directly and its own benchmark suite validates against pandapower, PowerModels.jl and egret |
| [PowerFM](https://github.com/Power-Agent/PowerFM) | Domain-trained foundation models for power/energy: **OpenPowerBench** (transformer models for topology-dependent tasks — power flow, OPF, contingency — and topology-independent tasks — load/price forecasting), **GridLDM** (diffusion models for time-series generation), **GridFM** (GNNs trained on grid topology), **mAIEnergy** (multimodal) | Python, models on Hugging Face Hub | This is the paper's "Foundation Model" pillar; §7 Lab 3 pulls an OpenPowerBench load-forecasting checkpoint as a fixed domain-specific baseline row, run *without* any LLM in the loop, next to the general-purpose agents |
| [PowerMCP](https://github.com/Power-Agent/PowerMCP) | MCP servers exposing pandapower (and other engines) as tools an LLM can call | Python | `pip install powermcp && powermcp install` |
| [PowerSkills](https://github.com/Power-Agent/PowerSkills) | Agent-Skill playbooks on top of PowerMCP — "load case → solve base case → escalate to contingency → mitigation playbook" | Python + Markdown SKILL.md | Progressive disclosure: low-risk ops first |
| [PowerWF](https://github.com/Power-Agent/PowerWF) | Reference agentic workflows (grid-impact evaluation, market-inquiry agent) | Python | We replace their suggested LangGraph/AutoGen/CrewAI orchestrator with Microsoft Agent Framework per this lab's brief |
| [PowerAgentBench](https://github.com/Power-Agent/PowerAgentBench) family | Deterministic evaluators: agent proposes a solution, an independent checker recomputes the physics and scores feasibility | Python | We borrow the *pattern* (structured task → tool calls → deterministic re-check → score) for our own "lite" benchmark rather than depending on the full external harness |
| [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) | Orchestration: sequential / concurrent / handoff / Magentic workflows, native MCP client support, checkpointing | Python (+.NET, unused here) | Points at any OpenAI-compatible endpoint — that's how it talks to our local llama.cpp server |
| [llama.cpp](https://github.com/ggml-org/llama.cpp) | Local inference server, OpenAI-compatible `/v1/chat/completions`, CPU-only | C/C++ | Serves Phi-4-mini-instruct (GGUF, Q4), swappable for Gemma-4/Llama-3.2 for the bake-off lab |
| [CSIRO Synthetic-NEM-2000-Bus](https://github.com/csiro-energy-systems/Synthetic-NEM-2000bus-Data) | The actual grid: ~2000 buses, all NEM states + Tasmania, 3 HVDC interconnectors, CC-BY 4.0 | MATPOWER `.m` | Our one and only network model — real topology, synthetic parameters, no confidentiality issue |
| `podman kube play` | Composition/runtime for every service above | — | Each pod is one YAML file, no cluster, no kubelet, just Podman turning k8s manifests into local containers |

Everything in this table already exists. This repo's job is the glue: kube manifests, the three
lab scripts, and the benchmark scorer. **Verify exact install commands against each project's
current README at build time** — the ones quoted above were fetched in July 2026 and may drift.

## 4. Component architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ podman kube play  (single pod-network, all on localhost)            │
│                                                                       │
│  ┌───────────────────┐   OpenAI-compatible HTTP   ┌────────────────┐│
│  │ llamacpp-server    │◄───────────────────────────│ agent-framework││
│  │ (Phi-4-mini GGUF,  │                            │ orchestrator   ││
│  │  CPU, --n-gpu-layers 0)                         │ (runs as a     ││
│  └───────────────────┘                             │ plain uv-run   ││
│                                                     │ process, not   ││
│  ┌───────────────────┐   MCP (stdio→HTTP bridge)   │ a pod — it's   ││
│  │ powermcp-pandapower│◄────────────────────────────│ the "driver")  ││
│  │ MCP server pod     │                            └────────────────┘│
│  └───────────────────┘                                                │
│           ▲                                                           │
│           │ loads                                                     │
│  ┌───────────────────┐                                                │
│  │ CSIRO snem2000.m   │  parsed by powerio (Rust, via Python binding) │
│  │ → pandapower net   │  before being handed to pandapower/PowerMCP   │
│  └───────────────────┘                                                │
└─────────────────────────────────────────────────────────────────────┘
```

The orchestrator itself is **not** containerised — it's the thing a human runs (`uv run
labs/02.../workflow.py`). Everything it *depends on* (model server, tool server) is a pod. That
split matters for the "why Kubernetes" argument in §9: you containerise the things that need
version-pinning and horizontal scale-out, not the control script.

## 5. Data: CSIRO Synthetic NEM 2000-Bus

- Source files are MATPOWER `.m` text case files: `snem2000.m` (full NEM), `snem1803.m`
  (mainland), `snem197.m` (Tasmania), `snem2000_acdc.m` (+3 HVDC links), `snem2000_tnep.m` (+9
  transmission-expansion candidates), and per-region `snemNSW.m` / `snemQLD.m` / `snemVIC.m` /
  `snemSA.m`.
- License CC-BY 4.0 — redistribution in this repo is fine with attribution; `scripts/
  fetch_csiro_nem_data.py` pulls them at install time rather than vendoring the raw files, to keep
  the repo small and to always pick up upstream corrections.
- Path in: `powerio` parses the `.m` file → normalised case struct → handed to
  `pandapower.converter.from_ppc(...)` (or pandapower's native MATPOWER path, whichever `powerio`'s
  Python binding target is — confirm at implementation time) → a `pandapowerNet` object every
  other component operates on.
- Why this dataset specifically: it's public, it's NEM topology (not a generic IEEE 14-bus toy),
  it's the right order of magnitude to make a contingency-analysis lab feel real (2000 buses is
  enough that N-1 over all lines is a genuine "why would I want this parallelised" moment), and
  it needs zero data-sharing agreement.

## 6. Repo layout (target state)

```
nem-poweragent-lab/
├── install.sh                       # the one command a board member's laptop needs to run
├── pyproject.toml                   # uv-managed workspace, single lockfile
├── docs/
│   ├── VISION.md                    # this file
│   └── DEFINITION_OF_DONE.md
├── data/                            # gitignored raw CSIRO files; fetch script populates
├── scripts/
│   ├── fetch_csiro_nem_data.py
│   └── record_asciinema_demo.sh
├── kube/
│   ├── llamacpp-phi-pod.yaml
│   ├── powermcp-pandapower-pod.yaml
│   └── benchmark-runner-job.yaml
├── labs/
│   ├── 01-simple-loadflow-fit/
│   ├── 02-medium-interconnection-screening/
│   └── 03-advanced-provider-bakeoff/
└── benchmarks/
    └── power-agent-bench-lite/
```

## 7. The three labs

Each lab folder will contain: a numbered `README.md` (do this → run this → you should see this →
here's why an AEMO modeller cares), one Python entry point runnable via `uv run`, and a fixed
expected-output fixture so the lab is self-checking, not vibes-checking.

### Lab 1 — Simple: load-flow model fitting (single agent, single tool, no orchestration framework)

- **Setup**: `snemSA.m` (South Australia only — small enough to run in seconds) loaded via
  `powerio` into pandapower.
- **Task given to the agent**: "Bus 14's voltage is reported at 0.968 pu in the field SCADA
  snapshot; the base case model gives 0.951 pu. Adjust the shunt/load scaling parameter within
  ±10% until the modelled voltage matches the field reading to within 0.002 pu." — this is the
  "model fitting" regression task in miniature: a single scalar parameter search against a
  deterministic physics re-check (a plain least-squares or bisection loop the agent calls as a
  tool, not something it eyeballs).
- **What it demonstrates**: an agent calling one MCP tool (`pandapower.runpp`) repeatedly inside a
  fit loop, with the local Phi-4-mini model only deciding *which parameter to try next* — the
  actual physics stays in pandapower, never in the LLM. This is the load-bearing point for the
  whole repo: the LLM proposes, pandapower disposes.
- **Definition of pass**: script prints the fitted parameter, iteration count, and final residual;
  compares against `expected_results.json` fixture within tolerance.

### Lab 2 — Medium: interconnection / asset-provisioning screening (Agent Framework Sequential + Concurrent workflow)

- **Setup**: `snem1803.m` (mainland), a hypothetical new 250 MW generator connection at a named
  bus.
- **Workflow** (mirrors PowerWF's "Grid Impact Evaluation" example, reimplemented on Agent
  Framework instead of LangGraph):
  1. *Sequential* step — load case, attach candidate generator, solve base-case AC power flow.
  2. *Concurrent* step — fan out an N-1 contingency screen (drop each of the ~20 lines local to
     the connection point) as parallel tool calls; each branch's result feeds back into one
     collector step.
  3. Sequential step — thermal/voltage-limit check against AEMO-style planning criteria
     (documented, not invented — pull the actual NEM planning voltage bands into the check),
     produce pass/fail per contingency.
  4. Final step — agent drafts a plain-English screening memo citing which contingencies (if any)
     breach limits; a human-in-the-loop checkpoint (Agent Framework's native support for this)
     gates before the memo is "finalised".
- **What it demonstrates**: the exact "deterministic scripting of workflow automation of steps
  necessary to provision an asset or study" line from the brief — every step is a script, the
  agent's job is sequencing and reporting, not computing. This is also the first place
  `podman kube play`'s pod-per-tool-version pattern earns its keep — the pandapower MCP server pod
  can be pinned to an exact version for the entire screening run, then torn down.

### Lab 3 — Advanced: multi-provider bake-off + multi-agent orchestration (Agent Framework Magentic/group-chat, Podman scale-out)

- **Setup**: same mainland case, but now the *goal* is a benchmark, not a single answer: run the
  Lab 1 style regression/model-fitting task (and 2–3 more task families borrowed from the
  PowerAgentBench-SS pattern — e.g. fit a line rating to match a known thermal trip, fit a
  generator droop constant to match a frequency-response trace) against **several local model
  providers** swapped through the same llama.cpp pod: Phi-4-mini-instruct, Gemma-4, Llama-3.2-3B
  — same tasks, same tolerance, same deterministic scorer, only the model file changes.
- **Orchestration**: Agent Framework's Magentic/group-chat pattern runs a small "manager +
  worker" pair per provider so the runs are directly comparable (identical prompts, tool set,
  and evaluator across providers); `podman kube play --replace` on the llama.cpp pod is what swaps
  the model between sweeps, and the benchmark runner itself ships as a Kubernetes `Job` manifest
  (`kube/benchmark-runner-job.yaml`) so the whole matrix (3 providers × N task families) can be
  farmed out as parallel Job pods instead of a serial for-loop — this is the concrete "here's where
  you'd actually reach for an orchestration platform" moment for the Operations audience.
- **PowerFM baseline (the fourth row, no LLM involved)**: alongside the LLM-agent providers,
  pull one pretrained [PowerFM](https://github.com/Power-Agent/PowerFM) **OpenPowerBench**
  load-forecasting checkpoint (topology-independent task family — a short-horizon regional demand
  forecast) from Hugging Face Hub, run it directly against a CSIRO NEM regional load trace, and
  score it on the identical held-out-window/error-tolerance metric used for the LLM-driven
  parameter-fit tasks. It is not asked to do the model-fitting task families (that would compare
  unlike things) — it establishes the "domain-trained foundation model, no agent loop, no tool
  calls" reference point the paper itself distinguishes from the agentic path, in the same
  scorecard, so the audience sees the Foundation-Model and Agent+MCP+Workflow pillars from §1
  side by side rather than as competing claims.
- **Output**: a single scorecard (JSON + printed table) — provider (Phi-4-mini / Gemma-4 /
  Llama-3.2-3B / PowerFM-OpenPowerBench), task family, pass/fail, error margin, wall-clock,
  tokens (n/a for the PowerFM row) — checked into `benchmarks/power-agent-bench-lite/results/` so
  the demo is re-runnable and diffable, not a screenshot.

#### Lab 3 — Super-Stretch Goal (explicitly out of the v1 Definition of Done)

Everything below is aspirational — it is what Lab 3 grows into *if* the core version above lands
cleanly and there's appetite (and hardware) to keep going. None of it is required to call the lab
"done"; it's written down now so a later push doesn't have to re-derive the shape from scratch.
Treat every subsection as independently optional — cut whichever ones don't fit the time or
hardware available on the day.

1. **Full case, full task suite, real parallelism.** Swap `snem1803.m` for the full `snem2000.m`
   (all NEM states + Tasmania), and swap the "2–3 borrowed task families" for genuine coverage of
   both [PowerAgentBench-SS](https://arxiv.org/pdf/2606.18789) (steady-state: power flow, OPF,
   contingency, thermal/voltage) *and* [PowerAgentBench-Dyn](https://arxiv.org/abs/2606.20401)
   (dynamic: model-quality review, security-risk screening) task families — not the "lite" scorer,
   the real breadth. At that scale the provider × task-family matrix stops being a for-loop you'd
   ever run serially and becomes the thing that actually justifies `kube/benchmark-runner-job.yaml`
   fanning out across a real multi-node cluster rather than a single Podman host — the honest
   answer to "when do you actually need Kubernetes, not just `podman kube play`" is *here*, once
   the matrix is large enough that a single machine's core count is the bottleneck.
2. **Wider, honestly-labelled provider matrix.** Add a larger local model if the demo hardware has
   the RAM for it (e.g. a quantized 8B–14B model) purely to show the latency/accuracy trade-off
   against Phi-4-mini's 3.8B — same tasks, same tolerance, one more row. Optionally add a single
   cloud frontier model as a **calibration reference only**: off by default, requires an explicit
   opt-in flag and the operator's own API key, clearly labelled "not on the golden path, shown only
   to calibrate how far local inference is from a state-of-the-art baseline." This is the one place
   in the whole repo a cloud key is even discussed, and it stays optional and clearly fenced off —
   the "no cloud LLM keys" rule (`docs/DEFINITION_OF_DONE.md`) governs everything else.
3. **PowerFM, plural.** The core lab uses one OpenPowerBench checkpoint for one task family
   (load forecasting). The stretch version adds a **GridFM** (GNN, trained on grid topology rather
   than text) baseline for the topology-dependent task families, and a **GridLDM** (diffusion)
   baseline for a time-series *generation* task (e.g. synthesising a plausible EV-charging load
   profile for a bus that has none) — each PowerFM model scored only on the task family it's
   actually suited for, so the scorecard reads as "best tool for the job" across foundation-model
   architectures, not a single forecasting number standing in for the whole PowerFM project.
4. **Chaos/resilience sweep.** A small "chaos" Job pod that, between benchmark runs, randomly
   escalates the contingency severity fed to each provider (N-1 → N-2 → a randomly perturbed load
   profile within realistic bounds) and tracks the model-size/provider accuracy curve as stress
   increases — a direct, hands-on echo of the cited paper's own framing ("a rising frequency of
   extreme weather events" straining "traditional control paradigms"): does a smaller local model's
   advice degrade gracefully or fall off a cliff as the scenario gets harder, and does that curve
   look different for the PowerFM baselines than for the LLM-agent providers?
5. **Live dashboard, not a post-hoc table.** Move the scorecard from "printed after the sweep
   finishes" to a live Gradio page that updates as each Job pod completes (Gradio's generator-based
   streaming updates make this a small addition, not a rewrite) — for a room full of people watching
   a demo, a leaderboard filling in row by row is a materially different experience than a table
   dropped at the end.
6. **Flint-authored dashboard, on request.** Wire the optional [Flint](https://github.com/microsoft/flint-chart)
   MCP server (`npx flint-chart-mcp`, Node-gated, static-chart fallback if Node isn't present — see
   the visualization discussion) as one more tool call the *orchestrating agent itself* can make:
   once the (already-computed, already-correct) scorecard data exists, let the agent decide how to
   chart it and render that live in the Gradio page next to the pre-built version. The data is
   fixed either way — only the presentation is agent-authored — which is why this is safe to hand
   to the LLM even though nothing else in this repo lets it touch anything load-bearing.
7. **Human row.** Add a `gr.Button("I'll try it myself")` to the Gradio dashboard that lets someone
   in the room attempt one of the Lab 1-style parameter-fit tasks by hand through the same UI,
   timed and scored on the identical metric, and appended to the leaderboard live next to the AI
   providers. Cheap to build, and it's the single most effective way to make a benchmark number
   mean something to a non-engineer in the room — they just watched themselves lose (or win) to
   Phi-4-mini on a task they now understand because they just did it.

## 8. Rust component

We are **not** writing a new Rust crate. `powerio` already does exactly what's needed — parses
CSIRO's native MATPOWER `.m` files, converts formats, and its own test suite already benchmarks
against pandapower — so the Rust requirement in the brief is satisfied by depending on it (via its
Python bindings, installed like any other `uv add`-able package once we confirm its packaging
story — source build via `maturin`/`cargo` if it isn't on PyPI yet). If, once we're hands-on with
the crate, its `.m` coverage doesn't handle every CSIRO file variant (the ACDC/TNEP variants push
into MATPOWER extension fields), the fallback is pandapower's own `from_ppc`/`from_mpc`
converters — but leading with `powerio` is the more interesting demo and the one the brief asked
for by name.

## 9. Why `podman kube play` / why Kubernetes-style thinking at all

Deliberately explained, not sold, because the board audience includes Operations and System
Design, who will (rightly) ask "why not just a shell script":

- **Version pinning as an audit artifact.** A planning submission that says "screened against
  pandapower 2.14.x, running in a container built from this exact Containerfile" is a
  reproducibility statement System Design can defend later. A shell script with `pip install -U`
  is not.
- **Parallel fan-out for contingency/bake-off sweeps.** Lab 2's N-1 screen and Lab 3's provider
  bake-off are both embarrassingly parallel. `podman kube play` applied to a `Job` manifest is the
  smallest possible step towards "now run this across a real cluster when the case is the full
  5000-bus NEM model instead of the 1803-bus mainland subset," without rewriting anything — the
  YAML is the same shape whether Podman or a real kubelet is behind it.
- **Where it stops being worth it**: for a single interactive fit (Lab 1), a container is pure
  overhead — that lab intentionally runs as a plain `uv run` process talking to one already-running
  pod, to make the contrast visible rather than containerising everything by reflex.
- **Not chosen**: a real Kubernetes cluster, Helm, or any managed k8s service — out of scope
  entirely; `podman kube play` gives us the manifest shape and the "one command, no cluster" story
  that fits a laptop demo.

## 10. `install.sh` — spec

One command, POSIX shell, checks-then-acts (never silently reinstalls something already present):

1. Check for `uv`; if absent, install via the official installer script (documented, not
   auto-piped-without-telling-the-user).
2. Check for `podman`; if absent, print the distro-specific install instructions and stop (we do
   not attempt to install a container runtime with root for the user).
3. Check for `cargo`/`rustc` only if `powerio` needs a source build on this platform; skip if a
   prebuilt wheel is available.
4. `uv sync` — installs pandapower, the `powerio` binding, `agent-framework`, `mcp`, `powermcp`,
   pytest, from a single `pyproject.toml`/`uv.lock`.
5. `scripts/fetch_csiro_nem_data.py` — downloads the CC-BY dataset into `data/` (idempotent,
   checksums the download).
6. `podman kube play kube/llamacpp-phi-pod.yaml` then `kube/powermcp-pandapower-pod.yaml` —
   downloads the Phi-4-mini GGUF on first run (documented size/time), starts both pods.
7. Smoke test: one `uv run` call that does a trivial power flow through the running pods and
   prints PASS/FAIL — this is the "did the install actually work" gate before anyone opens a lab.

## 11. asciinema training recording

`scripts/record_asciinema_demo.sh` wraps `asciinema rec` around: `./install.sh` → Lab 1 → Lab 2 →
Lab 3 summary table, with `PS1` and terminal width pinned so the `.cast` file plays back
consistently regardless of the presenter's own shell config. The recording is an artifact of this
repo, not a separate hand-edited video — re-running the script after any lab changes regenerates
it, so the walkthrough can't drift out of sync with the actual code the way a slide deck does.

## 12. Explicit non-goals

- No `b00t` dependency, anywhere.
- No commercial engines (PSS/E, PowerFactory, PowerWorld, PSCAD) required for any of the 3 labs —
  PowerMCP's servers for those tools exist and could be added later as *optional* extras, never on
  the golden path.
- No cloud LLM API keys — every model call in every lab goes to `localhost` only; this is a network
  policy worth stating explicitly to Operations, not just an implementation detail.
- No new Rust code (see §8) — we consume `powerio`, we don't fork it.
- Not a sales artifact — no ROI slide, no competitor comparison; the labs either reproduce the
  claimed behaviour on the reader's own machine or they don't.
