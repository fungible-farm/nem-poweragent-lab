# 0003 — Lab 3: bake-off scorecard has zero charts

- **Status:** open
- **Depends on:** 0001 (gap), 0002 (options research, "free tier")
- **Lab:** `labs/03-advanced-provider-bakeoff/`

## Why Lab 3 specifically

Lab 3's whole point is a comparison — 3 provider stand-ins × 3 task families, scored on
`passed`, `error_margin`, `iterations`, `wall_clock_s`, `tokens` — and the only artifact is
`benchmarks/power-agent-bench-lite/results/scorecard.json` (10 rows) plus a printed table. A
benchmark that can't be looked at defeats its own purpose: nobody eyeballs a JSON array and sees
who won.

## Proposed fix (free tier, per 0002 — no new dependency)

Add a chart-emitting step to `orchestrator.py` (it already has `--step {sweep,report,check}` per
`AGENTS.md`) — either extend `report` or add a `--step chart`:

- A grouped bar chart: one group per `task_family`, one bar per `provider`, bar height =
  `error_margin` (or `wall_clock_s` as a second panel) — `matplotlib`, already a hard dependency,
  already used exactly once elsewhere in the repo (Lab 5's `verify_stream.py`), so this would be
  its second use, not a new pattern.
- Read directly from the already-committed `scorecard.json` / `expected_scorecard.json` — do not
  compute anything new, so this stays consistent with `AGENTS.md`'s "the proof scripts are the
  proof" convention: the chart is a rendering of an already-verified result, not a new source of
  truth.
- Save as a committed PNG (matching Lab 5's `sample_transient_plot.png` precedent) plus wire it
  into `--step check` only to the extent of "does the file get produced," not a pixel diff — a
  visual output doesn't fit the existing numeric-tolerance fixture-diff pattern and shouldn't be
  forced into one.

## Stretch option

An interactive Plotly HTML version (`pandapower.plotting.plotly`-adjacent, or plain
`plotly.express.bar` — Lab 3's data is not a pandapower object so pandapower's own plotting module
doesn't apply here, only the general habit of using Plotly for anything meant to be explored
rather than glanced at) — useful if this ever needs to be dropped into a live demo/dashboard
rather than a static screenshot. Not required for a first pass.

## Not in scope here

Provider bake-off results as a *live*, auto-refreshing dashboard — that's the notebook-playbook
idea in 0005, not a per-lab change.
