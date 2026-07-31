#!/usr/bin/env python3
"""Lab 4 -- Real AEMO Data: Digital-Twin Reconciliation (Part A only).

See README.md in this directory for the full walkthrough, and
docs/LAB4_AEMO_REAL_DATA.md for the original three-part spec. Four steps:

    uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step dispatch
    uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step map
    uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step reconcile
    uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step check

Sandbox note (read this before the "why" of anything below): this sandbox's
egress policy returns 403 ("destination host not allowed", confirmed via
/root/.ccr/__agentproxy/status, not a transient failure) for nemweb.com.au
*and* for github.com itself -- only raw.githubusercontent.com and pypi.org
are reachable. That means:

  - NEMOSIS is pip-installable (it's on PyPI), but `dynamic_data_compiler()`
    cannot actually reach NEMWeb to fetch a real dispatch interval. There is
    no live AEMO data this sandbox can pull -- SAMPLE_DUID_DISPATCH below is
    a documented, fixed stand-in in NEMOSIS's real column shape, not a
    captured historical interval. It uses real DUIDs (well-known South
    Australian generating units) with illustrative capacity/dispatch
    figures -- treat every MW value here as illustrative, not as reported
    AEMO ground truth, and verify against AEMO's real DUDETAILSUMMARY /
    DISPATCH_UNIT_SCADA before using this for anything beyond demonstrating
    the mechanism.
  - `susantoj/NEM_constraints` cannot be pip/git-installed (github.com
    blocked), so Part B (constraint-equation literacy) is NOT implemented
    in this pass -- see the README's "Sandbox notes" section. Faking a
    constraint decoder rather than using the real library would violate
    this repo's "use libraries, don't reinvent" rule worse than simply not
    building it yet.
  - Part C (the 2016 SA Black System narrative) is likewise not built here
    -- it needs the same unreachable NEMWeb pull, just for a different date.

What IS real below: snemSA.m (real CSIRO file, powerio-parsed), every
power-flow result (an actual pandapower.runpp() call, never fabricated),
and the DUID names (real South Australian generating units). What is a
documented stand-in: the specific MW figures in SAMPLE_DUID_DISPATCH and
TOTALDEMAND_MW.

One consequence of the network block worth stating plainly: docs/
LAB4_AEMO_REAL_DATA.md's original plan was to reconcile the model against
AEMO's *actually-reported* interconnector flow. Without a live pull there
is no real reported figure to compare against -- so this implementation's
"reconciliation" is a mechanism demonstration (map real DUIDs onto the
synthetic network, impose sample dispatch, solve, check the power balance
is physically sane) against a self-consistent illustrative sample, not a
validated comparison to reality. Swap `sample_dispatch()`'s body for a real
`nemosis.dynamic_data_compiler()` call the moment NEMWeb is reachable and
the rest of this file's logic is unchanged -- at that point the reconciled
figure becomes a genuine one.

A second real finding from actually building this (kept, not smoothed
over): snemSA.m has no modelled branch corresponding to the real
Heywood/Murraylink interconnectors -- its designated slack bus (985, 165kV)
is an internal sub-transmission reference node, not a boundary injection at
an interconnector's real voltage level (Heywood is 275kV AC). Comparing
this bus's solved P to a real interconnector flow would overclaim a
correspondence that isn't there, so this lab scores the *power balance*
(does imposing real-DUID dispatch plus a demand-matched scaling of the
rest of the fleet solve to a slack residual small relative to demand -- the
AC-loss-plus-mismatch sanity check) rather than an interconnector-flow
match.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandapower as pp
from _shared.gridfit import load_case

LAB_DIR = Path(__file__).resolve().parent
DATA_FILE = LAB_DIR.parent.parent / "data" / "snemSA.m"
MAPPING_FILE = LAB_DIR / "duid_mapping.csv"
EXPECTED_FILE = LAB_DIR / "expected_reconciliation.json"


class SampleDuid(TypedDict):
    """One row of the NEMOSIS-shaped sample stand-in (see module docstring).

    Field names deliberately echo NEMOSIS's real DISPATCH_UNIT_SCADA /
    DUDETAILSUMMARY columns (DUID, SCADAVALUE) so swapping in a real pull
    later is a data-source change, not a schema change.
    """

    DUID: str
    FUEL_SOURCE_DESCRIPTOR: str
    approx_registered_capacity_mw: float
    SCADAVALUE: float


# Real, well-known South Australian (SA1) generating units and illustrative
# dispatch figures -- see module docstring for what "illustrative" means
# here. Capacities are approximate public-knowledge figures for these units,
# not sourced from a live DUDETAILSUMMARY pull (blocked, see above); verify
# before relying on them for anything beyond this demo. Wind units are given
# a SCADAVALUE at a plausible capacity factor (30-55%) for a windy but not
# extreme dispatch interval; TORRA4 (gas steam) at a mid-merit dispatch
# level. Pelican Point (PPCCGT, ~478 MW) is deliberately excluded: no
# synthetic generator in snemSA.m is remotely close to that capacity (the
# largest is ~137.6 MW), and forcing a bad match would be worse than
# documenting the gap -- a real implementation would need to aggregate
# several synthetic buses or accept the mismatch explicitly.
SAMPLE_DUID_DISPATCH: list[SampleDuid] = [
    {"DUID": "TORRA4", "FUEL_SOURCE_DESCRIPTOR": "Natural Gas (Steam)", "approx_registered_capacity_mw": 120.0, "SCADAVALUE": 85.0},
    {"DUID": "HALLWF1", "FUEL_SOURCE_DESCRIPTOR": "Wind", "approx_registered_capacity_mw": 94.5, "SCADAVALUE": 41.0},
    {"DUID": "HALLWF2", "FUEL_SOURCE_DESCRIPTOR": "Wind", "approx_registered_capacity_mw": 71.4, "SCADAVALUE": 30.0},
    {"DUID": "SNOWTWN1", "FUEL_SOURCE_DESCRIPTOR": "Wind", "approx_registered_capacity_mw": 98.0, "SCADAVALUE": 52.0},
    {"DUID": "WPWF", "FUEL_SOURCE_DESCRIPTOR": "Wind", "approx_registered_capacity_mw": 111.0, "SCADAVALUE": 47.0},
    {"DUID": "LKBONNY3", "FUEL_SOURCE_DESCRIPTOR": "Wind", "approx_registered_capacity_mw": 39.0, "SCADAVALUE": 18.0},
    {"DUID": "CATHROCK", "FUEL_SOURCE_DESCRIPTOR": "Wind", "approx_registered_capacity_mw": 66.0, "SCADAVALUE": 25.0},
    {"DUID": "STARHLWF", "FUEL_SOURCE_DESCRIPTOR": "Wind", "approx_registered_capacity_mw": 34.5, "SCADAVALUE": 12.0},
    {"DUID": "MTMILLAR", "FUEL_SOURCE_DESCRIPTOR": "Wind", "approx_registered_capacity_mw": 70.0, "SCADAVALUE": 33.0},
    {"DUID": "CLEMGPWF", "FUEL_SOURCE_DESCRIPTOR": "Wind", "approx_registered_capacity_mw": 56.7, "SCADAVALUE": 21.0},
    {"DUID": "BLUFF1", "FUEL_SOURCE_DESCRIPTOR": "Wind", "approx_registered_capacity_mw": 52.5, "SCADAVALUE": 19.0},
]

# NOTE on TOTALDEMAND: earlier drafts of this file hardcoded an
# "illustrative" TOTALDEMAND_MW disconnected from snemSA.m's actual load.
# That was a bug, not a modelling choice: it left generation targeting one
# total while `net.load` (untouched) summed to a different one, so the
# slack bus was forced to absorb the gap between them on top of real AC
# losses -- a mismatch about the reconciliation mechanism's own arithmetic,
# not about how well the sample dispatch reconciles against the network.
# reconcile_step() now reads the network's own total load as the demand
# figure (the DISPATCHREGIONSUM.TOTALDEMAND stand-in), so the only thing
# left for the slack bus to absorb is genuine AC losses -- see
# SLACK_BALANCE_TOLERANCE_FRACTION.

# Loss/mismatch sanity band: real AC transmission losses on a ~1900 MW
# system are typically 1-3% of throughput; 5% is a documented, generous
# upper bound so a genuine modelling error (bad mapping, non-convergence)
# fails the check while ordinary AC losses do not. This is a physical-
# plausibility check, not a match against a real reported figure -- see
# module docstring for why there is no such figure to match here.
SLACK_BALANCE_TOLERANCE_FRACTION: float = 0.05

# Float-equality slack for expected_reconciliation.json comparison, same
# rationale as Lab 1/2's fixture tolerances (solver last-bit noise across
# numpy/BLAS versions).
FIXTURE_FLOAT_ATOL: float = 1e-3


def dispatch_step(verbose: bool = True) -> list[SampleDuid]:
    """"Fetch" step: the sample-dispatch stand-in (see module docstring for
    why this isn't a live NEMOSIS pull in this sandbox).

    Returns:
        SAMPLE_DUID_DISPATCH, unchanged -- a function (not a bare module
        constant reference) so a real `nemosis.dynamic_data_compiler()`
        call is a one-function swap later.
    """
    if verbose:
        total = sum(d["SCADAVALUE"] for d in SAMPLE_DUID_DISPATCH)
        print(
            f"[sandbox stand-in, not a live NEMOSIS pull -- see module "
            f"docstring] {len(SAMPLE_DUID_DISPATCH)} DUIDs, "
            f"{total:.1f} MW mapped dispatch (TOTALDEMAND is read from "
            f"snemSA.m's own load total in reconcile_step, not hardcoded "
            f"here -- see the note above SAMPLE_DUID_DISPATCH)"
        )
        for d in SAMPLE_DUID_DISPATCH:
            print(f"  {d['DUID']:<10} {d['FUEL_SOURCE_DESCRIPTOR']:<20} "
                  f"cap~{d['approx_registered_capacity_mw']:.1f} MW  "
                  f"SCADAVALUE={d['SCADAVALUE']:.1f} MW")
    return SAMPLE_DUID_DISPATCH


class DuidMappingRow(TypedDict):
    """One row of the committed, human-readable duid_mapping.csv."""

    real_duid: str
    fuel_source_descriptor: str
    approx_registered_capacity_mw: float
    matched_synthetic_bus: int
    matched_synthetic_base_p_mw: float
    capacity_delta_mw: float
    rationale: str


def map_duids(verbose: bool = True) -> list[DuidMappingRow]:
    """"Map" step: nearest-capacity match each sample DUID to a synthetic
    generator bus in snemSA.m.

    Matching is capacity-proximity only, not fuel-type -- MATPOWER case
    files (snemSA.m's format) carry no fuel-type field, confirmed by
    inspecting `net.gen.columns` while building this lab (there is no
    "fuel" or "type"-with-real-values column), so docs/LAB4_AEMO_REAL_DATA.md's
    "fuel type where the CSIRO metadata records it" clause resolves to
    "never, for this dataset" -- stated plainly rather than silently
    dropped. Matching excludes the slack bus (985) and every synthetic
    generator with zero base-case p_mw (23 of 56 non-slack generators --
    not currently dispatched in the base case, so not a sensible target for
    "this is where a real running unit's output goes"). Each synthetic bus
    is used at most once (greedy, real DUIDs processed largest-capacity
    first).

    Returns:
        One DuidMappingRow per SAMPLE_DUID_DISPATCH entry, also written to
        duid_mapping.csv.
    """
    net, _ = load_case(DATA_FILE)
    candidates = net.gen[(net.gen.bus != 985) & (net.gen.p_mw > 0)].copy()
    candidates = candidates.sort_values("p_mw")

    rows: list[DuidMappingRow] = []
    used_buses: set[int] = set()
    for duid in sorted(
        SAMPLE_DUID_DISPATCH,
        key=lambda d: d["approx_registered_capacity_mw"],
        reverse=True,
    ):
        remaining = candidates[~candidates.bus.isin(used_buses)]
        if remaining.empty:
            raise RuntimeError(
                f"map_duids: ran out of unused synthetic generator buses "
                f"before mapping {duid['DUID']}"
            )
        diffs = (remaining.p_mw - duid["approx_registered_capacity_mw"]).abs()
        best_idx = diffs.idxmin()
        best_bus = int(remaining.loc[best_idx, "bus"])
        best_p_mw = float(remaining.loc[best_idx, "p_mw"])
        used_buses.add(best_bus)
        rows.append(
            {
                "real_duid": duid["DUID"],
                "fuel_source_descriptor": duid["FUEL_SOURCE_DESCRIPTOR"],
                "approx_registered_capacity_mw": duid["approx_registered_capacity_mw"],
                "matched_synthetic_bus": best_bus,
                "matched_synthetic_base_p_mw": round(best_p_mw, 3),
                "capacity_delta_mw": round(best_p_mw - duid["approx_registered_capacity_mw"], 3),
                "rationale": "nearest-capacity match among non-slack, "
                             "nonzero-p_mw synthetic generators (no fuel-type "
                             "field in snemSA.m -- see function docstring)",
            }
        )

    MAPPING_FILE.parent.mkdir(parents=True, exist_ok=True)
    with MAPPING_FILE.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    if verbose:
        print(f"{'real_duid':<10} {'->':<3} {'bus':>5} {'base_p_mw':>10} "
              f"{'target_mw':>10} {'delta_mw':>9}")
        for r in rows:
            print(f"{r['real_duid']:<10} {'->':<3} {r['matched_synthetic_bus']:>5} "
                  f"{r['matched_synthetic_base_p_mw']:>10.1f} "
                  f"{r['approx_registered_capacity_mw']:>10.1f} "
                  f"{r['capacity_delta_mw']:>9.1f}")
        print(f"written to {MAPPING_FILE}")
    return rows


class ReconciliationResult(TypedDict):
    """Outcome of imposing sample dispatch on snemSA.m and solving AC power flow."""

    total_demand_mw: float
    mapped_dispatch_mw: float
    unmapped_scale_factor: float
    converged: bool
    slack_p_mw: float
    slack_fraction_of_demand: float
    within_tolerance: bool
    tolerance_fraction: float


def reconcile_step(verbose: bool = True) -> ReconciliationResult:
    """"Reconcile" step: impose the sample dispatch on snemSA.m, scale the
    unmapped fleet to match the network's own total load, solve, and score
    the power balance (see module docstring for why this is a balance
    check, not an interconnector-flow match).

    The "TOTALDEMAND" figure (the DISPATCHREGIONSUM.TOTALDEMAND stand-in)
    is read from `net.load.p_mw.sum()` -- snemSA.m's own real base-case
    load total -- rather than a separately invented constant. An earlier
    version of this function used a hardcoded illustrative total that
    didn't match the network's actual load, which forced the slack bus to
    absorb that mismatch on top of genuine AC losses; using the real load
    total removes that artefact so the tolerance check below measures only
    losses, which is what it claims to measure.

    Returns:
        A ReconciliationResult; `within_tolerance` is the pass/fail gate
        matching docs/DEFINITION_OF_DONE.md's Lab 4 entry.
    """
    if not DATA_FILE.exists():
        print(
            f"[FAIL] {DATA_FILE} not found -- run "
            f"'uv run scripts/fetch_csiro_nem_data.py' first",
            file=sys.stderr,
        )
        sys.exit(1)

    mapping = map_duids(verbose=False)
    net, _ = load_case(DATA_FILE)
    total_demand_mw = float(net.load.p_mw.sum())

    mapped_buses = {row["matched_synthetic_bus"] for row in mapping}
    mapped_dispatch_mw = sum(d["SCADAVALUE"] for d in SAMPLE_DUID_DISPATCH)
    for row, duid in zip(mapping, SAMPLE_DUID_DISPATCH):
        net.gen.loc[net.gen.bus == row["matched_synthetic_bus"], "p_mw"] = duid["SCADAVALUE"]

    unmapped_mask = (~net.gen.bus.isin(mapped_buses)) & (net.gen.bus != 985)
    unmapped_base_total = float(net.gen.loc[unmapped_mask, "p_mw"].sum())
    target_unmapped_total = total_demand_mw - mapped_dispatch_mw
    # Scale factor for the rest of the fleet so mapped+unmapped generation
    # targets total_demand_mw before the AC solve (which will still add/
    # remove a slack residual for losses -- that residual is exactly what
    # this step scores). Guard against unmapped_base_total == 0, which
    # cannot occur here (33 nonzero non-slack gens minus 11 mapped leaves
    # 22 > 0) but would make the scale factor undefined.
    if unmapped_base_total <= 0:
        raise RuntimeError(
            "reconcile_step: no unmapped generation capacity to scale -- "
            "check map_duids() didn't consume every nonzero synthetic generator"
        )
    scale_factor = target_unmapped_total / unmapped_base_total
    net.gen.loc[unmapped_mask, "p_mw"] = net.gen.loc[unmapped_mask, "p_mw"] * scale_factor

    pp.runpp(net, init="flat")
    slack_p_mw = float(net.res_gen.loc[net.gen.bus == 985, "p_mw"].iloc[0])
    slack_fraction = abs(slack_p_mw) / total_demand_mw
    within_tolerance = slack_fraction <= SLACK_BALANCE_TOLERANCE_FRACTION

    result: ReconciliationResult = {
        "total_demand_mw": round(total_demand_mw, 3),
        "mapped_dispatch_mw": round(mapped_dispatch_mw, 3),
        "unmapped_scale_factor": round(scale_factor, 6),
        "converged": bool(net.converged),
        "slack_p_mw": round(slack_p_mw, 3),
        "slack_fraction_of_demand": round(slack_fraction, 6),
        "within_tolerance": within_tolerance,
        "tolerance_fraction": SLACK_BALANCE_TOLERANCE_FRACTION,
    }

    if verbose:
        print(
            f"Imposed {len(mapping)} real-DUID dispatch values "
            f"({mapped_dispatch_mw:.1f} MW), scaled remaining fleet by "
            f"{scale_factor:.4f}x to match snemSA.m's own total load "
            f"({total_demand_mw:.1f} MW)"
        )
        print(f"AC power flow converged: {result['converged']}")
        status = "PASS" if within_tolerance else "FAIL"
        print(
            f"Slack bus (985) residual: {slack_p_mw:+.2f} MW "
            f"({slack_fraction * 100:.2f}% of demand, tolerance "
            f"{SLACK_BALANCE_TOLERANCE_FRACTION * 100:.0f}%) -> {status}"
        )
        print(draft_memo(result, mapping))
    return result


def draft_memo(result: ReconciliationResult, mapping: list[DuidMappingRow]) -> str:
    """Plain-English reconciliation memo -- reports `result`, does not
    itself decide pass/fail (same discipline as Lab 2's draft_memo)."""
    lines = [
        "",
        "RECONCILIATION MEMO (illustrative sample, not a live pull -- see "
        "reconcile.py module docstring)",
        "=" * 70,
        f"{len(mapping)} real SA1 DUIDs mapped onto snemSA.m by nearest "
        f"generator capacity (no fuel-type field in this dataset).",
        f"Target regional demand: {result['total_demand_mw']:.1f} MW "
        f"(snemSA.m's own real base-case load total). Mapped real-DUID "
        f"dispatch (illustrative, see module docstring): "
        f"{result['mapped_dispatch_mw']:.1f} MW. Remaining fleet scaled "
        f"{result['unmapped_scale_factor']:.3f}x to close the balance before "
        f"solving.",
        f"AC power flow: {'converged' if result['converged'] else 'DID NOT CONVERGE'}.",
        f"Slack-bus residual (losses + any mismatch): "
        f"{result['slack_p_mw']:+.2f} MW "
        f"({result['slack_fraction_of_demand'] * 100:.2f}% of demand).",
    ]
    if result["within_tolerance"]:
        lines.append(
            f"WITHIN the {result['tolerance_fraction'] * 100:.0f}% sanity "
            f"band for AC losses on a system this size -- the mapping+impose "
            f"procedure produces a physically plausible balanced case."
        )
    else:
        lines.append(
            f"OUTSIDE the {result['tolerance_fraction'] * 100:.0f}% sanity "
            f"band -- investigate the mapping or the scaling before trusting "
            f"this case."
        )
    lines.append(
        "This is NOT a validation against AEMO's real reported outcome for "
        "any actual interval -- see reconcile.py's module docstring for why "
        "no such figure is available in this sandbox, and what changes once "
        "NEMWeb is reachable."
    )
    return "\n".join(lines)


def check_step() -> bool:
    """Self-check gate: re-run the reconciliation and diff against
    expected_reconciliation.json."""
    actual = reconcile_step(verbose=False)
    if not EXPECTED_FILE.exists():
        print(f"[FAIL] no fixture at {EXPECTED_FILE}", file=sys.stderr)
        return False
    expected = json.loads(EXPECTED_FILE.read_text())

    mismatches = []
    for key in ("mapped_dispatch_mw", "slack_p_mw", "slack_fraction_of_demand", "converged", "within_tolerance"):
        exp_val, act_val = expected[key], actual[key]
        if isinstance(exp_val, float):
            ok = abs(exp_val - act_val) <= FIXTURE_FLOAT_ATOL
        else:
            ok = exp_val == act_val
        if not ok:
            mismatches.append((key, exp_val, act_val))

    print(json.dumps(actual, indent=2))
    if mismatches:
        print("FAIL: fixture mismatch")
        for key, exp_val, act_val in mismatches:
            print(f"  {key}: expected={exp_val} actual={act_val}")
        return False
    print("MATCH: reconciliation result matches expected_reconciliation.json")
    return True


def main() -> None:
    """CLI entry point: dispatches to each step per --step."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--step", choices=["dispatch", "map", "reconcile", "check"], default="check"
    )
    args = parser.parse_args()

    if args.step == "dispatch":
        dispatch_step()
    elif args.step == "map":
        map_duids()
    elif args.step == "reconcile":
        reconcile_step()
    elif args.step == "check":
        ok = check_step()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
