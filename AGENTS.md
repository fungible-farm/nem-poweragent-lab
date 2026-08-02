# AGENTS.md

Guidance for AI coding agents (and anyone else) working in this repo. Read `docs/VISION.md` and
`docs/DEFINITION_OF_DONE.md` first for the full plan and the checklist this repo is built against;
this file is the short, practical version for making changes.

## What this repo is

A training lab demonstrating deterministic, agent-driven power-system workflows against a real NEM
network model (CSIRO's Synthetic-NEM-2000-Bus dataset), intended to run on local, open-source
components only (`pandapower`, `powerio`, `agent-framework`, `llama.cpp`, `podman kube play`). See
the root `README.md` for current per-lab status.

## Known sandbox network restrictions

Confirmed by hand (via `curl` and `/root/.ccr/__agentproxy/status`), not assumed: this sandbox's
egress policy returns 403 ("destination host not allowed," an organization policy denial, not a
transient failure — do not retry or route around it) for **`nemweb.com.au`** and for **`github.com`
itself**. `raw.githubusercontent.com` and `pypi.org` *are* reachable, which is how
`scripts/fetch_csiro_nem_data.py` and Lab 4's real DUID data both work despite this. Practically:

- Any AEMO NEMWeb pull (NEMOSIS's `dynamic_data_compiler()`, for instance) cannot reach live data
  here — pip-installing the library still works (PyPI), calling it does not.
- Any third-party GitHub repo you'd otherwise `pip install git+https://github.com/...` or browse
  via `api.github.com`/`github.com` is unreachable; only exact `raw.githubusercontent.com/<owner>/
  <repo>/<ref>/<path>` file fetches work, and only if you already know the path (no directory
  listing).

Don't re-discover this by trial and error on a future change — assume it's still true, name the
specific host you tried in any new "sandbox stand-in" docstring, and follow the pattern already
used in `labs/04-aemo-digital-twin-reconciliation/reconcile.py`.

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
- `labs/01-simple-loadflow-fit/`, `labs/02-medium-interconnection-screening/`,
  `labs/03-advanced-provider-bakeoff/` — implemented; each has real code, a fixture, a pytest test,
  and a README with "Sandbox notes."
- `labs/04-aemo-digital-twin-reconciliation/` — implemented (Part A + B required, Part C optional,
  also implemented); see `docs/LAB4_AEMO_REAL_DATA.md` and the lab's own `README.md`.
- `labs/05-spartan-chaosnet-transient-stream/` — implemented (laptop-portable core; the
  hardware-validated extension is optional and out of scope). See `docs/LAB5_SPARTAN_CHAOSNET.md`
  and the lab's own `README.md` "Sandbox notes" for the real DPsim/VILLASnode session and the one
  node-type substitution found by actually running it.
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
