# Lab 2 (Medium) — Interconnection / Asset-Provisioning Screening

> Status: **implemented**. `workflow.py`, `expected_contingency_table.json`, and `test_lab2.py` are
> real, runnable code — see `docs/VISION.md` §7 "Lab 2" for the original spec, and "Sandbox notes"
> below for where this run deviates and why.

## What you'll do

1. Load `snem1803.m` (mainland NEM), attach a hypothetical 250 MW generator at bus 175 (a real
   132 kV bus with 21 lines within 2 network hops — see Sandbox notes on how it was chosen).
2. Sequential step: solve the base-case AC power flow with the candidate generator attached.
3. Concurrent step: fan out an N-1 contingency screen (drop each of the 21 local lines) as
   genuinely parallel OS processes (`concurrent.futures.ProcessPoolExecutor`); collect results.
4. Sequential step: check each contingency against a simplified planning voltage/thermal band;
   produce a pass/fail table.
5. `--step check-limits` also renders a committed `sample_contingency_chart.png` (two panels: worst
   line-loading % vs the 100% thermal limit, and worst bus-voltage pu vs the 0.90–1.10 pu band),
   so the N-1 screen can be looked at, not just read as a table.
6. Final step: draft a plain-English screening memo; a human-in-the-loop checkpoint genuinely
   blocks before the memo is marked final.

## Why an AEMO modeller should care

This is the actual "deterministic scripting of workflow automation of steps necessary to
provision an asset or study" pattern from the brief: every physics step is a script, never
something reasoned about numerically. The version-pinned tool environment for the whole run is the
reproducibility statement a real screening submission would need to defend.

## Sandbox notes (read this before the walkthrough)

`docs/VISION.md`'s Lab 2 runs this as a Microsoft Agent Framework Sequential+Concurrent workflow,
calling a podman-hosted PowerMCP pandapower server for every physics step. This sandbox has no
`podman`, so there is no running PowerMCP pod to call over MCP — the four steps below are the same
sequential/concurrent shape (sequential base-case solve, a *genuinely* concurrent N-1 fan-out,
a sequential limit-check, a gated memo step) implemented as direct pandapower calls in-process
instead of MCP tool calls. The physics, the parallelism, and the human-in-the-loop gate are all
real; only the transport is swapped — see `workflow.py`'s module docstring for the exact call site
that would change.

Two more things worth knowing before you read the output:

- `snem1803.m`'s default pandapower DC-flat pre-solve hits a divide-by-zero (a zero-impedance
  branch typical of MATPOWER bus-merge modelling). `workflow.py` calls `pp.runpp(net, init="flat")`
  to skip that pre-solve; the AC Newton-Raphson then converges cleanly. Documented deviation from a
  bare `pp.runpp(net)` call.
- The simplified planning band used for the check-limits step (0.90–1.10 pu voltage, ≤100% thermal
  loading) is a documented approximation of NER Schedule 5.1a's per-voltage-level "normal voltage
  fluctuation limits" — a real screening submission would consult the exact S5.1a table for each
  nominal voltage level rather than this one flat band.
- Every one of the 21 contingencies screened shows a voltage breach at bus 1126 — but this is a
  **pre-existing base-case condition** (bus 1126 sits at 0.899 pu even with no line dropped at
  all, independent of the candidate connection), not something these contingencies caused.
  `workflow.py`'s `check_limits()` labels this explicitly ("pre-existing in base case, not caused
  by this contingency") rather than letting a real-data quirk look like a bug.
- There ARE two **genuinely contingency-induced** breaches, and this screen exists to catch exactly
  them: lines 151 and 152 are a parallel pair (both `[175-608]`, ~55-56% loaded in the base
  case), so dropping either one forces the surviving twin to carry both circuits — line 152 to
  **113.0%** when 151 is out, line 151 to **111.4%** when 152 is out. `check_limits()` marks both
  rows FAIL with a "contingency-induced" thermal clause, and `draft_memo()` reports them as "2
  contingency(ies) BREACH limits as a direct result of the outage" (this was a real finding, not a
  cosmetic one: the memo previously keyed on the word "pre-existing" appearing anywhere in a
  row's reason and mislabeled these rows as entirely pre-existing — fixed, see `draft_memo()`).
  That same honesty carries into `sample_contingency_chart.png`: the two panels plot the exact
  per-contingency numbers `check_limits()` already evaluates (worst loading vs the 100% limit,
  worst voltage vs the 0.90–1.10 band), so 19 of 21 bars sit flat at the pre-existing ~97.8% /
  0.899 pu point while the 151/152 bars visibly cross the 100% limit — the footnote states both
  findings. The PNG is a committed sample artifact (deterministic: same case + same lines => same
  pixels), regenerated on every `--step check-limits` run and asserted to exist by `--step check`,
  never pixel-diffed.

## Command

```
uv run scripts/fetch_csiro_nem_data.py   # once, to populate data/snem1803.m
uv run labs/02-medium-interconnection-screening/workflow.py --step base
uv run labs/02-medium-interconnection-screening/workflow.py --step contingencies
uv run labs/02-medium-interconnection-screening/workflow.py --step check-limits
uv run labs/02-medium-interconnection-screening/workflow.py --step memo --approve APPROVE
uv run python -m pytest labs/02-medium-interconnection-screening/test_lab2.py
```

## Step-by-step walkthrough (presenter / backup script)

1. **`uv run labs/02-medium-interconnection-screening/workflow.py --step base`**
   — You should see: `Loaded snem1803.m, attached candidate 250 MW generator at bus 175` followed
   by `Base-case power flow converged: True`.
   — Why it matters: this is the "does the case even solve before we stress it" gate every real
   screening study starts with.
2. **`uv run labs/02-medium-interconnection-screening/workflow.py --step contingencies`**
   — You should see: `Contingency 1/21 complete (line 143 [175-249] dropped: no violations)` ...
   through `Contingency 21/21`, arriving in completion order (not submission order) because they
   run as real parallel OS processes, not a visible serial loop.
   — *Backup if you don't want to run it live*: the committed `expected_contingency_table.json`
   fixture has the full N-1 table pre-computed; print it and say "here's the pass/fail table this
   step produces."
3. **`uv run labs/02-medium-interconnection-screening/workflow.py --step check-limits`**
   — You should see: a table — line, from/to bus, worst bus voltage, worst line loading, pass/fail
   — with every row FAIL. 19 rows show only the "(pre-existing in base case, not caused by this
   contingency)" voltage annotation; the rows for lines 151 and 152 additionally carry a
   "loading 113.0%/111.4% on line 152/151 exceeds 100.0% (contingency-induced)" clause — see
   Sandbox notes above for the parallel-pair story, and why the pre-existing-only reading of this
   screen was a bug, not a result. The step also ends with `[chart] wrote
   sample_contingency_chart.png`, a committed two-panel rendering of those same numbers (worst
   loading % vs the 100% thermal limit; worst voltage pu vs the 0.90–1.10 pu band).
   — Why it matters: this is the actual engineering judgment call, made deterministically against
   documented criteria, not eyeballed — and now it can be glanced at, not just read as a table.
4. **`uv run labs/02-medium-interconnection-screening/workflow.py --step memo --approve APPROVE`**
   — You should see: the drafted plain-English screening memo (now reporting the real
   contingency-induced finding: "RESULT: 2 contingency(ies) BREACH limits as a direct result of
   the outage: line 151/152 ..." — the parallel-pair overload from Sandbox notes), then
   `Human-in-the-loop checkpoint: APPROVE received -> MEMO FINALIZED.`
   — Run the same command *without* `--approve APPROVE` (and without a TTY, e.g. piped from
   `/dev/null`) to see the other half: `Human-in-the-loop checkpoint: BLOCKED, awaiting human
   approval.` and a non-zero exit — the workflow genuinely refuses to finalize on its own.
   — Why it matters: this is the human-in-the-loop checkpoint made literal — the agent proposes
   the memo text, it does not sign off on itself.
5. **`uv run python -m pytest labs/02-medium-interconnection-screening/test_lab2.py`**
   — You should see: `3 passed` — the fixture-match, blocks-without-approval, and
   finalizes-with-approval checks, wrapped for CI/`scripts/run_labs_1_3.sh`.
