# Lab 4 — Real AEMO Data: Digital-Twin Reconciliation & Constraint Literacy

> Status: **Part A implemented.** Parts B and C are spec-only, blocked in this sandbox by the same
> network restriction that shapes Part A — see "Sandbox notes" below. Full original concept, library
> choices, and caveats live in [`docs/LAB4_AEMO_REAL_DATA.md`](../../docs/LAB4_AEMO_REAL_DATA.md);
> this README describes what's actually built.

## What's implemented (Part A)

`reconcile.py` maps 11 real, well-known South Australian generating-unit DUIDs onto `snemSA.m`'s
synthetic generators by nearest capacity, imposes an illustrative sample dispatch on those buses,
scales the rest of the synthetic fleet to match the network's own real total load, solves an actual
AC power flow (`pandapower.runpp()`, every time), and scores the slack-bus residual against a 5%
AC-loss sanity band.

```
uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step dispatch
uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step map
uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step reconcile
uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step check
```

Or the full proof: `./scripts/run_lab4.sh`.

## Sandbox notes (read before trusting any number below)

This sandbox's egress policy returns 403 for **both** `nemweb.com.au` and `github.com` itself
(confirmed via `/root/.ccr/__agentproxy/status` — "destination host not allowed," not a transient
failure; only `raw.githubusercontent.com` and `pypi.org` are reachable). That has three consequences,
all named explicitly in `reconcile.py`'s module docstring as well as here:

1. **No live NEMOSIS pull is possible.** `nemosis` is pip-installable (it's on PyPI), but
   `dynamic_data_compiler()` cannot reach NEMWeb from here. `SAMPLE_DUID_DISPATCH` in `reconcile.py`
   is a documented, fixed stand-in in NEMOSIS's real column shape — real DUIDs, illustrative
   SCADAVALUE figures — **not** a captured historical interval. Swap `dispatch_step()`'s body for a
   real `dynamic_data_compiler()` call the moment NEMWeb is reachable; nothing downstream changes.
2. **Part B (constraint literacy) is not built.** `susantoj/NEM_constraints` cannot be pip/git
   installed (github.com blocked). Faking a constraint-equation decoder ourselves rather than using
   the real library would violate this repo's own "use libraries, don't reinvent" rule worse than
   simply not building Part B yet — so it isn't built yet.
3. **Part C (the 2016 SA Black System case study) is not built** for the same reason — it needs the
   same unreachable NEMWeb pull, just for a different date.

**A real finding from building this, kept rather than smoothed over:** `snemSA.m` has no modelled
branch corresponding to the real Heywood/Murraylink interconnectors. Its designated slack bus (985,
165kV) is an internal sub-transmission reference node, not a boundary injection at an
interconnector's real voltage level (Heywood is 275kV AC) — comparing its solved P to a real
interconnector flow would overclaim a correspondence that isn't there. So this lab scores the power
**balance** (does imposing real-DUID dispatch, then closing the gap to the network's own real total
load, solve to a slack residual within a plausible AC-loss band) rather than an interconnector-flow
match. And because there is no live pull, there is no real reported figure to reconcile against in
the first place — this is a mechanism demonstration against a self-consistent illustrative sample,
not a validated comparison to reality. Both points are stated in `reconcile.py`'s module docstring,
not just here.

**Two caveats that must appear in any presentation of this lab:** this is not a digital twin of the
real SA network (CSIRO's topology is synthetic, and see the interconnector finding above), and this
implementation does not attempt Part C's 2016 event replay at all.

## Why an AEMO modeller should care

Every other lab in this repo is entirely synthetic. This is the one place the repo has to be honest
about a real network meeting incomplete real-world access — the DUID mapping is auditable
(`duid_mapping.csv`, committed, human-readable, with a rationale column), the physics is always real
pandapower, and the gaps (no live data, no interconnector branch) are named rather than smoothed
over. That discipline — say what's real, name what's a stand-in, never fabricate a result — is the
actual point, not the specific MW numbers.

## Step-by-step walkthrough (presenter / backup script)

1. **`uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step dispatch`**
   — You should see: `[sandbox stand-in, not a live NEMOSIS pull...] 11 DUIDs, 383.0 MW mapped
   dispatch` followed by one line per DUID (name, fuel descriptor, approximate capacity,
   SCADAVALUE).
   — Why it matters: state the sandbox caveat here, first, before showing any numbers.
2. **`uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step map`**
   — You should see: a table, `real_duid -> bus base_p_mw target_mw delta_mw`, ending in
   `written to .../duid_mapping.csv`.
   — Why it matters: this is the auditable join — anyone in the room can open that CSV and check
   the mapping themselves, nothing is hidden in code.
3. **`uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step reconcile`**
   — You should see: the imposed dispatch total, the fleet scale factor, `AC power flow converged:
   True`, the slack-bus residual as both MW and % of demand against the stated 5% band, then the
   printed reconciliation memo (which repeats, in its own text, that this is not a validation
   against a real reported outcome).
   — *Backup if unavailable*: read `expected_reconciliation.json` and narrate it the same way.
4. **`uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step check`**
   — You should see: the JSON result followed by `MATCH: reconciliation result matches
   expected_reconciliation.json`.
5. **Parts B and C are not run** — say so, and point to "Sandbox notes" above for why, rather than
   skipping past them silently.
