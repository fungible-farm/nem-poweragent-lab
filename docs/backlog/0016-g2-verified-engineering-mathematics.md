# 0016 — G2: verified engineering mathematics

- **Status:** open. [PRD-0010](../prd/0010-powercoder-physics-grounded-engineering-agent.md) G2, priority A3. Depends on G1 for the command surface, but each
  tool can be built and tested behind today's MCP server first. Absorbs
  [0013](0013-sensitivity-newton-tool.md).
- **Requirements:** PC-REQ-010–016.

## Deliverables
| Capability | Starting point in this repo |
|---|---|
| AC/DC power flow with the proof contract | `powercoder/inference/studies.py` (`run_study_trial`). Add mismatches and residuals |
| AC/DC OPF: objective, binding constraints, duals | pandapower OPF (BSD-3) |
| N-1 and bounded N-2 screening, with coverage labels | Lab 2 screening (`labs/02-medium-interconnection-screening/workflow.py`) |
| PTDF, LODF, Jacobian, V/Q sensitivities with conditioning | pandapower internals, numpy/scipy |
| WLS state estimation with observability and bad-data checks | pandapower `estimation` |
| Dynamics and short circuit as separate services | DPsim (Lab 5), pandapower `shortcircuit` |

## Required tests
- **Reference cases:** synthetic, IEEE (from RestoreBench's corpora) and CSIRO cases, cross-checked
  against independent solutions.
- **Adversarial cases:** non-convergence, ill-conditioning, infeasible OPF, wrong topology, and
  isolating outages (FM-25 is the precedent: the reference solved it and the tool refused).

## Exit criteria
- Every tool returns the proof contract.
- Solver-specific tolerances, declared in advance, are met.
- Non-converged results are never reported as solved, and violations are recomputed independently.
- Failed, infeasible and indeterminate results are distinguishable.
- Contingency coverage is always reported.

## Cheapest first step
DC OPF and PTDF on `snem-sa-2000`, cross-checked against an independent implementation.

## WLS state estimation done (2026-10-23): `powercoder/engineering/state_estimation.py`
It runs pandapower's WLS estimation, chi-square test and largest-normalised-residual (LNR)
removal, and returns a typed result with the proof contract, an observability verdict and the
identity of every measurement removed. **The measurements are synthetic**: seeded noise around a
solved AC power flow, with the accuracy classes in `MEASUREMENT_STD` *assumed*, because G5 is
blocked.

| Case | Measurements | Clean estimate (max \|V − truth\|) | 50σ gross error on one flow |
|---|---|---|---|
| case9 | 45 | 1.28e-3 pu, no bad data suspected | detected; **exactly that measurement** removed (two trials) |
| snemSA | 3,295 | 4.06e-3 pu, no bad data suspected | detected and removed, **plus 10 good measurements** |

- **Measure both ends of a branch.** With one end only, a flow can be a *critical* measurement:
  its residual is zero, so a 25 MW error went undetected on case9. SCADA usually measures both
  ends, so the synthetic set does too.
- **LNR at |r_N| > 3 over-removes on a large set.** Each good measurement exceeds 3 by chance
  with probability about 0.27%, so 3,295 × 0.0027 ≈ 8.9 false removals are expected. The 10
  observed fit that. The threshold is `LNR_THRESHOLD`, pandapower's default. A size-aware
  threshold is a choice to make deliberately, not a default to change silently.
- **Unobservable is refused** (`observable = False`, `indeterminate`), never estimated.

## AC power flow proof and V/Q sensitivities done (2026-10-23): `powercoder/engineering/ac_analysis.py`
- **`ac_power_flow`** returns the proof contract: iterations, the Kirchhoff residual recomputed
  from the result tables, every limit violation, and cond(J). snemSA: converged in 5 iterations,
  residual 6.7e-9 MVA, cond(J) 3.4e7, `infeasible` (its 39 base voltage violations). case9:
  feasible, cond(J) 59.
- **`vq_sensitivity`** (dV/dQ from the reduced Jacobian) is cross-checked against an independent
  central finite difference (±0.1 Mvar re-solves). It agrees to 1e-5 relative on case9 and 7e-9
  on snemSA (tolerance 1e-3).
- **`qv_modal`** (smallest reduced-Jacobian eigenvalue and participating buses): case9 +5.71.
  **snemSA: two negative modes (−16.29, −13.59) at buses 1753–1755**, confirmed real in the
  linearised model by perturbation (ΔQ along the left eigenvector moves V by ΔQ/λ along the
  right one; correlation 0.9996). They sit at the ends of lines 293 and 294, the case's only
  negative-reactance branches (x ≈ −63 Ω, series-compensation equivalents). The eigenvalue
  criterion assumes inductive branches, so this is **flagged, not read as voltage
  instability**.
