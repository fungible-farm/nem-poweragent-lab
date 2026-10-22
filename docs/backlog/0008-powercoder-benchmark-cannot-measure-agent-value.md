# 0008 — PowerCoder benchmark cannot measure agent value (priority 1)

- **Status:** open. Merit 5 in the [independent review](reviews/2026-10-23-r6-merit-review.md), idea 8. Must be stated as a caveat beside any r6 number.
- **Found:** 2026-10-23. Measured on the r6 inputs (`domain-stratified-100-20261022`, `smoke/splits/train.jsonl`).

## Evidence
- All 100 benchmark tasks and all 273 training rows use one network, `snem-sa-2000`.
- Every fit task gives the same interval, [0.9, 1.1].
- 36 of the benchmark's 69 (subfamily, element) keys also occur in training, with different targets.
- Every task is solved by a fixed ~30-line policy (bisection, or one `operation="none"` trial), and the students are trained to imitate exactly that policy. A line-rating fit is solvable from one trial: `max_i_ka` scales and the current does not, so s = loading(1)/target (derived from the code, not run).
- `compare_agents.py` gated on the point estimate. `domain_threshold_met_ci_lower` now records the paired 95% interval's lower bound beside it. The six pairwise comparisons on one sample have no multiplicity correction.

## Consequence
A student that reproduces the template will clear +10 pp against bases near 5% without showing domain or agentic skill. r6 measures "can a LoRA learn the tool protocol", which is a legitimate harness result, not agent value.

## Proposal
1. **Baselines.** (a) The script as an agent: the oracle, scored with pass rate, tool calls and wall time. (b) Each base model with the procedure written into its system prompt. Report student − prompted base and script − student, with paired intervals.
2. **Tasks that need judgement.**
   - Choosing the study from free-text intent.
   - Fits with no interval given, or with a non-monotone or non-convergent end.
   - "New violations versus the base case", which needs a violation-listing tool.
   - Multi-step goals across contingencies.
   - A held-out network.
   - RestoreBench (Lab 10).
3. **Score efficiency against the script:** calls, tokens and wall time.

## Cheapest decisive experiment
Baseline (b) on the 20 smoke tasks for both base models, about 1–2 h of GPU. If a prompted base matches the student, fine-tuning added nothing measurable.
