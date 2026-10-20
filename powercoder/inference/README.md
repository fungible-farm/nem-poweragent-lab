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

## Model tool-use probe

With a student OpenAI-compatible server ready, run:

```sh
uv run --no-sync python -m powercoder.inference.tool_probe \
  --base-url http://127.0.0.1:8101 --model powercoder-axolotl-4b \
  --prompt training/axolotl/out/tool-probe-r1-prompt.txt \
  --journal training/axolotl/out/tool-probe-r1.jsonl
```

Supply a training-only prompt as plain text. The probe exposes tools discovered
from the actual MCP child, lets the real model select calls, and supplies actual
RPC responses in subsequent model turns. The controller flushes and fsyncs each
observation; existing journals are refused. It limits model turns and tool
calls, uses greedy generation, and never executes generated code. Raw model
responses, tool requests, actual tool responses and terminal states are retained.

A terminal `answered` state records protocol completion, not answer correctness;
inspect the independent tool responses and final answer. This probe is not the
release benchmark or evidence of the required improvement.

Observed qualification on 2026-10-20: `powercoder-axolotl-4b` served by vLLM
0.31.0 on GB10 made both requested calls for training example
`ex_981a9cd2b75678ce`. Real CSIRO results were 503 buses, 698 branches, 57
generators, 186 loads; the power flow converged in five iterations with 39
voltage violations. The final response retained `constraint_violation`, reported
physical validity false, and rounded the actual voltage range to 0.907–1.094 pu.
The controller exited 0 after two actual tool calls and a final `stop` response.
Raw evidence: `training/axolotl/out/tool-probe-r1.jsonl`. This training-prompt
qualification does not establish held-out accuracy, zero fabrication across a
suite, or an improvement over base.
