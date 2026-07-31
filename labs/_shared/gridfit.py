"""Shared helpers for Labs 1-3: powerio -> pandapower loading and the
deterministic "agent proposes, pandapower disposes" search loop.

Sandbox note (see each lab's README for the full version): the real
architecture in docs/VISION.md has an LLM (Phi-4-mini via a llama.cpp pod)
choosing the next trial value in the loop below, over MCP. This sandbox has
no podman and no budget to download/serve a GGUF model, so `propose_next`
below is a plain bisection policy standing in for that decision. It is
swapped out, not hidden: every call site names the swap explicitly.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pandapower as pp
import powerio as pio

# Upper bound on bisection iterations. Derived, not arbitrary: bisection
# halves the search interval every iteration, so for the widest interval
# used anywhere in these labs (+/-10% -> width 0.20, see SCALE_LO/SCALE_HI
# in labs/01.../run.py) and the tightest tolerance used (0.002 pu, also
# Lab 1), reaching interval width < tolerance needs
# ceil(log2(0.20 / 0.002)) = 7 iterations. 25 is a >3x safety margin over
# that worst case so a genuine non-convergence (bad bracket, non-monotonic
# `evaluate`) fails fast instead of looping silently.
DEFAULT_MAX_ITER: int = 25


def load_case(matpower_path: str | Path) -> tuple[pp.pandapowerNet, list[str]]:
    """Parse a MATPOWER .m case with powerio and convert to a pandapower net.

    powerio is the Rust-backed parser named in docs/VISION.md section 8 (the
    repo's Rust requirement). Its `convert_file(..., "pandapower-json")`
    path does the .m -> pandapower translation directly; pandapower's own
    `from_ppc`/`from_mpc` converters are the documented fallback in
    docs/VISION.md section 8 if a given .m variant isn't covered -- not
    needed here, powerio parses both snemSA.m and snem1803.m cleanly.

    Args:
        matpower_path: path to a MATPOWER ``.m`` case file.

    Returns:
        A tuple of ``(net, warnings)`` where ``net`` is the resulting
        pandapower network and ``warnings`` is powerio's list of
        lossy-conversion notices (e.g. dropped angle limits).
    """
    matpower_path = Path(matpower_path)
    pp_json, warnings = pio.convert_file(str(matpower_path), "pandapower-json")
    net = pp.from_json_string(pp_json)
    return net, warnings


@dataclass
class FitIteration:
    """One bisection trial: the value tried and what pandapower measured."""

    iteration: int
    trial: float
    observed: float
    residual: float


@dataclass
class FitResult:
    """Outcome of a `bisection_fit` run, including the full iteration log."""

    converged: bool
    trial: float
    observed: float
    residual: float
    iterations: list[FitIteration] = field(default_factory=list)


def bisection_fit(
    evaluate: Callable[[float], float],
    target: float,
    lo: float,
    hi: float,
    tol: float,
    max_iter: int = DEFAULT_MAX_ITER,
) -> FitResult:
    """Deterministic bisection search for a scalar trial parameter.

    `evaluate(trial)` must return the observed physical quantity for that
    trial value (a real pandapower.runpp() call downstream, every time --
    this function never fabricates a physics result). Requires
    evaluate(lo)-target and evaluate(hi)-target to have opposite signs
    (checked, not assumed) and `evaluate` to be monotonic on [lo, hi].

    This is the stand-in named in the module docstring for the LLM's
    "propose the next trial value" step; a live agent would call the same
    `evaluate` function as an MCP tool instead of this closed-form bisection.

    Args:
        evaluate: maps a trial value to the observed physical quantity.
        target: the value `evaluate(trial)` should converge to.
        lo: lower bound of the search interval.
        hi: upper bound of the search interval.
        tol: convergence tolerance on ``abs(observed - target)``.
        max_iter: hard cap on iterations; see DEFAULT_MAX_ITER for how the
            default value was derived.

    Returns:
        A FitResult; ``converged`` is False if `max_iter` was exhausted
        without reaching `tol`.

    Raises:
        ValueError: if `target` is not bracketed by `evaluate(lo)` and
            `evaluate(hi)` (i.e. they don't straddle it in sign).
    """
    iterations: list[FitIteration] = []

    f_lo = evaluate(lo) - target
    f_hi = evaluate(hi) - target
    if f_lo == 0:
        obs = evaluate(lo)
        iterations.append(FitIteration(1, lo, obs, obs - target))
        return FitResult(True, lo, obs, obs - target, iterations)
    if f_hi == 0:
        obs = evaluate(hi)
        iterations.append(FitIteration(1, hi, obs, obs - target))
        return FitResult(True, hi, obs, obs - target, iterations)
    if (f_lo > 0) == (f_hi > 0):
        raise ValueError(
            f"bisection_fit: target {target} is not bracketed by "
            f"[{lo}, {hi}] -> observed [{evaluate(lo)}, {evaluate(hi)}]"
        )

    a, b = lo, hi
    fa = f_lo
    for i in range(1, max_iter + 1):
        mid = (a + b) / 2.0
        observed = evaluate(mid)
        residual = observed - target
        iterations.append(FitIteration(i, mid, observed, residual))
        if abs(residual) <= tol:
            return FitResult(True, mid, observed, residual, iterations)
        if (residual > 0) == (fa > 0):
            a, fa = mid, residual
        else:
            b = mid
    last = iterations[-1]
    return FitResult(False, last.trial, last.observed, last.residual, iterations)


def scale_loads(net: pp.pandapowerNet, scale: float) -> pp.pandapowerNet:
    """Return a deep copy of `net` with every load's p_mw/q_mvar scaled.

    This is the "shunt/load scaling parameter" named in docs/VISION.md's
    Lab 1 spec -- a single scalar the fit loop searches over.
    """
    scaled = copy.deepcopy(net)
    scaled.load["p_mw"] = scaled.load["p_mw"] * scale
    scaled.load["q_mvar"] = scaled.load["q_mvar"] * scale
    return scaled
