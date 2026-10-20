"""Serve the canonical two-tool PowerMCP contract using the official MCP SDK.

This stdio endpoint wraps this repository's four-state contract. The existing
kube/powermcp_serve_http.py instead serves upstream Power-Agent's eight tools;
the two endpoints must not be treated as interchangeable.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from powercoder.inference.powermcp import PowerMCP


def create_server() -> Server:
    """Expose canonical schemas and real solver outcomes through SDK transport."""
    backend = PowerMCP()
    server = Server("powercoder-canonical")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Reuse the canonical schemas rather than duplicate their constraints."""
        return [
            Tool(name=f["name"], description=f["description"], inputSchema=f["parameters"])
            for schema in backend.get_tool_schemas()
            for f in [schema["function"]]
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Return actual solver data and evidence; stdout belongs to the SDK."""
        import json

        # Serialize backend access: its iteration observer temporarily patches
        # pandapower's NR function and must not run concurrently in one process.
        result = backend.execute_tool(name, arguments)
        return [TextContent(type="text", text=json.dumps(asdict(result), allow_nan=False))]

    return server


async def serve() -> None:
    """Run the SDK's standard parent-process pipe lifecycle."""
    server = create_server()
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(serve())
