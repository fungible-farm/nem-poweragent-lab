# Lab 4 — Real AEMO Data: Digital-Twin Reconciliation & Constraint Literacy

> Status: **implemented (Part A + Part B required, Part C optional -- also implemented)**.
> `fetch_day.py`, `map_duids.py`, `reconcile.py`, `explain_constraint.py`,
> `nem_constraints_vendored.py`, `expected_reconciliation.json`, `duid_mapping.csv`, and
> `test_lab4.py` are real, runnable code that makes real network calls to AEMO's public NEMWeb MMS
> data archive -- see [`docs/LAB4_AEMO_REAL_DATA.md`](../../docs/LAB4_AEMO_REAL_DATA.md) for the
> full concept and library choices, and "Sandbox notes" below for exactly where and why this build
> deviates from that spec.

## What you'll do (summary)

- **Part A**: pull one real, ordinary day (**15 June 2026**) of SA1 dispatch data via
  [NEMOSIS](https://github.com/UNSW-CEEM/NEMOSIS), map real DUIDs onto `snemSA.m`'s synthetic
  generators, impose real MW setpoints, solve a power flow, and compare the modelled
  interconnector-equivalent flow to AEMO's actual reported value — scored on a deliberately generous
  tolerance, because a synthetic topology meeting real data is expected to diverge, and the point
  is explaining the gap honestly, not hiding it.
- **Part B**: decode one real binding constraint for the same day using the public
  [`susantoj/NEM_constraints`](https://github.com/susantoj/NEM_constraints) library (vendored, not a
  hand-rolled parser — see "Sandbox notes") and print a plain-English translation.
- **Part C (optional, implemented)**: replay the same reconciliation mechanic against the real
  pre-event dispatch data from the 28 September 2016 SA Black System, clearly caveated as a guided
  reading of AEMO's own public report, not a fault-reproduction claim.

**Two caveats that must appear in any presentation of this lab, not just in the design doc:**
this is not a digital twin of the real SA network (CSIRO's topology is synthetic), and Part C is
not a claim that this model reproduces the 2016 event's actual root cause.

## Why an AEMO modeller should care

Every other lab in this repo is entirely synthetic — safe, fast, offline, but also easy to dismiss
as "toy data." This lab is where the repo has to be honest about a real network meeting a
synthetic model, and that honesty (stating tolerance, stating what the model can't show) is
itself the point: it's the discipline a real reconciliation-against-market-data exercise would
need, demonstrated rather than asserted. Part A's actual result (see step 3 below) is a **FAIL**
against its own stated tolerance — and the memo it prints correctly identifies *why* (the
synthetic network's internal line/transformer losses are ~30x the real interconnectors' reported
losses for the same interval), which is exactly the discipline this lab is built to demonstrate:
a wrong number with a right explanation is more useful than a number quietly tuned to pass.

## Sandbox notes (read this before the walkthrough)

- **`NEM_constraints` is vendored, not installed.** `uv pip install
  git+https://github.com/susantoj/NEM_constraints` fails at resolve time (checked directly): the
  repo has no `pyproject.toml`/`setup.py`, so there is nothing for `uv`/`pip` to build from a git
  URL. Per `AGENTS.md`'s sandbox-stand-in convention, the specific functions this lab needs
  (`get_mms_table`, `get_constraint_list`, `find_constraint`, `get_LHS_terms`, `get_RHS_terms`,
  `get_constraint_details`) are vendored into `nem_constraints_vendored.py`, citing the exact
  upstream file and commit (`NEMDE_constraints.py` @ `62f6a1efa87b8b68804ed32dbe16ae2589e69301`),
  under its original MIT license (`LICENSE-NEM_constraints`). Two changes from upstream, both
  documented at the top of that file: (1) a fix for a confirmed bug — upstream's URL construction
  for the post-July-2024 MMSDM archive layout double-percent-encodes `#`, producing a real HTTP 404
  on every call for a recent date; (2) an added `functools.lru_cache` memoization layer around
  `get_mms_table` (I/O caching only, not a logic change) since the unmodified function re-downloads
  the same multi-megabyte monthly archive zip on every call, and `explain_constraint.py` needs
  several calls per run while searching for an SA1-relevant constraint. The actual
  constraint-decoding logic (which MMS tables to join and how) is untouched from upstream — this
  lab does not hand-roll a constraint-equation parser.
- **Fuel-type DUID matching is unavailable, so `map_duids.py` matches on nameplate-capacity
  proximity only**, on both sides of the join: `snemSA.m`'s own generator metadata carries no
  fuel-type field at all (only a bus-indexed name), and AEMO's real fuel-type source (the NEM
  Registration and Exemption List, `www.aemo.com.au/-/media/Files/...xls`) returns a genuine HTTP
  403 from this sandbox (Cloudflare bot protection — confirmed by a direct `curl -I`), while
  `nemweb.com.au`, the actual MMSDM data archive this lab depends on for everything else, is fully
  reachable. This is the spec's own documented "else nameplate-capacity proximity" fallback,
  exercised because the primary path is blocked, not skipped as a shortcut.
- **Real DUID "capacity" is a day-max-SCADA proxy, not true registered capacity.**
  `DUDETAILSUMMARY` carries no capacity column; the table that does
  (`DUDETAIL.REGISTEREDCAPACITY`) is fully version-controlled, and NEMOSIS's
  `dynamic_data_compiler` can only fetch it by scanning every month from 2009 to the present
  (confirmed directly: 200+ monthly archive downloads, several minutes, for one table) — wildly
  disproportionate for a lab step meant to run in seconds. `map_duids.py` instead uses each real
  DUID's own day-max SCADA output as a real, physically-grounded (if imperfect) proxy.
- **The "interconnector-equivalent branch"** Part A reconciles against is `snemSA.m`'s single slack
  generator (bus 985, pandapower 0-indexed / bus 986 MATPOWER-numbered), tied to bus 1800 by a
  near-zero-impedance branch. `snemSA.m` is an SA-only island reduction of the full CSIRO case with
  no explicit branches to VIC1 at all, so this lab treats its one reference-bus generator (needed
  for *any* island case to solve) as the model's stand-in for the real Heywood (`V-SA`) +
  Murraylink (`V-S-MNSP1`) interconnectors combined. Named explicitly in `_lab4_shared.py`, which
  also asserts this at runtime so a future CSIRO data revision that breaks the assumption fails
  loudly rather than reconciling against the wrong bus.
- **Unmatched synthetic generators are set to 0 MW, not left at `snemSA.m`'s base-case dispatch.**
  `map_duids.py`'s capacity-proximity matching is not a bijection (89 real SA1 generator DUIDs vs.
  56 non-slack synthetic generators), so roughly a third of synthetic generators get no real DUID
  mapped onto them. Leaving those at their original base-case OPF output (tried first, during
  implementation) double-counts capacity against the real SCADA imposed elsewhere and reliably
  fails to converge (~2500 MW modelled generation against ~1800 MW real SA1 demand). Zeroing them
  means the reconciliation only asserts generation this lab has real evidence for.
- **Reconciliation tolerance: ±15%, floor 10 MW.** Taken directly from
  `docs/LAB4_AEMO_REAL_DATA.md`'s own suggested value ("e.g. ±15%"), deliberately looser than Lab
  1's tight synthetic-fit tolerance (0.002 pu) because a synthetic topology meeting real market
  data is expected to diverge on absolute quantities, not just on solver noise. The 10 MW floor
  exists so a near-zero real interconnector flow (which does occur on some 5-minute intervals)
  can't make the relative check meaningless.
- **No live local LLM.** As in every other lab (see `labs/01-simple-loadflow-fit/README.md`), the
  reconciliation memo and the constraint's plain-English paragraph are plain Python f-string
  templates over real computed/decoded values, not an LLM's free-form text — this sandbox has no
  `podman` and no budget to serve a GGUF model. Named in `reconcile.py`'s and
  `explain_constraint.py`'s own docstrings.
- **Part C uses Part A's DUID mapping across a 10-year date gap.** `duid_mapping.csv` is built once
  from DUIDs registered as of 15 June 2026 and applied unchanged to 28 September 2016's SCADA. A
  real generator dispatched in 2016 may since have been re-registered or decommissioned (absent
  from today's mapping) or vice versa — `reconcile.py --date 2016-09-28`'s printed memo names this
  explicitly as a second, distinct source of reconciliation error on top of Part A's network-loss
  explanation.

## Command

```
uv run labs/04-aemo-digital-twin-reconciliation/fetch_day.py --region SA1 --date 2026-06-15
uv run labs/04-aemo-digital-twin-reconciliation/map_duids.py
uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py
uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step check
uv run labs/04-aemo-digital-twin-reconciliation/explain_constraint.py
uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --date 2016-09-28   # optional Part C
uv run python -m pytest labs/04-aemo-digital-twin-reconciliation/test_lab4.py
```

## Step-by-step walkthrough (presenter / backup script)

1. **`uv run labs/04-aemo-digital-twin-reconciliation/fetch_day.py --region SA1 --date 2026-06-15`**
   — You should see: a short progress log as NEMOSIS downloads/caches `DISPATCH_UNIT_SCADA`,
   `DISPATCHPRICE`, `DISPATCHREGIONSUM`, `DISPATCHINTERCONNECTORRES` for that day, ending in
   `cached 151475 rows across 4 tables` (plus a separate `DUDETAILSUMMARY` line — see "Sandbox
   notes" for why that one is pulled and printed separately).
   — *Backup if offline*: this build ships no `data/nemosis_sample/` fixture because the live pull
   for 15 June 2026 succeeded during implementation and is this script's only tested path (see
   `fetch_day.py`'s module docstring) — narrate the printed output below as "here's what a
   successful live pull looks like" instead.
2. **`uv run labs/04-aemo-digital-twin-reconciliation/map_duids.py`**
   — You should see: a printed table of real DUID → matched synthetic generator bus → capacity
   diff (70 real DUIDs mapped onto 22 unique synthetic generator buses), and the same table written
   to `duid_mapping.csv`.
   — Why it matters: this is the auditable join step — anyone in the room can open that CSV and
   check the mapping themselves, nothing is hidden in code.
3. **`uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py`**
   — You should see: `Modelled interconnector-equivalent flow (bus 985): +234.2 MW`,
   `Actual combined V-SA + V-S-MNSP1 flow: +187.7 MW`, `Delta: +46.5 MW ... -> FAIL`, followed by a
   reconciliation memo that quantifies the gap: the solved synthetic network's own line +
   transformer losses (63.5 MW) are ~30x AEMO's published real interconnector losses for the same
   interval (2.1 MW), which alone accounts for most of the delta.
   — Why it matters: this is the "does the digital twin's power flow reconstruct the market
   outcome" check — and, just as importantly, the printed memo showing the model can say *why*
   it's off (with a real, computed number backing the explanation), not just that it's off.
4. **`uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step check`**
   — You should see: the reconciliation result as JSON, then
   `MATCH: modelled=234.168 actual=187.7 vs expected_reconciliation.json`. Note this checks that
   the computation *reproduces the fixture*, not that the reconciliation itself passed tolerance —
   `expected_reconciliation.json`'s own `"passed": false` is the correct, reproducible answer.
5. **`uv run labs/04-aemo-digital-twin-reconciliation/explain_constraint.py`**
   — You should see: a search across the day's binding constraints (`SA1-relevant` / `not
   SA1-relevant` printed per candidate checked), landing on a real constraint (e.g.
   `NSA_S_TB2_40`, "Torrens Island (TIPS) B2>= 40 MW for Network Support Agreement"), its decoded
   LHS/RHS terms, cross-referenced against `duid_mapping.csv`'s matched synthetic bus, and a
   one-paragraph plain-English translation.
   — Why it matters: this is the artifact with the most immediate day-to-day relevance to
   Operations — a decoded constraint in plain English, tied back to the same synthetic network
   Part A reconciled.
6. **(optional) `uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --date 2016-09-28`**
   — Before running: the script itself prints the caveat aloud first — **this is NOT a claim that
   this model reproduces the 2016 SA Black System event's actual root cause** — followed by a short
   narrative excerpt paraphrasing AEMO's public integrated final report, then the same
   reconciliation output shape as step 3 (modelled vs. actual interconnector flow, a memo — this
   one also naming the DUID-mapping date gap as an extra source of error). This step is a narrative
   aid, not a physics claim — the caveat prints before the numbers, every time.

## References (Part C)

- [AEMO's integrated final report — Black System South Australia 28 September 2016](https://www.aemo.com.au/-/media/files/electricity/nem/market_notices_and_events/power_system_incident_reports/2017/integrated-final-report-sa-black-system-28-september-2016.pdf)
- [AER investigation report — South Australia's 2016 state-wide blackout](https://www.aer.gov.au/publications/reports/compliance/investigation-report-south-australias-2016-state-wide-blackout)
