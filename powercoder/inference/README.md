# Canonical PowerMCP transport

Run `uv run --no-sync python -m powercoder.inference.mcp_server` as an MCP stdio
child process. It uses the installed official MCP Python SDK and exposes the
exact two schemas from `PowerMCP.get_tool_schemas()`: `load_network` and
`run_power_flow`. Responses preserve canonical status, solver data, error,
execution time and evidence. Calls execute serially because the iteration
observer temporarily patches the NR function.

This endpoint serves this repository's four-state contract. The older
`kube/powermcp_serve_http.py` wraps upstream Power-Agent's eight-tool server;
that separate endpoint does not establish canonical contract parity.

`uv run --no-sync python -m pytest tests/integration/test_canonical_mcp_transport.py -q`
starts the real stdio process, discovers schemas and makes actual solver calls.
It checks success and non-convergence against saved real-solver fixtures;
unsupported IDs are rejected by MCP schema validation before backend execution.
The small networks are named test fixtures, not NEM benchmark performance.

This is transport qualification. Model-controlled tool use, controller-owned
durable traces, scalar modification tools for fitting tasks and full benchmark
comparisons still need implementation and verification. A model's self-reported
trajectory alone cannot prove it called a tool.
