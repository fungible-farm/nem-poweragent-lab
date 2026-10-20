"""Complete Qwen and Granite experiments in sequence, retaining all evidence.

Serve and evaluate the pinned Qwen base, then the original saved Qwen student,
train the pinned Granite model on the same split, and evaluate both Granite base
and student. This driver owns every stage it starts, so one supervising unit
(`systemd-run --user`, see training/granite/README.md) stops all of them. Every
GPU stage first waits for measured unified-memory headroom. No stage is retried
or truncated automatically. A failed stage leaves its logs and stops this driver.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, TextIO

import httpx

from powercoder.inference.compare_agents import compare, verified_run
from powercoder.inference.domain_scorecard import compare_domain
from powercoder.inference.tool_probe import record
from training.granite.train import digest, verify_base

# Qualified on GB10 in the actual earlier tool-use probes; image ID is immutable.
INFERENCE_IMAGE: str = "d53cb735dd1822378c352da65b4ef1580c9764df7aed4bc8805c6c26f6b827de"
TRAINING_IMAGE: str = "74feb3e2e84cfde5d1d2d21c34213d60114d7eb7a80bb1f9352ff2dda15c00ff"
# Match the qualified Qwen server, including token context and single-sequence
# scheduling. Granite uses the built-in reasoning parser its model card permits.
CONTEXT_TOKENS: int = 16384
GPU_MEMORY_FRACTION: float = 0.12
# Granite's pinned weight index contains 16,761,102,336 bytes, exceeding 12%
# of the GB10's memory before runtime/KV cache. The local Granite service uses
# 22%; keep generation/context budgets identical while allocating enough RAM.
GRANITE_GPU_MEMORY_FRACTION: float = 0.22
# Pinned Granite index weight bytes (granite42-download-verified.json). BF16
# LoRA training must hold every base weight resident, so this is a hard floor.
GRANITE_WEIGHT_BYTES: int = 16_761_102_336
# Headroom beyond a stage's own floor for the evaluator, MCP solver children and
# vLLM's API process (each well under 1 GiB RSS in r2) plus kernel/page-cache
# slack. A chosen margin, not a measurement: on 2026-10-21 the GB10 OOM-killed
# a process at 3 GB MemAvailable, so a stage must not start that close.
MEMORY_MARGIN_BYTES: int = 8 << 30
# Shared llama-swap models unload after globalTTL = 600 s idle; allow for that
# plus a spell of active use by other gateway clients before refusing.
MEMORY_WAIT_TIMEOUT_S: float = 3600.0
MEMINFO: Path = Path("/proc/meminfo")
PORT: int = 8101
# Model startup took about 90 s in the first run; allow ten minutes cold.
STARTUP_TIMEOUT_S: float = 600.0
# Poll actual process/container state every five seconds, without active retries.
POLL_INTERVAL_S: float = 5.0
BENCHMARK: Path = Path("benchmarks/power-agent-bench-lite/results/domain-held-out-20261020/examples.jsonl")
EXCLUDED: Path = Path("powercoder/datasets/smoke/examples.jsonl")
GRANITE_CONFIG: Path = Path("training/unsloth/config.granite42.yaml")
REPO: Path = Path(__file__).resolve().parents[1]
# The exact Qwen base mount and snapshot the r2 base evaluation served; the
# snapshot's files are symlinks into the hub cache, so mount the hub, not it.
HF_HUB: Path = Path.home() / ".cache/huggingface/.cache/hub"
QWEN_BASE_SNAPSHOT: str = "models--Qwen--Qwen3.5-4B/snapshots/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"
QWEN_STUDENT: Path = Path("training/unsloth/out/merged-bf16")


def meminfo_bytes(field: str, meminfo: Path = MEMINFO) -> int:
    """Read one /proc/meminfo field (reported in KiB) as bytes."""
    for line in meminfo.read_text().splitlines():
        name, _, value = line.partition(":")
        if name == field:
            return int(value.split()[0]) * 1024
    raise KeyError(f"{field} missing from {meminfo}")


def await_memory(stage: str, required: int, events: TextIO, meminfo: Path = MEMINFO,
                 timeout: float = MEMORY_WAIT_TIMEOUT_S, sleep: Any = time.sleep,
                 clock: Any = time.monotonic) -> int:
    """Wait for MemAvailable to cover a stage's floor plus margin, else refuse.

    GB10 memory is unified, so other tenants (llama-swap models, persistent vLLM
    backends) compete with every stage. Starting below the floor invites a
    mid-stage OOM kill, which wastes hours and leaves partial evidence.

    Returns:
        The MemAvailable bytes observed when the stage was admitted.

    Raises:
        RuntimeError: Headroom did not appear within ``timeout`` seconds.
    """
    needed = required + MEMORY_MARGIN_BYTES
    deadline = clock() + timeout
    waiting = False
    while True:
        available = meminfo_bytes("MemAvailable", meminfo)
        if available >= needed:
            record(events, "memory_admitted", {"stage": stage, "available": available, "needed": needed})
            return available
        if not waiting:
            record(events, "memory_wait", {"stage": stage, "available": available, "needed": needed})
            waiting = True
        if clock() >= deadline:
            record(events, "memory_refused", {"stage": stage, "available": available, "needed": needed})
            raise RuntimeError(f"{stage}: MemAvailable {available} < {needed} bytes after {timeout} s")
        sleep(POLL_INTERVAL_S)


def container_info(name: str) -> dict[str, Any]:
    """Inspect the exact live container handle without exposing environment secrets."""
    template = '{"image": "{{.Image}}", "command": {{json .Config.CreateCommand}}, "state": {{json .State}}}'
    return json.loads(subprocess.check_output(["podman", "inspect", name, "--format", template], text=True))


def command(args: list[str], log: Path, events: TextIO) -> None:
    """Run one stage exactly once, preserving its complete stdout and stderr."""
    record(events, "stage_start", {"command": args, "log": str(log), "unix_time": time.time()})
    with log.open("x") as output:
        process = subprocess.Popen(args, stdout=output, stderr=subprocess.STDOUT, cwd=REPO)
        record(events, "stage_process", {"pid": process.pid, "command": args})
        code = process.wait()
    record(events, "stage_exit", {"exit_code": code, "unix_time": time.time(), "log": str(log)})
    if code:
        raise RuntimeError(f"Stage exited {code}: {args}; see {log}")


def serve(source: Path, name: str, model: str, reasoning: str, root: Path, events: TextIO,
          memory_fraction: float = GPU_MEMORY_FRACTION, model_path: str = "") -> None:
    """Start a pinned, local-only model endpoint and wait for actual readiness.

    ``source`` is mounted read-only at /student; ``model_path`` selects a
    directory inside it (the Hugging Face hub layout needs its whole tree).
    """
    # vLLM preallocates this fraction of total memory, so that is the floor.
    await_memory(name, int(memory_fraction * meminfo_bytes("MemTotal")), events)
    args = ["podman", "run", "-d", "--name", name, "--device", "nvidia.com/gpu=all",
            "--security-opt", "label=disable", "--shm-size", "1g", "-p", f"127.0.0.1:{PORT}:8000",
            "-v", f"{source.resolve()}:/student:ro", "-e", "HF_HUB_OFFLINE=1", "-e", "TRANSFORMERS_OFFLINE=1",
            "--entrypoint", "/opt/venv/bin/python", INFERENCE_IMAGE,
            "-m", "vllm.entrypoints.openai.api_server", "--model", f"/student/{model_path}".rstrip("/"),
            "--served-model-name", model,
            "--host", "0.0.0.0", "--port", "8000", "--dtype", "bfloat16", "--max-model-len", str(CONTEXT_TOKENS),
            "--max-num-seqs", "1", "--gpu-memory-utilization", str(memory_fraction), "--enforce-eager",
            "--enable-auto-tool-choice", "--tool-call-parser", "qwen3_coder", "--reasoning-parser", reasoning,
            "--generation-config", "vllm", "--limit-mm-per-prompt", '{"image":0,"video":0}']
    command(args, root / f"{name}-start.log", events)
    info = container_info(name)
    (root / f"{name}-serving.json").write_text(json.dumps(info, indent=2) + "\n")
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    with httpx.Client(timeout=POLL_INTERVAL_S) as client:
        while time.monotonic() < deadline:
            if not container_info(name)["state"]["Running"]:
                raise RuntimeError(f"Model server exited: {name}; inspect podman logs")
            try:
                response = client.get(f"http://127.0.0.1:{PORT}/v1/models")
                if response.status_code == 200 and model in {r["id"] for r in response.json()["data"]}:
                    record(events, "server_ready", {"container": name, "model": model})
                    return
            except httpx.TransportError:
                # A just-launched server has no listener until its weights load,
                # and rootless port forwarding resets connections until it does
                # (r3's first launch died on ReadError 104); container exit is
                # the failure signal, checked above.
                pass
            time.sleep(POLL_INTERVAL_S)
    raise RuntimeError(f"Server startup deadline exceeded: {name}")


def evaluate(model: str, directory: Path, events: TextIO) -> None:
    """Evaluate the full suite with the same command and budgets for every model."""
    command([sys.executable, "-m", "powercoder.inference.evaluate_agent", "--base-url", f"http://127.0.0.1:{PORT}",
             "--model", model, "--tasks", str(BENCHMARK), "--exclude", str(EXCLUDED), "--out", str(directory)],
            directory.parent / f"{directory.name}.log", events)
    summary, _ = verified_run(directory)
    record(events, "evaluation_complete", {"directory": str(directory), "summary": summary})


def stop_server(name: str, root: Path, events: TextIO) -> None:
    """Release only this experiment's server after its full evaluation completes."""
    command(["podman", "logs", name], root / f"{name}-server.log", events)
    command(["podman", "stop", name], root / f"{name}-stop.log", events)


def write_comparison(base: Path, candidate: Path, destination: Path, events: TextIO) -> dict[str, Any]:
    """Persist the measured delta even when it fails the requested gain threshold."""
    result = compare(base, candidate)
    with destination.open("x") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    record(events, "comparison_complete", {"path": str(destination), "result": result})
    return result


def write_numerical_comparison(base: Path, candidate: Path, destination: Path, events: TextIO) -> dict[str, Any]:
    """Add M09 numerical correctness while preserving the stricter agent scores."""
    result = compare_domain(base, candidate)
    with destination.open("x") as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write("\n")
    # Full individual responses stay in the artifact, keeping the stage journal compact.
    record(events, "numerical_comparison_complete", {"path": str(destination),
        "scorer_sha256": result["scorer_sha256"], "n_tasks": result["n_tasks"],
        "base_pass_at_1": result["base_pass_at_1"], "student_pass_at_1": result["student_pass_at_1"],
        "delta_percentage_points": result["delta_percentage_points"], "domain_threshold_met": result["domain_threshold_met"]})
    return result


def run(args: argparse.Namespace, events: TextIO) -> None:
    """Advance only after authoritative completion of each prior stage."""
    import yaml

    for label, source, model_path in (("qwen-base", HF_HUB, QWEN_BASE_SNAPSHOT),
                                      ("qwen-student", QWEN_STUDENT, "")):
        name = f"powercoder-{args.root.name}-{label}"
        model = f"powercoder-{label}"
        serve(source, name, model, "qwen3", args.root, events, model_path=model_path)
        evaluate(model, args.root / ("base" if label == "qwen-base" else "student"), events)
        stop_server(name, args.root, events)
    qwen = write_comparison(args.root / "base", args.root / "student", args.root / "qwen-comparison.json", events)
    qwen_numerical = write_numerical_comparison(args.root / "base", args.root / "student",
                                               args.root / "qwen-numerical-comparison.json", events)

    record(events, "await_download", {"container": args.download_container})
    while True:
        download = container_info(args.download_container)
        if not download["state"]["Running"]:
            if download["state"]["ExitCode"]:
                raise RuntimeError("Pinned Granite download failed; inspect its container logs")
            break
        time.sleep(POLL_INTERVAL_S)
    config = yaml.safe_load(GRANITE_CONFIG.read_text())
    hashes = verify_base(config["model"])
    record(events, "download_verified", {"container": download, "sha256": hashes})
    await_memory("granite-training", GRANITE_WEIGHT_BYTES, events)
    command(["podman", "run", "--name", f"powercoder-{args.root.name}-granite-training", "--device", "nvidia.com/gpu=all",
             "--network", "none", "--security-opt", "label=disable", "-v", f"{REPO}:/workspace",
             "-e", "HF_HUB_OFFLINE=1", "-e", "TRANSFORMERS_OFFLINE=1", "-e", "PYTHONUNBUFFERED=1",
             TRAINING_IMAGE, "python", "-m", "training.granite.train", "--config", str(GRANITE_CONFIG)],
            args.root / "granite-training.log", events)

    for label, source in (("granite-base", Path(config["model"]["name"])),
                          ("granite-student", Path(config["output"]["dir"]) / "merged-bf16")):
        name = f"powercoder-{args.root.name}-{label}"
        model = f"powercoder-{label}"
        serve(source, name, model, "nemotron_v3", args.root, events,
              memory_fraction=GRANITE_GPU_MEMORY_FRACTION)
        evaluate(model, args.root / label, events)
        stop_server(name, args.root, events)
    granite = write_comparison(args.root / "granite-base", args.root / "granite-student",
                               args.root / "granite-comparison.json", events)
    write_comparison(args.root / "base", args.root / "granite-student", args.root / "granite-vs-qwen-base.json", events)
    write_comparison(args.root / "student", args.root / "granite-student", args.root / "granite-vs-qwen-student.json", events)
    granite_numerical = write_numerical_comparison(args.root / "granite-base", args.root / "granite-student",
                                                  args.root / "granite-numerical-comparison.json", events)
    write_numerical_comparison(args.root / "base", args.root / "granite-student",
                               args.root / "granite-vs-qwen-base-numerical.json", events)
    write_numerical_comparison(args.root / "student", args.root / "granite-student",
                               args.root / "granite-vs-qwen-student-numerical.json", events)
    record(events, "pipeline_complete", {"qwen_domain_threshold_met": qwen["domain_threshold_met"],
        "granite_domain_threshold_met": granite["domain_threshold_met"],
        "qwen_solver_verified_threshold_met": qwen_numerical["domain_threshold_met"],
        "granite_solver_verified_threshold_met": granite_numerical["domain_threshold_met"]})


def main() -> None:
    """Create a fresh run root and durable journal; refuse automatic re-execution."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="New run directory; must not exist")
    parser.add_argument("--download-container", required=True)
    args = parser.parse_args()
    args.root.mkdir()
    # A supervisor's stop arrives as SIGTERM; unwind so the journal records it.
    signal.signal(signal.SIGTERM, lambda signum, _frame: sys.exit(128 + signum))
    with (args.root / "pipeline.jsonl").open("x") as events:
        record(events, "driver_start", {"pid": os.getpid(), "unix_time": time.time(),
            "source_sha256": {str(p.relative_to(REPO)): digest(p) for parent in (REPO / "powercoder/inference", REPO / "training/granite")
                              for p in parent.glob("*.py")}, "driver_sha256": digest(Path(__file__))})
        try:
            run(args, events)
        except Exception as error:
            record(events, "driver_error", {"type": type(error).__name__, "message": str(error)})
            raise
        except SystemExit as stop:
            record(events, "driver_stopped", {"exit_code": stop.code, "unix_time": time.time()})
            raise


if __name__ == "__main__":
    main()
