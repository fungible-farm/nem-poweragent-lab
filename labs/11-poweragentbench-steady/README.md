# Lab 11 — PowerAgentBench Steady Levels 1-2

Two more outside benchmarks from [PowerAgentBench](https://github.com/Power-Agent/PowerAgentBench),
on the IEEE 39-bus system. This system has real branch limits.

- **Level 1 — N-1 audit and mitigation.** A stressed case39, a published contingency list, and a
  bounded, costed action space (redispatch, voltage support, taps, shunts, load shed). The scorer
  checks base-case and contingency violations after the submitted actions.
- **Level 2 — agentic N-2 search.** The agent gets a limited validation budget, submits an
  evidence-backed ranked list of contingencies, and may redispatch. A hidden oracle scores
  discovery, evidence, mitigation and efficiency.

## What you'll do

```
just lab11-fetch        # independent pinned checkout in data/poweragentbench
just check-lab11        # fast gate: pinned sources + comparison logic
just lab11-check-slow   # Level 1 vs the published baseline, Level 2 baselines vs the fixture (~45 s)
```

Steps: `labs/11-poweragentbench-steady/steady_lab.py --step {verify,level1,level2,check}`.

## The actual result (2026-10-23, GB10 / aarch64)

| Check | Result |
|---|---|
| Checkout | commit `b39c48b`, 18 files unchanged (`expected_sources.json`) |
| Level 1, solution template vs the published `baseline_summary.json` | 44 fields; max absolute difference 1.48e-12; remaining violation score 0.4195833354652492 (published 0.41958333546521553); not feasible, as published |
| Level 2, the 7 scripted baselines on 8 case39 variants (budget 80, top-20) | every per-case row satisfies `score_agent`'s identities; the headline metrics match `expected_level2_headline.json`; two runs were byte-identical |

Level 2's headline metrics, as measured. PowerAgentBench publishes none, so these are this lab's own
run (`--step record-level2`), not a reference. The definitions are `score_agent`'s.

| Agent | Reported top-20 recall | Evidence rate | Violation reduction | Budget used |
|---|---|---|---|---|
| Base-loading | 0.519 | 1.0 | 0.0 | 1.0 |
| Hybrid-tool | 0.225 | 1.0 | 0.0 | 1.0 |
| Hybrid+redispatch | 0.225 | 1.0 | 0.077 | 1.0 |
| LODF-screen | 0.081 | 1.0 | 0.0 | 1.0 |
| Random | 0.079 | 1.0 | 0.0 | 1.0 |
| Topology | 0.0 | 1.0 | 0.0 | 1.0 |
| No-validation | 0.0 | 0.0 | 0.0 | 0.0 |

Only Hybrid+redispatch takes mitigating actions, so it is the only one with a violation reduction.
The README itself calls Level 2's evaluator "a lightweight DC approximation intended to test the
benchmark mechanics … not a replacement for AC security analysis".

## Design notes

- **Licence: an assumption, by user direction.** PowerAgentBench has no root licence
  ([#11](https://github.com/Power-Agent/PowerAgentBench/issues/11)). The user directed on
  2026-10-23 that Levels 1-2 be used as MIT, the licence of the organisation's other repositories.
  That is recorded as an assumption in `docs/PSCADOSSE.md`. The checkout is fetched, not vendored.
- **Own environment.** Levels 1-2 ship no lockfile. This lab's `pyproject.toml`/`uv.lock` pins
  what they resolve to (pypsa 1.2.4, pandapower 3.5.6, Python 3.12). It is kept out of the repo
  venv. Level 1's README cites pypsa 1.0.7; the published
  numbers still reproduce, as the table shows.
- **Level 2's fixture checks for drift; its identities check for errors.** With no published
  numbers, `expected_level2_headline.json` keeps 4 metrics per agent, defined in the file and
  written with its provenance (commit, date, lock hash, arguments), so it is never hand-edited. The
  error check is `LEVEL2_IDENTITIES`: identities that hold by `score_agent`'s definitions, checked on
  every per-case row. Evidence rate plus unvalidated-claim rate is 1, recall plus false-safe rate
  over the oracle top 20 is 1, and the budget used is in [0, 1].
- **Dynamic Levels are out of scope.** Level 1 needs PSS/E and DMView, and Level 2 needs DIgSILENT
  PowerFactory to simulate. All are commercial, so none is on the golden path. Whether Dynamic
  Level 2 can be scored offline from its shipped memory is unchecked.

## Scope

This lab runs the upstream scripted baselines only. A future model adapter or Level 1 agent
requires separate implementation and evaluation; neither is implied by these benchmark results.
The fetch helper, scorer wrapper and environment have no dependency on another lab or on WattsOn.
