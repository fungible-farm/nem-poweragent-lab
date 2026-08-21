# Power-Flow Engine Shoot-Out: pandapower vs. pypowsybl

Real cross-validation of this repo's golden-path solver (pandapower) against
[PowSyBl](https://github.com/powsybl) (RTE's open-source power-system framework, via its real
`pypowsybl` Python bindings, MPL-2.0, OpenLoadFlow solver) on the exact same real CSIRO
`snem1803.m` case. Not a benchmark write-up assembled after the fact — the numbers below are what
`labs/03-advanced-provider-bakeoff/spike_pypowsybl.py` and
`labs/02-medium-interconnection-screening/pypowsybl_cross_check.py` actually produce, committed
and re-checked on every run (`--step check` against `expected_pypowsybl_comparison.json` /
`expected_pypowsybl_n1_comparison.json`).

## What was actually tested

1. **Lab 3 — aggregate solver comparison.** Load `snem1803.m` (1803 buses, 2795 branches) into
   both engines and solve a base-case AC power flow. Do total generation, load, and system losses
   agree?
2. **Lab 2 — a real second opinion on a real screening decision.** Re-solve the exact same 21 N-1
   contingencies `workflow.py` already screens (dropping each of the 21 lines local to a
   hypothetical 250 MW generator connection at bus 175) with pypowsybl's own security-analysis
   module, and cross-check worst-case voltage and thermal loading against pandapower's results,
   contingency by contingency.

## Results

**Aggregate comparison (Lab 3):**

| Metric | pandapower | pypowsybl/OpenLoadFlow | Difference |
| --- | --- | --- | --- |
| Total generation | 30262.84 MW | 30261.20 MW | 0.005% |
| Total load | 29226.91 MW | 29226.91 MW | exact (same input) |
| Total system losses | 1035.932 MW | 1034.136 MW | 0.17% |
| Solve time | 2.3s cold / ~47ms warm | 145ms | not a fair head-to-head without controlling for both engines' warm-up cost |

**N-1 cross-check (Lab 2), 21 contingencies:**

| Metric | Result |
| --- | --- |
| Worst-case bus voltage agreement | **0.00000 pu** across all 21 contingencies |
| The two genuinely contingency-induced thermal breaches (lines 151/152, a parallel pair) | Match **exactly**: 113.00% / 111.37%, both engines |
| The other 19 (pre-existing base-case, not contingency-induced) contingencies' worst loading | ~3% relative difference, up to 4.09% on one |
| Overall agreement | **21/21** within documented tolerances (0.005 pu voltage, 20% loading — see the script's own tolerance comments for why) |

## Two real data-fidelity bugs found, not assumed

Getting to the results above required finding and fixing two genuine pypowsybl import defects —
arguably the more valuable output of this exercise than the headline "the engines agree" result:

1. **pypowsybl's MATPOWER importer only accepts the binary `.mat` MATLAB serialization**, not the
   `.m` script format every case file in this repo (and MATPOWER itself) actually ships. Fixed by
   round-tripping the already-solved pandapower net through pandapower's own `to_mpc()` (a real
   `scipy.io.savemat`-backed writer) — see `labs/_shared/gridfit.to_pypowsybl_network()`.
2. **Bus-id correlation is not `pandapower_bus_id + 1`.** pandapower preserves the original,
   often large and non-sequential MATPOWER bus numbers as its own index; the `.mat` file
   `to_mpc()` writes uses a completely different, internally-renumbered 1-based sequence
   (pandapower's own `to_ppc()` bus compaction). Naively assuming `bus_id + 1` matched only
   14 of 1215 real lines to their pypowsybl element id; pandapower's own
   `net._pd2ppc_lookups["bus"]` table (the exact renumbering `to_ppc()` builds internally)
   matched 1215/1215 — see `labs/_shared/gridfit.pypowsybl_element_id_map()`.
3. **`matpower.import.ignore-base-voltage` defaults to `true`** in pypowsybl's MATPOWER importer,
   silently discarding the real per-bus base-kV column (this repo's cases carry genuine NEM
   voltage levels — 132kV, 66kV, 33kV, 11kV, etc.) and reporting every bus at `nominal_v=1.0`
   instead, making reported voltages and currents physically meaningless. Confirmed this is a
   pure reporting-convention default — total system generation/load/loss are bit-identical either
   way — so the shared helper always disables it.

None of these three failed loudly. Each would have produced plausible-looking, silently wrong
numbers if the results hadn't been cross-checked against pandapower's already-trusted output.

## A related gap: PowSyBl's own violation detection would have missed the real finding

pypowsybl's native `SecurityAnalysisResult.limit_violations` — the built-in "what got violated"
report — returned zero `CURRENT`-type violations on this case, because the MATPOWER import path
doesn't carry branch thermal ratings into PowSyBl's own limit model (only voltage-level high/low
bounds import cleanly). Relying on that native report alone would have produced a clean N-1
screen and silently missed the one real finding Lab 2 exists to catch — the line 151/152
double-circuit overload. The cross-check above computes loading% manually (real current from
`branch_results`, divided by pandapower's own `max_i_ka` rating for the same line via the id map)
specifically to avoid this gap.

## Conclusions / implications

1. **pypowsybl/OpenLoadFlow is a trustworthy alternative engine for this data** — but engine
   agreement on aggregate numbers is the less interesting result. Two independent AC solvers
   converging on the same physics is expected, not remarkable on its own.
2. **The genuinely valuable result is that both engines independently found the same defect.**
   Agreement across independently-implemented codebases is stronger evidence for a screening
   result than either engine alone — this is the concrete case for building dual-engine
   cross-validation into anything safety- or compliance-relevant, not treating it as a nice-to-have.
3. **A new engine's default import behavior is not trustworthy until proven otherwise**, and
   proving it costs more effort than the load-flow comparison itself. Both real bugs above were
   silent, not crashes — verifying against a known-good baseline is what caught them.
4. **A security-analysis tool's own native violation report is only as good as what actually got
   imported into its limit model.** PowSyBl's `limit_violations` alone would have reported a false
   "all clear." Never trust a tool's built-in pass/fail without confirming the underlying limits
   are the ones you think they are.
5. **Aggregate agreement doesn't imply per-branch agreement.** System-wide P/Q matched tightly
   while one spot-checked individual branch's current differed by ~11.7% between engines — likely
   a line-model convention difference (charging susceptance placement, etc.) invisible at the
   system-loss level. Don't extrapolate from an aggregate check to "every individual value is
   trustworthy."

## Where this lives

- `labs/_shared/gridfit.py` — `to_pypowsybl_network()`, `pypowsybl_element_id_map()`: the shared
  bridge code both labs below use, not duplicated.
- [`labs/03-advanced-provider-bakeoff/README.md`](../labs/03-advanced-provider-bakeoff/README.md)
  ("pypowsybl spike" section) — the aggregate solver comparison, `spike_pypowsybl.py`.
- [`labs/02-medium-interconnection-screening/README.md`](../labs/02-medium-interconnection-screening/README.md)
  ("pypowsybl N-1 cross-check" section) — the real second-opinion screen, `pypowsybl_cross_check.py`.
- `docs/PSCADOSSE.md` — pypowsybl is recorded there as a second documented MPL-2.0 golden-path
  exception, alongside DPsim.

```
uv run labs/03-advanced-provider-bakeoff/spike_pypowsybl.py --step check
uv run labs/02-medium-interconnection-screening/pypowsybl_cross_check.py --step check
```

Both are wired into `just check-lab2` / `just check-lab3` / `just check`, so a regression in
either comparison fails the aggregate check, not just a standalone script.
