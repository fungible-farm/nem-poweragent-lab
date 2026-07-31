# `power-agent-bench-lite`

> Status: **spec only**. See `docs/VISION.md` §7 "Lab 3", including the PowerFM baseline row.

A small, self-hosted benchmark harness in the same spirit as the external
[PowerAgentBench](https://github.com/Power-Agent/PowerAgentBench) family (structured task → agent
tool calls → independent deterministic re-check → feasibility flag + normalized score), scoped
down to the task families exercised by Lab 1 and Lab 3 so it can run fully offline against the
CSIRO dataset without depending on the external benchmark's own case files or scoring service.

Results land in `results/` as JSON, one file per run, so bake-off comparisons are diffable across
providers and across time rather than screenshots.
