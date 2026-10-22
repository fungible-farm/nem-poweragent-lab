"""Bounded, stateless AC study trials for model-driven parameter fitting.

Only case identifiers and numeric study parameters are accepted, never code or
paths. Each call loads a fresh network. No target, reference answer, search
algorithm, or training/benchmark dataset is available to this module.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from functools import lru_cache
from typing import Any

import pandapower as pp

from powercoder.inference import powermcp as pm

# Match the existing fitting task interval; cap solver effort for tool calls.
SCALE_MIN: float = 0.9
SCALE_MAX: float = 1.1
MAX_ITERATIONS: int = 100
# Nameplate loading screening, in percent; not a full operational safety study.
THERMAL_LIMIT_PERCENT: float = 100.0


def tool_schema() -> dict[str, Any]:
    """Describe measurements and modifications without exposing a solution oracle."""
    return {"type": "function", "function": {
        "name": "run_study_trial",
        "description": (
            "Run one fresh Newton-Raphson AC trial. load_scale multiplies ALL loads' P/Q "
            "and observes bus_voltage; line_rating scales one line max_i_ka and observes "
            "line_loading; gen_dispatch scales one generator P and observes trafo_loading. "
            "Use operation=none for base/N-1 reports. Returns actual measurements, not a fitted answer. "
            "element_id selects the modified line/generator (unused for all-load scaling). "
            "observation_id selects the observed bus/line/transformer. "
            "Omit contingency_line (or pass null) for the intact network; an integer takes that "
            "line out of service, and 0 is a real line. "
            "status=constraint_violation with metric_valid=true is still a usable measurement: "
            "compare voltage_violations with base_case_voltage_violations, which the unmodified "
            "case already has."
        ),
        "parameters": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "network_id": {"type": "string", "enum": list(pm.CASE_FILES) + list(pm.FIXTURE_BUILDERS)},
                "operation": {"type": "string", "enum": ["none", "load_scale", "line_rating", "gen_dispatch"]},
                "scale": {"type": "number", "minimum": SCALE_MIN, "maximum": SCALE_MAX},
                "element_id": {"type": "integer"},
                "observation": {"type": "string", "enum": ["bus_voltage", "line_loading", "trafo_loading"]},
                "observation_id": {"type": "integer"},
                "contingency_line": {"type": ["integer", "null"]},
                "max_iter": {"type": "integer", "minimum": 1, "maximum": MAX_ITERATIONS},
            },
            # contingency_line is optional: when it was required, models filled it with 0
            # (line 0 out) or "None" to mean "no contingency" (AGENTS.md FM-7, FM-18).
            "required": ["network_id", "operation", "scale", "element_id", "observation", "observation_id", "max_iter"],
        },
    }}


@lru_cache(maxsize=None)
def base_case_voltage_violations(network_id: str) -> int | None:
    """Count bus-voltage band violations in the unmodified, intact case.

    snem-sa-2000 already has 39 such buses, so every trial on it is
    ``constraint_violation`` whatever the trial value (AGENTS.md FM-17). Reporting
    the base count lets a model tell an inherited violation from one its trial
    caused, without weakening the canonical status contract. Cached because each
    MCP server process serves one attempt and the case files never change.

    Returns:
        The violation count, or None when the unmodified case does not converge
        (a converged trial on such a case must not be reported as non-convergence).
    """
    net, _ = pm._load_network_object(network_id)
    try:
        pm._runpp_counted(net, numba=True, max_iteration=MAX_ITERATIONS)
    except pp.LoadflowNotConverged:
        return None
    vm = net.res_bus.vm_pu
    return int(((vm < pm.VOLTAGE_LIMIT_LOW_PU) | (vm > pm.VOLTAGE_LIMIT_HIGH_PU)).sum())


def run_study_trial(
    network_id: str, operation: str, scale: float, element_id: int,
    observation: str, observation_id: int, max_iter: int,
    contingency_line: int | None = None,
) -> pm.PowerMCPResult:
    """Apply one explicit perturbation and measure a real, independently solved network.

    Non-convergence and numerical failure never return usable metric values.
    Physical validity covers bus voltage and line/transformer nameplate screening
    only; convergence does not establish operational safety.
    """
    arguments = dict(locals())
    start = time.monotonic()
    try:
        if isinstance(scale, bool) or not isinstance(scale, (float, int)) or not math.isfinite(scale) or not SCALE_MIN <= scale <= SCALE_MAX:
            raise ValueError("scale must be finite and within the declared interval")
        for value in (element_id, observation_id, max_iter):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError("element/observation IDs and max_iter must be integers")
        if not 1 <= max_iter <= MAX_ITERATIONS:
            raise ValueError("max_iter outside the declared budget")
        if contingency_line is not None and (isinstance(contingency_line, bool) or not isinstance(contingency_line, int)):
            raise ValueError("contingency_line must be an integer or null")
        expected = {"load_scale": "bus_voltage", "line_rating": "line_loading", "gen_dispatch": "trafo_loading"}
        if operation not in {"none", *expected} or observation not in {"bus_voltage", "line_loading", "trafo_loading"}:
            raise ValueError("Unknown operation or observation")
        if operation != "none" and observation != expected[operation]:
            raise ValueError("Observation incompatible with modification")
        if operation == "none" and scale != 1.0:
            raise ValueError("operation=none requires scale=1")
        net, case_hash = pm._load_network_object(network_id)
        table, column = {"bus_voltage": ("res_bus", "vm_pu"), "line_loading": ("res_line", "loading_percent"), "trafo_loading": ("res_trafo", "loading_percent")}[observation]
        element_table = {"bus_voltage": "bus", "line_loading": "line", "trafo_loading": "trafo"}[observation]
        if observation_id not in net[element_table].index:
            raise ValueError("Unknown observation element")
        if operation == "load_scale":
            net.load.loc[:, ["p_mw", "q_mvar"]] *= scale
        elif operation in {"line_rating", "gen_dispatch"}:
            modified_table, modified_column = ("line", "max_i_ka") if operation == "line_rating" else ("gen", "p_mw")
            if element_id not in net[modified_table].index:
                raise ValueError("Unknown modification element")
            net[modified_table].loc[element_id, modified_column] *= scale
        if contingency_line is not None:
            if contingency_line not in net.line.index:
                raise ValueError("Unknown contingency line")
            net.line.loc[contingency_line, "in_service"] = False
        iterations = pm._runpp_counted(net, numba=True, max_iteration=max_iter)
        vm = net.res_bus.vm_pu
        if not all(math.isfinite(float(value)) for value in vm[net.bus.in_service]):
            raise ValueError("Unsolved or nonfinite voltage on an in-service bus")
        voltage_violations = int(((vm < pm.VOLTAGE_LIMIT_LOW_PU) | (vm > pm.VOLTAGE_LIMIT_HIGH_PU)).sum())
        line_loading = float(net.res_line.loading_percent.max()) if len(net.line) else 0.0
        trafo_loading = float(net.res_trafo.loading_percent.max()) if len(net.trafo) else 0.0
        data = {
            "study": arguments, "converged": True, "iterations": iterations,
            "metric": float(net[table].loc[observation_id, column]),
            "metric_unit": "pu" if observation == "bus_voltage" else "percent",
            "min_bus_voltage_pu": float(vm.min()), "max_bus_voltage_pu": float(vm.max()),
            "voltage_violations": voltage_violations,
            "base_case_voltage_violations": base_case_voltage_violations(network_id),
            "metric_valid": True,
            "contingency": f"line {contingency_line} out of service" if contingency_line is not None else "none (intact network)",
            "max_line_loading_percent": line_loading, "max_trafo_loading_percent": trafo_loading,
            "voltage_limit_pu": [pm.VOLTAGE_LIMIT_LOW_PU, pm.VOLTAGE_LIMIT_HIGH_PU],
            "thermal_limit_percent": THERMAL_LIMIT_PERCENT,
            "physical_scope": "bus voltage band and line/transformer nameplate loading only",
        }
        for value in (data["metric"], data["min_bus_voltage_pu"], data["max_bus_voltage_pu"], line_loading, trafo_loading):
            if not math.isfinite(value):
                raise ValueError("Nonfinite solver measurement")
        valid = not voltage_violations and max(line_loading, trafo_loading) <= THERMAL_LIMIT_PERCENT
        status = pm.ExecutionStatus.SUCCESS if valid else pm.ExecutionStatus.CONSTRAINT_VIOLATION
        source = json.dumps({"case_hash": case_hash, "arguments": arguments}, sort_keys=True)
        evidence = pm.PowerMCP._canonical_evidence(
            case_id=network_id, tool_name="run_study_trial",
            input_hash="sha256:" + hashlib.sha256(source.encode()).hexdigest(),
            status=status, result_payload=data, diagnostics=[], physical_valid=valid,
        )
        return pm.PowerMCPResult(status, data, execution_time_s=time.monotonic() - start, evidence=evidence)
    except pp.LoadflowNotConverged as error:
        return pm.PowerMCPResult(pm.ExecutionStatus.NON_CONVERGENCE, error=str(error), execution_time_s=time.monotonic() - start)
    except Exception as error:  # noqa: BLE001 -- preserve actual backend failures as explicit outcomes
        return pm.PowerMCPResult(pm.ExecutionStatus.EXECUTION_FAILURE, error=f"{type(error).__name__}: {error}", execution_time_s=time.monotonic() - start)
