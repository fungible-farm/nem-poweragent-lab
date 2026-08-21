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

## pypowsybl N-1 cross-check (a real second opinion, not another stand-in)

> Full write-up, conclusions, and implications:
> [`docs/POWERFLOW_ENGINE_SHOOTOUT.md`](../../docs/POWERFLOW_ENGINE_SHOOTOUT.md).

`pypowsybl_cross_check.py` re-solves the exact same 21 contingencies as an independent, real
second opinion: [PowSyBl](https://github.com/powsybl) (RTE's power-system framework, via its real
`pypowsybl` Python bindings, OpenLoadFlow solver) against `workflow.py`'s own pandapower screen.
This promotes pypowsybl from `labs/03-advanced-provider-bakeoff/spike_pypowsybl.py`'s standalone
aggregate-loss comparison into a real, wired-in capability — a genuine cross-validation of the
same screening decision this lab already makes, using `labs/_shared/gridfit.py`'s
`to_pypowsybl_network()` / `pypowsybl_element_id_map()` helpers (shared with the Lab 3 spike, not
duplicated).

**Two more real pypowsybl data-fidelity gaps found while building this** (beyond Lab 3's
`.m`→`.mat` finding), both worked around in the shared helper, not silently masked:

- **Bus-id correlation is not `pandapower_bus_id + 1`.** pandapower's own bus index preserves the
  original MATPOWER bus numbers (often large and non-sequential — this repo's cases can go past
  10000), but the `.mat` file `to_mpc()` writes uses a *completely different*, internally
  renumbered 1-based sequence (pandapower's own `to_ppc()` bus compaction). Naively assuming
  `pandapower_bus_id + 1` matched pypowsybl's `LINE-<a>-<b>` element ids on only 14 of 1215 real
  lines; using pandapower's own `net._pd2ppc_lookups["bus"]` (the exact table `to_ppc()` builds
  internally) matched 1215/1215.
- **`matpower.import.ignore-base-voltage` defaults to `true`.** pypowsybl's MATPOWER importer
  silently discards the real per-bus base-kV column by default — every bus came back at
  `nominal_v=1.0` regardless of this repo's real NEM voltage levels (132kV, 66kV, 33kV, 11kV,
  etc., genuinely present in the `.mat` file), making reported voltages and currents physically
  meaningless. Confirmed this is a pure reporting-convention default (total system generation/
  load/loss are bit-identical either way) — `to_pypowsybl_network()` always passes this parameter
  as `false`.

**Result:** worst-case bus voltage per contingency matches to within **0.00000 pu** across all 21
contingencies (both engines independently confirm the base-case 0.899 pu breach at bus 1126 /
`VL-910`). Worst-case line loading agrees closely for the two *genuinely contingency-induced*
thermal breaches this lab exists to catch — lines 151/152's parallel-pair overload — matching
**exactly** (113.00% / 111.37%, both engines, both directions). The other 19 (non-contingency-
induced, pre-existing base-case) contingencies show a real ~3% relative loading difference,
consistent with a per-branch current-modelling difference between the two solvers (see
`pypowsybl_cross_check.py`'s own tolerance comment) — named honestly rather than tightened away.
**21/21 contingencies agree** within the documented tolerances.

```
uv run labs/02-medium-interconnection-screening/pypowsybl_cross_check.py --step run
uv run labs/02-medium-interconnection-screening/pypowsybl_cross_check.py --step check
```

## Network diagram (`sample_network_diagram.svg`)

`render_network_diagram.py` draws the same 14-bus/21-line N-1 neighbourhood `workflow.py`'s own
screen already computes — the diagram is a rendering of an already-verified result, not a new
source of truth (same convention as `sample_contingency_chart.png` above). Deliberately scoped to
this local neighbourhood, not the full `snem1803.m` (1803 buses, no geographic coordinates —
would render as an unreadable hairball); layout is `networkx.kamada_kawai_layout` (deterministic,
no RNG), rendered to a real vector SVG via matplotlib's `Agg` backend.

Candidate bus 175 is marked distinctly (orange, larger). Every real parallel-line pair in this
neighbourhood — not just the well-known 151/152 pair — is drawn as two genuinely separate curved
edges rather than collapsed into one: 143/150 (175↔249), 145/146 (175↔275), 147/148 (175↔328),
181/182 (185↔254), and 151/152 (175↔608). Edge color/width encodes base-case `loading_percent`
(a blue scale, deliberately *not* a red-family colormap — 181/182 load up to 43.6%/36.7%, near
the top of this neighbourhood's range, and a red colormap there would look identical to the one
genuine finding below). Lines 151/152 are the sole exception: hard-coded bright red, since they
are the only *contingency-induced* breach this lab's screen actually found (see Sandbox notes
above) — every other parallel pair here is a normal double-circuit, not a violation.

```
uv run labs/02-medium-interconnection-screening/render_network_diagram.py
```

## Command

```
uv run scripts/fetch_csiro_nem_data.py   # once, to populate data/snem1803.m
uv run labs/02-medium-interconnection-screening/workflow.py --step base
uv run labs/02-medium-interconnection-screening/workflow.py --step contingencies
uv run labs/02-medium-interconnection-screening/workflow.py --step check-limits
uv run labs/02-medium-interconnection-screening/workflow.py --step memo --approve APPROVE
uv run python -m pytest labs/02-medium-interconnection-screening/test_lab2.py
```

## Running in a container (Windows-friendly)

No local `uv`/Python/pandapower install needed — build once, run anywhere Docker Desktop or Podman
Desktop is installed (both run on Windows via a WSL2 backend, and read a `Containerfile` exactly
like Linux/macOS native `podman`/`docker`):

```
podman build -t nem-poweragent-base:local -f Containerfile.base .
podman build -t lab2:local -f labs/02-medium-interconnection-screening/Containerfile .
podman run --rm lab2:local
```

(Swap `podman` for `docker` if that's what you have.) The first `build` installs this repo's full
dependency set once, shared by every other lab's own image — see `Containerfile.base`'s own
header. The default run reproduces the `--step check` output above exactly; override the `CMD` to
run another step, e.g. the human-in-the-loop memo gate:
`podman run --rm lab2:local --step memo --approve APPROVE`.

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
