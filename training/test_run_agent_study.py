"""CPU gates for the r6 driver: the smoke gate decides which students are evaluated."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from training import run_agent_study as driver


def test_a_student_failing_its_smoke_gate_is_neither_evaluated_nor_compared(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Qwen student passes 12/20, Granite student 3/20: only Granite's student is dropped."""
    smoke_passes = {"qwen-student": 12, "granite-student": 3}
    sessions: list[tuple[str, str, bool]] = []

    def fake_session(label: str, tag: str, _source: Path, _path: str, _fraction: float, root: Path,
                     _events: object, suites: list, latency: bool, restorebench: bool = False) -> None:
        sessions.append((label, tag, latency))
        for _stage, _tasks, out in suites:
            out.mkdir()
            if tag == "smoke":
                (out / "summary.json").write_text(json.dumps({"n_pass": smoke_passes[label], "n_tasks": 20}))

    monkeypatch.setattr(driver, "frozen_task_count", lambda _path: 20)
    monkeypatch.setattr(driver, "verify_student", lambda directory, _events: directory / "merged-bf16")
    monkeypatch.setattr(driver, "session", fake_session)
    compared: list[str] = []
    monkeypatch.setattr(driver, "write_comparison",
                        lambda first, second, *_a: compared.append(f"{first.name}-vs-{second.name}")
                        or {"delta_percentage_points": 0.0})
    monkeypatch.setattr(driver, "write_numerical_comparison", lambda *_a: {"delta_percentage_points": 0.0})
    root = tmp_path / "r6"
    root.mkdir()
    journal = tmp_path / "pipeline.jsonl"
    with journal.open("x") as stream:
        driver.run(driver.argparse.Namespace(root=root), stream)
    assert sessions == [("qwen-student", "smoke", False), ("granite-student", "smoke", False),
                        ("qwen-base", "benchmark", True), ("qwen-student", "benchmark", True),
                        ("granite-base", "benchmark", True), ("qwen-base", "restorebench", False),
                        ("qwen-student", "restorebench", False), ("granite-base", "restorebench", False)]
    assert compared == ["qwen-base-vs-qwen-student", "qwen-base-vs-granite-base", "qwen-student-vs-granite-base"]
    final = json.loads(journal.read_text().splitlines()[-1])
    assert final["kind"] == "pipeline_complete" and final["payload"]["smoke"] == {
        "qwen-student": True, "granite-student": False}


def test_memory_peak_is_the_drop_from_the_pre_start_baseline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unified memory: the server's footprint is baseline minus the lowest sample."""
    readings = iter([100, 90, 60, 80])
    monkeypatch.setattr(driver, "meminfo_bytes", lambda *_a: next(readings))
    sampler = driver.MemorySampler(tmp_path / "memory.jsonl")
    sampler.path.write_text("".join(json.dumps({"unix_time": t, "available": a}) + "\n"
                                    for t, a in ((1.0, 90), (2.0, 60), (3.0, 80))))
    assert sampler.peak() == {"baseline_available": 100, "min_available": 60, "peak_used": 40}
    assert sampler.peak(since=3.0)["peak_used"] == 20


def test_forced_arm_reuses_r6_and_compares_each_model_with_itself(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every model r6 evaluated is re-run with a required first-turn tool call."""
    previous = tmp_path / "r6"
    previous.mkdir()
    (previous / "pipeline.jsonl").write_text(json.dumps({"kind": "pipeline_complete", "payload": {
        "evaluated": ["qwen-base", "qwen-student"]}}) + "\n")
    sessions, compared = [], []
    monkeypatch.setattr(driver, "verify_student", lambda directory, _events: directory / "merged-bf16")
    monkeypatch.setattr(driver, "verify_evaluation", lambda directory, _events: None)
    monkeypatch.setattr(driver, "session", lambda label, tag, *_a, first_turn_tool_choice="auto", **_k:
                        sessions.append((label, tag, first_turn_tool_choice)))
    monkeypatch.setattr(driver, "write_comparison", lambda first, second, _dest, _events, allow:
                        compared.append((first.name, second.name, allow)) or {"delta_percentage_points": 1.0})
    monkeypatch.setattr(driver, "write_numerical_comparison", lambda *_a: {"delta_percentage_points": 2.0})
    root = tmp_path / "forced"
    root.mkdir()
    with (tmp_path / "events.jsonl").open("x") as stream:
        driver.forced_arm(driver.argparse.Namespace(root=root, forced_arm_from=previous), stream)
    assert sessions == [("qwen-base", "forced", "required"), ("qwen-student", "forced", "required")]
    assert compared == [("qwen-base", "qwen-base-forced", True), ("qwen-student", "qwen-student-forced", True)]
