# Lab 2 (Medium) — Interconnection / Asset-Provisioning Screening

> Status: **spec only** — see `docs/VISION.md` §6 "Lab 2". This mirrors PowerWF's "Grid Impact
> Evaluation" reference workflow, reimplemented on Microsoft Agent Framework instead of LangGraph.

## What you'll do

1. Load `snem1803.m` (mainland NEM), attach a hypothetical 250 MW generator at a named bus.
2. Sequential step: solve the base-case AC power flow with the candidate generator attached.
3. Concurrent step: fan out an N-1 contingency screen (drop each local line) as parallel MCP tool
   calls against the `powermcp-pandapower` pod; collect results.
4. Sequential step: check each contingency against documented NEM planning voltage/thermal bands;
   produce a pass/fail table.
5. Final step: agent drafts a plain-English screening memo; a human-in-the-loop checkpoint gates
   before the memo is marked final (Agent Framework's built-in checkpoint/resume, not a rubber
   stamp).

## Why an AEMO modeller should care

This is the actual "deterministic scripting of workflow automation of steps necessary to
provision an asset or study" pattern from the brief: every physics step is a script the agent
calls, never something it reasons about numerically. The pandapower MCP server pod is pinned to
one version for the whole run — that pin is the reproducibility statement a real screening
submission would need to defend.

## Command (once implemented)

```
uv run labs/02-medium-interconnection-screening/workflow.py
```
