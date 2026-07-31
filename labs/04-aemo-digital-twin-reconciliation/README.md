# Lab 4 — Real AEMO Data: Digital-Twin Reconciliation & Constraint Literacy

> Status: **spec only** — full concept, library choices, and caveats live in
> [`docs/LAB4_AEMO_REAL_DATA.md`](../../docs/LAB4_AEMO_REAL_DATA.md). This README is the
> lab-local summary plus the step-by-step walkthrough.

## What you'll do (summary)

- **Part A**: pull one real, ordinary day of SA1 dispatch data via
  [NEMOSIS](https://github.com/UNSW-CEEM/NEMOSIS), map real DUIDs onto `snemSA.m`'s synthetic
  generators, impose real MW setpoints, solve a power flow, and compare the modelled
  interconnector flow to AEMO's actual reported value — scored on a deliberately generous
  tolerance, because a synthetic topology meeting real data is expected to diverge, and the point
  is explaining the gap honestly, not hiding it.
- **Part B**: decode one real binding constraint for the same interval using the public
  [`susantoj/NEM_constraints`](https://github.com/susantoj/NEM_constraints) library (not a
  hand-rolled parser) and have the agent translate it into plain English.
- **Part C (optional)**: replay the same mechanic against the real pre-event dispatch data from
  the 28 September 2016 SA Black System, clearly caveated as a guided reading of AEMO's own public
  report, not a fault-reproduction claim.

**Two caveats that must appear in any presentation of this lab, not just in the design doc:**
this is not a digital twin of the real SA network (CSIRO's topology is synthetic), and Part C is
not a claim that this model reproduces the 2016 event's actual root cause.

## Why an AEMO modeller should care

Every other lab in this repo is entirely synthetic — safe, fast, offline, but also easy to dismiss
as "toy data." This lab is where the repo has to be honest about a real network meeting a
synthetic model, and that honesty (stating tolerance, stating what the model can't show) is
itself the point: it's the discipline a real reconciliation-against-market-data exercise would
need, demonstrated rather than asserted.

## Step-by-step walkthrough (presenter / backup script)

Written now, before the code exists, so it doubles as the script a presenter can talk through even
if the live run isn't available on the day (flaky network to NEMWeb, a cold cache, conference
Wi-Fi). Each step: what you run, what you should see, why it matters.

1. **`uv run labs/04-aemo-digital-twin-reconciliation/fetch_day.py --region SA1 --date 2026-06-15`**
   *(placeholder date — pick any recent unremarkable day at build time)*
   — You should see: a short progress log as NEMOSIS downloads/caches `DISPATCH_UNIT_SCADA`,
   `DISPATCHPRICE`, `DISPATCHREGIONSUM`, `DISPATCHINTERCONNECTORRES` for that day, ending in
   `cached N rows across 4 tables`.
   — *Backup if offline*: read from the committed sample cache under `data/nemosis_sample/` and
   say so explicitly — "this is a pre-fetched sample from build time, not a live pull."
2. **`uv run labs/04-aemo-digital-twin-reconciliation/map_duids.py`**
   — You should see: a printed table of real DUID → matched synthetic generator ID → match
   rationale (fuel type / capacity proximity), and the same table written to
   `duid_mapping.csv`.
   — Why it matters: this is the auditable join step — anyone in the room can open that CSV and
   check the mapping themselves, nothing is hidden in code.
3. **`uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py`**
   — You should see: modelled vs. actual interconnector flow (two numbers, one delta, one
   pass/fail against the stated tolerance), followed by the agent's short reconciliation memo.
   — Why it matters: this is the "does the digital twin's power flow reconstruct the market
   outcome" check — and, just as importantly, the printed memo showing the model can say *why*
   it's off, not just that it's off.
4. **`uv run labs/04-aemo-digital-twin-reconciliation/explain_constraint.py`**
   — You should see: the chosen binding constraint's ID, its decoded LHS/RHS terms (via
   `NEM_constraints`), and the agent's one-paragraph plain-English translation.
   — Why it matters: this is the artifact with the most immediate day-to-day relevance to
   Operations — a decoded constraint in plain English.
5. **(optional) `uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --date 2016-09-28`**
   — Before running: state the caveat aloud. You should see the same reconciliation output shape
   as step 3, plus a printed excerpt from AEMO's public report contextualising that day's dispatch
   mix. This step is a narrative aid, not a physics claim — say that before showing the numbers.
