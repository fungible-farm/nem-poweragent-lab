"""HTTP transport wrapper for PowerMCP's pandapower MCP server.

Why this file exists (a named sandbox stand-in, per AGENTS.md's rule): the
installed `powermcp` package (https://github.com/Power-Agent/PowerMCP) only
ships one launch path for its pandapower tool server --
`pandapower/panda_mcp.py`'s own `if __name__ == "__main__": mcp.run(transport
="stdio")` -- which the `powermcp run pandapower` CLI (powermcp/runner.py's
`_launch_script`) executes verbatim via `runpy.run_path(..., run_name=
"__main__")`. stdio is a parent-process-pipe transport; it cannot be dialled
from outside the pod, so `podman kube play`'s "start it, then make a
`list_tools` call against it from a separate process" requirement (this
repo's docs/DEFINITION_OF_DONE.md Composition section) is unreachable via the
CLI as shipped. This script does NOT modify PowerMCP's source. It instead:

1. Locates the real, installed `panda_mcp.py` via `powermcp`'s own registry
   (the same file the CLI would run), using the public
   `powermcp.registry.get_tool("pandapower").resolve_entry_script()` API.
2. Executes that file with `runpy.run_path(..., run_name=<anything but
   "__main__">)` so its own `@mcp.tool()`-decorated functions register
   exactly as they would under the CLI, but its `if __name__ == "__main__":`
   guard does NOT fire (avoiding the CLI's hardcoded stdio transport).
3. Takes the resulting `FastMCP` server object (`mcp` in that module's
   namespace) and calls `.run(transport="streamable-http")` on it directly --
   `mcp.server.fastmcp.FastMCP.run()` (confirmed by inspecting
   `inspect.signature(FastMCP.run)` against the pinned `mcp==1.12.2` in this
   image) accepts "stdio" | "sse" | "streamable-http"; streamable-HTTP is the
   MCP spec's current recommended HTTP transport (SSE is the older,
   now-secondary one), and is what every current `mcp` Python-SDK client
   speaks by default.

The eight tools panda_mcp.py registers (create_empty_network, load_network,
run_power_flow, run_contingency_analysis, get_network_info,
load_network_from_any, load_network_from_json, export_network_to_format) are
untouched -- this wrapper only changes how the process is *started*, not what
it does once started.
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path
from typing import Any

from powermcp.registry import get_tool

# Bind address inside the container's network namespace -- 0.0.0.0 so the
# published/hostPort mapping in kube/powermcp-pandapower-pod.yaml can reach
# it from the host; matches kube/llamacpp-phi-pod.yaml's own --host 0.0.0.0
# rationale (this pod only needs *inbound* connections, so no hostNetwork
# is required, same as that pod -- see this pod's own kube manifest header).
LISTEN_HOST: str = "0.0.0.0"

# 8000 is the mcp Python SDK's own FastMCP default (confirmed via
# `FastMCP(...).settings.model_dump()["port"]` against the pinned mcp==1.12.2
# in this image) -- kept as-is rather than picking a different number, since
# nothing else in this repo's other pods claims it. Overridable via
# POWERMCP_PORT for a host where 8000 is already taken (this sandbox's other
# concurrent podman workloads made exactly that necessary for the sibling
# llamacpp pod -- see kube/llamacpp-phi-pod.yaml's header).
LISTEN_PORT: int = int(os.environ.get("POWERMCP_PORT", "8000"))


def _load_pandapower_server() -> Any:
    """Execute PowerMCP's real panda_mcp.py without its stdio __main__ guard.

    Returns:
        The module's `mcp` global -- a `mcp.server.fastmcp.FastMCP` instance
        with all eight pandapower tools already registered via their
        `@mcp.tool()` decorators (decorator side effects run at module
        exec time, before `__main__` is ever checked).
    """
    entry_script: Path = get_tool("pandapower").resolve_entry_script()
    server_dir = str(entry_script.parent)
    if server_dir not in sys.path:
        # panda_mcp.py does `import pandapower as pp` at module scope; this
        # matches powermcp's own _launch_script, which inserts the same
        # directory for the same reason (relative-import-style server code).
        sys.path.insert(0, server_dir)
    namespace = runpy.run_path(str(entry_script), run_name="powermcp_pandapower_http")
    return namespace["mcp"]


def main() -> None:
    """Start the pandapower MCP server over streamable-HTTP and block."""
    server = _load_pandapower_server()
    server.settings.host = LISTEN_HOST
    server.settings.port = LISTEN_PORT
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
