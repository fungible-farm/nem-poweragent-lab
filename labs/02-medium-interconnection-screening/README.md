# Lab 2 (Medium) — Interconnection / Asset-Provisioning Screening

Before a new generator or big load can connect to the grid, the operator has to check it won't
break anything — including if a line or another generator drops out unexpectedly at the same time.
This lab runs that check for real: a candidate 250 MW generator, a full N-1 contingency screen, and
a human approval gate before anything is called final.

*New to N-1 contingency screening or pu voltage? See the root [README's Concepts section](../../README.md#concepts-in-plain-terms).*

## What you'll do

1. Load `snem1803.m` (the mainland NEM grid model) and attach a hypothetical 250 MW generator at
   bus 175, a real 132 kV bus with 21 lines within two hops of it.
2. Solve the base-case power flow with the candidate generator attached.
3. Run the N-1 screen: drop each of the 21 nearby lines, one at a time, and re-solve — as genuinely
   parallel OS processes (`concurrent.futures.ProcessPoolExecutor`), not a loop that just looks
   parallel.
4. Check every result against a simplified planning limit (voltage within 0.90–1.10 pu, line
   loading ≤100%) and produce a pass/fail table, plus a two-panel chart.
5. Draft a plain-English screening memo — blocked behind a human approval step that genuinely has
   to be satisfied before the memo is marked final.

The point of the lab: every physics step here is a deterministic script, not something an AI
reasons about numerically — the same "workflow automation with a real human checkpoint" pattern a
real interconnection study would need to defend.

## Design notes

The original spec (`docs/VISION.md` §7) runs these same four steps as a Microsoft Agent Framework
workflow calling a networked PowerMCP server for each physics step. This build calls `pandapower`
directly in-process instead — the physics, the real parallelism, and the human-approval gate are
all unaffected; only the transport is swapped. See `workflow.py`'s module docstring for the exact
call site you'd change to wire in the networked version.

Two things worth knowing before you read the output:

- `snem1803.m`'s default flat-start pre-solve hits a divide-by-zero (a zero-impedance branch, a
  common artifact of how MATPOWER models merge buses). `workflow.py` calls
  `pp.runpp(net, init="flat")` to skip that pre-solve; the AC solve then converges cleanly.
- The 0.90–1.10 pu / 100% limit band is a simplified stand-in for AEMO's real per-voltage-level
  limit table (NER Schedule 5.1a) — a real submission would use the exact table per voltage level,
  not one flat band.

## A real finding worth knowing before you read the table

Every one of the 21 contingencies shows a voltage breach at bus 1126 — but that's a **pre-existing
condition**: bus 1126 sits at 0.899 pu even with nothing dropped at all, so it isn't caused by any
of these contingencies. `check_limits()` labels it as such rather than letting a real-data quirk
look like a bug.

There are, however, two **genuinely contingency-induced** breaches, which is exactly what this
screen exists to catch: lines 151 and 152 are a parallel pair (both connecting the same two buses,
each carrying ~55–56% of the load normally). Drop either one, and the survivor has to carry both
circuits — 113.0% loading on line 152 when 151 is dropped, 111.4% on line 151 when 152 is dropped.
Both rows are marked FAIL for this reason specifically, distinct from the bus-1126 pre-existing
condition. `sample_contingency_chart.png` plots this directly: 19 of 21 bars sit flat at the
pre-existing ~97.8% / 0.899 pu point, while the 151/152 bars visibly cross the 100% line.

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

No local install needed — works identically under Docker Desktop, Podman Desktop, or native
podman/docker:

```
podman build -t nem-poweragent-base:local -f Containerfile.base .
podman build -t lab2:local -f labs/02-medium-interconnection-screening/Containerfile .
podman run --rm lab2:local
```

This reproduces the `--step check` output below. Override the step to see the human-approval gate:
`podman run --rm lab2:local --step memo --approve APPROVE`.

## Step-by-step walkthrough

1. **`--step base`** — `Loaded snem1803.m, attached candidate 250 MW generator at bus 175` then
   `Base-case power flow converged: True`. The "does the case even solve before we stress it" gate
   every real screening study starts with.
2. **`--step contingencies`** — `Contingency 1/21 complete (line 143 [175-249] dropped: no
   violations)` ... through 21/21, arriving in completion order rather than submission order,
   because they really are running as parallel processes. (No live run needed to follow along —
   `expected_contingency_table.json` has the full pre-computed table.)
3. **`--step check-limits`** — A table (line, from/to bus, worst voltage, worst loading, pass/fail)
   where every row is FAIL: 19 for the pre-existing bus-1126 condition, lines 151/152 for the real
   contingency-induced overload above. Ends with `[chart] wrote sample_contingency_chart.png`.
4. **`--step memo --approve APPROVE`** — The drafted memo, reporting "2 contingency(ies) BREACH
   limits as a direct result of the outage: line 151/152 ...", then `Human-in-the-loop checkpoint:
   APPROVE received -> MEMO FINALIZED.` Run the same command *without* `--approve APPROVE` (piped
   from `/dev/null`, so there's no terminal to prompt) to see it refuse instead: `BLOCKED, awaiting
   human approval` and a non-zero exit.
5. **`pytest test_lab2.py`** — `3 passed`: the fixture match, the blocks-without-approval case, and
   the finalizes-with-approval case.
