"""Study-trial responses must not mislead a model about contingencies or status."""

from __future__ import annotations

from powercoder.inference import powermcp as pm
from powercoder.inference.studies import base_case_voltage_violations, run_study_trial, tool_schema

# fixture-2bus-ok has a bus 1 load and no voltage violations, so it runs in milliseconds.
NETWORK: str = "fixture-2bus-ok"


def trial(**overrides: object) -> pm.PowerMCPResult:
    """Run one load-scale trial on the 2-bus fixture, observing bus 1."""
    arguments: dict = {"network_id": NETWORK, "operation": "load_scale", "scale": 1.0, "element_id": 1,
                       "observation": "bus_voltage", "observation_id": 1, "max_iter": 20}
    return run_study_trial(**(arguments | overrides))


def test_contingency_line_is_optional_and_the_intact_network_is_named() -> None:
    """Omitting contingency_line studies the intact network and says so (FM-18)."""
    assert "contingency_line" not in tool_schema()["function"]["parameters"]["required"]
    result = trial()
    assert result.data["study"]["contingency_line"] is None
    assert result.data["contingency"] == "none (intact network)"


def test_trial_reports_the_base_case_violations_and_a_valid_metric() -> None:
    """A converged trial carries the unmodified case's violation count (FM-17)."""
    result = trial(scale=0.95)
    assert result.status is pm.ExecutionStatus.SUCCESS
    assert result.data["metric_valid"] is True
    assert result.data["base_case_voltage_violations"] == base_case_voltage_violations(NETWORK) == 0
