"""Smoke-gate the retrained students, then evaluate all four models and measure them.

r6 of the PowerCoder study (docs/POWERCODER_HANDOFF_2026-10-21.md). Inputs are
frozen and verified before anything is served:

- the students from ``training/agent_sft.py`` (each ``hash_manifest.json``
  re-hashed), trained on tool-call trajectories (AGENTS.md FM-19);
- the 20-task smoke suite drawn from the *validation* split, so the gate never
  sees a benchmark task, and the stratified 100-task benchmark sample
  (``powercoder/datasets/sample_benchmark.py``).

Stages, every one owned by this driver and journaled to ``pipeline.jsonl``:

1. Smoke: each student serves alone and runs the 20 tasks. It passes only with
   at least ``SMOKE_MIN_PASS`` strict passes; a student that fails is not
   evaluated further, and its comparisons are recorded as skipped.
2. For each of Qwen base, Qwen student, Granite base, Granite student (one
   server at a time, as in r5): the latency benchmark on the idle server
   (``powercoder/inference/latency_bench.py``), then the 100-task evaluation.
   Host MemAvailable is sampled for the server's whole life.
3. The strict and solver-verified comparisons for every pair.
4. Lab 10: RestoreBench's single tool-using agent on all 46 IEEE 118 scenarios,
   each evaluated model served again on its own. This runs after the
   comparisons are written, so the external benchmark cannot cost the study its
   results (labs/10-poweragentbench-restorebench/README.md).

No stage is retried or truncated automatically; a failed stage stops the driver
with its logs kept.

``--forced-arm-from <r6 root>`` is a separate study arm (never part of r6): it
reuses r6's verified students and unforced 100-task runs and evaluates every
model r6 evaluated under strict tool calling, then writes one comparison per
model against its own r6 run. Strict tool calling here means: each server runs
with ``--tool-strict-level parameter`` (vLLM builds xgrammar's model-native
grammar from each request's tools and enforces the argument schemas on every
turn), and the first turn sends ``tool_choice="required"`` (it must be a tool
call). The prompt is unchanged: strictness is server-side, not a ``strict``
field in the rendered tools.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, TextIO

from powercoder.inference.evaluate_agent import frozen_task_count
from powercoder.inference.tool_probe import record
from training.granite.train import digest
from training.run_comparison import (
    CONCURRENCY, GPU_MEMORY_FRACTION, GRANITE_GPU_MEMORY_FRACTION, HF_HUB, MEMINFO, QWEN_BASE_SNAPSHOT, REPO,
    command, meminfo_bytes, serve, stop_server, verify_evaluation, write_comparison, write_numerical_comparison)

BENCHMARK: Path = Path("benchmarks/power-agent-bench-lite/results/domain-stratified-100-20261022/examples.jsonl")
SMOKE: Path = Path("training/unsloth/out/smoke-validation-20-20261022/examples.jsonl")
# Independence for both suites is audited against the students' training rows.
TRAIN_SPLIT: Path = Path("powercoder/datasets/smoke/splits/train.jsonl")
GRANITE_BASE: Path = Path("training/unsloth/out/granite-4.2-8b-base")
STUDENTS: dict[str, Path] = {
    "qwen-student": Path("training/unsloth/out/agent-sft-qwen35-4b-20261022-v2"),
    "granite-student": Path("training/unsloth/out/agent-sft-granite42-8b-20261022-v2"),
}
# Half the 20 smoke tasks. The scripted trajectories pass 20/20; the bases passed
# 3.9-5.6% of the 306-task benchmark (r4), so at p = 0.1, P(>= 10/20) ~ 7e-6:
# a pass is learned behaviour, not luck. Fixed before any student was served.
SMOKE_MIN_PASS: int = 10
# vLLM flag for the forced arm's servers: enforce tool-call envelope and argument
# schemas for every request (vLLM 0.31 ToolStrictLevel.PARAMETER).
STRICT_TOOL_CALLING: tuple[str, ...] = ("--tool-strict-level", "parameter")
# Host memory sampling period; vLLM's load and each request last seconds or more.
MEMORY_SAMPLE_S: float = 1.0
RESTOREBENCH_LAB: Path = Path("labs/10-poweragentbench-restorebench/restorebench_lab.py")
# Every scenario of the IEEE 118 corpus. RestoreBench caps an episode at 1,200 s
# (OrchestratorConfig.MAX_RUNTIME_SECONDS), so 46 at 8 in flight is bounded at ~2 h.
RESTOREBENCH_CORPUS: str = "ieee118"
RESTOREBENCH_SCENARIOS: int = 46


class MemorySampler:
    """Record MemAvailable once per period until stopped, in its own thread.

    GB10 memory is unified: weights, KV cache and activations all come out of
    MemAvailable, so the drop from the pre-start baseline is the server's peak
    footprint, provided nothing else starts meanwhile (the driver runs alone).
    """

    def __init__(self, path: Path) -> None:
        self.path, self.stop = path, threading.Event()
        self.baseline = meminfo_bytes("MemAvailable", MEMINFO)
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self) -> None:
        with self.path.open("x") as stream:
            while not self.stop.is_set():
                stream.write(json.dumps({"unix_time": time.time(),
                                         "available": meminfo_bytes("MemAvailable", MEMINFO)}) + "\n")
                stream.flush()
                self.stop.wait(MEMORY_SAMPLE_S)

    def __enter__(self) -> "MemorySampler":
        self.thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop.set()
        self.thread.join()

    def peak(self, since: float = 0.0) -> dict[str, int]:
        """Lowest MemAvailable after ``since`` and its drop from the baseline."""
        samples = [json.loads(line) for line in self.path.read_text().splitlines()]
        lowest = min(s["available"] for s in samples if s["unix_time"] >= since)
        return {"baseline_available": self.baseline, "min_available": lowest, "peak_used": self.baseline - lowest}


def verify_student(directory: Path, events: TextIO) -> Path:
    """Re-hash every adapter and merged file the trainer recorded; return the merged model.

    Raises:
        ValueError: if any file is missing or changed.
    """
    manifest = json.loads((directory / "hash_manifest.json").read_text())
    for relative, expected in manifest.items():
        if digest(directory / relative) != expected:
            raise ValueError(f"Student file changed since training: {directory / relative}")
    log = json.loads((directory / "train_log.json").read_text())
    record(events, "student_verified", {"directory": str(directory), "files": len(manifest),
        "completed_steps": log["completed_steps"], "trajectories_sha256": log["trajectories_sha256"]})
    return directory / "merged-bf16"


def evaluation(model: str, port: int, tasks: Path, out: Path,
               first_turn_tool_choice: str = "auto") -> tuple[list[str], Path]:
    """The evaluate_agent command for one suite, at the shared concurrency and budgets."""
    return ([sys.executable, "-m", "powercoder.inference.evaluate_agent", "--base-url", f"http://127.0.0.1:{port}",
             "--model", model, "--tasks", str(tasks), "--exclude", str(TRAIN_SPLIT), "--out", str(out),
             "--concurrency", str(CONCURRENCY), "--first-turn-tool-choice", first_turn_tool_choice],
            out.parent / f"{out.name}.log")


def session(label: str, tag: str, source: Path, model_path: str, fraction: float, root: Path, events: TextIO,
            suites: list[tuple[str, Path, Path]], latency: bool, restorebench: bool = False,
            first_turn_tool_choice: str = "auto", vllm_args: tuple[str, ...] = ()) -> None:
    """Serve one model alone; optionally benchmark latency; run each suite; release it.

    Args:
        tag: Distinguishes this session's container and files: a student is
            served once for its smoke gate and again for the benchmark.
        suites: (stage, tasks, out_dir) evaluations to run in order.
        latency: Run the latency benchmark on the idle server before any suite.
        restorebench: Run Lab 10's RestoreBench agent stage instead of or after the suites.
    """
    name, model = f"powercoder-{root.name}-{label}-{tag}", f"powercoder-{label}"
    reasoning = "nemotron_v3" if label.startswith("granite") else "qwen3"
    port = 8101
    with MemorySampler(root / f"{label}-{tag}-memory.jsonl") as memory:
        try:
            serve(source, name, model, reasoning, root, events, memory_fraction=fraction,
                  model_path=model_path, port=port, vllm_args=vllm_args)
            loaded = memory.peak()
            record(events, "memory_after_load", {"model": label, **loaded})
            if latency:
                start = time.time()
                command([sys.executable, "-m", "powercoder.inference.latency_bench", "--base-url",
                         f"http://127.0.0.1:{port}", "--model", model, "--tasks", str(SMOKE),
                         "--out", str(root / f"{label}-latency.json")], root / f"{label}-latency.log", events)
                record(events, "latency_complete", {"model": label, "path": str(root / f"{label}-latency.json"),
                                                     "memory": memory.peak(start)})
            for stage, tasks, out in suites:
                start = time.time()
                command(*evaluation(model, port, tasks, out, first_turn_tool_choice), events)
                verify_evaluation(out, events)
                record(events, "suite_memory", {"model": label, "stage": stage, "memory": memory.peak(start)})
            if restorebench:
                out = root / f"{label}-restorebench"
                command([sys.executable, str(RESTOREBENCH_LAB), "--step", "agent", "--base-url",
                         f"http://127.0.0.1:{port}", "--model", model, "--corpus", RESTOREBENCH_CORPUS,
                         "--limit", str(RESTOREBENCH_SCENARIOS), "--results-dir", str(out)],
                        root / f"{label}-restorebench.log", events)
                record(events, "restorebench_complete", {"model": label,
                    "summary": json.loads((out / "summary.json").read_text())})
        finally:
            stop_server(name, root, events)
    record(events, "memory_peak", {"model": label, "session": tag, **memory.peak()})


def run(args: argparse.Namespace, events: TextIO) -> None:
    """Gate, evaluate, measure and compare, each stage only after the last completed."""
    for suite in (SMOKE, BENCHMARK):
        record(events, "suite_verified", {"tasks": str(suite), "n_tasks": frozen_task_count(suite)})
    students = {label: verify_student(directory, events) for label, directory in STUDENTS.items()}
    fractions = {"qwen": GPU_MEMORY_FRACTION, "granite": GRANITE_GPU_MEMORY_FRACTION}
    root = args.root

    passed: dict[str, bool] = {}
    for label, merged in students.items():
        out = root / f"{label}-smoke"
        session(label, "smoke", merged, "", fractions[label.split("-")[0]], root, events,
                [("smoke", SMOKE, out)], latency=False)
        summary = json.loads((out / "summary.json").read_text())
        passed[label] = summary["n_pass"] >= SMOKE_MIN_PASS
        record(events, "smoke_gate", {"model": label, "n_pass": summary["n_pass"], "n_tasks": summary["n_tasks"],
                                      "required": SMOKE_MIN_PASS, "passed": passed[label]})

    models = [("qwen-base", HF_HUB, QWEN_BASE_SNAPSHOT), ("qwen-student", students["qwen-student"], ""),
              ("granite-base", GRANITE_BASE, ""), ("granite-student", students["granite-student"], "")]
    evaluated = []
    for label, source, model_path in models:
        if label in passed and not passed[label]:
            record(events, "evaluation_skipped", {"model": label, "reason": "smoke gate failed"})
            continue
        session(label, "benchmark", source, model_path, fractions[label.split("-")[0]], root, events,
                [("benchmark", BENCHMARK, root / label)], latency=True)
        evaluated.append(label)

    pairs = [("qwen-base", "qwen-student"), ("granite-base", "granite-student"), ("qwen-base", "granite-base"),
             ("qwen-student", "granite-student"), ("qwen-base", "granite-student"), ("qwen-student", "granite-base")]
    outcomes = {}
    for first, second in pairs:
        stem = f"{first}-vs-{second}"
        if first not in evaluated or second not in evaluated:
            record(events, "comparison_skipped", {"comparison": stem, "evaluated": evaluated})
            continue
        strict = write_comparison(root / first, root / second, root / f"{stem}.json", events)
        numerical = write_numerical_comparison(root / first, root / second, root / f"{stem}-numerical.json", events)
        outcomes[stem] = {"strict_delta_pp": strict["delta_percentage_points"],
                          "solver_verified_delta_pp": numerical["delta_percentage_points"]}
    record(events, "comparisons_complete", {"smoke": passed, "evaluated": evaluated, "comparisons": outcomes})

    sources = dict((label, (source, model_path)) for label, source, model_path in models)
    for label in evaluated:
        session(label, "restorebench", *sources[label], fractions[label.split("-")[0]], root, events,
                [], latency=False, restorebench=True)
    record(events, "pipeline_complete", {"smoke": passed, "evaluated": evaluated, "comparisons": outcomes})


def forced_arm(args: argparse.Namespace, events: TextIO) -> None:
    """Re-evaluate r6's models with a forced first-turn tool call; compare each with itself."""
    previous = args.forced_arm_from
    summary = [json.loads(line) for line in (previous / "pipeline.jsonl").read_text().splitlines()][-1]
    if summary["kind"] != "pipeline_complete":
        raise RuntimeError(f"{previous} has not completed r6")
    evaluated = summary["payload"]["evaluated"]
    students = {label: verify_student(directory, events) for label, directory in STUDENTS.items()}
    sources = {"qwen-base": (HF_HUB, QWEN_BASE_SNAPSHOT), "qwen-student": (students["qwen-student"], ""),
               "granite-base": (GRANITE_BASE, ""), "granite-student": (students["granite-student"], "")}
    fractions = {"qwen": GPU_MEMORY_FRACTION, "granite": GRANITE_GPU_MEMORY_FRACTION}
    outcomes = {}
    for label in evaluated:
        verify_evaluation(previous / label, events)
        forced = args.root / f"{label}-forced"
        session(label, "forced", *sources[label], fractions[label.split("-")[0]], args.root, events,
                [("benchmark-forced", BENCHMARK, forced)], latency=False, first_turn_tool_choice="required",
                vllm_args=STRICT_TOOL_CALLING)
        stem = f"{label}-auto-vs-forced"
        strict = write_comparison(previous / label, forced, args.root / f"{stem}.json", events, True)
        numerical = write_numerical_comparison(previous / label, forced, args.root / f"{stem}-numerical.json",
                                               events, True)
        outcomes[label] = {"strict_delta_pp": strict["delta_percentage_points"],
                           "solver_verified_delta_pp": numerical["delta_percentage_points"]}
    record(events, "pipeline_complete", {"arm": "strict-tool-calling-forced-first-turn", "from": str(previous),
                                         "comparisons": outcomes})


def main() -> None:
    """Create a fresh run root and durable journal; refuse automatic re-execution."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="New run directory; must not exist")
    parser.add_argument("--forced-arm-from", type=Path,
                        help="Completed r6 root: run only the forced-first-turn-tool-call arm against it")
    args = parser.parse_args()
    args.root.mkdir()
    # A supervisor's stop arrives as SIGTERM; unwind so the journal records it.
    signal.signal(signal.SIGTERM, lambda signum, _frame: sys.exit(128 + signum))
    with (args.root / "pipeline.jsonl").open("x") as events:
        record(events, "driver_start", {"pid": os.getpid(), "unix_time": time.time(), "smoke_min_pass": SMOKE_MIN_PASS,
            "source_sha256": {str(p.relative_to(REPO)): digest(p)
                              for parent in (REPO / "powercoder/inference", REPO / "powercoder/datasets", REPO / "training")
                              for p in parent.glob("*.py")}})
        try:
            (forced_arm if args.forced_arm_from else run)(args, events)
        except Exception as error:
            record(events, "driver_error", {"type": type(error).__name__, "message": str(error)})
            raise
        except SystemExit as stop:
            record(events, "driver_stopped", {"exit_code": stop.code, "unix_time": time.time()})
            raise


if __name__ == "__main__":
    main()
