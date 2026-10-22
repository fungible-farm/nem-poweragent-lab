"""Compare complete, identically budgeted domain runs with paired uncertainty."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from powercoder.datasets.audit import load_rows
from powercoder.inference.evaluate_agent import frozen_task_count
from training.unsloth.evaluate import DOMAIN_IMPROVEMENT_THRESHOLD, uncertainty


def verified_run(directory: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Require all benchmark IDs in order, with unchanged raw evidence journals."""
    summary = json.loads((directory / "summary.json").read_text())
    records = load_rows(directory / "results.jsonl")
    if any(row["kind"] != "result" for row in records):
        raise ValueError("Unexpected score journal event")
    results = [row["payload"] for row in records]
    task_path = Path(next(iter(summary["inputs"])))
    expected_ids = [row["example_id"] for row in load_rows(task_path)]
    count = frozen_task_count(task_path)
    if (not summary["complete"] or not summary["independence_audit"]["clean"]
        or summary["n_tasks"] != count or len(results) != count
        or [row["example_id"] for row in results] != expected_ids):
        raise ValueError("Incomplete or mismatched domain run")
    for path, expected_hash in summary["inputs"].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected_hash:
            raise ValueError("Benchmark/training source changed since the run")
    for row in results:
        journal = directory / f"{row['example_id']}.jsonl"
        if hashlib.sha256(journal.read_bytes()).hexdigest() != row["journal_sha256"]:
            raise ValueError("Raw evidence changed since scoring")
    if (summary["n_pass"] != sum(row["passed"] for row in results)
        or summary["pass_at_1"] != sum(row["passed"] for row in results) / len(results)):
        raise ValueError("Summary disagrees with per-task results")
    return summary, results


def compare(base_dir: Path, student_dir: Path, allow_tool_choice_difference: bool = False) -> dict[str, Any]:
    """Measure the actual delta, refusing incomplete or unequal conditions.

    ``allow_tool_choice_difference`` admits exactly one difference, the first
    turn's tool choice, for the forced-tool-call arm's own comparison.
    """
    base, first = verified_run(base_dir)
    student, second = verified_run(student_dir)
    for field in ("inputs", "max_turns", "max_tool_calls", "max_tokens", "temperature", "attempts_per_task", "inference_timeout_s"):
        if base[field] != student[field]:
            raise ValueError(f"Unequal evaluation conditions: {field}")
    # Runs before the option existed were all "auto".
    choices = [run.get("first_turn_tool_choice", "auto") for run in (base, student)]
    if choices[0] != choices[1] and not allow_tool_choice_difference:
        raise ValueError("Unequal evaluation conditions: first_turn_tool_choice")
    first_paired = [{"example_id": r["example_id"], "pass": r["passed"]} for r in first]
    second_paired = [{"example_id": r["example_id"], "pass": r["passed"]} for r in second]
    base_rate = sum(r["passed"] for r in first) / len(first)
    student_rate = sum(r["passed"] for r in second) / len(second)
    delta = student_rate - base_rate
    return {"n_tasks": len(first), "base_model": base["model"], "student_model": student["model"],
            "first_turn_tool_choice": {"base": choices[0], "student": choices[1]},
            "base_pass_at_1": base_rate, "student_pass_at_1": student_rate,
            "delta_pass_at_1": delta, "delta_percentage_points": delta * 100,
            "domain_threshold_met": delta >= DOMAIN_IMPROVEMENT_THRESHOLD,
            "uncertainty": uncertainty(first_paired, second_paired),
            "by_subfamily": {family: {
                "n_tasks": sum(r["subfamily"] == family for r in first),
                "base_pass": sum(r["passed"] for r in first if r["subfamily"] == family),
                "student_pass": sum(r["passed"] for r in second if r["subfamily"] == family),
            } for family in sorted({r["subfamily"] for r in first})},
            "g5_met": False, "g5_pending": "General Python and critical fabrication suites remain separate gates"}


def main() -> None:
    """Write a new comparison without overwriting previous measurements."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--student-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.base_dir, args.student_dir)
    with args.out.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
