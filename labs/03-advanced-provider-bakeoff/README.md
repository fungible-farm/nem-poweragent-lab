# Lab 3 (Advanced) — Multi-Provider Bake-off, Podman-Scaled

> Status: **implemented**. `orchestrator.py`, `expected_scorecard.json`, and `test_lab3.py` are
> real, runnable code — see `docs/VISION.md` §7 "Lab 3" for the original spec, and "Sandbox notes"
> below (the most significant deviation of any lab in this repo — read it before trusting the
> "provider" column).

## What you'll do

1. Reuse `snem1803.m` and 3 task families in the shape of Lab 1's parameter-fit task:
   `load-scale-fit` (a second bus, same mechanic as Lab 1), `line-rating-fit` (fit a line's rating
   to a 100%-of-nameplate thermal trip point), and `gen-droop-fit` (fit a generator's dispatch to a
   target transformer-loading level, a steady-state proxy for droop response).
2. Run the same tasks, same tolerances, same deterministic scorer against 3 local deterministic
   search policies standing in for LLM providers (see Sandbox notes).
3. Add a fourth, non-agentic row: a seasonal-persistence forecast against a synthetic regional
   demand trace, standing in for a PowerFM OpenPowerBench checkpoint (see Sandbox notes).
4. Write a single scorecard (JSON + printed table) to
   `benchmarks/power-agent-bench-lite/results/scorecard.json`, plus a grouped bar chart PNG
   (`scorecard_chart.png`, next to the JSON) so the 3-provider comparison can actually be looked
   at, not just read as a JSON array. Both are regenerated, gitignored local output (not
   committed) — `wall_clock_s` differs every real run, so the committed, diffable fixture is
   `expected_scorecard.json` instead (see "Backup" below).

## Why an AEMO modeller should care

This is the "which local model is actually good enough for this class of task, and how would you
know" question, answered with a re-runnable, diffable artifact instead of an anecdote. The
architecture — run the same tasks/tolerances/scorer across every provider, append a non-agentic
foundation-model baseline in the same scorecard rather than treating it as a competing claim — is
the real deliverable here; see Sandbox notes for what stands in for what in *this* run.

## Sandbox notes (read this before the walkthrough)

`docs/VISION.md`'s Lab 3 swaps three *live* local LLMs (Phi-4-mini-instruct, Gemma-4,
Llama-3.2-3B) through a single llama.cpp pod via `podman kube play --replace`, orchestrated with
Agent Framework's Magentic/group-chat pattern, plus a PowerFM OpenPowerBench checkpoint pulled from
Hugging Face Hub. This sandbox has no `podman`, no GPU, and no budget to download and serve three
GGUF models or a PowerFM checkpoint. So, concretely:

- **`local-policy-A` / `local-policy-B` / `local-policy-C`** are three deterministic search
  policies (plain bisection, false-position/regula-falsi, and a seeded-noise perturbed bisection —
  see `orchestrator.py`'s docstrings) standing in for the three LLMs' "propose the next trial
  value" role. They are never given a real model's name, so the scorecard can never be mistaken
  for a real model comparison — the variation you see between them (different iteration counts,
  different error margins) is real, reproducible variation between three different *algorithms*,
  not between three different *language models*.
- **`PowerFM-OpenPowerBench-stub`** is a seasonal-persistence forecast against a synthetic (not
  historical-AEMO) regional demand trace built from `snem1803.m`'s own static load table plus a
  documented daily-shape multiplier — not a real trained forecasting model. The scorecard slot,
  metric (MAPE over a held-out day), and "single forward pass, no tool calls" character are real;
  the specific model is not.
- There is no Magentic/group-chat orchestration — there is no live chat model to orchestrate. The
  orchestration that *is* real here is running the 3×3 provider/task-family matrix plus the
  baseline row and collecting them into one scorecard, which is the part of Lab 3 that is
  architecture, not model weights.
- `kube/benchmark-runner-job.yaml` is a written, valid Kubernetes Job manifest shaped to run this
  same matrix as parallel pods per `docs/VISION.md` §9 — it has **not** been executed here (no
  `podman` binary in this sandbox). See the manifest's own header comment for exactly what's
  missing to make it fully wire up (a Containerfile, and a `PROVIDER_FILTER` env var so each
  indexed completion scores one provider instead of all three).

## pypowsybl spike (solver comparison, not a bake-off provider)

`spike_pypowsybl.py` answers a different question from the rest of this lab: not "which search
policy is best," but "is [PowSyBl](https://github.com/powsybl) (RTE's open-source power-system
modelling framework, via its real `pypowsybl` Python bindings) a viable alternative power-flow
*engine* for this repo's real NEM data at all." It is deliberately **not** wired into the
provider matrix above — this lab's "providers" are search policies, all running the same
underlying pandapower solver; a different solver is a different axis entirely.

**Real finding #1 — a genuine toolchain gap, not this repo's bug:** pypowsybl's MATPOWER
importer only accepts the binary MATLAB `.mat` serialization of a case, not the human-readable
`.m` script format every `.m` file in this repo (and everything MATPOWER itself ships) actually
is — confirmed against both `snem1803.m` and a hand-written textbook `case9.m`, both rejected by
`pypowsybl.network.is_loadable()`, and confirmed against
[PowSyBl's own MATPOWER import docs](https://powsybl.readthedocs.io/projects/powsybl-core/en/latest/grid_exchange_formats/matpower/),
which state the same requirement plainly. No MATLAB/Octave is installed in this environment to do
that conversion the documented way. **Fix used here:** round-trip the already-loaded pandapower
net through pandapower's own `to_mpc()` (a real `scipy.io.savemat`-backed MATPOWER `.mat` writer)
before handing it to pypowsybl — both solvers then run against the exact same in-memory network.

**Real finding #2 — the two engines agree, within a small, named, honestly-reported gap:** on the
real `snem1803.m` case (1803 buses, 2795 branches), pandapower and pypowsybl/OpenLoadFlow both
converge, total load matches exactly (identical input data), total generation agrees to
**0.005%**, and total system real-power losses agree to **0.17%** (1035.9 MW vs 1034.1 MW) — the
line/trafo loss *split* differs somewhat more than the total (886/150 MW vs 912/122 MW), most
likely a transformer tap-model convention difference between the two solvers' formulations, not a
solver defect; not investigated further than that within this spike's scope.
pypowsybl/OpenLoadFlow's own solve is faster (145ms vs pandapower's 2.3s on a cold/first call;
pandapower drops to ~47ms once its numba JIT is warm) — not a fair head-to-head timing claim
either way without controlling for both engines' warm-up cost, reported honestly rather than
picking whichever number favors one side.

**Verdict for this spike:** pypowsybl is a real, usable alternative load-flow engine for this
repo's NEM case data, gated on the `.m`→`.mat` round-trip step above. Whether it's worth
promoting onto the golden path (a second MPL-2.0 dependency alongside DPsim — see
`docs/PSCADOSSE.md`) is an open question for a future PRD, not decided by this spike.

```
uv run labs/03-advanced-provider-bakeoff/spike_pypowsybl.py --step run
uv run labs/03-advanced-provider-bakeoff/spike_pypowsybl.py --step check
```

## Command

```
uv run scripts/fetch_csiro_nem_data.py   # once, to populate data/snem1803.m
uv run labs/03-advanced-provider-bakeoff/orchestrator.py --step sweep
uv run labs/03-advanced-provider-bakeoff/orchestrator.py --step report
uv run python -m pytest labs/03-advanced-provider-bakeoff/test_lab3.py
```

## Running in a container (Windows-friendly)

No local `uv`/Python install needed — build once, run anywhere Docker Desktop or Podman Desktop is
installed (both run on Windows via a WSL2 backend, and read a `Containerfile` exactly like
Linux/macOS native `podman`/`docker`):

```
podman build -t nem-poweragent-base:local -f Containerfile.base .
podman build -t lab3:local -f labs/03-advanced-provider-bakeoff/Containerfile .
podman run --rm lab3:local
```

(Swap `podman` for `docker` if that's what you have.) The first `build` installs this repo's full
dependency set once, shared by every other lab's own image — see `Containerfile.base`'s own
header. The default run reproduces the `--step check` output above exactly; override the `CMD` to
run the full sweep instead: `podman run --rm lab3:local --step sweep`.

This lab also has a second, separate image at the repo root — `Containerfile.bakeoff`, built to
`power-agent-bench-lite:local` — which is the Kubernetes-style provider-partitioned sweep image
`kube/benchmark-runner-job.yaml` actually runs (see that manifest's own header). The
`labs/03-advanced-provider-bakeoff/Containerfile` above is the lighter "just run the tutorial"
path built off the same shared base every other lab uses; the two are deliberately not merged.

## Step-by-step walkthrough (presenter / backup script)

1. **`uv run labs/03-advanced-provider-bakeoff/orchestrator.py --step sweep`**
   — You should see: rows arriving as each provider × task-family pair completes —
   `local-policy-A | load-scale-fit   | PASS | err=0.0013 | 0.57s`, ending with the PowerFM
   baseline row, which prints `n/a tokens/latency-per-call (single forward pass)` since it's a
   single forecast, not a search loop.
   — *Backup if you'd rather not run it live*: this directory's committed
   `expected_scorecard.json` has one full pre-run sweep (the `scorecard.json` written into
   `benchmarks/power-agent-bench-lite/results/` is regenerated, gitignored output, not committed —
   see "What you'll do" step 4); load and print `expected_scorecard.json` instead, saying plainly
   "this is a pre-recorded run, not live."
2. **`uv run labs/03-advanced-provider-bakeoff/orchestrator.py --step report`**
   — You should see: the final scorecard table (10 rows: 3 providers × 3 task families + 1
   baseline), plus `Scorecard written to .../scorecard.json`. This step also (re)renders
   `benchmarks/power-agent-bench-lite/results/scorecard_chart.png` — a grouped bar chart,
   one group per task family, one bar per local-policy provider, bar height = `error_margin` (the
   PowerFM baseline is excluded from this chart: its task family has no local-policy peer to
   compare against in the same units — it stays in the JSON/table above). Neither the JSON nor the
   PNG is committed — both regenerate locally each time this step runs.
   — Why it matters: this is the "which local approach is actually good enough, and how would you
   know" question answered with a re-runnable artifact instead of an anecdote — and now one that
   can be glanced at, not just read as a JSON array.
3. **`uv run python -m pytest labs/03-advanced-provider-bakeoff/test_lab3.py`**
   — You should see: `1 passed` — the full sweep re-run and diffed against
   `expected_scorecard.json` (wall-clock excluded from the comparison, since it's machine-dependent
   by nature).
4. **(super-stretch only, see `docs/VISION.md` §7)**: full `snem2000.m`, real
   PowerAgentBench-SS/Dyn coverage, a live Gradio leaderboard, a chaos/resilience sweep — not part
   of this v1 walkthrough, called out here only so a presenter knows where the demo could grow.
