#!/usr/bin/env python3
"""Lab 4 step 3 (+ optional step 5) -- digital-twin reconciliation.

    uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py
    uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step check
    uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --date 2016-09-28   # optional Part C

Imposes real SCADA MW on the synthetic generators matched by map_duids.py
(duid_mapping.csv, summed per synthetic bus), scales all synthetic loads by
a single factor so total demand matches the real DISPATCHREGIONSUM total,
solves a real `pandapower.runpp()`, and compares the modelled flow at
snemSA.m's interconnector-equivalent bus (see _lab4_shared.py) to the real
combined V-SA + V-S-MNSP1 flow (DISPATCHREGIONSUM's NETINTERCHANGE for
SA1) within RECONCILE_TOLERANCE_FRACTION.

**Honesty caveat (docs/LAB4_AEMO_REAL_DATA.md, verbatim requirement):**
this is not a digital twin of the real SA network. snemSA.m's topology is
synthetic -- real NEM statistics, invented specific line and bus
parameters. This script's teaching point is the reconciliation
methodology and the discipline of explaining the gap, not a claim that the
modelled network reproduces reality.

Sandbox stand-ins (all named here and in this lab's README "Sandbox
notes"):
- The "interconnector-equivalent branch" is snemSA.m's single slack
  generator (see _lab4_shared.INTERCONNECTOR_EQUIVALENT_BUS's docstring
  for why) standing in for the real Heywood (V-SA) + Murraylink
  (V-S-MNSP1) interconnectors combined -- snemSA.m is an SA-only island
  reduction with no explicit branches to VIC1 at all.
- Unmatched synthetic generators (buses with no real DUID mapped to them
  by map_duids.py) are set to 0 MW, not left at their snemSA.m base-case
  Pg -- see `_impose_real_generation`'s docstring for why leaving them at
  base-case output reliably fails to converge (it double-counts capacity
  against the real generators SCADA is imposed on) and why 0 MW is the
  honest choice: this reconciliation only asserts generation this lab has
  real evidence for.
- All synthetic loads are scaled by one uniform factor
  (`_shared.gridfit.scale_loads`, the same helper Lab 1 uses), not a
  per-bus real allocation -- this lab has no real bus-level SA1 demand
  data, only the regional DISPATCHREGIONSUM total, so "scale any
  unmatched load buses" (docs/LAB4_AEMO_REAL_DATA.md Part A step 5) is
  implemented as "scale every load bus by the same regional ratio," the
  only demand-matching this lab's real data actually supports.

--step check's optional Part C use (docs/LAB4_AEMO_REAL_DATA.md Part C):
**this is explicitly not a claim that this model reproduces the 2016 SA
Black System event's actual root cause.** That event's real cause --
wind-farm low-voltage-ride-through and rate-of-change-of-frequency
protection settings tripping in sequence -- needs dynamic/transient
simulation this lab does not attempt (a single snapshot AC power flow
cannot show a cascading protection-trip sequence). What --date 2016-09-28
*can* honestly show is the real pre-event dispatch mix (high wind
penetration, real interconnector loading) reconciled against the same
synthetic network exactly as in Part A, with AEMO's own report supplying
the narrative the model itself cannot -- see PART_C_NARRATIVE below and
this lab's README "References."
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Final, Optional, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandapower as pp
import pandas as pd
from _lab4_shared import (
    LAB4_DATE,
    NEMOSIS_CACHE_DIR,
    PART_C_DATE,
    PART_C_INTERVAL,
    RECONCILE_INTERVAL,
    RECONCILE_TOLERANCE_FLOOR_MW,
    RECONCILE_TOLERANCE_FRACTION,
    SA_INTERCONNECTOR_IDS,
    load_synthetic_net,
    slack_bus,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _shared.gridfit import scale_loads

from nemosis import dynamic_data_compiler

LAB_DIR: Final[Path] = Path(__file__).resolve().parent
MAPPING_CSV: Final[Path] = LAB_DIR / "duid_mapping.csv"
EXPECTED_FILE: Final[Path] = LAB_DIR / "expected_reconciliation.json"

# Same rationale as Lab 1/2's FIXTURE_FLOAT_ATOL / FIXTURE_VOLTAGE_ATOL:
# looser than JSON print precision to absorb pandapower Newton-Raphson
# solver noise across numpy/BLAS versions, tight enough to catch a real
# regression. 0.5 MW is small relative to both RECONCILE_TOLERANCE_FLOOR_MW
# (10 MW) and any plausible real interconnector flow (~hundreds of MW).
FIXTURE_FLOAT_ATOL_MW: Final[float] = 0.5

# docs/LAB4_AEMO_REAL_DATA.md Part C's guided-reading excerpt. Paraphrased
# (not a verbatim quote) from AEMO's own public integrated final report on
# the 28 September 2016 SA Black System event (see README "References"
# for the exact document) -- included so `reconcile.py --date 2016-09-28`
# is self-contained even without network access to AEMO's PDF, and printed
# every time --date 2016-09-28 is used, immediately after the caveat.
PART_C_NARRATIVE: Final[str] = (
    "AEMO's integrated final report (2017) describes the pre-event SA1 "
    "dispatch mix on 28 September 2016 as unusually wind-heavy: five "
    "reported tornadoes tracked across the state, wind generation was "
    "supplying roughly half of SA1's demand, and the Heywood "
    "interconnector was importing power from Victoria. Multiple line "
    "faults in quick succession triggered voltage disturbances; a "
    "sequence of wind farms' low-voltage-ride-through protection settings "
    "reduced their output faster than their registered performance "
    "standards assumed, Heywood's flow surged to fill the gap and tripped "
    "on overcurrent protection, and the resulting frequency collapse "
    "islanded and then blacked out the entire SA1 region. None of that "
    "protection-trip sequence is visible in a single snapshot AC power "
    "flow -- see the caveat above."
)


class ReconciliationResult(TypedDict):
    """JSON-serializable reconciliation outcome, also the shape of
    expected_reconciliation.json."""

    date: str
    interval: str
    converged: bool
    matched_synthetic_generators: int
    load_scale_factor: float
    total_demand_actual_mw: float
    modelled_interconnector_mw: float
    actual_interconnector_mw: float
    synthetic_network_losses_mw: float
    actual_interconnector_losses_mw: float
    delta_mw: float
    tolerance_fraction: float
    passed: bool


def _interval_for_date(date: str) -> str:
    """Pick the dispatch interval to reconcile for a given --date.

    Args:
        date: ISO 'YYYY-MM-DD' date.

    Returns:
        The full 'YYYY-MM-DD HH:MM:SS' interval: RECONCILE_INTERVAL for
        LAB4_DATE, PART_C_INTERVAL for PART_C_DATE, else a default of
        noon on the given date (documented fallback for any other date a
        user passes ad hoc).
    """
    if date == LAB4_DATE:
        return RECONCILE_INTERVAL
    if date == PART_C_DATE:
        return PART_C_INTERVAL
    return f"{date} 12:00:00"


def _day_window(date: str) -> tuple[str, str]:
    day = datetime.date.fromisoformat(date)
    next_day = day + datetime.timedelta(days=1)
    fmt = "%Y/%m/%d %H:%M:%S"
    start = datetime.datetime.combine(day, datetime.time.min).strftime(fmt)
    end = datetime.datetime.combine(next_day, datetime.time.min).strftime(fmt)
    return start, end


def _pull_reconciliation_inputs(
    date: str, interval: str
) -> tuple[pd.DataFrame, float, float, float]:
    """Pull the real quantities this reconciliation needs.

    Args:
        date: ISO date (drives the NEMOSIS fetch window).
        interval: the specific 'YYYY-MM-DD HH:MM:SS' dispatch interval.

    Returns:
        (scada_at_interval, total_demand_mw, actual_interconnector_mw,
        actual_losses_mw): SCADA MW per DUID at `interval`; SA1's real
        TOTALDEMAND at `interval`; SA1's real combined interconnector
        import (-NETINTERCHANGE, i.e. positive = importing into SA1) at
        `interval`; the real combined V-SA + V-S-MNSP1 MWLOSSES at
        `interval` (used by the reconciliation memo to quantify how much
        of the modelled-vs-actual delta is explained by snemSA.m's own,
        much larger, internal line/transformer losses -- see
        `_reconciliation_memo`).
    """
    start, end = _day_window(date)
    scada = dynamic_data_compiler(
        start, end, "DISPATCH_UNIT_SCADA", str(NEMOSIS_CACHE_DIR),
        fformat="parquet", keep_csv=False,
    )
    scada_at_interval = scada[scada["SETTLEMENTDATE"] == interval]

    regionsum = dynamic_data_compiler(
        start, end, "DISPATCHREGIONSUM", str(NEMOSIS_CACHE_DIR),
        fformat="parquet", keep_csv=False,
    )
    sa_row = regionsum[
        (regionsum["SETTLEMENTDATE"] == interval) & (regionsum["REGIONID"] == "SA1")
    ]
    if sa_row.empty:
        print(
            f"[FAIL] no DISPATCHREGIONSUM row for SA1 at {interval} -- "
            f"run fetch_day.py for this date first",
            file=sys.stderr,
        )
        sys.exit(1)
    total_demand = float(sa_row.iloc[0]["TOTALDEMAND"])
    net_interchange = float(sa_row.iloc[0]["NETINTERCHANGE"])
    actual_interconnector_mw = -net_interchange  # positive = import to SA1

    interconnectorres = dynamic_data_compiler(
        start, end, "DISPATCHINTERCONNECTORRES", str(NEMOSIS_CACHE_DIR),
        fformat="parquet", keep_csv=False,
    )
    ic_rows = interconnectorres[
        (interconnectorres["SETTLEMENTDATE"] == interval)
        & (interconnectorres["INTERCONNECTORID"].isin(SA_INTERCONNECTOR_IDS))
    ]
    actual_losses_mw = float(ic_rows["MWLOSSES"].sum())

    return scada_at_interval, total_demand, actual_interconnector_mw, actual_losses_mw


def _impose_real_generation(
    net: pp.pandapowerNet, mapping: pd.DataFrame, scada_at_interval: pd.DataFrame
) -> int:
    """Set each synthetic generator's p_mw from real SCADA: the sum of
    every real DUID map_duids.py matched onto it, or 0.0 if map_duids.py
    matched no real DUID onto it at all.

    The "0.0 for unmapped generators" half of this is a deliberate
    modelling decision, not an oversight: map_duids.py's nearest-capacity
    matching is not a bijection (89 real SA1 generator DUIDs vs. 56
    non-slack synthetic generators, so several real DUIDs share a nearest
    synthetic bus -- see map_duids.py), which leaves roughly a third of
    snemSA.m's generators with no real DUID mapped onto them at all. Left
    at snemSA.m's own base-case OPF dispatch (this function's first
    version), those generators' unchanged Pg stacks on top of the real
    SCADA imposed elsewhere and inflates total synthetic generation to
    ~2500 MW against a real ~1800 MW SA1 demand -- a generation surplus
    that reflects double-counted capacity, not anything about the real
    grid, and reliably fails to converge. Zeroing them instead means this
    reconciliation only asserts generation this lab actually has real
    SCADA evidence for; the resulting shortfall is exactly what the
    interconnector-equivalent slack bus (see _lab4_shared.py) is for.

    Args:
        net: the synthetic pandapower net (mutated in place).
        mapping: duid_mapping.csv, loaded.
        scada_at_interval: DISPATCH_UNIT_SCADA rows for exactly one
            dispatch interval.

    Returns:
        Number of synthetic generators with at least one real DUID
        mapped onto them (regardless of that DUID's SCADA reading at this
        particular interval, which may itself be 0).
    """
    scada_by_duid = scada_at_interval.set_index("DUID")["SCADAVALUE"]
    imposed = mapping.copy()
    imposed["scada_mw"] = imposed["real_duid"].map(scada_by_duid).fillna(0.0)
    per_bus_mw = imposed.groupby("synthetic_gen_bus")["scada_mw"].sum()

    bus_to_gen_idx = {int(b): i for i, b in net.gen["bus"].items()}
    mapped_buses = set(int(b) for b in mapping["synthetic_gen_bus"].unique())
    matched = 0
    for bus, gen_idx in bus_to_gen_idx.items():
        if net.gen.at[gen_idx, "slack"]:
            continue  # the interconnector-equivalent bus, not a real generator
        if bus in mapped_buses:
            net.gen.at[gen_idx, "p_mw"] = float(per_bus_mw.get(bus, 0.0))
            matched += 1
        else:
            net.gen.at[gen_idx, "p_mw"] = 0.0
    return matched


def reconcile(date: str = LAB4_DATE, verbose: bool = True) -> ReconciliationResult:
    """Run Part A's full reconciliation for one dispatch interval.

    Args:
        date: ISO date to reconcile (LAB4_DATE for the ordinary-day run,
            PART_C_DATE for the optional 2016 case study).
        verbose: if True, print the step-by-step progress and the closing
            reconciliation memo (see README step 3/5).

    Returns:
        A ReconciliationResult, JSON-serializable and diffable against
        expected_reconciliation.json (see check_step).
    """
    interval = _interval_for_date(date)
    if date == PART_C_DATE:
        print("=" * 72)
        print(
            "CAVEAT: this is NOT a claim that this model reproduces the 2016 "
            "SA Black System event's actual root cause. See reconcile.py's "
            "module docstring and this lab's README before reading further."
        )
        print("=" * 72)
        print(PART_C_NARRATIVE)
        print()

    if not MAPPING_CSV.exists():
        print(
            f"[FAIL] {MAPPING_CSV} not found -- run "
            f"'uv run labs/04-aemo-digital-twin-reconciliation/map_duids.py' first",
            file=sys.stderr,
        )
        sys.exit(1)
    mapping = pd.read_csv(MAPPING_CSV)

    net, _warnings = load_synthetic_net()
    slack = slack_bus(net)  # asserts the interconnector-equivalent assumption

    if verbose:
        print(f"Reconciling {date} interval {interval} (region SA1)")

    scada_at_interval, total_demand_actual, actual_interconnector_mw, actual_losses_mw = (
        _pull_reconciliation_inputs(date, interval)
    )

    matched = _impose_real_generation(net, mapping, scada_at_interval)

    base_load_mw = float(net.load["p_mw"].sum())
    load_scale = total_demand_actual / base_load_mw
    net = scale_loads(net, load_scale)

    if verbose:
        print(
            f"Imposed real SCADA MW on {matched} synthetic generators; "
            f"scaled loads x{load_scale:.4f} ({base_load_mw:.1f} MW base -> "
            f"{total_demand_actual:.1f} MW actual SA1 demand)"
        )

    pp.runpp(net)
    converged = bool(net.converged)
    modelled_interconnector_mw = float(net.res_gen.at[
        net.gen[net.gen["slack"]].index[0], "p_mw"
    ])
    synthetic_losses_mw = float(net.res_line["pl_mw"].sum() + net.res_trafo["pl_mw"].sum())

    delta = modelled_interconnector_mw - actual_interconnector_mw
    tolerance_mw = max(
        RECONCILE_TOLERANCE_FRACTION * abs(actual_interconnector_mw),
        RECONCILE_TOLERANCE_FLOOR_MW,
    )
    passed = converged and abs(delta) <= tolerance_mw

    if verbose:
        status = "PASS" if passed else "FAIL"
        print(
            f"Modelled interconnector-equivalent flow (bus {slack}): "
            f"{modelled_interconnector_mw:+.1f} MW"
        )
        print(f"Actual combined {' + '.join(SA_INTERCONNECTOR_IDS)} flow: "
              f"{actual_interconnector_mw:+.1f} MW")
        print(
            f"Delta: {delta:+.1f} MW (tolerance +/-{tolerance_mw:.1f} MW = "
            f"{RECONCILE_TOLERANCE_FRACTION:.0%} of actual, floor "
            f"{RECONCILE_TOLERANCE_FLOOR_MW:.0f} MW) -> {status}"
        )
        print()
        print(
            _reconciliation_memo(
                matched, len(mapping), delta, tolerance_mw, passed,
                synthetic_losses_mw, actual_losses_mw, mapping_is_stale=(date != LAB4_DATE),
            )
        )

    return {
        "date": date,
        "interval": interval,
        "converged": converged,
        "matched_synthetic_generators": matched,
        "load_scale_factor": round(load_scale, 6),
        "total_demand_actual_mw": round(total_demand_actual, 3),
        "modelled_interconnector_mw": round(modelled_interconnector_mw, 3),
        "actual_interconnector_mw": round(actual_interconnector_mw, 3),
        "synthetic_network_losses_mw": round(synthetic_losses_mw, 3),
        "actual_interconnector_losses_mw": round(actual_losses_mw, 3),
        "delta_mw": round(delta, 3),
        "tolerance_fraction": RECONCILE_TOLERANCE_FRACTION,
        "passed": passed,
    }


def _reconciliation_memo(
    matched_gens: int, total_mapped_duids: int, delta_mw: float, tolerance_mw: float,
    passed: bool, synthetic_losses_mw: float, actual_losses_mw: float,
    mapping_is_stale: bool = False,
) -> str:
    """Draft the plain-English reconciliation memo docs/LAB4_AEMO_REAL_
    DATA.md Part A step 8 asks for: modelled vs. actual, and a plausible
    explanation for the difference, graded on correctly identifying the
    divergence as a topology-fidelity artifact, not a bug.

    Sandbox note: same as Lab 2's draft_memo -- docs/VISION.md has an LLM
    draft this text; this sandbox has no live model server (see
    labs/01-simple-loadflow-fit/run.py's module docstring for why), so
    this is a plain Python f-string template. It only explains a delta
    `reconcile()` already computed -- it does not decide pass/fail itself.

    Args:
        matched_gens: synthetic generators that received an imposed
            real-SCADA value.
        total_mapped_duids: total real DUIDs in duid_mapping.csv.
        delta_mw: modelled minus actual interconnector flow.
        tolerance_mw: the absolute MW tolerance band used.
        passed: whether reconcile() judged this within tolerance.
        synthetic_losses_mw: real pandapower-computed line + transformer
            losses across the whole solved synthetic network.
        actual_losses_mw: real AEMO-published combined V-SA + V-S-MNSP1
            MWLOSSES for the same interval.
        mapping_is_stale: True when duid_mapping.csv (always built for
            LAB4_DATE) is being applied to a *different* date's SCADA --
            i.e. an optional Part C run. A real DUID's capacity proxy, or
            its very existence, can differ between the two dates (plant
            commissioned/decommissioned, re-registered), which is a
            second, distinct source of reconciliation error on top of the
            network-loss one this function otherwise leads with.

    Returns:
        The memo text.
    """
    verdict = (
        "within the stated tolerance" if passed
        else "outside the stated tolerance"
    )
    loss_gap_mw = synthetic_losses_mw - actual_losses_mw
    # Only credit the loss gap as *the* explanation when it plausibly
    # pushes the delta in the same direction and is large enough to
    # matter -- a same-magnitude loss gap of the *opposite* sign to the
    # overall delta (seen on some Part C intervals, see mapping_is_stale)
    # means something else dominates, and claiming otherwise would be the
    # kind of hand-wave this lab is explicitly trying not to do.
    loss_explains = (
        abs(loss_gap_mw) >= 0.5 * abs(delta_mw)
        and (loss_gap_mw > 0) == (delta_mw > 0)
        if abs(delta_mw) > 1e-6
        else False
    )
    lines = [
        "RECONCILIATION MEMO",
        "=" * 60,
        f"{matched_gens} of snemSA.m's 56 non-slack generators received a real "
        f"SCADA MW value, aggregated from {total_mapped_duids} matched real "
        f"SA1 DUIDs (see duid_mapping.csv).",
        f"Modelled-vs-actual interconnector-equivalent delta: {delta_mw:+.1f} MW "
        f"({verdict}, tolerance +/-{tolerance_mw:.1f} MW).",
        "",
        f"Whole-network real losses in the solved synthetic model: "
        f"{synthetic_losses_mw:.1f} MW (line + transformer). AEMO's "
        f"published combined V-SA + V-S-MNSP1 loss for the same interval: "
        f"{actual_losses_mw:.1f} MW -- a {loss_gap_mw:+.1f} MW gap.",
    ]
    if loss_explains:
        lines.append(
            f"This loss gap alone accounts for most of the {delta_mw:+.1f} MW "
            f"reconciliation delta: snemSA.m's per-line resistance values are "
            f"synthetic estimates (real NEM topology, invented specific "
            f"parameters -- see this lab's README 'Honesty caveat'), not "
            f"calibrated to reproduce real transmission loss factors, so the "
            f"whole-network model carries far more internal loss than the "
            f"real interconnectors alone report. This is a topology-fidelity "
            f"artifact, not a bug: the reconciliation's value is in "
            f"quantifying and explaining the gap, not eliminating it."
        )
    else:
        explanation = (
            "This gap is expected even so, not a bug: snemSA.m's line "
            "impedances, its single slack bus standing in for two real "
            "interconnectors (Heywood AC + Murraylink DC) with different "
            "loss characteristics, and a uniform load-scaling factor in "
            "place of real bus-level demand are all synthetic-topology "
            "approximations, not physics errors."
        )
        if mapping_is_stale:
            explanation += (
                " On top of that, duid_mapping.csv was built from DUIDs "
                f"registered as of {LAB4_DATE} and is being applied here to "
                "an earlier interval: a real generator dispatched that day "
                "may since have been re-registered or decommissioned (and "
                "so is absent from today's mapping, imposing 0 MW where "
                "real output existed), or vice versa -- a second, distinct "
                "source of error specific to reconciling against a "
                "historical date with a present-day DUID mapping."
            )
        explanation += (
            " The reconciliation's value is in quantifying and explaining "
            "this gap, not in eliminating it -- see this lab's README "
            "'Honesty caveat.'"
        )
        lines.append(explanation)
    return "\n".join(lines)


def check_step(date: str = LAB4_DATE) -> bool:
    """Self-check gate: re-run reconcile() for LAB4_DATE and diff against
    expected_reconciliation.json.

    Deliberately always checks LAB4_DATE regardless of what a caller might
    pass, matching this lab's committed fixture (Part C's 2016 run is a
    narrative extra, not a fixture-checked path -- its real-world event
    data doesn't need a regression fixture the way the ordinary-day
    mechanic does).

    Returns:
        True if every compared field matches within FIXTURE_FLOAT_ATOL_MW
        (floats) or exactly (bool/int); False otherwise.
    """
    actual = reconcile(LAB4_DATE, verbose=False)

    if not EXPECTED_FILE.exists():
        print(f"[FAIL] no fixture at {EXPECTED_FILE}", file=sys.stderr)
        return False
    expected = json.loads(EXPECTED_FILE.read_text())

    mismatches = []
    for key, val in expected.items():
        exp_val, act_val = val, actual[key]
        if isinstance(exp_val, float):
            ok = abs(exp_val - act_val) <= FIXTURE_FLOAT_ATOL_MW
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

    print(
        f"MATCH: modelled={actual['modelled_interconnector_mw']} "
        f"actual={actual['actual_interconnector_mw']} vs "
        f"expected_reconciliation.json"
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=LAB4_DATE)
    parser.add_argument("--step", choices=["run", "check"], default="run")
    args = parser.parse_args()

    if args.step == "run":
        reconcile(args.date)
    elif args.step == "check":
        ok = check_step(args.date)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
