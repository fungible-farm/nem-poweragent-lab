# Lab 1 (Simple) — Load-Flow Parameter Fit

> Status: **spec only** — see `docs/VISION.md` §7 "Lab 1" for the full description. Code,
> `expected_results.json`, and the step-by-step walkthrough below will be filled in during
> implementation; this file fixes the intended shape so review can happen before code is written.

## What you'll do

1. Load `snemSA.m` (South Australia subset of the CSIRO Synthetic-NEM-2000-Bus model) through
   `powerio` into a pandapower network.
2. Solve the base-case AC power flow — note bus 14's modelled voltage.
3. Ask the local Phi-4-mini agent to adjust one load-scaling parameter, within ±10%, until the
   modelled voltage at bus 14 matches a given field SCADA reading (0.968 pu) to within 0.002 pu —
   the agent proposes values, pandapower's `runpp` is the ground truth on every iteration.
4. Compare the fitted parameter and residual against `expected_results.json`.

## Why an AEMO modeller should care

This is the smallest possible version of "model calibration against field data" — the same
mechanic used (at far larger scale) whenever a base case is tuned to match a real SCADA snapshot
before it's trusted for a study. The point of the lab is narrow on purpose: the LLM never touches
the physics, it only chooses the next trial value in a search loop that pandapower evaluates.

## Command (once implemented)

```
uv run labs/01-simple-loadflow-fit/run.py
```

## Step-by-step walkthrough (presenter / backup script)

Written now, before the code exists, so it doubles as the script a presenter can talk through
even if the live run isn't available on the day. Each step: what you run, what you should see,
why it matters.

1. **`uv run labs/01-simple-loadflow-fit/run.py --step load`**
   — You should see: `Loaded snemSA.m via powerio: N buses, M generators` followed by
   `Base-case power flow converged: bus 14 voltage = 0.951 pu`.
   — Why it matters: this is the "before" state — a modelled voltage that doesn't yet match the
   field reading, the same gap a modeller would see calibrating any base case.
2. **`uv run labs/01-simple-loadflow-fit/run.py --step fit`**
   — You should see: one line per iteration — `iter 1: trial=1.00x → 0.951 pu (residual 0.017)`,
   `iter 2: trial=1.04x → 0.958 pu (residual 0.010)`, … ending in
   `converged: trial=1.07x, bus 14 = 0.968 pu, residual 0.001 (PASS, tol 0.002)`.
   — Why it matters: every line comes from an actual `pandapower.runpp()` call — the model only
   proposes which trial value to try next; watching this scroll makes that split concrete rather
   than asserted.
3. **`uv run labs/01-simple-loadflow-fit/run.py --step check`**
   — You should see: the fitted parameter and residual diffed against
   `expected_results.json`, printing `MATCH` or a clear failure with both values shown.
   — *Backup if the live model server is unavailable*: read `expected_results.json` directly and
   narrate it as "here's what a passing run prints" — the fixture exists precisely so this lab
   never needs a live LLM to be explainable.
4. **Open the Gradio page** (`http://localhost:7860` once `run.py --ui` is running): a network
   diagram (pandapower's own Plotly plot, bus 14 highlighted) next to the convergence-curve line
   chart, with a slider to step through the fit iterations by hand.
   — Why it matters: this is the moment a non-engineer in the room can nudge the slider
   themselves and watch the residual close — the mechanic becomes tangible, not just narrated.
