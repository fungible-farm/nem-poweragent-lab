"""Serve the canonical two-tool PowerMCP contract using the official MCP SDK.

This stdio endpoint wraps this repository's four-state contract. The existing
kube/powermcp_serve_http.py instead serves upstream Power-Agent's eight tools;
the two endpoints must not be treated as interchangeable.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from powercoder.inference.powermcp import PowerMCP

# Wall-clock fields vary run to run; fed back to a greedy model they changed
# its next turn, making identical attempts diverge (AGENTS.md FM-3).
MODEL_HIDDEN_FIELDS: frozenset[str] = frozenset({"execution_time_s"})


def tool_definitions(study_tools: bool = False) -> list[Tool]:
    """The tools this server lists; the latency benchmark sends the same list."""
    schemas = PowerMCP().get_tool_schemas()
    if study_tools:
        from powercoder.inference.studies import tool_schema

        schemas.append(tool_schema())
    return [Tool(name=f["name"], description=f["description"], inputSchema=f["parameters"])
            for schema in schemas for f in [schema["function"]]]


def create_server(study_tools: bool = False) -> Server:
    """Expose canonical schemas and real solver outcomes through SDK transport."""
    backend = PowerMCP()
    server = Server("powercoder-canonical")
    tools = tool_definitions(study_tools)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Reuse the canonical schemas rather than duplicate their constraints."""
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Return actual solver data and evidence; stdout belongs to the SDK."""
        import json

        # Serialize backend access: its iteration observer temporarily patches
        # pandapower's NR function and must not run concurrently in one process.
        if study_tools and name == "run_study_trial":
            from powercoder.inference.studies import run_study_trial

            result = run_study_trial(**arguments)
        else:
            result = backend.execute_tool(name, arguments)
        visible = {k: v for k, v in asdict(result).items() if k not in MODEL_HIDDEN_FIELDS}
        return [TextContent(type="text", text=json.dumps(visible, allow_nan=False))]

    return server


async def serve(study_tools: bool = False) -> None:
    """Run the SDK's standard parent-process pipe lifecycle."""
    server = create_server(study_tools)
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-tools", action="store_true")
    asyncio.run(serve(parser.parse_args().study_tools))
