#!/usr/bin/env python3
"""Lab 1 (Simple) -- Load-Flow Parameter Fit.

See README.md in this directory for the full walkthrough. Three steps:

    uv run labs/01-simple-loadflow-fit/run.py --step load
    uv run labs/01-simple-loadflow-fit/run.py --step fit
    uv run labs/01-simple-loadflow-fit/run.py --step check

Sandbox note: docs/VISION.md's Lab 1 has a local Phi-4-mini LLM (served by
llama.cpp in a podman pod) choosing each trial load-scaling value over MCP.
This sandbox has no podman and no budget to download/serve a GGUF model, so
the "propose next trial" decision is `gridfit.bisection_fit`'s deterministic
bisection policy instead -- named explicitly here and in gridfit.py, not
hidden. The physics on every iteration is a real `pandapower.runpp()` call
either way; that split (LLM/policy proposes, pandapower disposes) is the
actual point of the lab and is unaffected by the swap.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandapower as pp
from _shared.gridfit import bisection_fit, load_case, scale_loads


class FitStepResult(TypedDict):
    """JSON-serializable result of `fit_step`, also the shape of
    expected_results.json."""

    target_bus: int
    base_case_voltage_pu: float
    field_scada_voltage_pu: float
    fitted_scale: float
    fitted_voltage_pu: float
    residual_pu: float
    iterations: int
    converged: bool
    tolerance_pu: float

LAB_DIR = Path(__file__).resolve().parent
DATA_FILE = LAB_DIR.parent.parent / "data" / "snemSA.m"
EXPECTED_FILE = LAB_DIR / "expected_results.json"

# Bus 2008 is a real bus ID from snemSA.m (11 kV, load 50.0 MW). Chosen (by
# a one-off exploration script, not shipped) as the highest-load bus whose
# base-case voltage sits in [0.9, 1.05] pu -- i.e. a bus whose voltage a
# modeller would plausibly want to calibrate, not one already at 1.0 pu by
# construction. docs/VISION.md's original spec illustrates the mechanic with
# a hypothetical "bus 14"; snemSA.m's real bus IDs are non-sequential
# (986, 1633, 1634, ... not 1..N), so there is no bus literally named 14 --
# 2008 is the real stand-in, named here rather than silently substituted.
TARGET_BUS: int = 2008

# Synthetic "field SCADA reading" for bus 2008. Not a real measurement --
# this lab has no live SCADA feed -- it is a fixed constant chosen so the
# required fit lies strictly inside the +/-10% search bound (SCALE_LO/HI
# below) rather than at its edge, and away from a scale that would make the
# very first bisection probe accidentally exact. The base-case (unscaled)
# voltage at bus 2008 is ~0.9348 pu; 0.9422 is achievable at scale ~0.925x.
FIELD_SCADA_VOLTAGE_PU: float = 0.9422

# "...within 0.002 pu" -- docs/VISION.md section 7, Lab 1 spec, verbatim.
FIT_TOLERANCE_PU: float = 0.002

# "...within +/-10%..." -- docs/VISION.md section 7, Lab 1 spec, verbatim:
# the load-scaling parameter search is bounded to [0.90x, 1.10x] of the
# base-case load.
SCALE_LO: float = 0.90
SCALE_HI: float = 1.10


def load_step(verbose: bool = True) -> tuple[pp.pandapowerNet, float]:
    """Run the "load" step: parse snemSA.m and solve the base-case AC power flow.

    Args:
        verbose: if True, print the same progress lines a presenter would
            narrate live (see README's step-by-step walkthrough).

    Returns:
        The solved pandapower net and the base-case voltage (pu) at
        TARGET_BUS.
    """
    if not DATA_FILE.exists():
        print(
            f"[FAIL] {DATA_FILE} not found -- run "
            f"'uv run scripts/fetch_csiro_nem_data.py' first",
            file=sys.stderr,
        )
        sys.exit(1)

    net, warnings = load_case(DATA_FILE)
    pp.runpp(net)
    base_voltage = float(net.res_bus.at[TARGET_BUS, "vm_pu"])

    if verbose:
        print(
            f"Loaded snemSA.m via powerio: {len(net.bus)} buses, "
            f"{len(net.gen)} generators"
        )
        print(f"Base-case power flow converged: bus {TARGET_BUS} voltage = "
              f"{base_voltage:.3f} pu")
    return net, base_voltage


# Decimal places for values written to JSON (fixture + stdout). This is a
# display/serialization choice only, unrelated to FIT_TOLERANCE_PU (the
# physics convergence tolerance) -- 6 places is comfortably more precision
# than pandapower's Newton-Raphson default tolerance (1e-8 MVA mismatch,
# which maps to ~1e-6 pu voltage precision in practice), so rounding here
# never masks a real difference between runs.
JSON_ROUND_DECIMALS: int = 6

# Float-equality slack for expected_results.json comparison in check_step.
# Deliberately looser than JSON_ROUND_DECIMALS' 1e-6 because pandapower's
# Newton-Raphson iteration count/path can differ by a unit in the last
# place across numpy/BLAS versions without the physics actually changing;
# 1e-4 pu is two orders of magnitude tighter than FIT_TOLERANCE_PU (0.002),
# so it still catches a genuine regression while tolerating solver noise.
FIXTURE_FLOAT_ATOL: float = 1e-4


def fit_step(verbose: bool = True) -> FitStepResult:
    """Run the "fit" step: bisect the load-scaling parameter against the
    synthetic field-SCADA target at TARGET_BUS.

    Args:
        verbose: if True, print one line per bisection iteration plus the
            final converged/failed summary line.

    Returns:
        A FitStepResult, JSON-serializable and diffable against
        expected_results.json (see check_step).
    """
    net, base_voltage = load_step(verbose=verbose)

    def evaluate(scale: float) -> float:
        """The physics ground truth for one trial `scale`: a real pandapower
        AC power-flow solve, never an LLM guess -- see module docstring."""
        trial_net = scale_loads(net, scale)
        pp.runpp(trial_net)
        return float(trial_net.res_bus.at[TARGET_BUS, "vm_pu"])

    result = bisection_fit(
        evaluate,
        target=FIELD_SCADA_VOLTAGE_PU,
        lo=SCALE_LO,
        hi=SCALE_HI,
        tol=FIT_TOLERANCE_PU,
    )

    if verbose:
        for it in result.iterations:
            print(
                f"iter {it.iteration}: trial={it.trial:.4f}x -> "
                f"{it.observed:.3f} pu (residual {it.residual:+.4f})"
            )
        status = "PASS" if result.converged else "FAIL (did not converge)"
        print(
            f"converged: trial={result.trial:.4f}x, bus {TARGET_BUS} = "
            f"{result.observed:.3f} pu, residual {result.residual:+.4f} "
            f"({status}, tol {FIT_TOLERANCE_PU})"
        )

    return {
        "target_bus": TARGET_BUS,
        "base_case_voltage_pu": round(base_voltage, JSON_ROUND_DECIMALS),
        "field_scada_voltage_pu": FIELD_SCADA_VOLTAGE_PU,
        "fitted_scale": round(result.trial, JSON_ROUND_DECIMALS),
        "fitted_voltage_pu": round(result.observed, JSON_ROUND_DECIMALS),
        "residual_pu": round(result.residual, JSON_ROUND_DECIMALS),
        "iterations": len(result.iterations),
        "converged": result.converged,
        "tolerance_pu": FIT_TOLERANCE_PU,
    }


def check_step() -> bool:
    """Run the "check" step: re-run the fit and diff it against
    expected_results.json.

    Returns:
        True if every compared field matches within FIXTURE_FLOAT_ATOL
        (floats) or exactly (non-floats); False otherwise. This is the
        self-checking gate named in docs/DEFINITION_OF_DONE.md ("its
        printed result matches expected_results.json within the documented
        tolerance on every run").
    """
    actual = fit_step(verbose=False)

    if not EXPECTED_FILE.exists():
        print(f"[FAIL] no fixture at {EXPECTED_FILE}", file=sys.stderr)
        return False

    expected = json.loads(EXPECTED_FILE.read_text())

    mismatches = []
    for key in ("fitted_scale", "fitted_voltage_pu", "residual_pu", "iterations"):
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

    print(
        f"MATCH: fitted_scale={actual['fitted_scale']} "
        f"residual_pu={actual['residual_pu']} vs expected_results.json"
    )
    return True


def main() -> None:
    """CLI entry point: dispatches to load_step / fit_step / check_step
    per --step, exiting non-zero on --step check failure (so this doubles
    as a CI/pytest-friendly gate, not just a demo script)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--step", choices=["load", "fit", "check"], default="check"
    )
    args = parser.parse_args()

    if args.step == "load":
        load_step()
    elif args.step == "fit":
        fit_step()
    elif args.step == "check":
        ok = check_step()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
