# Lab 3 (Advanced) — Multi-Provider Bake-off, Podman-Scaled

> Status: **spec only** — see `docs/VISION.md` §7 "Lab 3".

## What you'll do

1. Reuse `snem1803.m` and 3+ task families in the shape of Lab 1's parameter-fit task (line rating
   fit, generator droop-constant fit, plus at least one more borrowed from the PowerAgentBench-SS
   task pattern).
2. Run the same tasks, same tolerances, same deterministic scorer against several local model
   providers served through the same llama.cpp pod (Phi-4-mini-instruct, Gemma-4, Llama-3.2-3B),
   swapped in with `podman kube play --replace`.
3. Orchestrate each provider's manager+worker pair with Agent Framework's Magentic/group-chat
   pattern so every provider sees an identical prompt/tool surface.
4. **Add a fourth, non-agentic row**: pull a pretrained [PowerFM](https://github.com/Power-Agent/PowerFM)
   **OpenPowerBench** load-forecasting checkpoint from Hugging Face Hub and run it directly (no
   LLM, no tool calls, no orchestration) against a CSIRO regional load trace, scored on the same
   held-out-window metric. This is the paper's "Foundation Model" pillar sitting next to the
   "Agent + MCP + Workflow" pillar in one scorecard — not a competing claim, the two other thirds
   of the same architecture (see `docs/VISION.md` §1).
5. Run the same matrix as a Kubernetes `Job` (`kube/benchmark-runner-job.yaml`) so the 3×N sweep
   can be farmed out as parallel pods instead of a serial loop.
6. Write a single scorecard (JSON + printed table) to
   `benchmarks/power-agent-bench-lite/results/`.

## Why an AEMO modeller should care

This is the "which local model is actually good enough for this class of task, and how would you
know" question, answered with a re-runnable, diffable artifact instead of an anecdote — and the
moment in the whole repo where reaching for orchestration (rather than a for-loop) is the
Operations-relevant call, because the workload is genuinely parallel and genuinely repeated. The
PowerFM row also answers a question the board will ask unprompted: "why not just use a proper
forecasting model instead of an LLM?" — the scorecard shows exactly where a purpose-built
foundation model wins outright (forecasting) and where the agentic tool-calling path is doing a
different job entirely (interactive parameter fitting against an engine you don't want to
retrain a model on).

## Command (once implemented)

```
uv run labs/03-advanced-provider-bakeoff/orchestrator.py
```
