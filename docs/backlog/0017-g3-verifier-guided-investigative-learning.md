# 0017 — G3: verifier-guided investigative learning

- **Status:** open. [PRD-0010](../prd/0010-powercoder-physics-grounded-engineering-agent.md) G3, priority A4. Depends on G0 ([0008](0008-powercoder-benchmark-cannot-measure-agent-value.md))
  and G2 ([0016](0016-g2-verified-engineering-mathematics.md)).
- **Requirements:** PC-REQ-050–055, PC-CON-004.

## Deliverables
- **Procedural task generator:** many networks (CSIRO cases, plus IEEE 118 and PEGASE 89),
  operating points, contingencies, free-text objectives and unbracketed fits. Today's set is one
  network and one interval.
- **Rewards from the existing grader:** `grade()`, provenance, and a tool-call cost. Unsupported
  conclusions are penalised.
- **GRPO run:** starting from the r6 students. Rollouts go through the r6 harness (`tool_probe`, the
  MCP server, `evaluate_agent`) so training and evaluation match.
- **Distillation:** `powercoder/distillation/teacher.py` with solver-verified rejection sampling
  for tasks that no script covers.
- **Inference-time search:** the strict-tool-calling 2×2 queued after r6b is the first data point.

## Ablations (all with tools, equal budgets, frozen unseen networks)
1. Prompted base.
2. r6 student.
3. RL student.
4. RL student with verifier-guided search.
5. Larger planner with student workers.

## Exit criteria
- **Improvement:** over the strongest baseline on a primary benchmark declared in advance, with a
  paired confidence interval that excludes zero (`compare_agents.domain_threshold_met_ci_lower`).
- **No regression** on safety and evidence checks.
- **Cost recorded:** tool calls and wall time.
- **Robustness tests done:** reward hacking and verifier disagreement.
- **Isolation:** training and hidden evaluation stay separate.

## Cheapest first step
A GRPO pilot on the r6 Qwen student over generated load-scale fits drawn from two networks, scored
on calls to reach tolerance against bisection. Pair it with 0013's Newton tool, to see whether RL
discovers sensitivity-guided steps.
