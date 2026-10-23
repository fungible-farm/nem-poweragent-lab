# 0017 — G3: verifier-guided investigative learning

- **Status:** open; **CPU groundwork done** 2026-10-24, incl. held-out networks and pool v2 (below). The GRPO run needs the GPU and starts from the r7 students. [PRD-0010](../prd/0010-powercoder-physics-grounded-engineering-agent.md) G3, priority A4. Depends on G0 ([0008](0008-powercoder-benchmark-cannot-measure-agent-value.md))
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

## Groundwork for the RL pilot (2026-10-24)
- **Procedural pool:** `powercoder/datasets/procedural.py` (`just powercoder::procedural-pool`).
  - Load-scale fits come from **two networks**, snem-sa-2000 and snem-1803. The latter is solvable
    since the flat-start retry (0008).
  - Each network's elements are *discovered*: buses whose voltage is strictly monotone over five
    load scales and spans at least 1e-3 pu; 40 per network.
  - References come from the benchmark's own real bisection.
  - A 40-task pool (20 + 20) is audited clean against all four evaluation suites (306-task,
    stratified 100, smoke 20, judgement 40).
- **Reward:** `training/rl_reward.py`.
  - +1 for an answer that passes the solver re-check, v3 field provenance and tool evidence.
  - −1 for a final answer with an untraced number.
  - −0.02 per tool call (0.02 × 24 = 0.48 < 1, so correct always beats incorrect).
  - Tested on a real scripted attempt: reward exactly 1 − 0.02 × calls.
- **The baseline to beat** (bisection replayed through the study tool):

  | Network | Median calls | Range |
  |---|---|---|
  | snem-sa-2000 | 5 | 4–7 |
  | snem-1803 | 6 | 4–7 |

  An RL student "discovers sensitivity-guided steps" (0013) only if it reaches tolerance in
  fewer calls than these, at the same pass rate.

## Held-out networks and pool v2 (2026-10-24) — resolves the caveat above

The v1 pool drew from snem-1803, the network r7 holds out. The tools now also serve pandapower's
built-in IEEE 39, IEEE 118 and PEGASE 89 cases (BSD-3; `powermcp.STANDARD_CASES`, identified by
the hash of their serialised data). All three solve in 3-4 Newton iterations. The network roles
are fixed in `procedural.py`, and an assert forbids overlap:

| Role | Networks |
|---|---|
| SFT trajectories (r7) | snem-sa-2000 |
| RL pool (`POOL_NETWORKS`) | snem-sa-2000, ieee118, pegase89 |
| Held out (`HELD_OUT_NETWORKS`) | snem-1803 (r7 judgement and unsolvable suites), ieee39 |

The widened network list is in the schema r7 trains on (trajectories v5), so RL rollouts later
use the same tool block as the r7 students: no train/serve skew.

Pool v2 (`training/unsloth/out/procedural-pool-20261024-v2`, `just powercoder::procedural-pool`):

- 150 load-scale fits, 50 per pool network, with 40 discovered elements each;
- prompt wording v2; 36 fits are unbracketed (no interval in the prompt);
- audited clean against six suites: benchmark 100 v1/v2, smoke 20 v1/v2, judgement v2 and
  unsolvable v2. `main` refuses to freeze a pool that is unclean or audited against nothing.

The baseline to beat, bisection replayed through the study tool over pool v2:

| Network | Median calls | Range |
|---|---|---|
| snem-sa-2000 | 6 | 4–8 |
| ieee118 | 6 | 4–7 |
| pegase89 | 6 | 4–7 |

**Left, and why:**
- **GRPO run and distillation:** need the GPU. They start from the r7 students, after the r7 chain.
- **Contingency fits:** `score_answer`'s independent fit check re-solves the intact network, so
  an N-1 fit needs a grader that applies the outage first. Without one, those fits would be scored
  against the wrong network.
- **Operating points and free-text objectives:** not built. The judgement suite's intent prompts
  are the model for free-text objectives.
