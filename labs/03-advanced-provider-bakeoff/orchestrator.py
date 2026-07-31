#!/usr/bin/env python3
"""Lab 3 (Advanced) -- Multi-Provider Bake-off, Podman-Scaled.

See README.md in this directory for the full walkthrough. Two steps:

    uv run labs/03-advanced-provider-bakeoff/orchestrator.py --step sweep
    uv run labs/03-advanced-provider-bakeoff/orchestrator.py --step report
    uv run labs/03-advanced-provider-bakeoff/orchestrator.py --step check

Sandbox note (the most significant deviation from docs/VISION.md of any lab
in this repo -- read this before trusting the "provider" column):
docs/VISION.md's Lab 3 swaps three *live* local LLMs (Phi-4-mini-instruct,
Gemma-4, Llama-3.2-3B) through a single llama.cpp pod via
`podman kube play --replace`, orchestrated with Agent Framework's
Magentic/group-chat pattern, plus a PowerFM OpenPowerBench checkpoint
pulled from Hugging Face Hub. This sandbox has no podman, no GPU, and no
budget to download and serve three GGUF models or a PowerFM checkpoint. So:

  - PROVIDER_A/B/C below are three deterministic search *policies*
    (see gridfit.bisection_fit, _regula_falsi_fit, _perturbed_bisection_fit)
    standing in for the three LLMs' "propose the next trial value" role --
    named "local-policy-A/B/C", never given a real model's name, so the
    scorecard can never be mistaken for a real model comparison.
  - The POWERFM_BASELINE row is a seasonal-persistence forecast against a
    synthetic (not historical-AEMO) regional demand trace, standing in for
    a real OpenPowerBench checkpoint -- see powerfm_baseline_row().
  - There is no Magentic/group-chat orchestration (no live chat model to
    orchestrate); the "orchestration" that is real here is running the
    task-family x provider matrix and collecting results into one
    scorecard, which is the part of Lab 3 that is architecture, not model
    weights.

Every function below that stands in for something is named in its own
docstring, per this repo's "documented, not silently swapped" rule
(docs/DEFINITION_OF_DONE.md).
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandapower as pp
from _shared.gridfit import (
    DEFAULT_MAX_ITER,
    FitIteration,
    FitResult,
    bisection_fit,
    load_case,
    scale_loads,
)

LAB_DIR = Path(__file__).resolve().parent
DATA_FILE = LAB_DIR.parent.parent / "data" / "snem1803.m"
RESULTS_DIR = LAB_DIR.parent.parent / "benchmarks" / "power-agent-bench-lite" / "results"
SCORECARD_FILE = RESULTS_DIR / "scorecard.json"
EXPECTED_FILE = LAB_DIR / "expected_scorecard.json"

# ---------------------------------------------------------------------------
# Task family targets. Each was picked (by a one-off exploration script, not
# shipped) as a real, computed quantity from snem1803.m's own base-case
# solve -- never an invented number -- documented per-family below.
# ---------------------------------------------------------------------------

LOAD_SCALE_TARGET_BUS: int = 526  # 526 has base-case voltage 0.9642 pu with
# real headroom in both directions across the +/-10% scan (0.9570-0.9642 pu),
# unlike CANDIDATE_BUS-adjacent buses which are already near a limit.
LOAD_SCALE_TARGET_PU: float = 0.9585  # inside the observed [0.9570, 0.9642]
# range at scale in [0.9, 1.0]; requires ~3 bisection iterations, same
# order of magnitude as Lab 1's fit.
LOAD_SCALE_TOLERANCE_PU: float = 0.002  # same tolerance as Lab 1, section 7.

LINE_RATING_TARGET_LINE: int = 1070  # snem1803.m's most heavily loaded line
# in the base case (97.84% of its max_i_ka rating) -- a genuine "close to
# its thermal limit" line, not a hand-picked easy case.
LINE_RATING_TARGET_PERCENT: float = 100.0  # "100% of nameplate rating" is
# the standard definition of a thermal trip point; this is not an invented
# number, it is the universal engineering convention.
LINE_RATING_TOLERANCE_PERCENT: float = 0.5  # +/-0.5 percentage points --
# tighter than THERMAL_LIMIT_PERCENT's pass/fail granularity in Lab 2,
# appropriate for a rating-fit exercise rather than a pass/fail screen.

DROOP_TARGET_TRAFO: int = 99  # the step-up transformer for the generator at
# bus 18 (snem1803.m's 2nd-largest real-power generator by base-case
# dispatch); its loading responds measurably to that generator's dispatch
# (32.5%-40.1% across +/-10% dispatch), unlike bus-18's own voltage, which a
# PV/voltage-controlled bus holds constant regardless of P -- see README's
# "why transformer loading, not voltage" note.
DROOP_TARGET_GEN_BUS: int = 18
DROOP_TARGET_PERCENT: float = 38.5  # inside the observed [32.5, 40.1] range.
DROOP_TOLERANCE_PERCENT: float = 0.5

SCALE_LO, SCALE_HI = 0.90, 1.10  # +/-10%, same bound as every other lab.

# ---------------------------------------------------------------------------
# Synthetic regional-demand trace for the PowerFM baseline row (see
# powerfm_baseline_row()).
# ---------------------------------------------------------------------------

# A commonly-illustrated generic NEM daily demand shape (24 hourly
# multipliers, normalised so the evening peak = 1.0): overnight trough
# ~65% of peak, morning ramp, a small midday dip, evening peak. This is a
# textbook-shape illustration, not measured AEMO data -- real historical
# half-hourly regional demand traces are Lab 4's job, pulled via NEMOSIS.
DAILY_SHAPE_MULTIPLIERS: tuple[float, ...] = (
    0.68, 0.65, 0.64, 0.65, 0.68, 0.74,  # 00:00-05:00 overnight trough
    0.82, 0.90, 0.94, 0.93, 0.90, 0.88,  # 06:00-11:00 morning ramp
    0.86, 0.85, 0.87, 0.89, 0.92, 0.97,  # 12:00-17:00 afternoon
    1.00, 0.98, 0.93, 0.86, 0.78, 0.71,  # 18:00-23:00 evening peak + decay
)
# Day-on-day growth applied to the held-out day, representative of ordinary
# demand drift (not a stress event -- Lab 3's stretch-goal chaos sweep in
# docs/VISION.md section 7 is where deliberate stress is added).
HELD_OUT_DAY_GROWTH: float = 0.015
# Seed for the small per-hour noise added to the held-out day, so the
# PowerFM baseline's score is reproducible run-to-run (required for
# expected_scorecard.json to be diffable) while still being non-trivial
# (a pure day2==day1*growth trace would make persistence forecasting
# trivially perfect, which would prove nothing).
POWERFM_NOISE_SEED: int = 20260731  # today's date at authorship time, as a
# memorable, arbitrary-but-fixed seed -- any fixed seed works equally well.
POWERFM_NOISE_STDDEV_MW: float = 15.0
POWERFM_MAPE_PASS_THRESHOLD_PERCENT: float = 5.0  # a commonly-used
# short-horizon load-forecast accuracy bar (MAPE <= 5%) for the "pass" cut.

# Float-equality slack for expected_scorecard.json comparison. Wall-clock is
# excluded from the fixture entirely (see check_step) since it is
# inherently non-deterministic across machines/runs.
FIXTURE_FLOAT_ATOL: float = 1e-3


class TaskFamilyResult(TypedDict):
    """One provider's scored attempt at one task family."""

    provider: str
    task_family: str
    passed: bool
    error_margin: Optional[float]
    iterations: Optional[int]
    wall_clock_s: float
    tokens: Optional[int]
    detail: str


@dataclass
class TaskFamily:
    """A parameter-fit task family: a scalar search bounded to [SCALE_LO,
    SCALE_HI], scored by whether the fitted observation lands within
    `tolerance` of `target`. Mirrors Lab 1's mechanic, generalised so the
    provider matrix below can run the same harness against three different
    physical quantities."""

    name: str
    evaluate: Callable[[float], float]
    target: float
    tolerance: float
    describe_unit: str


def _make_task_families(net: pp.pandapowerNet) -> list[TaskFamily]:
    """Build the 3 task families against an already-solved base `net`.

    Each `evaluate` closure is a real `pandapower.runpp()` call on a
    modified copy of `net` -- physics ground truth, never fabricated,
    exactly as in Lab 1 (see gridfit.py module docstring).
    """

    def load_scale_evaluate(scale: float) -> float:
        trial_net = scale_loads(net, scale)
        pp.runpp(trial_net, init="flat")
        return float(trial_net.res_bus.at[LOAD_SCALE_TARGET_BUS, "vm_pu"])

    def line_rating_evaluate(scale: float) -> float:
        # Note: max_i_ka is a reporting/rating parameter, not an input to
        # the AC power-flow equations, so this task's physical solve is
        # identical for every `scale` -- only the post-solve loading_percent
        # ratio changes. Still run through a full pp.runpp() per iteration
        # for harness uniformity with the other two (genuinely
        # solve-sensitive) task families; documented here so nobody mistakes
        # this task for one where the search changes the physics.
        trial_net = copy.deepcopy(net)
        trial_net.line.at[LINE_RATING_TARGET_LINE, "max_i_ka"] *= scale
        pp.runpp(trial_net, init="flat")
        return float(
            trial_net.res_line.at[LINE_RATING_TARGET_LINE, "loading_percent"]
        )

    def droop_evaluate(scale: float) -> float:
        trial_net = copy.deepcopy(net)
        gen_idx = trial_net.gen[trial_net.gen.bus == DROOP_TARGET_GEN_BUS].index[0]
        trial_net.gen.at[gen_idx, "p_mw"] *= scale
        pp.runpp(trial_net, init="flat")
        return float(trial_net.res_trafo.at[DROOP_TARGET_TRAFO, "loading_percent"])

    return [
        TaskFamily(
            "load-scale-fit", load_scale_evaluate, LOAD_SCALE_TARGET_PU,
            LOAD_SCALE_TOLERANCE_PU, "pu",
        ),
        TaskFamily(
            "line-rating-fit", line_rating_evaluate, LINE_RATING_TARGET_PERCENT,
            LINE_RATING_TOLERANCE_PERCENT, "%",
        ),
        TaskFamily(
            "gen-droop-fit", droop_evaluate, DROOP_TARGET_PERCENT,
            DROOP_TOLERANCE_PERCENT, "%",
        ),
    ]


# ---------------------------------------------------------------------------
# Provider stand-ins. Three distinct deterministic search policies so the
# scorecard shows genuine (seeded, reproducible) variation across "providers"
# rather than three identical rows -- see module docstring.
# ---------------------------------------------------------------------------


def _regula_falsi_fit(
    evaluate: Callable[[float], float],
    target: float,
    lo: float,
    hi: float,
    tol: float,
    max_iter: int = DEFAULT_MAX_ITER,
) -> FitResult:
    """False-position (regula falsi) search: like bisection but the next
    trial is the linear-interpolation root of the secant line through the
    bracket endpoints, not the midpoint. Stands in for "local-policy-B"
    (see module docstring) -- typically fewer iterations than bisection on
    smooth, near-linear responses, which is the real, benign reason two
    genuinely different local models can converge at different speeds on
    the same task.
    """
    iterations: list[FitIteration] = []
    a, b = lo, hi
    fa = evaluate(a) - target
    fb = evaluate(b) - target
    if (fa > 0) == (fb > 0):
        raise ValueError(
            f"_regula_falsi_fit: target {target} not bracketed by [{lo}, {hi}]"
        )
    for i in range(1, max_iter + 1):
        trial = b - fb * (b - a) / (fb - fa)
        observed = evaluate(trial)
        residual = observed - target
        iterations.append(FitIteration(i, trial, observed, residual))
        if abs(residual) <= tol:
            return FitResult(True, trial, observed, residual, iterations)
        if (residual > 0) == (fa > 0):
            a, fa = trial, residual
        else:
            b, fb = trial, residual
    last = iterations[-1]
    return FitResult(False, last.trial, last.observed, last.residual, iterations)


def _perturbed_bisection_fit(
    evaluate: Callable[[float], float],
    target: float,
    lo: float,
    hi: float,
    tol: float,
    max_iter: int = DEFAULT_MAX_ITER,
    noise_scale: float = 0.01,
    seed: int = 0,
) -> FitResult:
    """Bisection with a small seeded random perturbation on each proposed
    trial value. Stands in for "local-policy-C" (see module docstring) --
    a deliberately noisier proposer, representing the real, benign fact
    that a smaller/weaker local model sometimes proposes a slightly
    off-target next value and needs an extra correcting iteration. Seeded
    (`seed`) so the noise -- and therefore the whole scorecard row -- is
    exactly reproducible run to run, per this repo's "fixed seed" rule
    (docs/DEFINITION_OF_DONE.md).
    """
    rng = random.Random(seed)
    iterations: list[FitIteration] = []
    a, b = lo, hi
    fa = evaluate(a) - target
    fb = evaluate(b) - target
    if (fa > 0) == (fb > 0):
        raise ValueError(
            f"_perturbed_bisection_fit: target {target} not bracketed by [{lo}, {hi}]"
        )
    for i in range(1, max_iter + 1):
        mid = (a + b) / 2.0
        jitter = rng.uniform(-noise_scale, noise_scale) * (b - a)
        trial = min(max(mid + jitter, min(a, b)), max(a, b))
        observed = evaluate(trial)
        residual = observed - target
        iterations.append(FitIteration(i, trial, observed, residual))
        if abs(residual) <= tol:
            return FitResult(True, trial, observed, residual, iterations)
        if (residual > 0) == (fa > 0):
            a, fa = trial, residual
        else:
            b, fb = trial, residual
    last = iterations[-1]
    return FitResult(False, last.trial, last.observed, last.residual, iterations)


# Each entry: display name -> the search function it uses. Real provider
# names (Phi-4-mini-instruct / Gemma-4 / Llama-3.2-3B) are never used as
# labels here -- see module docstring for why.
PROVIDERS: dict[str, Callable[..., FitResult]] = {
    "local-policy-A": bisection_fit,
    "local-policy-B": _regula_falsi_fit,
    "local-policy-C": _perturbed_bisection_fit,
}


def run_sweep(verbose: bool = True) -> list[TaskFamilyResult]:
    """Run every (provider, task family) pair and collect results.

    Args:
        verbose: if True, print one row as each pair completes.

    Returns:
        3 providers x 3 task families = 9 TaskFamilyResult rows (tokens is
        always None: no live model server ran, see module docstring).
    """
    if not DATA_FILE.exists():
        print(
            f"[FAIL] {DATA_FILE} not found -- run "
            f"'uv run scripts/fetch_csiro_nem_data.py' first",
            file=sys.stderr,
        )
        sys.exit(1)
    net, _ = load_case(DATA_FILE)
    pp.runpp(net, init="flat")
    families = _make_task_families(net)

    rows: list[TaskFamilyResult] = []
    for provider_name, search_fn in PROVIDERS.items():
        for family in families:
            start = time.perf_counter()
            result = search_fn(
                family.evaluate, family.target, SCALE_LO, SCALE_HI, family.tolerance
            )
            elapsed = time.perf_counter() - start
            passed = result.converged and abs(result.residual) <= family.tolerance
            row: TaskFamilyResult = {
                "provider": provider_name,
                "task_family": family.name,
                "passed": passed,
                "error_margin": round(abs(result.residual), 6),
                "iterations": len(result.iterations),
                "wall_clock_s": round(elapsed, 4),
                "tokens": None,
                "detail": (
                    f"fitted={result.trial:.4f}x -> {result.observed:.4f}"
                    f"{family.describe_unit} (target {family.target}"
                    f"{family.describe_unit})"
                ),
            }
            rows.append(row)
            if verbose:
                mark = "PASS" if passed else "FAIL"
                print(
                    f"{provider_name:<14} | {family.name:<16} | {mark} | "
                    f"err={row['error_margin']:.4f} | {row['wall_clock_s']:.2f}s"
                )
    return rows


def powerfm_baseline_row(verbose: bool = True) -> TaskFamilyResult:
    """The non-agentic baseline row: a seasonal-persistence forecast scored
    on a held-out day of a synthetic regional demand trace.

    Sandbox stand-in for docs/VISION.md's PowerFM OpenPowerBench
    load-forecasting checkpoint (see module docstring) -- no LLM, no tool
    calls, no orchestration, matching the real PowerFM row's "a single
    forward pass" character even though the forward pass here is a naive
    persistence rule rather than a trained model.

    Returns:
        A TaskFamilyResult with task_family="load-forecast-24h",
        iterations=None and tokens=None (a single forward pass has neither).
    """
    if not DATA_FILE.exists():
        print(
            f"[FAIL] {DATA_FILE} not found -- run "
            f"'uv run scripts/fetch_csiro_nem_data.py' first",
            file=sys.stderr,
        )
        sys.exit(1)
    net, _ = load_case(DATA_FILE)
    total_load_mw = float(net.load.p_mw.sum())

    rng = random.Random(POWERFM_NOISE_SEED)
    day1 = [total_load_mw * m for m in DAILY_SHAPE_MULTIPLIERS]
    day2_actual = [
        total_load_mw * m * (1.0 + HELD_OUT_DAY_GROWTH)
        + rng.gauss(0.0, POWERFM_NOISE_STDDEV_MW)
        for m in DAILY_SHAPE_MULTIPLIERS
    ]
    # Seasonal-persistence prediction: forecast hour h of the held-out day
    # as hour h of the training day (the standard, simplest forecasting
    # baseline; a real PowerFM checkpoint would be scored the same way but
    # would be expected to beat naive persistence).
    day2_predicted = day1

    start = time.perf_counter()
    abs_pct_errors = [
        abs(actual - pred) / actual * 100.0
        for actual, pred in zip(day2_actual, day2_predicted)
    ]
    mape = sum(abs_pct_errors) / len(abs_pct_errors)
    elapsed = time.perf_counter() - start

    passed = mape <= POWERFM_MAPE_PASS_THRESHOLD_PERCENT
    row: TaskFamilyResult = {
        "provider": "PowerFM-OpenPowerBench-stub",
        "task_family": "load-forecast-24h",
        "passed": passed,
        "error_margin": round(mape, 4),
        "iterations": None,
        "wall_clock_s": round(elapsed, 6),
        "tokens": None,
        "detail": (
            f"MAPE={mape:.2f}% over 24 held-out hours "
            f"(pass <= {POWERFM_MAPE_PASS_THRESHOLD_PERCENT}%)"
        ),
    }
    if verbose:
        mark = "PASS" if passed else "FAIL"
        print(
            f"{row['provider']:<28} | {row['task_family']:<18} | {mark} | "
            f"MAPE={row['error_margin']:.2f}% | n/a tokens/latency-per-call "
            f"(single forward pass)"
        )
    return row


def sweep_step(verbose: bool = True) -> list[TaskFamilyResult]:
    """Run the full matrix: 3 providers x 3 task families, plus the PowerFM
    baseline row, appended last (per docs/VISION.md's presenter walkthrough:
    "ending with the PowerFM ... baseline row")."""
    rows = run_sweep(verbose=verbose)
    rows.append(powerfm_baseline_row(verbose=verbose))
    return rows


def report_step(rows: Optional[list[TaskFamilyResult]] = None) -> list[TaskFamilyResult]:
    """Write the scorecard to benchmarks/power-agent-bench-lite/results/ and
    print it as a table.

    Args:
        rows: scorecard rows; runs sweep_step() if not supplied.

    Returns:
        The rows written (same as input if supplied).
    """
    if rows is None:
        rows = sweep_step(verbose=False)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    SCORECARD_FILE.write_text(json.dumps(rows, indent=2))

    header = f"{'provider':<28} {'task_family':<18} {'pass':>5} {'err_margin':>11} {'wall_s':>8}"
    print(header)
    print("-" * len(header))
    for row in rows:
        mark = "PASS" if row["passed"] else "FAIL"
        print(
            f"{row['provider']:<28} {row['task_family']:<18} {mark:>5} "
            f"{row['error_margin']:>11.4f} {row['wall_clock_s']:>8.3f}"
        )
    n_pass = sum(1 for r in rows if r["passed"])
    print(f"\n{n_pass}/{len(rows)} pass. Scorecard written to {SCORECARD_FILE}")
    return rows


def check_step() -> bool:
    """Self-check gate: re-run the full sweep and diff pass/fail + error
    margins against expected_scorecard.json. Wall-clock is intentionally
    excluded from the comparison (machine-dependent, not a correctness
    signal).

    Returns:
        True if every row's provider/task_family/passed/error_margin
        matches the fixture within FIXTURE_FLOAT_ATOL; False otherwise.
    """
    actual = sweep_step(verbose=False)
    if not EXPECTED_FILE.exists():
        print(f"[FAIL] no fixture at {EXPECTED_FILE}", file=sys.stderr)
        return False
    expected = json.loads(EXPECTED_FILE.read_text())

    ok = True
    if len(actual) != len(expected):
        print(f"FAIL: expected {len(expected)} rows, got {len(actual)}")
        ok = False
    for exp, act in zip(expected, actual):
        same_key = (exp["provider"], exp["task_family"]) == (act["provider"], act["task_family"])
        same_pass = exp["passed"] == act["passed"]
        same_margin = abs(exp["error_margin"] - act["error_margin"]) <= FIXTURE_FLOAT_ATOL
        if not (same_key and same_pass and same_margin):
            print(f"FAIL: mismatch: expected={exp} actual={act}")
            ok = False
    if ok:
        print(f"MATCH: all {len(actual)} scorecard rows match expected_scorecard.json")
    return ok


def main() -> None:
    """CLI entry point: dispatches to sweep/report/check per --step."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--step", choices=["sweep", "report", "check"], default="check"
    )
    args = parser.parse_args()

    if args.step == "sweep":
        sweep_step()
    elif args.step == "report":
        report_step()
    elif args.step == "check":
        ok = check_step()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
