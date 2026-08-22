# AGENTS.md

Guidance for AI coding agents (and anyone else) working in this repo. Read `docs/VISION.md` and
`docs/DEFINITION_OF_DONE.md` first for the full plan and the checklist this repo is built against;
this file is the short, practical version for making changes.

## What this repo is

A training lab demonstrating deterministic, agent-driven power-system workflows against a real NEM
network model (CSIRO's Synthetic-NEM-2000-Bus dataset), intended to run on local, open-source
components only (`pandapower`, `powerio`, `agent-framework`, `llama.cpp`, `podman kube play`). See
the root `README.md` for current per-lab status.

## Capabilities & access (per agent/skill context, not one global truth)

Egress and tool availability are tracked **per agent/skill context** — there is no single rule
that holds for every session. Two governing rules:

1. **A tool that doesn't work in your session is an environment mismatch for that context.** Name
   the exact tool/host to the user and stop. Do NOT silently retry, route around it, or fold the
   failure into a repo-wide rule.
2. **A tool/host that works when the table below says otherwise is a session observation, not a
   policy change.** Re-verify before relying on it, report it to the user, and never rewrite the
   table from a single run.

### Capability matrix

| Capability | Context | Expected access / tooling | Mismatch → action |
|---|---|---|---|
| AEMO NEMWeb pull (`nemosis.dynamic_data_compiler`) | any lab agent | blocked — 403 org-policy denial, hand-confirmed via `curl` + `/root/.ccr/__agentproxy/status` | 403 / connection error → inform user; do not retry or route around |
| CSIRO case fetch (`scripts/fetch_csiro_nem_data.py`) | any lab agent | `raw.githubusercontent.com` reachable (this is how Lab 4's real DUID data works) | fetch fails → env mismatch → inform user |
| PyPI / `uv sync` / `uv run` | any lab agent | `pypi.org` reachable; `uv` installed | `uv sync` fails → env mismatch → inform user |
| `github.com` / `gh` / `git` | any lab agent | session-dependent (documented baseline: blocked; observed reachable once, 2026-08-02) | `gh`/`git`/`curl` fails → env mismatch → inform user |
| `crates.io` (`cargo add`/`cargo build`) | any lab agent | session-dependent (documented baseline: blocked — 403, observed 2026-08-02; reachable again, `cargo add --dry-run` resolved cleanly, observed 2026-08-21 building `rust/fft-detector`) | fetch/build fails → env mismatch → inform user; do not assume blocked without a real test in this session |
| codebase-memory skill | `codebase-memory` skill | `codebase-memory-mcp` on PATH, registered in repo `.mcp.json` | handshake / `list_projects` fails → env mismatch → inform user |
| demo display (`just peek` / `just watch`) | demo/display workflow | `chafa` + `mpv` on PATH (install.sh step 7 / `just deploy`) | `command -v` empty → run `just deploy` or inform user |
| animation render (`just render`) | demo workflow | system `ffmpeg` | ffmpeg missing → env mismatch → inform user |
| pods / `podman kube play` | Labs 1-5 golden path | `podman` installed | missing → `install.sh` refuses by design (documented) |

Provenance: the `nemweb.com.au` row is org policy, confirmed by hand (not assumed). The
`github.com` / `crates.io` rows are live session observations — exactly the kind of thing that can
differ per agent/blessing. In any new "sandbox stand-in" docstring, name the specific host you
tried (follow the pattern in `labs/04-aemo-digital-twin-reconciliation/reconcile.py`) rather than
citing this table as a policy guarantee.

## Package management: `uv` only

Never use bare `pip`/`pip3`. Always:

```
uv sync                       # install pinned deps from pyproject.toml/uv.lock
uv run <script>                # run anything inside the project's venv
uv run python -m pytest labs/  # run the test suite
```

## Running the labs

**Canonical commands live in the root `Justfile` — `just --list` is the index** (install, sync,
fetch, proof, test, per-lab check gates, per-lab walkthrough steps, animation render, and the
`peek`/`watch` display recipes). The equivalent bare commands, for reference:

```
uv run scripts/fetch_csiro_nem_data.py   # once: fetch + checksum-verify CSIRO case data into data/
./scripts/run_labs_1_3.sh                # the committed end-to-end proof: fetch -> Labs 1-3 -> pytest -> PASS/FAIL
./scripts/run_lab4.sh                    # the committed end-to-end proof: fetch -> Lab 4 Parts A+B -> pytest -> PASS/FAIL
```

Each lab is also runnable step by step — see the lab's own `README.md` "Command"/"What's
implemented" section (`labs/01-simple-loadflow-fit/run.py --step {load,fit,check}`,
`labs/02-medium-interconnection-screening/workflow.py --step {base,contingencies,check-limits,memo}`,
`labs/03-advanced-provider-bakeoff/orchestrator.py --step {sweep,report,check}`,
`labs/04-aemo-digital-twin-reconciliation/fetch_day.py`, `map_duids.py`, `reconcile.py [--step
check] [--date 2016-09-28]`, `explain_constraint.py`).

**The proof scripts are the proof, not a transcript.** If you change a lab, re-run its proof script
(or at least that lab's `--step check` and pytest file) before considering the change done. Running
commands ad hoc in a session is not proof anything works — a committed script re-deriving the same
result on a clean checkout is.

## Non-negotiable conventions in this codebase

- **No undocumented magic numbers.** Every constant with a specific value (a bus ID, a tolerance,
  a percentage, an iteration cap) must be a named `UPPER_CASE` module-level constant with a comment
  or docstring explaining *where the value came from* (a cited spec line, a real measured quantity
  from an actual run, a derived bound) — never a bare literal dropped into a function body. See
  `labs/01-simple-loadflow-fit/run.py` or `labs/_shared/gridfit.py` for the pattern.
- **PEP 484 type hints everywhere it's practical**, including on module-level constants
  (`FOO: float = 1.0`) and function signatures. Use `TypedDict` for structured dict return values
  instead of bare `dict`.
- **Docstrings on every non-trivial function/class**, explaining what it does, its Args/Returns
  (and Raises where relevant), and — critically for this repo — *why*, when the function stands in
  for something not available in this sandbox (see next point).
- **Sandbox stand-ins must be named, not hidden.** This repo's full spec (`docs/VISION.md`) assumes
  `podman`, a live local LLM server (llama.cpp serving Phi-4-mini/Gemma-4/Llama-3.2-3B), Microsoft
  Agent Framework orchestration, and PowerMCP tool servers. The current build/CI sandbox has none
  of these. Wherever code substitutes something simpler (a deterministic bisection search standing
  in for an LLM's "propose the next trial value" step, direct pandapower calls standing in for an
  MCP tool call, `concurrent.futures.ProcessPoolExecutor` standing in for a podman-hosted pod fan-out),
  the substitution must be named explicitly in that function's docstring *and* in the lab's own
  `README.md` "Sandbox notes" section. Never silently swap in a simplification without saying so at
  the call site — a future contributor with real infrastructure available needs to find the exact
  line to replace.
- **Every lab is self-checking.** A lab's `--step check` (or equivalent) command re-runs its
  computation and diffs the result against a committed `expected_*.json` fixture with a documented
  tolerance, and has a `test_labN.py` pytest wrapper. If you add a new lab step or task, add or
  update the fixture and the test — don't leave a step that can only be "vibes-checked" by reading
  printed output.
- **Real data over synthetic data, wherever real data is actually available.** The CSIRO
  Synthetic-NEM-2000-Bus MATPOWER case files are real (if synthetic-topology) public data, fetched
  and checksum-verified by `scripts/fetch_csiro_nem_data.py` — never hand-roll a toy network when a
  real case file already covers the need. Physics results (voltages, loadings, convergence) must
  come from an actual `pandapower.runpp()` call, never be fabricated or hard-coded to look
  plausible.
- **Golden-path licensing (PSCADOSSE):** the golden path prefers foundational, OSI-approved,
  permissive components (Apache-2.0 / MIT / BSD), foundation-backed where possible — see
  `docs/PSCADOSSE.md` for the policy and the verified license map (incl. the DPsim/MPL-2.0
  exception and the "copyleft display CLIs are fine — they're not API surface" distinction).
  Record a new dependency's license at the point of adoption.
- **No `b00t` dependency, no commercial power-system engines on the golden path, no cloud LLM API
  keys anywhere.** See `docs/DEFINITION_OF_DONE.md` "Governance / non-goals held" for the full list.

## Repo layout quick reference

- `docs/VISION.md` — full architecture plan and per-lab spec; the source of truth for what each
  lab is *supposed* to do.
- `docs/DEFINITION_OF_DONE.md` — the checklist this repo is built against; consult before claiming
  anything is "done."
- `docs/backlog/` — gaps found after the fact (not deliberate non-goals — see
  `docs/VISION.md` §12 for those), one numbered file per item, indexed at
  `docs/backlog/README.md` and pointed to from `docs/VISION.md` §13.
- `labs/_shared/gridfit.py` — shared powerio->pandapower loading and the bisection search helper
  used by Labs 1 and 3.
- `labs/_shared/scenario_engine/` — the composable `Generator`/`Detector` platform
  (`docs/prd/0001-composable-generator-detector-platform.md`): `generators.py`/`detectors.py`
  (the two Protocols plus five concrete classes each), `scenario.py` (schedule DAG extension +
  `run_scenario()` driver), `scoring.py` (two-section PASS/FAIL report), `demo_scenario.py` (the
  PRD's own synthetic proof scenario). Imported by Lab 5's `chaosnet.py`/`run_dpsim.py` (whose
  original single fault becomes a one-`NetworkFaultGenerator` degenerate case, zero behaviour
  change) — a deliberate exception to `gridfit.py`'s "labs import `_shared`, never the reverse"
  precedent, documented in the package's own `__init__.py`, since this module's whole point is
  reusing Lab 5's `phase_model.py` views directly rather than reimplementing them. Self-checked by
  `labs/_shared/test_scenario_engine.py` against `labs/_shared/expected_demo_scenario_run.json`.
- `labs/01-simple-loadflow-fit/`, `labs/02-medium-interconnection-screening/`,
  `labs/03-advanced-provider-bakeoff/` — implemented; each has real code, a fixture, a pytest test,
  and a README with "Sandbox notes."
- `labs/04-aemo-digital-twin-reconciliation/` — implemented (Part A + B required, Part C optional,
  also implemented); see `docs/LAB4_AEMO_REAL_DATA.md` and the lab's own `README.md`.
- `labs/05-spartan-chaosnet-transient-stream/` — implemented (laptop-portable core; the
  hardware-validated extension is optional and out of scope). See `docs/LAB5_SPARTAN_CHAOSNET.md`
  and the lab's own `README.md` "Sandbox notes" for the real DPsim/VILLASnode session and the one
  node-type substitution found by actually running it.
  `labs/05-spartan-chaosnet-transient-stream/scenarios/` — PRD-0002's SA 2016 Black System cascade
  scenario (`sa_2016_black_system.py`), built on `labs/_shared/scenario_engine/`; see that script's
  own module docstring for its tap-role mapping and named engineering deviations from the PRD's
  original sketch. Self-checked by `test_sa_2016_black_system.py`, skipped by default (opt in with
  `RUN_SLOW_SCENARIOS=1`) since its `--step check` solves ~43s of grid time.
- `labs/06-sysml-digital-thread/` — implemented (both tracks). A SysML v2/MBSE tooling evaluation
  (PRD-0006), not a physics lab: two tracks (Track A — this repo's own real Agent/MCPServer/
  DataSource inventory; Track B — a real `data/snemSA.m` bus/generator/line cluster; Track C —
  PRD-0005's own real pipeline-phase sequence) share one LinkML→`.sysml`→syntax-gate→isometric-SVG
  (+Track A SBOM) pipeline. See the lab's own `README.md` "Design notes" for the real-tool
  evaluation (SysML v2 Pilot Implementation via a GraalVM container) and exactly why it fell back to
  a named in-repo stand-in.
- `kube/benchmark-runner-job.yaml` — a written, valid Kubernetes Job manifest for Lab 3, not yet
  executed with `podman` in this sandbox (Lab 3's own fixture doesn't require it); see the file's
  own header. `kube/villasnode-tap-pod.yaml` (Lab 5), by contrast, has been actually run with
  `podman kube play` in this sandbox — see its own header.
- `data/` — gitignored; populated by `scripts/fetch_csiro_nem_data.py`, never vendored/committed.
- `benchmarks/power-agent-bench-lite/results/` — gitignored except `.gitkeep`. Both `scorecard.json`
  and `scorecard_chart.png` are regenerated, local-only output from `--step report`/`--step check`
  (real re-derivation; `wall_clock_s` differs every run), never committed — the committed, diffable
  fixture is `labs/03-advanced-provider-bakeoff/expected_scorecard.json`.
- `labs/04-aemo-digital-twin-reconciliation/duid_mapping.csv` — Lab 4's committed, auditable
  DUID-to-synthetic-generator mapping, regenerated by `map_duids.py`.
