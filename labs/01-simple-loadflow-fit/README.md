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
