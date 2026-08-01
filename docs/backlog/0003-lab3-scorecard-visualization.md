# 0003 — Lab 3: bake-off scorecard has zero charts

- **Status:** done.
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
- Read directly from the already-written `scorecard.json` / committed `expected_scorecard.json` — do not
  compute anything new, so this stays consistent with `AGENTS.md`'s "the proof scripts are the
  proof" convention: the chart is a rendering of an already-verified result, not a new source of
  truth.
- Save as a committed PNG (matching Lab 5's `sample_transient_plot.png` precedent) plus wire it
  into `--step check` only to the extent of "does the file get produced," not a pixel diff — a
  visual output doesn't fit the existing numeric-tolerance fixture-diff pattern and shouldn't be
  forced into one.

Implemented: `orchestrator.py` now has a `_plot_scorecard()` helper -- a 3-series grouped bar
chart (one group per task_family, one bar per local-policy provider, bar height = `error_margin`,
each bar value-labeled via `ax.bar_label()`), reading directly from the `rows` already passed to
`report_step()` -- nothing recomputed. The 4th row (`PowerFM-OpenPowerBench-stub`, task_family
`load-forecast-24h`) is deliberately excluded from the chart: it has no local-policy peer sharing
its task_family/units (MAPE% vs pu/loading-%), so it would render as an incomparable lone 4th
group rather than a genuine 3-way comparison; it remains visible in the printed table and
`scorecard.json`. `wall_clock_s` was *not* added as a second panel: in this sandbox's stand-in
(three deterministic search policies, not live LLM calls — see `orchestrator.py`'s module
docstring) wall-clock is small (~0.2-0.6s), dominated by `pandapower.runpp()` solver overhead
rather than genuine per-provider variation, and is already excluded from `check_step()`'s fixture
diff as machine-dependent — a second panel built on a number this noisy would add chart complexity
without a real second signal; `error_margin` alone is the chart worth having for a first pass.
Output: `scorecard_chart.png` in `benchmarks/power-agent-bench-lite/results/` (that directory is
wholesale-ignored except `.gitkeep`). Like `scorecard.json` in the same directory, the PNG is
deliberately *not* committed — `wall_clock_s` changes every real run/test, and the PNG is a
rendering of that per-run data, so committing either turns into pure git churn with no diffable
value (the real fixture, `expected_scorecard.json`, already lives committed in `LAB_DIR`); both
regenerate locally on demand from `--step report`.
`report_step()` writes the chart unconditionally (not gated behind a Lab 4/5-style `refresh_chart`
flag; that gate exists to protect a *committed* fixture from an ad-hoc run — there is nothing
committed here to protect). `check_step()` calls `sweep_step()` directly and never calls
`report_step()`, so an ordinary `--step check` never touches either file; neither its presence nor
absence says anything about correctness (a fresh clone legitimately has neither until
`--step report` runs once). The chart's real "does it still render" gate is
`test_lab3.py::test_lab3_report_renders_scorecard_chart`, which unlinks the PNG and exercises
`report_step()` directly (confirmed by running it: both Lab 3 tests pass, the fixture-diff test
reports `MATCH: all 10 scorecard rows match expected_scorecard.json`). Colors (`#2a78d6` blue / `#eb6834` orange /
`#1baf7a` aqua -- the dataviz skill's default palette's first three categorical slots) were
validated as a 3-way *all-pairs* set (not just adjacent pairs, since all three bars in a 3-bar
group are visually adjacent to the reader) via `node scripts/validate_palette.js
"#2a78d6,#eb6834,#1baf7a" --mode light --pairs all` and the dark-mode hex triplet
`"#3987e5,#d95926,#199e70" --mode dark --pairs all`: both ALL CHECKS PASS (worst all-pairs CVD
9.2 light / 9.4 dark, worst all-pairs normal-vision 24.0 light / 20.9 dark); light mode WARNs on
the aqua slot's contrast against the chart surface (2.74:1), satisfied by the skill's "relief
rule" since every bar is already value-labeled. See
`labs/03-advanced-provider-bakeoff/README.md`'s walkthrough step 2 and "What you'll do" step 4.

## Stretch option

An interactive Plotly HTML version (`pandapower.plotting.plotly`-adjacent, or plain
`plotly.express.bar` — Lab 3's data is not a pandapower object so pandapower's own plotting module
doesn't apply here, only the general habit of using Plotly for anything meant to be explored
rather than glanced at) — useful if this ever needs to be dropped into a live demo/dashboard
rather than a static screenshot. Not required for a first pass.

## Not in scope here

Provider bake-off results as a *live*, auto-refreshing dashboard — that's the notebook-playbook
idea in 0005, not a per-lab change.
