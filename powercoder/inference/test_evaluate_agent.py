"""Adversarial evidence gates for the model-controlled domain benchmark."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from powercoder.inference.evaluate_agent import grade, relevant_evidence


@pytest.fixture
def task() -> dict:
    """A named small input isolates evidence binding without running inference."""
    return {"example_id": "evidence-test", "subfamily": "pf-line-rating-fit",
            "task": {"inputs": {"case": "snem-sa-2000", "element": "line 36"}}}


def observation(**overrides: object) -> dict:
    """Build a controller response envelope; these values claim no real physics."""
    study = {"network_id": "snem-sa-2000", "operation": "line_rating", "scale": 1.0,
             "element_id": 36, "observation": "line_loading", "observation_id": 36,
             "contingency_line": None}
    study.update(overrides)
    return {"kind": "tool_response", "payload": {"result": {"isError": False,
            "content": [{"type": "text", "text": json.dumps({"status": "constraint_violation",
                         "data": {"study": study, "converged": True}})}]}}}


def test_evidence_must_bind_final_scale_case_element_and_contingency(task: dict) -> None:
    """A real call for a different study cannot substantiate a guessed answer."""
    assert relevant_evidence(task, "1.0", [observation()])
    for change in ({"scale": 1.1}, {"network_id": "other-case"},
                   {"element_id": 37}, {"observation_id": 37},
                   {"operation": "load_scale"}, {"contingency_line": 36}):
        assert not relevant_evidence(task, "1.0", [observation(**change)])
    assert not relevant_evidence(task, "1.0", [])


def test_nonconverged_and_mcp_errors_never_supply_evidence(task: dict) -> None:
    """Transport validation and solver failure must not count as measurements."""
    event = observation()
    event["payload"]["result"]["isError"] = True
    assert not relevant_evidence(task, "1.0", [event])
    event = observation()
    event["payload"]["result"]["content"][0]["text"] = json.dumps({"status": "non_convergence"})
    assert not relevant_evidence(task, "1.0", [event])


def test_truncated_correct_answer_cannot_pass(tmp_path: Path) -> None:
    """An exact report in an unfinished generation remains a failed attempt."""
    answer = "Power flow converged in 5 iterations. Min bus voltage = 0.9070 pu, max bus voltage = 1.0941 pu, max line loading = 2.66%, voltage violations = 39."
    task = {"example_id": "report-test", "subfamily": "pf-report",
            "task": {"inputs": {"case": "snem-sa-2000"}}, "expected": {"answer": answer}}
    events = [observation(operation="none"),
              {"kind": "model_response", "payload": {"choices": [{"message": {"content": answer}}]}},
              {"kind": "terminal", "payload": {"state": "incomplete_generation"}}]
    journal = tmp_path / "journal.jsonl"
    journal.write_text("".join(json.dumps(e) + "\n" for e in events))
    result = grade(task, journal)
    assert result["numerical_pass"] and result["tool_evidence_pass"]
    assert not result["passed"]
