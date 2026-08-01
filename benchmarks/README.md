# `power-agent-bench-lite`

> Status: **implemented** — see `labs/03-advanced-provider-bakeoff/orchestrator.py` and its own
> README's "Sandbox notes" for what stands in for a live model server in this environment.
> `results/scorecard.json` is real, committed output from `orchestrator.py --step report`, diffable
> against `labs/03-advanced-provider-bakeoff/expected_scorecard.json`. See `docs/VISION.md` §7
> "Lab 3" for the original spec, including the PowerFM baseline row.

A small, self-hosted benchmark harness in the same spirit as the external
[PowerAgentBench](https://github.com/Power-Agent/PowerAgentBench) family (structured task → agent
tool calls → independent deterministic re-check → feasibility flag + normalized score), scoped
down to the task families exercised by Lab 1 and Lab 3 so it can run fully offline against the
CSIRO dataset without depending on the external benchmark's own case files or scoring service.

Results land in `results/` as JSON, one file per run, so bake-off comparisons are diffable across
providers and across time rather than screenshots.
