"""Qualify actual model-to-MCP tool use with a durable controller-owned journal.

This is a bounded interface probe, not a scored benchmark. Only the supplied
prompt is exposed to the model; the controller never executes model Python.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, TextIO

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import httpx

from powercoder.inference.client import InferenceClient

# Qualification budgets, not release benchmark parameters.
MAX_TURNS: int = 12
MAX_TOOL_CALLS: int = 24
# 2048 truncated 32 of 76 Qwen3.5-4B base attempts mid-reasoning (r2/r3,
# finish_reason=length; AGENTS.md FM-2). Reasoning is not carried between
# turns, so this bounds one response, not the conversation.
MAX_TOKENS: int = 8192
# One full response at the ~14 tok/s low end measured on GB10 takes ~585 s;
# with concurrent requests sharing the GPU allow ~3x that. A request that still
# exceeds it is that attempt's terminal ``inference_timeout`` (FM-6): r4's
# Granite side-by-side stage decoded ~4 tok/s per stream and one timeout
# aborted the whole stage. Every compared run records this value, and
# compare_agents refuses runs whose values differ.
INFERENCE_TIMEOUT_S: float = 1800.0
# The evaluation's system turn. Training trajectories (powercoder/datasets/
# trajectories.py) reuse it verbatim, so students train on the prompt they are
# evaluated with (AGENTS.md FM-19).
# "auto" is the r1-r6 protocol. The other two force a tool call on the first turn
# only (later turns are "auto" so the model can still answer), as a separate study
# arm never mixed with "auto" runs (compare_agents treats it as a condition):
# - "structural_tag": xgrammar's structural tag in the model's own XML tool-call
#   format (grammars/build_structural_tag.py), so the trained format is kept;
# - "required": vLLM's tool_choice="required", which it turns into a JSON-array
#   schema, a different format from the one the models were trained on.
FIRST_TURN_TOOL_CHOICES: tuple[str, ...] = ("auto", "structural_tag", "required")
STRUCTURAL_TAG: Path = Path(__file__).resolve().parent / "grammars/forced_first_turn.structural_tag.json"
SERVED_TOOLS: Path = Path(__file__).resolve().parent / "grammars/served_tools.json"
SYSTEM_PROMPT: str = ("Use the available tools to solve the task. Report only results supported by actual "
                      "tool responses. Convergence and physical validity are different.")
# vLLM's 400 text when prompt + max_tokens exceeds --max-model-len.
CONTEXT_OVERFLOW: str = "maximum context length"


def record(stream: TextIO, kind: str, payload: Any) -> None:
    """Persist each observation before the next model or tool invocation."""
    stream.write(json.dumps({"kind": kind, "payload": payload}, allow_nan=False) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def structural_tag(tools: list[dict[str, Any]]) -> dict[str, Any]:
    """vLLM's ``structured_outputs`` field carrying the committed structural tag.

    Raises:
        ValueError: if the tools the tag was built from are not the served tools.
    """
    if json.dumps(tools) != json.dumps(json.loads(SERVED_TOOLS.read_text())):
        raise ValueError("Served tools differ from grammars/served_tools.json; rebuild the structural tag")
    return {"structured_outputs": {"structural_tag": STRUCTURAL_TAG.read_text()}}


async def probe(args: argparse.Namespace, journal: TextIO) -> int:
    """Let the real model choose tools and feed back actual MCP responses."""
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "powercoder.inference.mcp_server"] + (["--study-tools"] if args.study_tools else []),
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    first_choice = getattr(args, "first_turn_tool_choice", "auto")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": args.prompt.read_text()},
    ]
    record(journal, "start", {
        "model": args.model, "base_url": args.base_url, "messages": messages,
        "max_tokens": MAX_TOKENS, "temperature": 0.0,
        "max_turns": MAX_TURNS, "max_tool_calls": MAX_TOOL_CALLS,
        "inference_timeout_s": INFERENCE_TIMEOUT_S,
        "first_turn_tool_choice": first_choice,
        "benchmark_claim": False,
    })
    async with (
        stdio_client(parameters) as (reader, writer),
        ClientSession(reader, writer) as session,
    ):
        await session.initialize()
        discovered = (await session.list_tools()).tools
        tools = [{"type": "function", "function": {
            "name": t.name, "description": t.description, "parameters": t.inputSchema,
        }} for t in discovered]
        record(journal, "tools", tools)
        calls = 0
        ids: set[str] = set()
        with InferenceClient(args.base_url, timeout=INFERENCE_TIMEOUT_S) as client:
            for turn in range(MAX_TURNS):
                try:
                    forced = turn == 0 and first_choice != "auto"
                    result = await asyncio.to_thread(
                        client.chat_completion, args.model, messages,
                        max_tokens=MAX_TOKENS, temperature=0.0, tools=tools,
                        tool_choice="required" if forced and first_choice == "required" else "auto",
                        extra=structural_tag(tools) if forced and first_choice == "structural_tag" else None,
                    )
                except httpx.HTTPStatusError as error:
                    # The conversation outgrew the server's context: this
                    # attempt's failure, not a backend fault (AGENTS.md FM-5).
                    if error.response.status_code == 400 and CONTEXT_OVERFLOW in error.response.text:
                        record(journal, "terminal", {"state": "context_exhausted", "actual_tool_calls": calls,
                                                     "error": error.response.text[:500]})
                        return 1
                    raise
                except httpx.TimeoutException as error:
                    # One slow attempt is that attempt's failure; the client
                    # closes the connection, so vLLM aborts the request.
                    record(journal, "terminal", {"state": "inference_timeout", "actual_tool_calls": calls,
                                                 "timeout_s": INFERENCE_TIMEOUT_S, "error": type(error).__name__})
                    return 1
                record(journal, "model_response", result)
                choice = result["choices"][0]
                message = choice["message"]
                messages.append({k: message[k] for k in ("role", "content", "tool_calls") if k in message})
                requested = message.get("tool_calls") or []
                if not requested:
                    success = choice["finish_reason"] == "stop" and bool(message.get("content"))
                    record(journal, "terminal", {
                        "state": "answered" if success else "incomplete_generation",
                        "actual_tool_calls": calls, "accuracy_claim": False,
                    })
                    return 0 if success else 1
                for call in requested:
                    if calls >= MAX_TOOL_CALLS or call["id"] in ids:
                        record(journal, "terminal", {"state": "invalid_tool_protocol", "actual_tool_calls": calls})
                        return 1
                    ids.add(call["id"])
                    record(journal, "tool_request", call)
                    try:
                        arguments = json.loads(call["function"]["arguments"])
                    except (ValueError, TypeError) as error:
                        record(journal, "terminal", {"state": "invalid_tool_arguments", "actual_tool_calls": calls, "error": str(error)})
                        return 1
                    response = await session.call_tool(call["function"]["name"], arguments)
                    observed = response.model_dump(mode="json", by_alias=True)
                    record(journal, "tool_response", {"tool_call_id": call["id"], "result": observed})
                    calls += 1
                    messages.append({"role": "tool", "tool_call_id": call["id"],
                                     "content": json.dumps(observed, allow_nan=False)})
    record(journal, "terminal", {"state": "turn_budget_exhausted", "actual_tool_calls": calls})
    return 1


def main() -> int:
    """Require an explicit prompt and refuse overwriting earlier observations."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--study-tools", action="store_true")
    args = parser.parse_args()
    args.journal.parent.mkdir(parents=True, exist_ok=True)
    with args.journal.open("x") as journal:
        try:
            return asyncio.run(probe(args, journal))
        except Exception as error:
            record(journal, "controller_error", {
                "type": type(error).__name__, "message": str(error),
            })
            raise


if __name__ == "__main__":
    raise SystemExit(main())
