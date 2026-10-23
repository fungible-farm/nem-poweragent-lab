"""Stored trajectories must render exactly the prompt the evaluation serves."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from powercoder.datasets import trajectories
from powercoder.datasets.trajectories import write_in_order
from powercoder.inference import powermcp as pm
from powercoder.inference.mcp_server import tool_definitions


def served_tools() -> list[dict]:
    """The tool list exactly as tool_probe builds it from the MCP server."""
    return [{"type": "function", "function": {"name": t.name, "description": t.description,
                                              "parameters": t.inputSchema}}
            for t in tool_definitions(study_tools=True)]


def test_stored_tools_keep_the_served_key_order(tmp_path: Path) -> None:
    """Sorted keys changed every tool block the students were trained on (FM-23)."""
    tools = served_tools()
    path = write_in_order(tmp_path / "t.jsonl", [{"example_id": "e", "subfamily": "pf-report", "fault": None,
                                                  "tools": tools, "messages": []}])
    stored = json.loads(path.read_text())["tools"]
    assert json.dumps(stored) == json.dumps(tools)
    assert list(stored[0]) == ["type", "function"] and list(stored[0]["function"])[0] == "name"


CASE: str = "snem-sa-2000"


@pytest.mark.skipif(not (pm.REPO_ROOT / pm.CASE_FILES[CASE]).exists(),
                    reason="needs data/ (scripts/fetch_csiro_nem_data.py)")
def test_unknown_bus_recovery_uses_the_id_the_error_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The corrected call observes the bus the tool's error named, and the trajectory still grades."""
    row = {"example_id": "ex_unknown_bus", "subfamily": "pf-report", "lifecycle": {"split": "train"},
           "task": {"prompt": f"Run an AC power flow on case '{CASE}' with line 94 out of service (N-1 contingency) "
                              "and report the result.", "inputs": {"case": CASE, "contingency_line": 94}}}
    journals = tmp_path / "journals"
    journals.mkdir()
    # Grading needs the row's reference; the full build grades every kept row with grade().
    monkeypatch.setattr(trajectories, "grade", lambda _row, _journal: {"passed": True})
    trajectory, reason = asyncio.run(trajectories.build(row, journals, "unknown_bus"))
    assert reason == "kept"
    calls = [m for m in trajectory["messages"] if m["role"] == "assistant" and m.get("tool_calls")]
    first, second = (json.loads(m["tool_calls"][0]["function"]["arguments"]) for m in calls)
    valid = trajectories.first_bus(CASE)
    assert first["observation_id"] == valid - trajectories.UNKNOWN_BUS_OFFSET
    assert second["observation_id"] == valid and second["contingency_line"] == 94
    error = json.loads(json.loads(trajectory["messages"][3]["content"])["content"][0]["text"])["error"]
    assert f"ids are {valid}," in error and calls[1]["content"] == trajectories.RECOVERY_NOTES["unknown_bus"].format(
        bad=first["observation_id"], valid=valid)


def test_unknown_bus_is_added_to_report_recovery_rows_not_swapped_in() -> None:
    """Adding the variant keeps every earlier trajectory; fits get no extra variant."""
    report = {"subfamily": "pf-report", "task": {"inputs": {"contingency_line": 3}}}
    assert [trajectories.fault_for(report, index) for index in (0, 2)] == ["run_power_flow_contingency"] * 2
    assert trajectories.extra_faults(report) == ["unknown_bus"]
    assert trajectories.extra_faults({"subfamily": "pf-load-scale-fit"}) == []


@pytest.mark.skipif(not (pm.REPO_ROOT / pm.CASE_FILES[CASE]).exists(),
                    reason="needs data/ (scripts/fetch_csiro_nem_data.py)")
def test_with_namespace_tools_the_unknown_bus_recovery_lists_buses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Backlog 0026: refused id -> ls the buses -> the first listed id, which report() observes."""
    row = {"example_id": "ex_unknown_bus_ls", "subfamily": "pf-report", "lifecycle": {"split": "train"},
           "task": {"prompt": f"Run an AC power flow on case '{CASE}' and report the result.", "inputs": {"case": CASE}}}
    journals = tmp_path / "journals"
    journals.mkdir()
    monkeypatch.setattr(trajectories, "grade", lambda _row, _journal: {"passed": True})
    trajectory, reason = asyncio.run(trajectories.build(row, journals, "unknown_bus", namespace=True))
    assert reason == "kept"
    calls = [(m["tool_calls"][0]["function"]["name"], json.loads(m["tool_calls"][0]["function"]["arguments"]), m["content"])
             for m in trajectory["messages"] if m["role"] == "assistant" and m.get("tool_calls")]
    valid = trajectories.first_bus(CASE)
    assert [name for name, _, _ in calls] == ["run_study_trial", "ls", "run_study_trial"]
    assert calls[1][1] == {"path": f"/case/{CASE}/bus"} and calls[2][1]["observation_id"] == valid
    assert calls[2][2] == trajectories.RECOVERY_NOTES["unknown_bus_listed"].format(valid=valid)
    assert [t["function"]["name"] for t in trajectory["tools"]][-2:] == ["ls", "get"]
