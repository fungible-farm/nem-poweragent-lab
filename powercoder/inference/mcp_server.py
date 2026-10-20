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


def create_server(study_tools: bool = False) -> Server:
    """Expose canonical schemas and real solver outcomes through SDK transport."""
    backend = PowerMCP()
    server = Server("powercoder-canonical")
    schemas = backend.get_tool_schemas()
    if study_tools:
        from powercoder.inference.studies import tool_schema

        schemas.append(tool_schema())

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Reuse the canonical schemas rather than duplicate their constraints."""
        return [
            Tool(name=f["name"], description=f["description"], inputSchema=f["parameters"])
            for schema in schemas
            for f in [schema["function"]]
        ]

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
        return [TextContent(type="text", text=json.dumps(asdict(result), allow_nan=False))]

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
