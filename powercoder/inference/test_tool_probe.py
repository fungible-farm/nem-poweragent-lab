"""Gate: a slow inference request fails its own attempt, not the whole run."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from powercoder.inference import tool_probe


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
    prompt.write_text("Report the base-case power flow for snem-sa-2000.")
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
    prompt.write_text("Report the base-case power flow for snem-sa-2000.")
    args = argparse.Namespace(base_url="http://127.0.0.1:1", model="m", prompt=prompt, study_tools=True,
                              first_turn_tool_choice="required")
    journal = tmp_path / "journal.jsonl"
    with journal.open("w") as stream:
        asyncio.run(tool_probe.probe(args, stream))
    assert RecordingClient.choices == ["required"]
    assert json.loads(journal.read_text().splitlines()[0])["payload"]["first_turn_tool_choice"] == "required"


def test_structural_tag_rides_on_auto_and_must_match_the_served_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The committed tag is sent as vLLM structured_outputs on turn 0, with tool_choice auto."""
    seen: list[dict] = []

    class TagClient(SlowClient):
        def chat_completion(self, *_args: Any, **kwargs: Any) -> dict[str, Any]:
            seen.append(kwargs)
            return {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "done"}}]}

    monkeypatch.setattr(tool_probe, "InferenceClient", TagClient)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Report the base-case power flow for snem-sa-2000.")
    args = argparse.Namespace(base_url="http://127.0.0.1:1", model="m", prompt=prompt, study_tools=True,
                              first_turn_tool_choice="structural_tag")
    with (tmp_path / "journal.jsonl").open("w") as stream:
        asyncio.run(tool_probe.probe(args, stream))
    assert seen[0]["tool_choice"] == "auto"
    tag = json.loads(seen[0]["extra"]["structured_outputs"]["structural_tag"])
    assert tag["type"] == "structural_tag"
