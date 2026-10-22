# 0011 — Strict-tool-calling arm: redesign as a 2×2 before running it

- **Status:** implemented 2026-10-23 (`run_agent_study --strict-arm`). Queued to run after r6 completes, through `powercoder-agent-study-r6-strict-wait`. The confounded single arm was never run. Review idea 1 (merit 3) and B2 ([review](reviews/2026-10-23-r6-merit-review.md)).

## Problem
As built, the arm changes two things at once: `tool_choice="required"` on turn 0, and `--tool-strict-level parameter` on every turn. `compare` records only the first. Strict schemas also block exactly the `"None"` strings that B1 (0009) trained in, so a gain could not be credited to forcing. Backlog 0007 measured that grammar-constrained decoding can be semantically evasive: a forced call could be well formed and useless.

## Proposal
Run strict {off, on} × first-turn {auto, required} on the 20 smoke tasks with both base models, about 4 × 20 attempts per model. Record both flags in the manifest (0010 item 5). Score useless forced calls separately: well-formed calls to the wrong study.

## Measured basis (2026-10-22)
vLLM 0.31 builds xgrammar's model-native Qwen-XML tool grammar per request. `"required"` and the server flag both produced native XML (`</think><tool_call>…`, without the two newlines Qwen otherwise writes). No grammar is stored in the repo.
