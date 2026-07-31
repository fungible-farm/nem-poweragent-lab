# Lab 4 — Real AEMO Data: Digital-Twin Reconciliation & Constraint Literacy

Status: **spec only**. This is a new, separate file (rather than a §7 subsection of
`docs/VISION.md`) because it's the one lab that crosses from "everything synthetic, everything
offline-capable" into "pulls real, live-market data over the network" — a different risk profile
that deserves its own document, its own caveats, and room to grow into Labs 5+ later without
bloating the core vision doc.

## Why a 4th lab

Labs 1–3 are entirely synthetic: the CSIRO topology, and every "field reading" or "hypothetical
generator" fed into them, is invented for the exercise. That's deliberate — it keeps them fast,
offline-capable, and free of any data-licensing question. But the paper this whole repo is
grounded in (`docs/VISION.md` §1) opens on a very real premise: *aging infrastructure, rising
system complexity, more frequent extreme weather*. Nothing in Labs 1–3 touches anything real
enough to make that premise land. Lab 4 closes that gap: it pulls actual historical NEM dispatch
data and reconciles it against the CSIRO synthetic network, honestly — including being explicit
about where a synthetic topology *can't* match reality, rather than quietly hiding the gap.

## Libraries used (nothing here is hand-rolled)

| Need | Library | Note |
|---|---|---|
| Download & cache real AEMO MMS data | [NEMOSIS](https://github.com/UNSW-CEEM/NEMOSIS) (`pip install nemosis`) | `dynamic_data_compiler()` against `DISPATCH_UNIT_SCADA`, `DISPATCHPRICE`, `DISPATCHREGIONSUM`, `DISPATCHINTERCONNECTORRES`, `DISPATCHCONSTRAINT`; `static_table()` against `DUDETAILSUMMARY`/`GENCONDATA` |
| Understand the MMS table joins (DUID ↔ generator ↔ participant) | [mms-guide](https://www.mdavis.xyz/mms-guide/) (Matthew Davis) | The `PARTICIPANTID → STATIONID → DUID` hierarchy, and the "these are versioned — dedup by `EFFECTIVEDATE` desc, `LASTCHANGED` desc, take the first row" pattern. Reference, not a runtime dependency. |
| Decode a binding constraint equation into LHS/RHS terms | [susantoj/NEM_constraints](https://github.com/susantoj/NEM_constraints) | Public GitHub repo — "Python functions for wrangling public NEMDE constraint equation formulations": `get_constraint_list`, `find_constraint`, `get_constraint_details`, `get_LHS_terms`, `get_RHS_terms`, `get_generic_RHS_func`. **This answers the "is there a public library for this" question directly — yes, use this rather than writing a constraint-equation parser.** |
| Prior art for DUID → generator metadata collation | [akxen/egrimod-nem](https://github.com/akxen/egrimod-nem) | Its `collate_generator_data` notebook already compiles generator technical/economic attributes from AEMO's MMSDM + NTNDP. It builds its *own* GA/ABS-derived topology, which we don't use — we stay on the CSIRO synthetic network for consistency with Labs 1–3 — but its generator-collation methodology is directly reusable so the DUID-matching step in Part A isn't invented from scratch. |
| Network + physics | `powerio` + `pandapower` | Same as every other lab — CSIRO `snemSA.m`, unchanged |

Verify exact function signatures against each project's current source at implementation time —
NEMOSIS and NEM_constraints both move independently of this repo.

## Part A (core) — Digital-twin reconciliation against an ordinary day

1. Pick one recent, unremarkable day and one region (default: **SA1**, since it lines up with the
   `snemSA.m` case already used in Lab 1).
2. `NEMOSIS.dynamic_data_compiler()` pulls `DISPATCH_UNIT_SCADA` (actual MW per DUID),
   `DISPATCHPRICE`, `DISPATCHREGIONSUM`, and `DISPATCHINTERCONNECTORRES` for that day, cached
   locally exactly the way Lab 1–3's CSIRO fetch is cached.
3. `NEMOSIS.static_table('DUDETAILSUMMARY', ...)` gives DUID → STATIONID → PARTICIPANTID plus
   fuel type and registered capacity, deduplicated per the mms-guide's versioning rule.
4. **Match each real SA1 DUID to the nearest synthetic generator in `snemSA.m`** by fuel type
   (where the CSIRO metadata records it) and nameplate-capacity proximity otherwise. This mapping
   is written out as a plain, committed CSV (`real_duid → synthetic_gen_id`, with the matching
   rationale as a column) — auditable by a human, not buried inside code.
5. Impose the real SCADA MW values on the matched synthetic generators; scale any unmatched load
   buses so total synthetic demand matches the real `DISPATCHREGIONSUM` regional total.
6. Solve the AC power flow in pandapower (same tool, same version pin, as every other lab).
7. Compare the modelled flow across the synthetic network's interconnector-equivalent branch to
   the real `DISPATCHINTERCONNECTORRES` value for the same 5-minute dispatch interval. Score
   **pass within a stated, generous tolerance (e.g. ±15%)** — deliberately looser than Lab 1's
   tight synthetic-fit tolerance, because a synthetic topology meeting real data is expected to
   diverge, and the point of the exercise is producing an honest explanation of the gap, not
   forcing an artificially tight match.
8. The agent's final output is a short reconciliation memo: modelled vs. actual, and a plausible
   explanation for the difference (line impedances are synthetic, HVDC/interconnector topology is
   approximate, etc.) — the memo is graded on whether it correctly identifies *that* the
   divergence is a topology-fidelity artifact, not a bug.

**Honesty caveat, stated up front in this lab's own README, not just here:** this is not a
digital twin of the real SA network. The CSIRO model is synthetic — real NEM statistics, invented
specific line and bus parameters. The lab's teaching point is the *reconciliation methodology and
the discipline of explaining the gap*, not a claim that the modelled network reproduces reality.

## Part B — Constraint literacy (uses `NEM_constraints` directly, per the library question)

1. Pull `DISPATCHCONSTRAINT` for the same interval/region, filter to constraints with a nonzero
   marginal value (i.e. actually binding).
2. Use `NEM_constraints`' `get_constraint_details` / `get_LHS_terms` / `get_RHS_terms` to decode
   the constraint's `GENCONDATA`/SPD-table formulation into its component terms — no equation
   parser written in this repo.
3. The agent (PowerSkills-style progressive disclosure — start with "what does this constraint
   say," escalate only if asked "why is it binding") translates the decoded formulation into plain
   English, cross-referencing which of Part A's matched synthetic generators/lines the constraint's
   DUIDs correspond to.
4. Output: one paragraph an Operations reader could actually use — this is the single most
   directly "useful tomorrow" artifact in the whole repo, since opaque constraint equations are a
   genuine, everyday friction point.

## Part C — Optional historical case study (clearly caveated, not the spine of the lab)

Swap the "ordinary day" in Part A for the real pre-event dispatch data from **28 September 2016**
(the SA state-wide Black System event) as one additional input date, and walk through AEMO's own
published findings (see references) as a guided narrative alongside the reconciliation output.

**This is explicitly not a fault-reproduction claim.** The event's actual root cause — wind-farm
low-voltage-ride-through and rate-of-change-of-frequency protection settings tripping in
sequence — is not something a snapshot AC power-flow model can show; that requires dynamic/
transient simulation this lab doesn't attempt. What this part *can* honestly show: the real
pre-event dispatch mix (high wind penetration, specific interconnector loading) reconciled against
the synthetic network exactly as in Part A, with AEMO's own report supplying the narrative the
model itself cannot. State this caveat before showing the section, every time.

References: [AEMO's integrated final report](https://www.aemo.com.au/-/media/files/electricity/nem/market_notices_and_events/power_system_incident_reports/2017/integrated-final-report-sa-black-system-28-september-2016.pdf),
[AER investigation report](https://www.aer.gov.au/publications/reports/compliance/investigation-report-south-australias-2016-state-wide-blackout).

## Definition-of-done additions (fold into `docs/DEFINITION_OF_DONE.md` when Lab 4 is built)

- [ ] The NEMOSIS pull for the chosen ordinary day (and optionally 2016-09-28) is cached and
      idempotent, same discipline as the CSIRO fetch script.
- [ ] The DUID → synthetic-generator mapping is a committed, human-readable CSV with a rationale
      column — never implicit inside code.
- [ ] The reconciliation tolerance and the reason it's looser than Lab 1's is stated in the lab's
      own `README.md`, not only in this design doc.
- [ ] The constraint-decode step uses `NEM_constraints` (or an equivalent public, cited library) —
      no hand-rolled constraint-equation parser anywhere in this repo.
- [ ] The "this is not a digital twin of the real network" and "this is not a fault-reproduction"
      caveats both appear verbatim (or equivalent) in the lab's own README.
