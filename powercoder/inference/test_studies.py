"""Study-trial responses must not mislead a model about contingencies or status."""

from __future__ import annotations

import pytest

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


# snem-sa-2000 line 60: an N-1 outage that isolates buses (FM-25). Measured
# 2026-10-23; the reference solver reports the contingency as converged.
ISOLATING_LINE: int = 60
CASE: str = "snem-sa-2000"


@pytest.mark.skipif(not (pm.REPO_ROOT / pm.CASE_FILES[CASE]).exists(),
                    reason="needs data/ (scripts/fetch_csiro_nem_data.py)")
def test_an_outage_that_isolates_buses_is_a_valid_study_with_them_listed() -> None:
    """De-energized buses are listed and skipped, as the reference solver does, not a failure."""
    net, _ = pm._load_network_object(CASE)
    result = run_study_trial(network_id=CASE, operation="none", scale=1.0, element_id=0, observation="bus_voltage",
                             observation_id=int(min(net.bus.index)), max_iter=50, contingency_line=ISOLATING_LINE)
    assert result.status in {pm.ExecutionStatus.SUCCESS, pm.ExecutionStatus.CONSTRAINT_VIOLATION}
    assert result.data["de_energized_buses"] > 0 and result.data["de_energized_bus_ids"]
    assert result.data["converged"] and result.data["min_bus_voltage_pu"] > 0


def test_an_intact_network_response_has_no_de_energized_fields() -> None:
    """Responses without isolation stay byte-identical to the trained ones."""
    assert "de_energized_buses" not in trial().data
