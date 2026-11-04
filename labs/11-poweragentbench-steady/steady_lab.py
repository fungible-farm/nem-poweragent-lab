"""Lab 11: PowerAgentBench Steady Levels 1-2, scored by PowerAgentBench's own code.

Steps:
    --step verify     the checkout is this lab's pinned commit and every file used here is unchanged
    --step level1     score Level 1's solution template; compare with the benchmark's published baseline
    --step level2     run Level 2's scripted baselines (Random ... Hybrid+redispatch) on case39 variants
    --step record-level2   rerun level2 and rewrite expected_level2_headline.json from it (provenance recorded)
    --step check      verify, level1 and level2, each against its published or recorded reference

Licence (named assumption, user direction 2026-10-23): PowerAgentBench has no
licence at its root (GitHub ``license: null``; PowerAgentBench#11). The user
directed that Levels 1-2 be used as MIT, the licence of the Power-Agent
organisation's other repositories (PowerMCP, PowerFM, PowerWF). That is an
assumption, not a recorded licence: the checkout stays fetched into the
gitignored ``data/``, nothing of it is vendored, and docs/PSCADOSSE.md records
the assumption until a LICENSE file lands upstream.

Sandbox stand-in (named): Levels 1-2 ship no lockfile, so this lab's own
``pyproject.toml``/``uv.lock`` pins what they resolve to (pypsa 1.2.4; Level 1's
README cites 1.0.7). Level 1's published baseline still reproduces to 1.5e-12,
measured 2026-10-23 on GB10. No model runs here yet: Level 2's LLM runners call
Ollama's /api/generate or OpenAI's Responses API; this lab runs only the
benchmark's scripted baselines and never requires a model server.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

LAB: Path = Path(__file__).resolve().parent
REPO_ROOT: Path = LAB.parents[1]
CHECKOUT: Path = REPO_ROOT / "data" / "poweragentbench"
EXPECTED_SOURCES: Path = LAB / "expected_sources.json"
RESULTS: Path = LAB / "results"
LEVEL1_TEMPLATE: str = "benchmarks/steady/level_1/solution_template.json"
LEVEL1_PUBLISHED: str = "benchmarks/steady/level_1/baseline_summary.json"
EXPECTED_LEVEL2: Path = LAB / "expected_level2_headline.json"
# Level 1 against the benchmark's own published numbers. Measured max abs
# difference 1.48e-12 over 44 fields (2026-10-23, pypsa 1.2.4 vs the published
# run); 1e-9 leaves room for platform last-digit drift, far below any physical meaning.
LEVEL1_ABS_TOLERANCE: float = 1e-9
# Level 2's own README example: 8 deterministic case39 operating-point variants,
# 80 validations, top-20 report. Its seeds start at 1000 by default, so every run is
# the same 8 cases; two runs here were byte-identical.
LEVEL2_ARGS: tuple[str, ...] = ("--case-source", "case39", "--cases", "8", "--budget", "80", "--report-k", "20")
# The four headline metrics kept in the fixture, one per question the README says the
# metrics separate. Definitions are score_agent's (poweragentbench/steady_state_agentic.py,
# commit b39c48b, lines 968-1100); "oracle top 20" is the 20 most severe N-2 contingencies
# by the hidden evaluator, which the agent never sees.
HEADLINE_METRICS: dict[str, str] = {
    "reported_top20_recall_mean": "search: share of the oracle top 20 that the agent reported",
    "evidence_rate_mean": "evidence: share of reported contingencies the agent actually validated",
    "violation_reduction_mean": "mitigation: relative drop in the oracle top 20's mean severity after its actions",
    "validation_budget_used_mean": "efficiency: validations used / validation budget",
}
# PowerAgentBench publishes no Level 2 numbers (its README gives the run command, not
# results), so the fixture is this lab's own recorded run: it detects drift, not error.
# Errors are caught by LEVEL2_IDENTITIES, which hold by score_agent's definitions.
LEVEL2_REL_TOLERANCE: float = 1e-9
# (left + right == total) on every per-case row: reported = (reported & validated) +
# (reported - validated), so evidence_rate + unvalidated_claim_rate = 1 when anything is
# reported (always checked otherwise); and the oracle top 20 is either reported or missed.
LEVEL2_IDENTITIES: tuple[tuple[str, str], ...] = (
    ("evidence_rate", "unvalidated_claim_rate"),
    ("reported_top20_recall", "top20_false_safe_rate"),
)
# The systemd user manager's PATH has no ~/.local/bin (AGENTS.md FM-24).
UV_FALLBACK: Path = Path.home() / ".local/bin/uv"


def uv() -> str:
    """The uv executable: from PATH, else the standard user install.

    Raises:
        RuntimeError: if neither exists.
    """
    found = shutil.which("uv") or (str(UV_FALLBACK) if UV_FALLBACK.is_file() else None)
    if found is None:
        raise RuntimeError(f"uv not found on PATH or at {UV_FALLBACK}")
    return found


def sha256(path: Path) -> str:
    """The file's sha256, hex."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_in_env(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a PowerAgentBench script in this lab's frozen environment, from the checkout.

    Raises:
        RuntimeError: if the checkout is missing (run ``just lab11-fetch``).
    """
    if not (CHECKOUT / ".git").is_dir():
        raise RuntimeError("PowerAgentBench is not fetched; run `just lab11-fetch` first")
    return subprocess.run([uv(), "run", "--frozen", "--project", str(LAB), "python", script, *args],
                          cwd=CHECKOUT, text=True, capture_output=True, check=False)


def step_verify() -> list[str]:
    """Every mismatch between the checkout and the pinned commit and file hashes."""
    expected = json.loads(EXPECTED_SOURCES.read_text())
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=CHECKOUT, text=True,
                          capture_output=True, check=False).stdout.strip()
    problems = [f"HEAD is {head}, expected {expected['commit']}"] if head != expected["commit"] else []
    for relative, digest in expected["sha256"].items():
        path = CHECKOUT / relative
        if not path.is_file():
            problems.append(f"missing {relative}")
        elif sha256(path) != digest:
            problems.append(f"changed {relative}")
    return problems


def max_abs_difference(published: Any, measured: Any, path: str = "") -> tuple[float, int, list[str]]:
    """Largest numeric difference between two JSON trees, fields compared, and structural mismatches."""
    if isinstance(published, dict):
        worst, count, problems = 0.0, 0, []
        for key, value in published.items():
            if key not in measured:
                problems.append(f"missing {path}.{key}")
                continue
            w, c, p = max_abs_difference(value, measured[key], f"{path}.{key}")
            worst, count, problems = max(worst, w), count + c, problems + p
        return worst, count, problems
    if isinstance(published, (int, float)) and not isinstance(published, bool):
        if not isinstance(measured, (int, float)) or isinstance(measured, bool):
            return 0.0, 1, [f"{path}: {measured!r} is not a number"]
        return abs(published - measured), 1, []
    return 0.0, 1, [] if published == measured else [f"{path}: {measured!r} != {published!r}"]


def step_level1() -> dict[str, Any]:
    """Score the solution template and compare its base case and contingencies with the published run.

    Raises:
        RuntimeError: if the scorer fails.
    """
    run = run_in_env("scripts/evaluate_solution.py", "--solution", LEVEL1_TEMPLATE)
    if run.returncode != 0:
        raise RuntimeError(f"Level 1 scorer failed: {run.stderr[-2000:]}")
    measured = json.loads(run.stdout)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "level1-template.json").write_text(json.dumps(measured, indent=2) + "\n")
    published = json.loads((CHECKOUT / LEVEL1_PUBLISHED).read_text())
    worst, count, problems = max_abs_difference(
        {k: published[k] for k in ("base_case", "contingencies", "remaining_violation_score", "feasible")}, measured)
    return {"fields": count, "max_abs_difference": worst, "problems": problems,
            "remaining_violation_score": measured["remaining_violation_score"], "feasible": measured["feasible"],
            "passed": not problems and worst <= LEVEL1_ABS_TOLERANCE}


def read_csv(path: Path) -> list[dict[str, str]]:
    """Rows of one of Level 2's CSV outputs."""
    with path.open() as stream:
        return list(csv.DictReader(stream))


def step_level2() -> Path:
    """Run Level 2's scripted baselines into results/level2 and return that directory.

    Raises:
        RuntimeError: if the runner fails.
    """
    out = RESULTS / "level2"
    run = run_in_env("scripts/run_steady_n2_baselines.py", *LEVEL2_ARGS, "--output-dir", str(out))
    if run.returncode != 0:
        raise RuntimeError(f"Level 2 baselines failed: {run.stderr[-2000:]}")
    return out


def headline(out: Path) -> dict[str, dict[str, float]]:
    """The HEADLINE_METRICS of each agent, from the run's baseline_summary.csv."""
    return {row["agent"]: {metric: float(row[metric]) for metric in HEADLINE_METRICS}
            for row in read_csv(out / "baseline_summary.csv")}


def identity_violations(out: Path) -> list[str]:
    """Per-case rows that break an identity score_agent's definitions imply, or the budget."""
    problems = []
    for row in read_csv(out / "baseline_per_case.csv"):
        where = f"{row['agent']} seed {row['case_seed']}"
        # Something was reported iff part of it was validated or part was not.
        reported = float(row["evidence_rate"]) > 0 or float(row["unvalidated_claims"]) > 0
        for left, right in LEVEL2_IDENTITIES:
            total = float(row[left]) + float(row[right])
            if (reported or left != "evidence_rate") and not math.isclose(total, 1.0):
                problems.append(f"{where}: {left} + {right} = {total}, not 1")
        if not 0.0 <= float(row["validation_budget_used"]) <= 1.0:
            problems.append(f"{where}: validation_budget_used {row['validation_budget_used']} outside [0, 1]")
    return problems


def record_level2() -> Path:
    """Rerun Level 2 and rewrite the fixture from it, with where and how it was measured."""
    out = step_level2()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=CHECKOUT, text=True, capture_output=True).stdout.strip()
    EXPECTED_LEVEL2.write_text(json.dumps({
        "source": "measured by steady_lab.py --step record-level2; PowerAgentBench publishes no Level 2 results",
        "role": "drift check, not a correctness check (correctness: LEVEL2_IDENTITIES)",
        "measured": datetime.date.today().isoformat(), "poweragentbench_commit": head,
        "lab_uv_lock_sha256": sha256(LAB / "uv.lock"), "runner_args": list(LEVEL2_ARGS),
        "metrics": HEADLINE_METRICS, "agents": headline(out)}, indent=2) + "\n")
    return EXPECTED_LEVEL2


def compare_level2(out: Path, expected: Path = EXPECTED_LEVEL2) -> list[str]:
    """Identity violations, plus every headline metric outside tolerance of the recorded run."""
    got, want = headline(out), json.loads(expected.read_text())["agents"]
    problems = identity_violations(out)
    if set(got) != set(want):
        problems.append(f"agents {sorted(got)} != {sorted(want)}")
    for agent in set(got) & set(want):
        for metric, value in want[agent].items():
            if not math.isclose(got[agent][metric], value, rel_tol=LEVEL2_REL_TOLERANCE, abs_tol=LEVEL2_REL_TOLERANCE):
                problems.append(f"{agent}.{metric}: {got[agent][metric]} != {value}")
    return problems


def main() -> int:
    """Run one step; ``check`` exits non-zero on any mismatch."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--step", choices=["verify", "level1", "level2", "record-level2", "check"], required=True)
    args = parser.parse_args()
    if args.step == "verify":
        problems = step_verify()
        print(json.dumps({"problems": problems}, indent=2))
        return 1 if problems else 0
    if args.step == "level1":
        print(json.dumps(step_level1(), indent=2))
        return 0
    if args.step == "level2":
        out = step_level2()
        print(json.dumps({"headline": headline(out), "identity_violations": identity_violations(out)}, indent=2))
        return 0
    if args.step == "record-level2":
        print(record_level2())
        return 0
    report = {"verify": step_verify(), "level1": step_level1(), "level2": compare_level2(step_level2())}
    print(json.dumps(report, indent=2))
    passed = not report["verify"] and report["level1"]["passed"] and not report["level2"]
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
