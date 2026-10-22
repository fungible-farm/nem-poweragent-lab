# 0010 — Provenance check (PC-REQ-1) is weaker than its requirement

- **Status:** open. Review findings B4–B6 ([review](reviews/2026-10-23-r6-merit-review.md)), all reproduced with the reviewer's probe.
- **Context:** `grade()` also requires numerical correctness and matching tool evidence, so most of the cases below still fail the strict score. The weakness is in provenance as a stand-alone guarantee, and in the solver-verified v2 score, which does not require tool evidence.

## Reproduced cases
- **Accepted:**
  - "converged in 100 iterations, voltage violations = 2000" traces to a schema limit and to the case name.
  - A no-tool report with coarse values (1, 1, 1, 2000, 135).
  - "1,039" is read as 1 and 039.
  - A negative invented value traces because the sign is ignored.
  - A fit answer equal to the prompt's interval end (1.1) or to its target.
  - An empty answer (vacuously traced).
- **Rejected:** a truncated value, 0.9069 for 0.90697.
- **Perverse incentive:** printing fewer digits makes an answer easier to trace.

## Proposal
1. **Trace each number to a field.** A report value must match the field it claims to be: min voltage to `min_bus_voltage_pu`, not any number.
2. **Narrow the sources.** Exclude schema limits, ids and the case name, and use the prompt only for ids. A fit scale must equal a tried scale, as `relevant_evidence` already requires.
3. **Keep signs. Parse thousands separators. Accept truncation as well as rounding.**
4. **Require tool evidence** in the solver-verified score.
5. **Record serving flags** (for example `--tool-strict-level`) in each run manifest, and have `compare_agents` refuse runs that differ in them. Today they sit only in the serving JSON.
6. **Done in this pass:** `latency_bench` measures decode to the end of the stream, not to the last streamed delta (B7, speculative).
