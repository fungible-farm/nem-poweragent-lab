# 0015 — G1: typed command protocol and policy gateway

- **Status:** open; **cheapest first step done** 2026-10-24 (below). [PRD-0010](../prd/0010-powercoder-physics-grounded-engineering-agent.md) G1, priority A2. Depends on G0 ([0008](0008-powercoder-benchmark-cannot-measure-agent-value.md)).
- **Requirements:** PC-REQ-001–005, PC-CON-003/005.

## Deliverables
- **Command IR and DSL:** a versioned typed IR in Rust, as a new crate in the existing `rust/`
  workspace beside `mission-engine`, covering the ten commands in PRD-0010 §4.1. A textual DSL
  compiles to it.
- **Schema and grammar generation from one source:** JSON Schema for MCP tool definitions, served
  to vLLM. vLLM builds the xgrammar grammar per request, so no grammar file is stored (0014). GBNF
  for llama.cpp follows only if a llama.cpp planner is used, on sm3lly per DEC-013.
- **Policy gateway:** permissions, scope, units and types, resource and time limits, query
  complexity, and safety restrictions. It sits in front of today's MCP server
  (`powercoder/inference/mcp_server.py`).
- **Evidence contract and replay:** extends `powercoder/inference/provenance.py` and the
  per-attempt journals `evaluate_agent` already writes.

## Exit criteria
- ≥99% valid commands on the protocol suite.
- 100% of unauthorised commands rejected.
- Every accepted number has a valid evidence reference.
- Replays reproduce within tolerance.
- No test lets retrieved content bypass authorisation.

## Cheapest first step
Write the IR types and their JSON-Schema emitter for two commands, `SOLVE` and `SIMULATE`. Make
them wrap the existing `run_study_trial` semantics, and check the emitted schema is byte-identical
to today's served tool schema. Matching it exactly avoids an FM-23-style train/serve skew.

## First step done (2026-10-24): `rust/command-ir`
- **The IR:** a new crate in the `rust/` workspace with `SOLVE` (intact or N-1 power flow, one
  observation) and `SIMULATE` (one load-scale, line-rating or dispatch trial, observing what that
  modification moves). Both are validated against the study tool's own rules (served networks,
  scale in [0.9, 1.1], 1–100 iterations) and lowered to `run_study_trial` arguments in schema
  order. `contingency_line` is omitted for the intact network, as the trained procedure does
  (FM-18).
- **Schema emitter:** `study_trial_schema()` with Python `json.dumps` separators is
  **byte-identical** to the served schema. That's pinned from both sides: `cargo test -p command-ir`
  checks it against the fixture, and `powercoder/inference/test_command_ir.py` checks that Python
  still serves the fixture.
- **DSL:** `SOLVE snem-sa-2000 OUTAGE 94 OBSERVE bus_voltage 985` /
  `SIMULATE snem-sa-2000 load_scale 1.0375 OBSERVE 985` compile to the IR. Refused before any call:
  unknown networks, out-of-range scales, `None` ids and anything that is not a command.
- **Run it:** `just powercoder::command-ir-test`.

**Left for G1:**
- the other eight PRD-0010 §4.1 commands;
- Python serving the IR-generated schema (not only matching it);
- the policy gateway (permissions, units, limits) in front of `mcp_server.py`;
- replay;
- the ≥99% valid-command protocol suite.
