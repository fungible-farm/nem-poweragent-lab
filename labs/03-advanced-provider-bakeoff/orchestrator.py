#!/usr/bin/env python3
"""Lab 3 (Advanced) -- Multi-Provider Bake-off, Podman-Scaled.

See README.md in this directory for the full walkthrough. Four steps:

    uv run labs/03-advanced-provider-bakeoff/orchestrator.py --step sweep
    uv run labs/03-advanced-provider-bakeoff/orchestrator.py --step report
    uv run labs/03-advanced-provider-bakeoff/orchestrator.py --step check
    uv run labs/03-advanced-provider-bakeoff/orchestrator.py --step collect

`--step sweep` scores every provider in one process by default (the serial
reference path `check`/`report` also use). Setting the `PROVIDER_FILTER` env
var (a provider name, or an integer index into PROVIDERS -- see
_select_providers()) restricts a single `--step sweep` invocation to one
provider and persists its 3 rows to a distinct partial-scorecard file; this
is what kube/benchmark-runner-job.yaml's 3 indexed Job completions do so the
matrix is genuinely partitioned across concurrent pods instead of each pod
redundantly scoring all 3 providers. `--step collect` merges those partial
files (plus a freshly-computed PowerFM baseline row) back into one scorecard
in the same shape `--step report` writes for the serial path -- see
collect_step().

Sandbox note (the most significant deviation from docs/VISION.md of any lab
in this repo -- read this before trusting the "provider" column):
docs/VISION.md's Lab 3 swaps three *live* local LLMs (Phi-4-mini-instruct,
Gemma-4, Llama-3.2-3B) through a single llama.cpp pod via
`podman kube play --replace`, orchestrated with Agent Framework's
Magentic/group-chat pattern, plus a PowerFM OpenPowerBench checkpoint
pulled from Hugging Face Hub. A real Phi-4-mini-instruct pod now exists and
runs in this sandbox (kube/llamacpp-phi-pod.yaml, podman-verified -- see
kube/README.md, and `podman kube play --replace` genuinely works, confirmed
independently swapping that pod without touching a concurrently-running
powermcp pod), but this script was not rewired to call it, and no GPU or
budget exists to also download/serve Gemma-4, Llama-3.2-3B, or a real
PowerFM checkpoint. So:

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
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandapower as pp  # noqa: E402
from _shared.gridfit import (  # noqa: E402
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
SCORECARD_CHART_FILE = RESULTS_DIR / "scorecard_chart.png"  # committed alongside
# SCORECARD_FILE, per docs/backlog/0003-lab3-scorecard-visualization.md --
# "Save as a committed PNG (matching Lab 5's sample_transient_plot.png
# precedent)". Lives in RESULTS_DIR (not LAB_DIR) because it is a rendering
# of SCORECARD_FILE, which itself already lives there -- keeping the chart
# next to the data it renders, same locality principle as Lab 4's CHART_FILE
# sitting next to EXPECTED_FILE in LAB_DIR.

# Bar colors for _plot_scorecard()'s 3-series grouped bar chart (one series
# per local-policy provider; the PowerFM baseline row is excluded from this
# chart, see _plot_scorecard()'s docstring). Categorical slots 1-3 (blue,
# orange, aqua) from the dataviz skill's default palette
# (references/palette.md), validated here as a 3-way *all-pairs* set (not
# just adjacent-pairs, since a 3-bar group means every pair of bars is
# visually adjacent to the reader) via the skill's own validator:
# `node scripts/validate_palette.js "#2a78d6,#eb6834,#1baf7a" --mode light
# --pairs all` and `node scripts/validate_palette.js
# "#3987e5,#d95926,#199e70" --mode dark --pairs all` (run directly, not
# estimated) both report ALL CHECKS PASS -- worst all-pairs CVD separation
# 9.2 (light, deutan) / 9.4 (dark, deutan), worst all-pairs normal-vision
# separation 24.0 (light) / 20.9 (dark), contrast >=3:1 in dark mode. Light
# mode WARNs on slot 3 (aqua, #1baf7a) vs the light chart surface (2.74:1,
# below the 3:1 floor) -- the skill's documented "relief rule" for that WARN
# is satisfied here because every bar is already value-labeled via
# ax.bar_label() (see below), so the WARN does not block shipping. This PNG
# is rendered once, on matplotlib's default (light) surface -- like Lab 4/5's
# charts, there is no dark-mode PNG variant; the dark-mode hexes are
# validated only so this palette stays swappable without re-deriving colors.
SCORECARD_CHART_PROVIDER_COLORS: dict[str, str] = {
    "local-policy-A": "#2a78d6",
    "local-policy-B": "#eb6834",
    "local-policy-C": "#1baf7a",
}

# In-image footnote ink (the PowerFM-exclusion note, see _plot_scorecard()).
# Same "Muted (axis/labels)" palette.md role, same hex, as Lab 5's
# TOPOLOGY_EDGE_COLOR -- already-validated muted ink, reused rather than
# re-deriving a new one for a single small caption.
SCORECARD_CHART_FOOTNOTE_COLOR: str = "#898781"

# Matches Lab 4/5's matplotlib convention (Agg backend, fig/ax, tight_layout,
# dpi=130, plt.close(fig)). Figure sized wider than Lab 4's 2-series (7, 5)
# to leave room for 3 task-family groups x 3 bars plus a 3-entry legend.
SCORECARD_CHART_FIGSIZE: tuple[float, float] = (9.0, 5.0)
SCORECARD_CHART_DPI: int = 130

# Total x-width allotted to one task_family's group of bars (matplotlib's
# own documented grouped-bar-with-N-series idiom: divide the group width by
# the series count, then center each series' slot on an offset from the
# group's x position) -- 0.8 leaves a 0.2 visual gap before the next group,
# same ratio Lab 4's RECONCILIATION_CHART_BAR_WIDTH (0.35 out of a 1.0-wide
# group slot) uses. SCORECARD_CHART_BAR_FILL_FRACTION shrinks each bar's
# drawn width below its full slot so a visible surface gap survives between
# adjacent bars within a group, same rationale as Lab 4's
# RECONCILIATION_CHART_BAR_FILL_FRACTION.
SCORECARD_CHART_GROUP_WIDTH: float = 0.8
SCORECARD_CHART_BAR_FILL_FRACTION: float = 0.85

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

# Env var read by _select_providers() to partition PROVIDERS across
# concurrent processes -- kube/benchmark-runner-job.yaml's 3 indexed Job
# completions each set this from `batch.kubernetes.io/job-completion-index`
# (always an integer 0, 1, 2, ... under Indexed completion mode), and a
# human can equally run `PROVIDER_FILTER=local-policy-B uv run
# orchestrator.py --step sweep` directly. Unset (the default) means "run
# every provider" -- the original serial reference path, unchanged, which
# is what expected_scorecard.json / test_lab3.py exercise.
PROVIDER_FILTER_ENV_VAR: str = "PROVIDER_FILTER"

# Glob for the per-provider partial scorecards written by a
# PROVIDER_FILTER-restricted `--step sweep` (write_partial_scorecard()) and
# read back by `--step collect` (collect_step()).
PARTIAL_SCORECARD_GLOB: str = "scorecard.partial.*.json"


def _select_providers() -> dict[str, Callable[..., FitResult]]:
    """Resolve which entries of PROVIDERS this invocation should score.

    Reads PROVIDER_FILTER_ENV_VAR from the environment:
      - unset or empty: every provider (the serial reference path;
        preserves expected_scorecard.json / test_lab3.py's behaviour
        exactly).
      - a literal key of PROVIDERS (e.g. "local-policy-B"): just that one.
      - an integer string (what
        kube/benchmark-runner-job.yaml's `batch.kubernetes.io/job-
        completion-index` fieldRef actually provides): resolved
        positionally against PROVIDERS' iteration order (stable dict order,
        guaranteed since Python 3.7) -- completion index 0 -> the first
        provider, 1 -> the second, 2 -> the third.

    Returns:
        A dict with exactly the PROVIDERS entries to score this run. When
        the filter is unset, this is PROVIDERS itself (not a copy), so
        callers can use `providers is PROVIDERS` to detect the unfiltered
        (serial) case.

    Raises:
        SystemExit: PROVIDER_FILTER_ENV_VAR is set but names neither a
        valid provider nor a valid index -- fail fast rather than silently
        scoring zero or the wrong provider.
    """
    raw = os.environ.get(PROVIDER_FILTER_ENV_VAR)
    if not raw:
        return PROVIDERS
    if raw in PROVIDERS:
        return {raw: PROVIDERS[raw]}
    provider_names = list(PROVIDERS)
    try:
        idx = int(raw)
    except ValueError:
        print(
            f"[FAIL] {PROVIDER_FILTER_ENV_VAR}={raw!r} is neither a provider "
            f"name {provider_names} nor an integer index",
            file=sys.stderr,
        )
        sys.exit(1)
    if not (0 <= idx < len(provider_names)):
        print(
            f"[FAIL] {PROVIDER_FILTER_ENV_VAR}={raw!r} out of range for "
            f"{len(provider_names)} providers {provider_names}",
            file=sys.stderr,
        )
        sys.exit(1)
    name = provider_names[idx]
    return {name: PROVIDERS[name]}


def run_sweep(
    providers: Optional[dict[str, Callable[..., FitResult]]] = None,
    verbose: bool = True,
) -> list[TaskFamilyResult]:
    """Run every (provider, task family) pair and collect results.

    Args:
        providers: which providers to score; defaults to all of PROVIDERS
            (the serial reference path). kube/benchmark-runner-job.yaml's
            partitioned pods pass a single-entry dict via _select_providers().
        verbose: if True, print one row as each pair completes.

    Returns:
        len(providers) x 3 task families TaskFamilyResult rows (9 in the
        unfiltered/default case; 3 when `providers` is restricted to one
        entry). tokens is always None: no live model server ran, see module
        docstring.
    """
    if providers is None:
        providers = PROVIDERS
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
    for provider_name, search_fn in providers.items():
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
    """Run the matrix selected by PROVIDER_FILTER_ENV_VAR (see
    _select_providers()): 3 providers x 3 task families, plus the PowerFM
    baseline row appended last (per docs/VISION.md's presenter walkthrough:
    "ending with the PowerFM ... baseline row") -- unless the filter
    restricts this run to a single provider, in which case only that
    provider's 3 rows are returned and the PowerFM row is *not* appended:
    it isn't part of any single provider's partition of the matrix, so a
    partitioned run would otherwise triplicate it across kube/benchmark-
    runner-job.yaml's 3 completions. collect_step() adds it back in exactly
    once when merging partial runs."""
    providers = _select_providers()
    rows = run_sweep(providers=providers, verbose=verbose)
    if providers is PROVIDERS:
        rows.append(powerfm_baseline_row(verbose=verbose))
    return rows


def write_partial_scorecard(rows: list[TaskFamilyResult]) -> Path:
    """Write one partitioned provider's rows to their own file in
    RESULTS_DIR, so multiple concurrent PROVIDER_FILTER-restricted
    `--step sweep` runs (kube/benchmark-runner-job.yaml's 3 indexed Job
    completions, sharing one results volume) don't clobber each other.
    collect_step() reads every such file back and merges them into one
    scorecard.

    Args:
        rows: this run's rows -- expected to be exactly one provider's 3
            task-family rows, i.e. sweep_step() called with
            PROVIDER_FILTER_ENV_VAR set.

    Returns:
        The path written.

    Raises:
        ValueError: if `rows` is empty or spans more than one provider --
            this function only ever writes a single partitioned provider's
            output, never a mix.
    """
    if not rows:
        raise ValueError("write_partial_scorecard: rows is empty")
    providers_seen = {row["provider"] for row in rows}
    if len(providers_seen) != 1:
        raise ValueError(
            f"write_partial_scorecard expects exactly one provider's rows, "
            f"got {providers_seen}"
        )
    provider_name = providers_seen.pop()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    partial_file = RESULTS_DIR / f"scorecard.partial.{provider_name}.json"
    partial_file.write_text(json.dumps(rows, indent=2))
    print(f"Partial scorecard for {provider_name} written to {partial_file}")
    return partial_file


def collect_step() -> list[TaskFamilyResult]:
    """Merge distinct per-provider partial scorecards (written by
    PROVIDER_FILTER-restricted `--step sweep` runs, e.g.
    kube/benchmark-runner-job.yaml's 3 indexed completions, via
    write_partial_scorecard()) back into one scorecard matching the shape
    report_step() writes for the serial reference path.

    This is the collection half of the "farm the matrix out instead of a
    for-loop" path named in docs/VISION.md section 9: it reads every
    RESULTS_DIR / "scorecard.partial.*.json" file present, orders the rows
    by PROVIDERS' own iteration order (so the merged result is directly
    comparable, row for row, to the serial run_sweep() path -- each
    provider's search is deterministic and independent of the others, so
    partitioned rows have the same values as the serial run, not just the
    same shape), computes the PowerFM baseline row itself (not part of any
    partitioned provider's file -- see powerfm_baseline_row()), and writes
    the combined scorecard via report_step().

    Returns:
        The merged rows, in the same provider/task_family order as
        sweep_step()'s unfiltered (serial) output.

    Raises:
        SystemExit: a provider named in PROVIDERS has no partial file in
            RESULTS_DIR -- a genuinely missing/failed completion should
            fail this step loudly, not silently produce a short scorecard.
    """
    rows_by_provider: dict[str, list[TaskFamilyResult]] = {}
    for partial_file in sorted(RESULTS_DIR.glob(PARTIAL_SCORECARD_GLOB)):
        provider_rows: list[TaskFamilyResult] = json.loads(partial_file.read_text())
        for row in provider_rows:
            rows_by_provider.setdefault(row["provider"], []).append(row)

    missing = [name for name in PROVIDERS if name not in rows_by_provider]
    if missing:
        print(
            f"[FAIL] no partial scorecard found for provider(s) {missing} in "
            f"{RESULTS_DIR} (expected files matching {PARTIAL_SCORECARD_GLOB}) "
            "-- run the partitioned sweep for every provider before collecting",
            file=sys.stderr,
        )
        sys.exit(1)

    merged: list[TaskFamilyResult] = []
    for provider_name in PROVIDERS:
        merged.extend(rows_by_provider[provider_name])
    merged.append(powerfm_baseline_row(verbose=False))
    return report_step(merged)


def _plot_scorecard(rows: list[TaskFamilyResult], path: Path) -> None:
    """Render the bake-off's core comparison as a grouped bar chart: one
    group per task_family, one bar per local-policy provider within the
    group, bar height = error_margin
    (docs/backlog/0003-lab3-scorecard-visualization.md's proposed fix).

    Only the 3 PROVIDERS entries (local-policy-A/B/C) and the 3 task
    families they share (load-scale-fit, line-rating-fit, gen-droop-fit) are
    plotted -- both are derived from `rows` itself (filtering to
    `row["provider"] in PROVIDERS`, then taking task_family in first-seen
    order), not hard-coded, so this stays in sync with PROVIDERS/
    _make_task_families() without a second source of truth. The
    PowerFM-OpenPowerBench-stub baseline row is deliberately excluded: its
    task_family (load-forecast-24h) has no local-policy peer to compare
    against in the same units (MAPE% vs pu/loading-%), so it would render as
    a lone, incomparable 4th group rather than a genuine 3-way comparison --
    the entire point of a bake-off chart. It remains visible in the printed
    table and scorecard.json this function's caller already writes.

    error_margin's unit differs by task_family (pu for load-scale-fit, % for
    the other two -- see TaskFamily.describe_unit in _make_task_families())
    so bars are only meaningfully comparable *within* a group, never across
    groups; the y-axis label says so explicitly rather than implying a
    single shared unit.

    Args:
        rows: scorecard rows, e.g. from report_step()'s own `rows` argument
            -- read directly, nothing recomputed here.
        path: output PNG path (SCORECARD_CHART_FILE).
    """
    provider_names = [name for name in PROVIDERS if any(
        r["provider"] == name for r in rows
    )]
    task_families: list[str] = []
    for row in rows:
        if row["provider"] not in PROVIDERS:
            continue
        if row["task_family"] not in task_families:
            task_families.append(row["task_family"])

    margin_by_family_provider: dict[str, dict[str, float]] = {
        family: {} for family in task_families
    }
    for row in rows:
        if row["provider"] not in PROVIDERS:
            continue
        margin_by_family_provider[row["task_family"]][row["provider"]] = row["error_margin"]

    n_series = len(provider_names)
    slot_width = SCORECARD_CHART_GROUP_WIDTH / n_series
    bar_render_width = slot_width * SCORECARD_CHART_BAR_FILL_FRACTION
    offsets = [(i - (n_series - 1) / 2) * slot_width for i in range(n_series)]
    x_positions = range(len(task_families))

    fig, ax = plt.subplots(figsize=SCORECARD_CHART_FIGSIZE)
    for i, provider_name in enumerate(provider_names):
        values = [margin_by_family_provider[family][provider_name] for family in task_families]
        xs = [x + offsets[i] for x in x_positions]
        bars = ax.bar(
            xs, values, bar_render_width, label=provider_name,
            color=SCORECARD_CHART_PROVIDER_COLORS[provider_name],
        )
        ax.bar_label(bars, fmt="%.4f", padding=3, fontsize=8)

    ax.set_xticks(list(x_positions))
    ax.set_xticklabels(task_families)
    ax.set_ylabel("error margin (units vary by task family -- compare within a group only)")
    ax.set_title("Lab 3 provider bake-off -- error margin by task family")
    ax.legend()
    ax.grid(True, axis="y", linewidth=0.4, alpha=0.4)
    fig.tight_layout()
    # Reserve room below the x-axis labels for the footnote added next --
    # tight_layout() alone only accounts for the axes already on the figure,
    # not the fig.text() added after it.
    fig.subplots_adjust(bottom=0.16)
    # In-image footnote (not just README/docstring prose): a reader who only
    # ever sees the raw PNG (a PR diff, a slide, a file browser) has no other
    # way to learn the PowerFM row was left out on purpose, not missed.
    fig.text(
        0.5, 0.02,
        "PowerFM-OpenPowerBench-stub excluded: no local-policy peer shares "
        "its task_family/units -- see scorecard.json for its row.",
        ha="center", fontsize=7, color=SCORECARD_CHART_FOOTNOTE_COLOR,
    )
    fig.savefig(path, dpi=SCORECARD_CHART_DPI)
    plt.close(fig)


def report_step(rows: Optional[list[TaskFamilyResult]] = None) -> list[TaskFamilyResult]:
    """Write the scorecard to benchmarks/power-agent-bench-lite/results/,
    print it as a table, and (re)render the committed scorecard chart PNG.

    The chart write is unconditional here (unlike Lab 4/5's
    `refresh_chart`-gated pattern): check_step() below calls sweep_step()
    directly and never calls report_step(), so there is no self-check code
    path that could route through here and clobber the committed PNG with a
    machine-dependent re-derivation -- report_step() only ever runs via an
    explicit `--step report` or `--step collect` invocation, both of which
    are already deliberate "regenerate the committed scorecard" actions.

    Args:
        rows: scorecard rows; runs sweep_step() if not supplied.

    Returns:
        The rows written (same as input if supplied).
    """
    if rows is None:
        rows = sweep_step(verbose=False)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    SCORECARD_FILE.write_text(json.dumps(rows, indent=2))
    _plot_scorecard(rows, SCORECARD_CHART_FILE)

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
    signal). Also asserts the committed scorecard chart PNG exists
    (mirroring Lab 4/5's `..._FILE.exists()` pattern) -- a pixel diff isn't
    attempted, per docs/backlog/0003-lab3-scorecard-visualization.md ("wire
    it into --step check only to the extent of 'does the file get
    produced'"). This step never regenerates SCORECARD_CHART_FILE itself
    (see report_step()'s docstring for why there is nothing to gate here).

    Returns:
        True if every row's provider/task_family/passed/error_margin
        matches the fixture within FIXTURE_FLOAT_ATOL and the chart PNG
        exists; False otherwise.
    """
    actual = sweep_step(verbose=False)
    if not EXPECTED_FILE.exists():
        print(f"[FAIL] no fixture at {EXPECTED_FILE}", file=sys.stderr)
        return False
    if not SCORECARD_CHART_FILE.exists():
        print(f"[FAIL] no chart at {SCORECARD_CHART_FILE}", file=sys.stderr)
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
        "--step", choices=["sweep", "report", "check", "collect"], default="check"
    )
    args = parser.parse_args()

    if args.step == "sweep":
        rows = sweep_step()
        # A PROVIDER_FILTER-restricted run is one partition of the matrix
        # (kube/benchmark-runner-job.yaml's indexed pods) -- persist it so
        # `--step collect` can merge it with the other partitions. The
        # unfiltered/serial path prints only, unchanged from before.
        if os.environ.get(PROVIDER_FILTER_ENV_VAR):
            write_partial_scorecard(rows)
    elif args.step == "report":
        report_step()
    elif args.step == "check":
        ok = check_step()
        sys.exit(0 if ok else 1)
    elif args.step == "collect":
        collect_step()


if __name__ == "__main__":
    main()
