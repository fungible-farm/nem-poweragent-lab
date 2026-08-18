# Lab 1 (Simple) — Load-Flow Parameter Fit

> Status: **implemented**. `run.py`, `expected_results.json`, and `test_lab1.py` are real, runnable
> code — see `docs/VISION.md` §7 "Lab 1" for the original spec this implements, and the "Sandbox
> notes" section below for where this run deviates from that spec and why.

## What you'll do

1. Load `snemSA.m` (South Australia subset of the CSIRO Synthetic-NEM-2000-Bus model) via `powerio`
   into a pandapower network.
2. Solve the base-case AC power flow — note bus 2008's modelled voltage (the real bus this
   implementation uses in place of the spec's illustrative "bus 14" — see Sandbox notes).
3. Bisect a load-scaling parameter, within ±10%, until the modelled voltage at bus 2008 matches a
   fixed synthetic "field SCADA" target (0.9422 pu) to within 0.002 pu — every trial is a real
   `pandapower.runpp()` call, never an eyeballed guess.
4. Compare the fitted parameter and residual against `expected_results.json`.

## Why an AEMO modeller should care

This is the smallest possible version of "model calibration against field data" — the same
mechanic used (at far larger scale) whenever a base case is tuned to match a real SCADA snapshot
before it's trusted for a study. The point of the lab is narrow on purpose: the physics never lives
in the proposer, it only chooses the next trial value in a search loop that pandapower evaluates.

## Sandbox notes (read this before the walkthrough)

`docs/VISION.md`'s Lab 1 has a local Phi-4-mini LLM (served by llama.cpp in a podman pod) choosing
each trial value over MCP. This sandbox has no `podman` and no budget to download/serve a GGUF
model, so `run.py` uses `labs/_shared/gridfit.py`'s deterministic bisection search in place of that
decision — named explicitly in both files' docstrings, not hidden. The physics on every iteration
is still a real `pandapower.runpp()` call; that split (proposer proposes, pandapower disposes) is
the actual point of the lab and is unaffected by the swap. Bus 2008 stands in for the spec's
illustrative "bus 14" because `snemSA.m`'s real bus IDs are non-sequential (986, 1633, 1634, ...),
so there is no bus literally named 14.

## Command

```
uv run scripts/fetch_csiro_nem_data.py   # once, to populate data/snemSA.m
uv run labs/01-simple-loadflow-fit/run.py --step load
uv run labs/01-simple-loadflow-fit/run.py --step fit
uv run labs/01-simple-loadflow-fit/run.py --step check
uv run python -m pytest labs/01-simple-loadflow-fit/test_lab1.py
```

## Running in a container (Windows-friendly)

No local `uv`/Python/pandapower install needed — build once, run anywhere Docker Desktop or Podman
Desktop is installed (both run on Windows via a WSL2 backend, and read a `Containerfile` exactly
like Linux/macOS native `podman`/`docker`):

```
podman build -t nem-poweragent-base:local -f Containerfile.base .
podman build -t lab1:local -f labs/01-simple-loadflow-fit/Containerfile .
podman run --rm lab1:local
```

(Swap `podman` for `docker` if that's what you have — both read this repo's `Containerfile`s
identically.) The first `build` installs this repo's full dependency set once, shared by every
other lab's own image — see `Containerfile.base`'s own header. The default run reproduces the
`--step check` output above exactly; override the `CMD` to run another step, e.g.
`podman run --rm lab1:local --step fit`.

## Step-by-step walkthrough (presenter / backup script)

1. **`uv run labs/01-simple-loadflow-fit/run.py --step load`**
   — You should see: `Loaded snemSA.m via powerio: 503 buses, 57 generators` followed by
   `Base-case power flow converged: bus 2008 voltage = 0.935 pu`.
   — Why it matters: this is the "before" state — a modelled voltage that doesn't yet match the
   field reading, the same gap a modeller would see calibrating any base case.
2. **`uv run labs/01-simple-loadflow-fit/run.py --step fit`**
   — You should see: one line per iteration —
   `iter 1: trial=1.0000x -> 0.935 pu (residual -0.0074)`,
   `iter 2: trial=0.9500x -> 0.940 pu (residual -0.0025)`,
   `iter 3: trial=0.9250x -> 0.941 pu (residual -0.0008)`, ending in
   `converged: trial=0.9250x, bus 2008 = 0.941 pu, residual -0.0008 (PASS, tol 0.002)`, followed by
   `[chart] wrote sample_network_chart.png`.
   — Why it matters: every line comes from an actual `pandapower.runpp()` call — the proposer only
   picks which trial value to try next; watching this scroll makes that split concrete rather than
   asserted. The chart (`sample_network_chart.png`) renders the fitted network via
   `pandapower.plotting` — every bus colored by its real solved voltage, bus 2008 highlighted — so
   the calibration target is visible in the wider network, not just a number in a log line
   (docs/backlog/0001-topology-and-results-visualization-gap.md item 2 / docs/backlog/0002's free
   tier).
3. **`uv run labs/01-simple-loadflow-fit/run.py --step check`**
   — You should see: the fitted parameter and residual printed as JSON, then
   `MATCH: fitted_scale=0.925 residual_pu=-0.000791 vs expected_results.json`.
   — *Backup if you don't want to run the fit live*: read `expected_results.json` directly and
   narrate it as "here's what a passing run prints" — the fixture exists precisely so this lab
   never needs a live run to be explainable.
4. **`uv run python -m pytest labs/01-simple-loadflow-fit/test_lab1.py`**
   — You should see: `2 passed`. This is the same check step (plus a dedicated chart-artifact
   assertion) wrapped for CI/`scripts/run_labs_1_3.sh`.

## Files

- `run.py` — the three-step walkthrough script (`load` / `fit` / `check`) described above.
  `--step fit` also (re)writes the committed `sample_network_chart.png`, gated by `refresh_chart`
  so `--step check`'s self-check re-derivation never mutates it (see `fit_step`'s docstring).
- `expected_results.json` — committed fixture `--step check` diffs against.
- `sample_network_chart.png` — committed `pandapower.plotting` network diagram: every bus of the
  fitted network colored by its real solved voltage (`vm_pu`), bus 2008 (the calibration target)
  highlighted. Regenerate via `run.py --step fit`; see `_plot_network`'s docstring in `run.py` for
  the exact pandapower.plotting APIs used and why (docs/backlog/0001 item 2, docs/backlog/0002).
- `animate_convergence.py` — renders `animate_convergence.mp4` (gitignored; this script is the
  committed artifact that re-derives it) from a real bisection-fit run, for presenter use. See its
  own module docstring.
- `test_lab1.py` — pytest wrapper around `--step check` plus a dedicated assertion that
  `sample_network_chart.png` exists.
