"""Stored trajectories must render exactly the prompt the evaluation serves."""

from __future__ import annotations

import json
from pathlib import Path

from powercoder.datasets.trajectories import write_in_order
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
