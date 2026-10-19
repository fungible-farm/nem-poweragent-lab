"""Candidate filtering for the M05 distillation work package.

Executes the teacher's candidate Python script in an isolated subprocess
(same venv, fresh process, bounded wall clock), parses its single-line JSON
answer, and runs an INDEPENDENT numerical check: the pandapower solver is
re-run on the same case at the candidate's claimed parameters, and the
re-computed quantity is compared against the task target. The solver is the
objective observation; the teacher's reasoning is never retained as truth.

Acceptance classes (the mission's rejected/quarantined distinction):
  accepted    -- the script ran, produced a parseable answer, and the
                 independent solver check passed within tolerance.
  rejected    -- the script ran and produced a parseable answer, but the
                 independent check FAILED (numerically wrong / out of range).
  quarantined -- the script could not be evaluated at all (non-zero exit,
                 timeout, or no parseable JSON answer).
"""
from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import pandapower as pp

from powercoder.inference import powermcp as pm
from powercoder.datasets import generate as gen

REPO_ROOT: Path = Path(__file__).resolve().parents[2]

# Case-file mapping (matches teacher.CASE_FILES and powermcp.CASE_FILES).
CASE_FILES: dict[str, str] = {
    "snem-sa-2000": "data/snemSA.m",
    "snem-1803": "data/snem1803.m",
}

# Wall-clock bound for one candidate execution. A correct script finishes in
# a few seconds (the solver is numba-warm); anything slower is treated as
# hung and quarantined rather than let it stall the batch.
EXEC_TIMEOUT_S: float = 180.0

# Tolerances for the independent check. Voltage/loading fields are compared
# with a small absolute tolerance (the solver is deterministic, so a correct
# answer reproduces the reference to far better than this); iteration counts
# and violation counts must match exactly.
VOLTAGE_FIELD_ATOL: float = 1e-3
LOADING_FIELD_ATOL: float = 1e-3

FIT_SUBFAMILIES: frozenset[str] = frozenset(
    {"pf-load-scale-fit", "pf-line-rating-fit", "pf-gen-dispatch-fit"}
)


@dataclass
class FilterResult:
    """Outcome of executing + independently checking one candidate."""

    status: str  # accepted / rejected / quarantined
    answer: Optional[Any]
    diagnostics: list[str] = field(default_factory=list)
    exec_ok: bool = False
    exec_returncode: Optional[int] = None
    exec_wall_s: float = 0.0
    exec_stdout: str = ""
    exec_stderr: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def is_accepted(self) -> bool:
        return self.status == "accepted"


def execute_candidate(code: str) -> dict[str, Any]:
    """Run `code` in a fresh subprocess of the current venv.

    The script is written to a temp file and run with cwd=REPO_ROOT so its
    relative `data/...` path resolves. The subprocess uses sys.executable so
    it runs in the SAME venv as the driver (pandapower/powerio available).
    """
    with tempfile.TemporaryDirectory(prefix="powercoder-m05-") as tmp:
        script = Path(tmp) / "candidate.py"
        script.write_text(code, encoding="utf-8")
        started = time.monotonic()
        try:
            proc = subprocess.run(
                [sys.executable, str(script)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=EXEC_TIMEOUT_S,
            )
            wall = time.monotonic() - started
            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": proc.stdout or "",
                "stderr": proc.stderr or "",
                "wall_s": wall,
                "timed_out": False,
            }
        except subprocess.TimeoutExpired as exc:
            wall = time.monotonic() - started
            return {
                "ok": False,
                "returncode": None,
                "stdout": (exc.stdout or b"").decode("utf-8", "replace")
                if isinstance(exc.stdout, bytes)
                else (exc.stdout or ""),
                "stderr": (exc.stderr or b"").decode("utf-8", "replace")
                if isinstance(exc.stderr, bytes)
                else (exc.stderr or ""),
                "wall_s": wall,
                "timed_out": True,
            }


def parse_answer(stdout: str) -> Optional[Any]:
    """Find the first stdout line that parses to a JSON object with 'answer'.

    The teacher is instructed to print exactly one such line; we are lenient
    about leading/trailing noise but strict about the shape.
    """
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "answer" in obj:
            return obj["answer"]
    return None


def _parse_element(element: str) -> tuple[str, int, Optional[int]]:
    """Parse 'bus <id>' / 'line <id>' / 'generator <id> (transformer <id>)'.

    Returns (kind, primary_id, secondary_id) where kind is one of
    {'bus','line','gen'} and secondary_id is the transformer id for 'gen'.
    """
    m = re.match(r"bus\s+(\d+)", element)
    if m:
        return "bus", int(m.group(1)), None
    m = re.match(r"line\s+(\d+)", element)
    if m:
        return "line", int(m.group(1)), None
    m = re.match(r"generator\s+(\d+)\s*\(transformer\s+(\d+)\)", element)
    if m:
        return "gen", int(m.group(1)), int(m.group(2))
    raise ValueError(f"unrecognised element grammar: {element!r}")


# Cache of base networks per case. pm._load_network_object is expensive
# (~40s for snem-sa-2000: powerio parse + gridfit.load_case), and the filter
# re-solves every candidate against the same base. The M04 modifiers deepcopy
# the base before mutating it, so a shared cached base is safe. Caching cuts
# ~40s off every filter re-solve (the dominant hidden cost in a batch run).
_BASE_NET_CACHE: dict[str, Any] = {}


def _get_base_net(case: str) -> Any:
    """Return the cached base network for a case, loading it on first use."""
    if case not in _BASE_NET_CACHE:
        _BASE_NET_CACHE[case] = pm._load_network_object(case)[0]
    return _BASE_NET_CACHE[case]


def _check_fit(example: dict[str, Any], answer: Any) -> tuple[bool, dict[str, Any], list[str]]:
    """Independently re-solve a fit task at the candidate's scale_factor."""
    inputs = example["task"]["inputs"]
    subfamily = example["subfamily"]
    case = inputs["case"]
    element = inputs["element"]
    target = float(inputs["target"])
    tolerance = float(inputs["tolerance"])
    scale_lo = float(inputs["scale_lo"])
    scale_hi = float(inputs["scale_hi"])

    diags: list[str] = []
    if not isinstance(answer, dict) or "scale_factor" not in answer:
        return False, {}, ["answer must be an object with 'scale_factor'"]
    s = float(answer["scale_factor"])

    if not (scale_lo <= s <= scale_hi):
        diags.append(
            f"scale_factor {s} outside search interval [{scale_lo}, {scale_hi}]"
        )

    kind, primary, secondary = _parse_element(element)
    base_net = _get_base_net(case)
    if subfamily == "pf-load-scale-fit":
        modifier = gen._modifier_load_scale
        reader = gen._reader_bus_voltage(primary)
    elif subfamily == "pf-line-rating-fit":
        modifier = gen._make_modifier_line_rating(primary)
        reader = gen._reader_line_loading(primary)
    else:  # pf-gen-dispatch-fit
        modifier = gen._make_modifier_gen_dispatch(primary)
        reader = gen._reader_trafo_loading(secondary)

    net = modifier(base_net, s)
    try:
        iters, vm_min, vm_max, viol = gen._solve(net)
    except pp.LoadflowNotConverged:
        diags.append(f"power flow did not converge at scale_factor={s}")
        return False, {"scale_factor": s, "converged": False}, diags
    except Exception as exc:  # execution failure
        diags.append(f"solver raised {type(exc).__name__}: {exc} at s={s}")
        return False, {"scale_factor": s, "converged": False}, diags

    metric = reader(net)
    residual = abs(metric - target)
    within = residual <= tolerance
    evidence = {
        "scale_factor": s,
        "metric": metric,
        "target": target,
        "residual": residual,
        "within_tolerance": within,
        "converged": True,
        "iterations": iters,
        "vm_min_pu": vm_min,
        "vm_max_pu": vm_max,
        "voltage_violations": viol,
    }
    if not within:
        diags.append(
            f"independent check: |metric - target| = {residual:.6f} > "
            f"tolerance {tolerance} (metric={metric:.6f}, target={target:.6f})"
        )
    return within, evidence, diags


def _check_pf_report(example: dict[str, Any], answer: Any) -> tuple[bool, dict[str, Any], list[str]]:
    """Independently re-solve a pf-report task and compare the fields."""
    inputs = example["task"]["inputs"]
    case = inputs["case"]
    contingency = inputs.get("contingency_line")

    diags: list[str] = []
    if not isinstance(answer, dict):
        return False, {}, ["answer must be an object"]

    base_net = _get_base_net(case)
    net = copy.deepcopy(base_net)
    if contingency is not None:
        net.line = net.line.drop(index=int(contingency))

    try:
        iters, vm_min, vm_max, viol = gen._solve(net)
    except pp.LoadflowNotConverged:
        converged, iters, vm_min, vm_max, viol = False, 0, float("nan"), float("nan"), 0
    except Exception:
        converged, iters, vm_min, vm_max, viol = False, 0, float("nan"), float("nan"), 0
    else:
        converged = True
    max_loading = gen._max_line_loading(net) if converged else float("nan")

    reference = {
        "converged": converged,
        "iterations": iters,
        "min_bus_voltage_pu": vm_min,
        "max_bus_voltage_pu": vm_max,
        "max_line_loading_percent": max_loading,
        "voltage_violations": viol,
    }

    def close(key: str, atol: float) -> bool:
        ref = reference[key]
        cand = answer.get(key)
        if cand is None:
            return False
        try:
            return abs(float(cand) - float(ref)) <= atol
        except (TypeError, ValueError):
            return False

    ok = True
    if bool(answer.get("converged")) != converged:
        ok = False
        diags.append(f"converged mismatch: candidate={answer.get('converged')} reference={converged}")
    if converged:
        if int(answer.get("iterations", -1)) != iters:
            ok = False
            diags.append(f"iterations mismatch: candidate={answer.get('iterations')} reference={iters}")
        for key, atol in (
            ("min_bus_voltage_pu", VOLTAGE_FIELD_ATOL),
            ("max_bus_voltage_pu", VOLTAGE_FIELD_ATOL),
            ("max_line_loading_percent", LOADING_FIELD_ATOL),
        ):
            if not close(key, atol):
                ok = False
                diags.append(f"{key} mismatch: candidate={answer.get(key)} reference={reference[key]}")
        if int(answer.get("voltage_violations", -1)) != viol:
            ok = False
            diags.append(f"voltage_violations mismatch: candidate={answer.get('voltage_violations')} reference={viol}")

    evidence = {"reference": reference, "candidate": answer}
    return ok, evidence, diags


def _check_mcp_trajectory(example: dict[str, Any], answer: Any) -> tuple[bool, dict[str, Any], list[str]]:
    """Independently re-run the MCP tool sequence and compare the outcome."""
    inputs = example["task"]["inputs"]
    case = inputs["case"]
    expected_status = example["expected"]["structured"]["trajectory"][-1]["status"]

    diags: list[str] = []
    if not isinstance(answer, dict) or "trajectory" not in answer:
        return False, {}, ["answer must be an object with 'trajectory'"]
    trajectory = answer["trajectory"]
    if not isinstance(trajectory, list) or not trajectory:
        return False, {}, ["trajectory must be a non-empty list"]

    tools = [step.get("tool") for step in trajectory if isinstance(step, dict)]
    if "load_network" not in tools or "run_power_flow" not in tools:
        diags.append(f"trajectory missing required tools; got {tools}")
        return False, {"tools": tools}, diags

    # Independent re-run through the canonical PowerMCP layer.
    mcp = pm.PowerMCP()
    try:
        mcp.load_network(case)
        result = mcp.run_power_flow(
            case,
            method="nr",
            max_iter=int(inputs.get("max_iter", 50)),
            check_limits=bool(inputs.get("check_limits", True)),
        )
        actual_status = result.status.value
    except Exception as exc:
        diags.append(f"independent re-run raised {type(exc).__name__}: {exc}")
        return False, {"tools": tools}, diags

    matches = actual_status == expected_status
    if not matches:
        diags.append(
            f"final status mismatch: candidate={expected_status} "
            f"independent={actual_status}"
        )
    evidence = {
        "tools": tools,
        "n_steps": len(trajectory),
        "independent_status": actual_status,
        "expected_status": expected_status,
        "matches": matches,
    }
    return matches, evidence, diags


def filter_example(example: dict[str, Any], code: str) -> FilterResult:
    """Execute a candidate and independently verify it.

    Args:
        example: an M04 training example (task + expected + subfamily).
        code: the teacher's candidate Python script.

    Returns:
        A FilterResult with status in {accepted, rejected, quarantined}, the
        parsed answer, diagnostics, and the independent-check evidence.
    """
    exec_info = execute_candidate(code)
    if not exec_info["ok"]:
        reason = "timeout" if exec_info["timed_out"] else f"exit {exec_info['returncode']}"
        return FilterResult(
            status="quarantined",
            answer=None,
            diagnostics=[
                f"execution failed ({reason}) after {exec_info['wall_s']:.2f}s",
                exec_info["stderr"].strip()[-2000:],
            ],
            exec_ok=False,
            exec_returncode=exec_info["returncode"],
            exec_wall_s=exec_info["wall_s"],
            exec_stdout=exec_info["stdout"],
            exec_stderr=exec_info["stderr"],
        )

    answer = parse_answer(exec_info["stdout"])
    if answer is None:
        return FilterResult(
            status="quarantined",
            answer=None,
            diagnostics=[
                "no parseable JSON answer on stdout",
                exec_info["stdout"].strip()[-2000:],
            ],
            exec_ok=True,
            exec_returncode=exec_info["returncode"],
            exec_wall_s=exec_info["wall_s"],
            exec_stdout=exec_info["stdout"],
            exec_stderr=exec_info["stderr"],
        )

    subfamily = example["subfamily"]
    if subfamily in FIT_SUBFAMILIES:
        ok, evidence, diags = _check_fit(example, answer)
    elif subfamily == "pf-report":
        ok, evidence, diags = _check_pf_report(example, answer)
    elif subfamily == "mcp-trajectory":
        ok, evidence, diags = _check_mcp_trajectory(example, answer)
    else:
        ok, evidence, diags = False, {}, [f"unknown subfamily {subfamily!r}"]

    return FilterResult(
        status="accepted" if ok else "rejected",
        answer=answer,
        diagnostics=diags,
        exec_ok=True,
        exec_returncode=exec_info["returncode"],
        exec_wall_s=exec_info["wall_s"],
        exec_stdout=exec_info["stdout"],
        exec_stderr=exec_info["stderr"],
        evidence=evidence,
    )
