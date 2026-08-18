"""Scoring harness for scenario_engine runs
(docs/prd/0001-composable-generator-detector-platform.md Goal 4).

`score_run()` scores a completed scenario run's `GeneratorEvent` log and
`Finding` log against a committed ground-truth fixture, in two
*independent* sections: generator-realism (did the modelled events fire at
the right time) and detector-performance (did a detector actually flag
them). PRD-0001's own reasoning: a scenario can nail the cascade physics
while a detector misses it (false negative), or raise a correct alarm off
physics that don't match the real timing (physically wrong but
"detected") -- the report must be able to say which happened, so the two
sections are always scored and printed separately, never merged into one
pass/fail number.
"""
from __future__ import annotations

from typing import TypedDict

import numpy as np

from .detectors import Finding
from .generators import GeneratorEvent


class ScoreEntry(TypedDict):
    """One scored line item -- PRD-0001's own scoring-harness sketch
    (`{name, expected, actual, tolerance, pass}`), typed.

    Attributes:
        name: human-readable entry name (e.g. "generator:fault-1" or
            "detector:osc-1:oscillation").
        expected: the fixture's ground-truth time_s.
        actual: the run's own observed time_s (`float("nan")` if the
            named generator/detector never fired/found anything).
        tolerance: the fixture's own tolerance_s for this entry.
        passed: True if `abs(actual - expected) <= tolerance`.
    """

    name: str
    expected: float
    actual: float
    tolerance: float
    passed: bool


class ScoreReport(TypedDict):
    """The full scoring report -- PRD-0001 Goal 4's two independent
    sections plus a summary flag.

    Attributes:
        generator_realism: one ScoreEntry per fixture-named generator.
        detector_performance: one ScoreEntry per fixture-named detector
            target.
        all_passed: True only if every entry in both sections passed.
    """

    generator_realism: list[ScoreEntry]
    detector_performance: list[ScoreEntry]
    all_passed: bool


def score_generator_realism(
    events: list[GeneratorEvent], fixture: dict
) -> list[ScoreEntry]:
    """Score each fixture-named generator firing's earliest actual fire
    time against its committed ground-truth `time_s`, within
    `tolerance_s`.

    Args:
        events: the scenario run's own committed GeneratorEvent log (may
            contain more than one event per generator_id, e.g. a
            NetworkFaultGenerator's close-then-open pair -- the *earliest*
            firing is what's scored, matching "the first simulated instant
            this generator's condition is met").
        fixture: `fixture["generators"]` -- `generator_id ->
            {"time_s": ..., "tolerance_s": ...}`.

    Returns:
        One ScoreEntry per fixture-named `generator_id`. A `generator_id`
        in the fixture that never actually fired scores as failed with
        `actual = float("nan")`.
    """
    earliest: dict[str, float] = {}
    for e in events:
        gid = e["generator_id"]
        if gid not in earliest or e["time_s"] < earliest[gid]:
            earliest[gid] = e["time_s"]

    entries: list[ScoreEntry] = []
    for gid, spec in fixture.get("generators", {}).items():
        actual = earliest.get(gid, float("nan"))
        tol = float(spec["tolerance_s"])
        passed = bool(np.isfinite(actual) and abs(actual - spec["time_s"]) <= tol)
        entries.append(
            {
                "name": f"generator:{gid}",
                "expected": float(spec["time_s"]),
                "actual": float(actual),
                "tolerance": tol,
                "passed": passed,
            }
        )
    return entries


def score_detector_performance(findings: list[Finding], fixture: dict) -> list[ScoreEntry]:
    """Score each fixture-named detector target against the earliest
    matching Finding (by `detector_id` + `kind`), within `tolerance_s` and
    `min_confidence`.

    Args:
        findings: the scenario run's own committed Finding log (every
            detector's `consume()` output, concatenated).
        fixture: `fixture["detectors"]` -- `"detector_id:kind" ->
            {"time_s": ..., "tolerance_s": ..., "min_confidence": ...}`.

    Returns:
        One ScoreEntry per fixture-named detector target. A target with no
        matching Finding (or none meeting `min_confidence`) scores as
        failed with `actual = float("nan")`.
    """
    entries: list[ScoreEntry] = []
    for key, spec in fixture.get("detectors", {}).items():
        detector_id, kind = key.split(":", 1)
        min_confidence = float(spec.get("min_confidence", 0.0))
        matches = [
            f
            for f in findings
            if f["detector_id"] == detector_id
            and f["kind"] == kind
            and f["confidence"] >= min_confidence
        ]
        actual = min((f["time_s"] for f in matches), default=float("nan"))
        tol = float(spec["tolerance_s"])
        passed = bool(np.isfinite(actual) and abs(actual - spec["time_s"]) <= tol)
        entries.append(
            {
                "name": f"detector:{key}",
                "expected": float(spec["time_s"]),
                "actual": float(actual),
                "tolerance": tol,
                "passed": passed,
            }
        )
    return entries


def score_run(
    events: list[GeneratorEvent], findings: list[Finding], fixture: dict
) -> ScoreReport:
    """Score one scenario run against its committed ground-truth fixture,
    in the two independent sections PRD-0001 Goal 4 requires.

    Args:
        events: the run's committed GeneratorEvent log.
        findings: the run's committed Finding log (all detectors).
        fixture: parsed `expected_*.json` ground-truth dict with
            `"generators"` and `"detectors"` sections.

    Returns:
        A ScoreReport with both sections plus an overall `all_passed` flag.
    """
    generator_realism = score_generator_realism(events, fixture)
    detector_performance = score_detector_performance(findings, fixture)
    all_passed = all(e["passed"] for e in generator_realism + detector_performance)
    return {
        "generator_realism": generator_realism,
        "detector_performance": detector_performance,
        "all_passed": all_passed,
    }


def print_score_report(report: ScoreReport) -> None:
    """Print a PASS/FAIL line per ScoreEntry plus a summary line, matching
    every other lab's `--step check` convention (AGENTS.md "every lab is
    self-checking").

    Args:
        report: output of `score_run()`.
    """
    print("-- generator realism --")
    for e in report["generator_realism"]:
        status = "PASS" if e["passed"] else "FAIL"
        print(
            f"[{status}] {e['name']}: expected={e['expected']:.4f}s "
            f"actual={e['actual']:.4f}s tol={e['tolerance']:.4f}s"
        )
    print("-- detector performance --")
    for e in report["detector_performance"]:
        status = "PASS" if e["passed"] else "FAIL"
        print(
            f"[{status}] {e['name']}: expected={e['expected']:.4f}s "
            f"actual={e['actual']:.4f}s tol={e['tolerance']:.4f}s"
        )
    total = len(report["generator_realism"]) + len(report["detector_performance"])
    if report["all_passed"]:
        print(
            f"MATCH: scenario run scored {len(report['generator_realism'])} generator + "
            f"{len(report['detector_performance'])} detector entries "
            f"({total} total), all within tolerance"
        )
    else:
        n_fail = sum(
            not e["passed"]
            for e in report["generator_realism"] + report["detector_performance"]
        )
        print(f"FAIL: {n_fail}/{total} entries outside tolerance")
