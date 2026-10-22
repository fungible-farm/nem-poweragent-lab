"""Numbers in an answer must come from this attempt's tool responses or its prompt."""

from __future__ import annotations

import json

from powercoder.inference.provenance import check, printed_tolerance

PROMPT: str = ("Run an AC power flow on case 'snem-sa-2000' with line 208 out of service (N-1 contingency) "
               "and report the result.")
SOLVED: list[dict] = [{"kind": "tool_response", "payload": {"result": {"content": [{"type": "text", "text": json.dumps(
    {"status": "constraint_violation", "data": {"iterations": 5, "min_bus_voltage_pu": 0.9069716219,
     "max_bus_voltage_pu": 1.09411, "max_line_loading_percent": 2.661366, "voltage_violations": 39}})}]}}}]
ANSWER: str = ("Power flow on 'snem-sa-2000' with line 208 out of service (N-1 contingency) converged in 5 "
               "iterations. Min bus voltage = 0.9070 pu, max bus voltage = 1.0941 pu, max line loading = 2.66%, "
               "voltage violations = 39.")


def test_a_reference_report_built_from_the_tool_response_is_traced() -> None:
    """Rounded solver values, prompt ids and 'N-1' all trace."""
    assert check(ANSWER, SOLVED, PROMPT) == {"numbers": ["2000", "208", "1", "5", "0.9070", "1.0941", "2.66", "39"],
                                             "untraced": [], "traced": True}


def test_the_same_answer_without_a_tool_call_is_fabricated() -> None:
    """The first r6 Qwen student's failure: right shape, no solver behind it."""
    result = check(ANSWER, [], PROMPT)
    assert not result["traced"] and result["untraced"] == ["5", "0.9070", "1.0941", "2.66", "39"]


def test_a_value_off_by_more_than_its_printed_precision_is_untraced() -> None:
    """0.9071 is not 0.90697 at four decimals."""
    assert check("Min bus voltage = 0.9071 pu", SOLVED, PROMPT)["untraced"] == ["0.9071"]


def test_printed_tolerance_is_half_a_unit_in_the_last_digit() -> None:
    assert printed_tolerance("1.0941") == 0.5e-4 and printed_tolerance("39") == 0.5


def test_digits_inside_evidence_hashes_do_not_trace() -> None:
    """'5' must not trace to the hex digits of a sha256 evidence hash."""
    hashed = [{"kind": "tool_response", "payload": {"result": {"content": [{"type": "text", "text": json.dumps(
        {"evidence": {"input_hash": "sha256:146f5102"}})}]}}}]
    assert check("converged in 5 iterations", hashed, "")["untraced"] == ["5"]
