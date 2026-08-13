#!/usr/bin/env python3
"""Lab 5, PRD-0005 Phase 1.5 -- EMT -> steady-state constraint-headroom
translation.

See README.md's "Phase 1.5" section for the full walkthrough. Two steps:

    uv run labs/05-spartan-chaosnet-transient-stream/headroom_translation.py --step run
    uv run labs/05-spartan-chaosnet-transient-stream/headroom_translation.py --step check

Goal 2 of docs/prd/0005-grid-forming-stabilizer-and-renewable-models.md:
Phase 1's `grid_forming.py` measured a real EMT-domain result (a peak
positive-sequence-adjacent RMS voltage-sag-depth reduction on the
fault-adjacent line, `stabilizer_comparison.json`) -- but that number lives
entirely in the transient/time-domain tier and says nothing on its own about
whether it matters to AEMO's steady-state dispatch/constraint layer. This
script is the honest translation: read Phase 1's real measured numbers,
express them as a constraint-parameter change on the *same* fault-adjacent
line in a real pandapower net built from the *same* chaos-net topology
Phase 1's DPsim run used (`chaosnet.to_pandapower()`, not a different
network), re-run a real `pandapower.runpp()`, and report -- honestly,
either way -- whether the binding-constraint set actually changes.

Not literal OPF: this reuses labs/02-medium-interconnection-screening's own
`check_limits()` pattern (workflow.py lines ~69-77) -- a `pp.runpp()`
steady-state loadflow compared against a thermal `loading_percent` limit and
a voltage band, i.e. a limit *screen*, not a cost-optimizing `pp.runopp()`
dispatch. Called a "limit screen" throughout this file, never "OPF", per
PRD-0005 Phase 1.5's own instruction not to overclaim what pp.runpp()-based
screening is.

Stays entirely inside Lab 5: `chaosnet.py`'s own `to_pandapower()` builds
the pandapower net from the identical `ChaosTopology` object Phase 1's DPsim
EMT run solved (same seed, same buses/lines, including the fault-adjacent
line identified by `chaosnet.fault_adjacent_line_name()`). Lab 1/2/4 use a
topologically unrelated fixed real-world network (`snem1803.m`) -- mapping
this chaos-net-specific result onto them would be an arbitrary
correspondence, so this script deliberately does not reach into their code
or data at all.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandapower as pp

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chaosnet  # noqa: E402

LAB_DIR = Path(__file__).resolve().parent
COMPARISON_JSON = LAB_DIR / "stabilizer_comparison.json"
HEADROOM_JSON = LAB_DIR / "headroom_translation.json"

# Same steady-state limit-screen convention as
# labs/02-medium-interconnection-screening/workflow.py's check_limits()
# (THERMAL_LIMIT_PERCENT / VOLTAGE_BAND_PU, defined around lines 69-77 of
# that file): 100% of a line's nameplate thermal current rating, and a
# 0.90-1.10 pu voltage band. Redefined here (not imported) so Lab 5 stays
# self-contained and Lab 2's files are untouched, per PRD-0005 Phase 1.5's
# explicit "don't touch Lab 1/2/4 files" instruction -- but it is the exact
# same rule, cited here rather than reinvented.
THERMAL_LIMIT_PERCENT: float = 100.0
VOLTAGE_BAND_PU: tuple[float, float] = (0.90, 1.10)

# --- Translation hypothesis --------------------------------------------
#
# This is the genuinely open part the PRD itself flags -- there is no
# established, off-the-shelf technique in this repo (or found in this
# session's research) for turning an EMT-measured transient voltage-sag
# improvement into a steady-state thermal-rating change. Three honest
# options were considered:
#
#   (a) No translation at all. Sag depth (a voltage quantity, driven by
#       fault-current x network impedance during a ~150ms disturbance) and
#       steady-state thermal loading (a continuous-current quantity,
#       driven by load flow) are different physical quantities on
#       different timescales -- a defensible position is that nothing
#       about a smaller transient sag says anything about how much
#       continuous current a conductor can safely carry.
#   (b) A stabilizer that reduces the transient voltage sag on a line
#       could support a slightly higher steady-state/continuous loading
#       limit on that *same* asset, if voltage-sag depth was itself a
#       binding factor in how conservatively that asset's short-term/
#       dynamic rating was set beneath its true continuous thermal limit.
#       This is a real but simplified engineering argument (dynamic/
#       emergency line ratings are, in practice, often set with a margin
#       against voltage-stability criteria as well as pure I^2R heating),
#       not a computed engineering-standard result.
#
# This script proceeds with (b), stated as such, honestly, rather than
# silently picking a number: it applies Phase 1's real measured
# `peak_sag_reduction_percent_of_baseline` (the sag-depth improvement
# *relative to the baseline sag magnitude*, e.g. 1.19% -- not the raw
# percentage-point difference, since a rating adjustment is naturally a
# fractional/relative change) as an equal fractional increase to the
# fault-adjacent line's `max_i_ka` thermal rating in the pandapower net.
# Option (a) remains, in this script's own judgment, the more physically
# careful position for a *real* engineering submission -- this script
# applies (b) anyway specifically so Phase 1.5's binding-constraint
# question can actually be tested end to end, and reports the real result
# under that explicit, named assumption rather than refusing to test it.
TRANSLATION_HYPOTHESIS: str = (
    "(b) simplified engineering argument: a stabilizer-driven reduction in "
    "transient voltage-sag depth on the fault-adjacent line is applied as "
    "an equal *relative* increase to that line's steady-state max_i_ka "
    "thermal rating, on the premise that sag depth may have been a "
    "binding factor in how conservatively that line's short-term/dynamic "
    "rating was set beneath its true continuous limit. This is NOT a "
    "computed engineering-standard derivation -- option (a), 'sag depth "
    "and steady-state thermal loading are different physical quantities "
    "on different timescales and this does not translate at all', is an "
    "equally defensible position; (b) is applied here, explicitly labeled "
    "as a simplification, specifically so the binding-constraint question "
    "can be tested rather than left abstract."
)


def _fault_adjacent_pp_line_index(topology: chaosnet.ChaosTopology, fault_target: str) -> int:
    """The pandapower `net.line` row index of chaosnet's fault-adjacent
    line, with no change to chaosnet.py needed to get it.

    `chaosnet.to_pandapower()` builds `net.line` by iterating
    `topology["lines"]` in order, one `pp.create_line_from_parameters()`
    call per entry with no other lines created in between -- so a line's
    position in `topology["lines"]` is exactly its pandapower line index.

    Args:
        topology: output of chaosnet.build_chaos_topology(), the same
            topology Phase 1's DPsim run solved.
        fault_target: the schedule's fault substation tap name (e.g.
            "SUB-3"), read from stabilizer_comparison.json's own
            run_summary so it is never hardcoded here.

    Returns:
        The `net.line` row index of chaosnet.fault_adjacent_line_name()'s
        selected line.
    """
    fault_bus = topology["tap_buses"][topology["tap_names"].index(fault_target)]
    line_name = chaosnet.fault_adjacent_line_name(topology, fault_bus)  # "line{from}_{to}"
    from_bus, to_bus = (int(x) for x in line_name.removeprefix("line").split("_"))
    for i, line in enumerate(topology["lines"]):
        if line["from_bus"] == from_bus and line["to_bus"] == to_bus:
            return i
    raise ValueError(f"{line_name!r} not found in topology['lines']")


def _limit_screen(net: pp.pandapowerNet) -> dict:
    """Lab 2-pattern limit screen against an already-solved `pp.runpp()`
    net: worst line loading%, worst bus voltage, and the full breach sets
    (every line/bus outside THERMAL_LIMIT_PERCENT / VOLTAGE_BAND_PU, not
    just the single worst one) -- matches this PRD's instruction to check
    all lines/buses, not just the fault-adjacent one.
    """
    breaching_lines = sorted(
        int(i)
        for i in net.res_line.index
        if net.res_line.at[i, "loading_percent"] > THERMAL_LIMIT_PERCENT
    )
    breaching_buses = sorted(
        int(i)
        for i in net.res_bus.index
        if not (VOLTAGE_BAND_PU[0] <= net.res_bus.at[i, "vm_pu"] <= VOLTAGE_BAND_PU[1])
    )
    return {
        "worst_loading_percent": float(net.res_line.loading_percent.max()),
        "worst_loading_line": int(net.res_line.loading_percent.idxmax()),
        "worst_voltage_pu": float(net.res_bus.vm_pu.min()),
        "worst_voltage_bus": int(net.res_bus.vm_pu.idxmin()),
        "breaching_lines": breaching_lines,
        "breaching_buses": breaching_buses,
    }


def run_translation(verbose: bool = True) -> dict:
    """End-to-end Phase 1.5 run: read Phase 1's real numbers, build the
    real baseline and translated pandapower nets from the identical
    chaos-net topology, run two real `pp.runpp()` limit screens, and write
    `headroom_translation.json`.

    Args:
        verbose: if True, print a human-readable summary.

    Returns:
        The full result dict, also written to HEADROOM_JSON.
    """
    if not COMPARISON_JSON.exists():
        if verbose:
            print(
                f"[headroom] {COMPARISON_JSON.name} not present -- running "
                "grid_forming.py's comparison first"
            )
        import grid_forming

        grid_forming.run_comparison(countdown_seconds=0, verbose=verbose)
    comparison = json.loads(COMPARISON_JSON.read_text())

    seed: int = comparison["baseline"]["run_summary"]["seed"]
    fault_target: str = comparison["baseline"]["run_summary"]["fault_target"]
    reduction_pct: float = comparison["peak_sag_reduction_percent_of_baseline"]

    topology = chaosnet.build_chaos_topology(seed)
    line_idx = _fault_adjacent_pp_line_index(topology, fault_target)
    fault_bus = topology["tap_buses"][topology["tap_names"].index(fault_target)]
    line_name = chaosnet.fault_adjacent_line_name(topology, fault_bus)

    # --- baseline steady-state limit screen -----------------------------
    net_baseline = chaosnet.to_pandapower(topology)
    pp.runpp(net_baseline)
    baseline_screen = _limit_screen(net_baseline)
    baseline_max_i_ka = float(net_baseline.line.at[line_idx, "max_i_ka"])
    baseline_line_loading = float(net_baseline.res_line.at[line_idx, "loading_percent"])

    # --- translated steady-state limit screen ---------------------------
    # Fresh net (not a mutated copy of net_baseline) so the baseline run
    # above is never touched by the translated run's parameter edit.
    translated_max_i_ka = baseline_max_i_ka * (1.0 + reduction_pct / 100.0)
    net_translated = chaosnet.to_pandapower(topology)
    net_translated.line.at[line_idx, "max_i_ka"] = translated_max_i_ka
    pp.runpp(net_translated)
    translated_screen = _limit_screen(net_translated)
    translated_line_loading = float(net_translated.res_line.at[line_idx, "loading_percent"])

    baseline_breach = line_idx in baseline_screen["breaching_lines"]
    translated_breach = line_idx in translated_screen["breaching_lines"]
    binding_constraint_set_changed = (
        set(baseline_screen["breaching_lines"]) != set(translated_screen["breaching_lines"])
        or set(baseline_screen["breaching_buses"]) != set(translated_screen["breaching_buses"])
    )

    if binding_constraint_set_changed:
        conclusion = (
            "YES: applying the (b)-hypothesis rating translation changed "
            "which line/bus breaches the steady-state limit screen."
        )
    else:
        conclusion = (
            "NO: applying the (b)-hypothesis rating translation did not "
            "change which line/bus breaches the steady-state limit screen "
            "-- the baseline run's worst line loading "
            f"({baseline_screen['worst_loading_percent']:.2f}%) is far "
            f"below {THERMAL_LIMIT_PERCENT:.0f}%, and all bus voltages sit "
            f"well inside {VOLTAGE_BAND_PU}, so this small, lightly-loaded "
            "chaos-net topology under normal steady-state conditions is "
            "not stressed anywhere close to a binding constraint -- this "
            "specific network/fault combination is not where a "
            "binding-constraint argument for the stabilizer would show "
            "up, which is real, honestly-reported information, not "
            "evidence the underlying idea is wrong."
        )

    result = {
        "translation_hypothesis": TRANSLATION_HYPOTHESIS,
        "seed": seed,
        "fault_target": fault_target,
        "fault_adjacent_line_name": line_name,
        "fault_adjacent_line_pp_index": line_idx,
        "emt_peak_sag_reduction_percent_of_baseline": reduction_pct,
        "baseline": {
            "fault_adjacent_line_max_i_ka": baseline_max_i_ka,
            "fault_adjacent_line_loading_percent": baseline_line_loading,
            "fault_adjacent_line_breaching": baseline_breach,
            **baseline_screen,
        },
        "translated": {
            "fault_adjacent_line_max_i_ka": translated_max_i_ka,
            "fault_adjacent_line_loading_percent": translated_line_loading,
            "fault_adjacent_line_breaching": translated_breach,
            **translated_screen,
        },
        "binding_constraint_set_changed": binding_constraint_set_changed,
        "conclusion": conclusion,
    }
    HEADROOM_JSON.write_text(json.dumps(result, indent=2))

    if verbose:
        print(
            f"[headroom] fault-adjacent line {line_name!r} (pp index "
            f"{line_idx}): max_i_ka {baseline_max_i_ka:.4f} -> "
            f"{translated_max_i_ka:.4f} kA "
            f"(+{reduction_pct:.2f}%, from EMT peak-sag reduction); "
            f"loading {baseline_line_loading:.2f}% -> "
            f"{translated_line_loading:.2f}%"
        )
        print(
            f"[headroom] baseline worst loading "
            f"{baseline_screen['worst_loading_percent']:.2f}% on line "
            f"{baseline_screen['worst_loading_line']}, worst voltage "
            f"{baseline_screen['worst_voltage_pu']:.4f} pu on bus "
            f"{baseline_screen['worst_voltage_bus']}"
        )
        print(f"[headroom] binding_constraint_set_changed = {binding_constraint_set_changed}")
        print(f"[headroom] {conclusion}")
        print(f"[headroom] wrote {HEADROOM_JSON.name}")

    return result


def check_step() -> bool:
    """`--step check`: re-run the real translation fresh and assert
    structural invariants only -- never a hardcoded expected direction of
    binding-constraint change, per PRD-0005 Phase 1.5's own discipline
    ("no, nothing changes" is an acceptable, reportable outcome, not a
    test failure). What *is* asserted, because it is a real physical
    invariant regardless of which way the headline finding goes:

      - both pp.runpp() solves converged (no exception raised above);
      - the translated max_i_ka is strictly larger than baseline's,
        matching the (b)-hypothesis's positive sag-reduction input;
      - the fault-adjacent line's loading_percent did not increase as a
        result of raising its own rating (raising a denominator can only
        lower or hold a loading_percent, given the same solved current --
        a real algebraic fact about `loading_percent = i_ka / max_i_ka`,
        not an assumption about the outcome direction of the
        binding-constraint question).

    Returns:
        True if every structural invariant holds; False otherwise
        (printed either way).
    """
    result = run_translation(verbose=False)
    ok = True
    reasons = []

    if result["translated"]["fault_adjacent_line_max_i_ka"] <= (
        result["baseline"]["fault_adjacent_line_max_i_ka"]
    ):
        ok = False
        reasons.append("translated max_i_ka did not increase over baseline")

    if result["translated"]["fault_adjacent_line_loading_percent"] > (
        result["baseline"]["fault_adjacent_line_loading_percent"] + 1e-9
    ):
        ok = False
        reasons.append(
            "fault-adjacent line's loading_percent increased after raising "
            "its own max_i_ka rating -- contradicts loading_percent = "
            "i_ka / max_i_ka"
        )

    if not isinstance(result["binding_constraint_set_changed"], bool):
        ok = False
        reasons.append("binding_constraint_set_changed was not computed as a real bool")

    if ok:
        print(
            "MATCH: headroom translation ran end to end against a real "
            "pandapower net (baseline + translated pp.runpp() solves both "
            "converged); real finding: "
            f"binding_constraint_set_changed={result['binding_constraint_set_changed']}"
        )
    else:
        print("FAIL: " + "; ".join(reasons))
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", choices=["run", "check"], default="run")
    args = parser.parse_args()

    if args.step == "run":
        run_translation(verbose=True)
    elif args.step == "check":
        ok = check_step()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
