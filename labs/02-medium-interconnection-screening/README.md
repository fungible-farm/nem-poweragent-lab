# Lab 2 (Medium) — Interconnection / Asset-Provisioning Screening

> Status: **spec only** — see `docs/VISION.md` §7 "Lab 2". This mirrors PowerWF's "Grid Impact
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

## Step-by-step walkthrough (presenter / backup script)

1. **`uv run labs/02-medium-interconnection-screening/workflow.py --step base`**
   — You should see: `Loaded snem1803.m, attached candidate 250 MW generator at bus <id>`
   followed by `Base-case power flow converged`.
   — Why it matters: this is the "does the case even solve before we stress it" gate every real
   screening study starts with.
2. **`uv run labs/02-medium-interconnection-screening/workflow.py --step contingencies`**
   — You should see: a live-updating count, `Contingency 7/23 complete (line L-114 dropped:
   no violations)`, run as parallel tool calls, not a visible serial loop — the point is that they
   genuinely overlap, not just that the log looks busy.
   — *Backup if the pandapower MCP pod isn't reachable*: the committed
   `expected_contingency_table.json` fixture has the full N-1 table pre-computed; print it and say
   "here's the pass/fail table this step produces."
3. **`uv run labs/02-medium-interconnection-screening/workflow.py --step check-limits`**
   — You should see: a table — contingency ID, worst bus voltage, worst line loading, pass/fail
   against the stated NEM planning bands — with any breach highlighted.
   — Why it matters: this is the actual engineering judgment call, made deterministically against
   documented criteria, not eyeballed.
4. **`uv run labs/02-medium-interconnection-screening/workflow.py --step memo`**
   — You should see: the agent's drafted plain-English screening memo printed to the terminal,
   then a Gradio page opens with `gr.Button("Approve")` sitting unclicked — the workflow genuinely
   pauses here.
   — Why it matters: this is the human-in-the-loop checkpoint made literal — click the button
   yourself, and only then does the memo get marked final. This is the single best "show, don't
   tell" moment for the "the agent proposes, a human still signs off" argument.
