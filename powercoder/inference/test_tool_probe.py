"""Gate: a slow inference request fails its own attempt, not the whole run."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from powercoder.inference import powermcp, tool_probe

# These tests stub the inference client, which never reads the prompt; any text
# will do, so it names no case or element.
UNREAD_PROMPT: str = "Prompt text the stubbed inference client never reads."
# A network the real MCP server can load in milliseconds (a built fixture, not a
# case file), for the one tool call the two-turn stub makes.
FIXTURE_NETWORK: str = next(iter(powermcp.FIXTURE_BUILDERS))


class SlowClient:
    """Stands in for InferenceClient; every request exceeds the read timeout."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def __enter__(self) -> "SlowClient":
        return self

    def __exit__(self, *_exc: Any) -> None:
        pass

    def chat_completion(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise httpx.ReadTimeout("timed out")


def test_inference_timeout_is_a_terminal_attempt_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # r4 2026-10-22 04:41: one httpx.ReadTimeout aborted both Granite evaluators.
    monkeypatch.setattr(tool_probe, "InferenceClient", SlowClient)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text(UNREAD_PROMPT)
    args = argparse.Namespace(base_url="http://127.0.0.1:1", model="m", prompt=prompt, study_tools=True)
    journal = tmp_path / "journal.jsonl"
    with journal.open("w") as stream:
        assert asyncio.run(tool_probe.probe(args, stream)) == 1
    terminal = json.loads(journal.read_text().splitlines()[-1])
    assert terminal["kind"] == "terminal"
    assert terminal["payload"]["state"] == "inference_timeout"


class RecordingClient(SlowClient):
    """Answers immediately and records each turn's tool_choice."""

    choices: list[str] = []

    def chat_completion(self, *_args: Any, **kwargs: Any) -> dict[str, Any]:
        RecordingClient.choices.append(kwargs["tool_choice"])
        return {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "done"}}]}


def test_required_tool_choice_applies_to_the_first_turn_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The forced arm grammar-forces turn 0; the journal records the condition."""
    monkeypatch.setattr(tool_probe, "InferenceClient", RecordingClient)
    RecordingClient.choices = []
    prompt = tmp_path / "prompt.txt"
    prompt.write_text(UNREAD_PROMPT)
    args = argparse.Namespace(base_url="http://127.0.0.1:1", model="m", prompt=prompt, study_tools=True,
                              first_turn_tool_choice="required")
    journal = tmp_path / "journal.jsonl"
    with journal.open("w") as stream:
        asyncio.run(tool_probe.probe(args, stream))
    assert RecordingClient.choices == ["required"]
    assert json.loads(journal.read_text().splitlines()[0])["payload"]["first_turn_tool_choice"] == "required"


def test_structural_tag_turn_sends_the_committed_grammar_with_tool_choice_auto(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Requirement PC-REQ-2: a forced first turn keeps the model's own tool-call format.

    Turn 0 must carry the file at tool_probe.STRUCTURAL_TAG, byte for byte, as
    vLLM's ``structured_outputs.structural_tag``, with ``tool_choice="auto"``
    (vLLM's "required" would swap in a JSON format the models were not trained
    on). Later turns must carry no grammar.
    """
    seen: list[dict] = []

    class TwoTurnClient(SlowClient):
        """First reply is a tool call, second an answer, so both turns are observed."""

        def chat_completion(self, *_args: Any, **kwargs: Any) -> dict[str, Any]:
            seen.append(kwargs)
            if len(seen) == 1:
                call = {"id": "c0", "type": "function", "function": {"name": "load_network",
                                                                      "arguments": json.dumps({"network_id": FIXTURE_NETWORK})}}
                return {"choices": [{"finish_reason": "tool_calls",
                                     "message": {"role": "assistant", "content": None, "tool_calls": [call]}}]}
            return {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "done"}}]}

    monkeypatch.setattr(tool_probe, "InferenceClient", TwoTurnClient)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text(UNREAD_PROMPT)
    args = argparse.Namespace(base_url="http://127.0.0.1:1", model="m", prompt=prompt, study_tools=True,
                              first_turn_tool_choice="structural_tag")
    with (tmp_path / "journal.jsonl").open("w") as stream:
        asyncio.run(tool_probe.probe(args, stream))
    assert [turn["tool_choice"] for turn in seen] == ["auto", "auto"]
    assert seen[0]["extra"] == {"structured_outputs": {"structural_tag": tool_probe.STRUCTURAL_TAG.read_text()}}
    assert seen[1]["extra"] is None


def test_a_grammar_built_from_other_tools_stops_the_run_not_the_attempt(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Requirement PC-REQ-3: a stale grammar is a harness fault, never a model failure.

    The grammar embeds the tool schemas it was built from. If the served tools
    change, evaluate_agent must refuse before any attempt, with an error that
    attempt() does not catch as a model protocol error (ValueError/KeyError/TypeError).
    """
    from powercoder.inference import evaluate_agent

    stale = tmp_path / "served_tools.json"
    stale.write_text(json.dumps([{"type": "function", "function": {"name": "an_old_tool", "parameters": {}}}]))
    monkeypatch.setattr(tool_probe, "SERVED_TOOLS", stale)
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text("")
    monkeypatch.setattr(evaluate_agent, "load_rows", lambda _path: [])
    args = argparse.Namespace(tasks=tasks, exclude=tasks, out=tmp_path / "run", model="m", base_url="http://x",
                              concurrency=1, first_turn_tool_choice="structural_tag")
    with pytest.raises(tool_probe.StructuralTagOutOfDate) as raised:
        asyncio.run(evaluate_agent.evaluate(args))
    assert not isinstance(raised.value, (ValueError, KeyError, TypeError))
    assert not args.out.exists()
