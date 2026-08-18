# 0001 — No lab renders a topology diagram or a results chart

- **Status:** done — charts landed for Labs 2, 3, 4, and 5 (0002's free tier via 0003/0004, plus
  this item's Lab 2 contingency screen); Lab 1's visual evidence was already committed
  (`animate_convergence.py`/`.mp4`, `git log --oneline -- labs/01-simple-loadflow-fit/
  animate_convergence.py` shows this landed before this status line was last written — the
  "Lab 1's visual" gap below was stale); item 2's `pandapower.plotting` miss is now closed too,
  via Lab 1's `run.py` `_plot_network()` / `sample_network_chart.png` (buses colored by real
  solved voltage, TARGET_BUS highlighted — see that lab's README "Files" section).
- **Found:** 2026-08-01, auditing the repo after all 5 labs were already marked "implemented" in
  `AGENTS.md`.
- **Linked as vision:** this item is referenced from `docs/VISION.md` §13 "Known gaps / backlog" —
  see that section for how it fits the rest of the plan. This file is the detail; `VISION.md` is
  the index.

## The gap, stated plainly

This is a power-system-topology repo — every lab loads a real network model, Lab 5 procedurally
*generates* a graph — and across all 5 labs, nothing is ever drawn. The only visual artifact in
the entire repo is one static PNG.

## Evidence (grep'd, not asserted)

```
$ grep -rln "matplotlib\|plt\.\|\.savefig\|plotly\|nx\.draw" labs/ scripts/ --include="*.py"
labs/05-spartan-chaosnet-transient-stream/verify_stream.py
```

`matplotlib>=3.11.1` is a `pyproject.toml` dependency. It is imported in exactly **one** of
roughly fifteen lab/script `.py` files — `verify_stream.py`, which plots the one fault-transient
voltage waveform (`labs/05-spartan-chaosnet-transient-stream/sample_transient_plot.png`, via
`plt.subplots()` / `fig.savefig()` at lines 153/173 of that file). No other lab imports
`matplotlib`, `plotly`, or calls any `networkx` drawing function.

Specific misses, in order of how obvious they are in hindsight:

1. **Lab 5 builds a NetworkX graph and never draws it.** `chaosnet.py` /
   `generate_topology.py` call `nx.connected_watts_strogatz_graph` to perturb a SimBench seed
   grid into a new topology every run. Grepping `chaosnet.py`/`generate_topology.py` for
   `draw|plot|spring_layout|savefig` returns nothing. The one lab whose entire premise is "a new
   topology each run" has no way to *see* the topology it generated — only a bus/line count
   printed as text.
2. **No lab calls `pandapower.plotting`, despite every lab loading a pandapower network.**
   `pandapower.plotting.simple_plot()` draws the network (buses, lines, loading colors) in one
   call, and is unused across all 5 labs — confirmed by
   `grep -rln "pandapower.plotting\|pp.plotting\|simple_plot\|to_html" labs/` returning nothing.
3. **Lab 3's bake-off scorecard — the one dataset built to be compared — is JSON-only.**
   `benchmarks/power-agent-bench-lite/results/scorecard.json` has 10 rows with fields
   `provider, task_family, passed, error_margin, iterations, wall_clock_s, tokens, detail` — an
   obvious grouped-bar-chart shape — and is only ever printed as a table. See 0003 for the
   dedicated backlog item.
4. **Lab 2's N-1 contingency screen (loading vs. limit) and Lab 4's reconciliation (modelled vs.
   actual interconnector flow)** are both classic bar/time-series comparisons, both rendered only
   as printed text / a markdown memo (`draft_memo()` in Lab 2's `workflow.py`; Lab 4's
   `reconcile.py` memo output). See 0004 for options.
5. **Every lab README has a "presenter / backup script" walkthrough section** — this repo is
   explicitly built for live demos — yet 4 of 5 labs' demo evidence is a terminal transcript, not
   a visual artifact.

## Why this counts as a real gap, not a nice-to-have

`AGENTS.md` "Non-negotiable conventions" already requires every lab to be self-checking against a
committed fixture — the repo takes verifiability seriously. Visualization is the missing half of
*legibility*: a modeller can verify a number is correct without ever being able to see the network
it came from or compare it against another provider's result at a glance. For an audience
explicitly described throughout this repo as "AEMO modellers," a network diagram is the single
most standard artifact in the discipline, and it is entirely absent.

## Non-goal of this item

This file only records the gap. It does not prescribe a fix — see 0002 (options research), 0003
(Lab 3 concrete plan), 0004 (Lab 4/5 options), and 0005 (the notebook-playbook suggestion that
ties remediation across labs together).
