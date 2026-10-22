# 0023 — The SA case (snemSA) has no real branch ratings, one cost, and one slack

- **Status:** open. Found 2026-10-23 while building the G2 tools (`powercoder/engineering/`, [0016](0016-g2-verified-engineering-mathematics.md)).
- **Affects:**
  - G2's OPF and thermal checks, and G3's task generator ([0017](0017-g3-verifier-guided-investigative-learning.md));
  - any "outperform engineers" claim that relies on this network.

## Evidence (measured)
- **No real branch ratings.** All 698 branches in `data/snemSA.m` have rateA = rateB = rateC = 10000 MVA
  (`grep -cE '10000\s+10000\s+10000' data/snemSA.m` gives 698), MATPOWER's conventional "no limit" value.
  The highest AC loading over all 698 N-1 outages is 3.76% (2.66% in the base case), so thermal
  screening finds nothing.
- **DC OPF is plain economic dispatch with many equal optima.** All 57 generators cost the same
  10 €/MWh, and no branch limit enters pandapower's OPF. The objective is exactly 10 × load, and
  the dispatch is arbitrary: pandapower and HiGHS choose dispatches up to 137 MW apart, both
  optimal.
- **One slack generator:** gen 29 at bus 985, behind transformer 0.
  - Its outage de-energizes 502 of 503 buses, because pandapower energizes only islands that
    contain a slack, even though 2,008.8 MW of generation remains in that island.
  - 70 N-1 outages strand generation this way. Their de-energized load is an upper bound, reported
    as `de_energized_generation_mw`.
- **Voltage is the only binding signal.** Of the 698 outages, 133 introduce new voltage
  violations and none introduces a thermal one.

## Consequence
On this case, OPF, thermal-limit and transfer-capacity tasks (PRD-0010 Demonstration A) have no
signal, and "largest permissible transfer" is unbounded by the thermal limits. Voltage tasks are
meaningful. The slack artifact makes islanding outages look far worse than a system with
distributed reserve would.

## Proposal
1. **For G2/G3 tasks needing limits and costs,** use cases that have them: IEEE 118 and PEGASE 89
   from RestoreBench (CC BY 4.0), or other CSIRO cases once checked. Record each case's provenance.
2. **If snemSA stays in use,** add documented, derived ratings (for example, a percentile rule from
   conductor type, stated as a named assumption), and per-generator costs from a cited source.
   Never present invented values as data.
3. **Use distributed slack** (pandapower `distributed_slack`, or a gen per island) for islanding
   studies, and report both conventions.
