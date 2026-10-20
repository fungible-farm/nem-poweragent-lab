"""Reject partial or altered benchmark evidence before reporting a model gain."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from powercoder.inference import compare_agents as comparator
from powercoder.inference.tool_probe import INFERENCE_TIMEOUT_S, MAX_TOKENS, MAX_TOOL_CALLS, MAX_TURNS

FIXTURE: Path = Path(__file__).parents[2] / "training/unsloth/fixtures/evaluation_cases.json"


@pytest.fixture
def paired_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Build small integrity fixtures; these journals assert no real physics."""
    cases = json.loads(FIXTURE.read_text())
    tasks = [cases["tasks"][0], cases["tasks"][-1]]
    monkeypatch.setattr(comparator, "DOMAIN_TASK_COUNT", len(tasks))
    source = tmp_path / "tasks.jsonl"
    source.write_text("".join(json.dumps(t) + "\n" for t in tasks))
    for label, outcomes in (("base", [False, True]), ("student", [True, True])):
        directory = tmp_path / label
        directory.mkdir()
        rows = []
        for task, passed in zip(tasks, outcomes, strict=True):
            journal = directory / f"{task['example_id']}.jsonl"
            journal.write_text('{"kind":"test_integrity_fixture"}\n')
            rows.append({"kind": "result", "payload": {"example_id": task["example_id"],
                "subfamily": task["subfamily"], "passed": passed,
                "journal_sha256": hashlib.sha256(journal.read_bytes()).hexdigest()}})
        (directory / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        summary = {"complete": True, "model": label, "n_tasks": len(tasks),
            "n_pass": sum(outcomes), "pass_at_1": sum(outcomes) / len(tasks),
            "independence_audit": {"clean": True},
            "inputs": {str(source): hashlib.sha256(source.read_bytes()).hexdigest()},
            "max_turns": MAX_TURNS, "max_tool_calls": MAX_TOOL_CALLS, "max_tokens": MAX_TOKENS,
            "temperature": 0.0, "attempts_per_task": 1, "inference_timeout_s": INFERENCE_TIMEOUT_S}
        (directory / "summary.json").write_text(json.dumps(summary))
    return tmp_path / "base", tmp_path / "student"


def test_measures_paired_gain(paired_runs: tuple[Path, Path]) -> None:
    """Use actual per-task outcomes and retain the separate release gate."""
    result = comparator.compare(*paired_runs)
    assert result["delta_pass_at_1"] == 0.5
    assert result["domain_threshold_met"]
    assert not result["g5_met"]


def test_missing_task_cannot_be_a_complete_run(paired_runs: tuple[Path, Path]) -> None:
    """A nominally complete summary cannot hide a missing scored attempt."""
    base, student = paired_runs
    path = student / "results.jsonl"
    path.write_text(path.read_text().splitlines()[0] + "\n")
    with pytest.raises(ValueError, match="Incomplete"):
        comparator.compare(base, student)


def test_changed_raw_evidence_rejected(paired_runs: tuple[Path, Path]) -> None:
    """Edited solver/model transcripts invalidate their earlier scores."""
    base, student = paired_runs
    journal = next(p for p in student.glob("*.jsonl") if p.name != "results.jsonl")
    journal.write_text("changed evidence\n")
    with pytest.raises(ValueError, match="Raw evidence"):
        comparator.compare(base, student)


def test_unequal_generation_budget_rejected(paired_runs: tuple[Path, Path]) -> None:
    """Additional attempts or tokens cannot silently improve one candidate."""
    base, student = paired_runs
    path = student / "summary.json"
    summary = json.loads(path.read_text())
    summary["max_tokens"] *= 2
    path.write_text(json.dumps(summary))
    with pytest.raises(ValueError, match="Unequal evaluation conditions"):
        comparator.compare(base, student)


def test_inflated_summary_rejected(paired_runs: tuple[Path, Path]) -> None:
    """The aggregate rate must agree with the individual scored outcomes."""
    base, student = paired_runs
    path = base / "summary.json"
    summary = json.loads(path.read_text())
    summary["pass_at_1"] = 1.0
    path.write_text(json.dumps(summary))
    with pytest.raises(ValueError, match="Summary disagrees"):
        comparator.compare(base, student)
