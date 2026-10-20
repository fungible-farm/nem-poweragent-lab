"""Evaluate every held-out task through real model-selected MCP calls.

The controller exposes only the task prompt, never the reference or grader.
Each task has one greedy attempt with the qualified probe's fixed budgets.
Journals are durable and exclusive; model protocol failures count as failures,
while transport/backend errors stop the run visibly rather than becoming scores.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, TypedDict

from powercoder.datasets.audit import audit_rows, load_rows
from powercoder.inference.tool_probe import INFERENCE_TIMEOUT_S, MAX_TOKENS, MAX_TOOL_CALLS, MAX_TURNS, probe, record
from training.unsloth.evaluate import FIT_SUBFAMILIES, extract_scale, score_answer

# The audited 2026-10-20 benchmark manifest has exactly 306 unique tasks.
DOMAIN_TASK_COUNT: int = 306


class TaskResult(TypedDict):
    """Independent numerical correctness and controller evidence for one attempt."""

    example_id: str
    subfamily: str
    answer: str
    numerical_pass: bool
    tool_evidence_pass: bool
    passed: bool
    verification: dict[str, Any]
    diagnostics: list[str]
    journal_sha256: str


def relevant_evidence(task: dict[str, Any], answer: str, events: list[dict[str, Any]]) -> bool:
    """Require an actual successful measurement of the requested study.

    For fits the independently checked final scale must itself have been tried.
    A tool call on another case, element, contingency, or scale is insufficient.
    """
    from powercoder.distillation.filter import _parse_element

    inputs = task["task"]["inputs"]
    scale = extract_scale(answer) if task["subfamily"] in FIT_SUBFAMILIES else None
    for event in events:
        if event["kind"] != "tool_response":
            continue
        result = event["payload"]["result"]
        if result.get("isError"):
            continue
        for content in result.get("content", []):
            if content.get("type") != "text":
                continue
            observed = json.loads(content["text"])
            data = observed.get("data") or {}
            study = data.get("study") or {}
            if observed.get("status") not in {"success", "constraint_violation"}:
                continue
            if study.get("network_id") != inputs["case"]:
                continue
            if study.get("contingency_line") != inputs.get("contingency_line"):
                continue
            if task["subfamily"] == "pf-report":
                if study.get("operation") == "none" and data.get("converged"):
                    return True
                continue
            kind, primary, secondary = _parse_element(inputs["element"])
            operation, observation = {
                "bus": ("load_scale", "bus_voltage"),
                "line": ("line_rating", "line_loading"),
                "gen": ("gen_dispatch", "trafo_loading"),
            }[kind]
            if (study.get("operation") == operation
                and study.get("observation") == observation
                and study.get("observation_id") == (secondary if kind == "gen" else primary)
                and (kind == "bus" or study.get("element_id") == primary)
                and scale is not None and study.get("scale") == scale
                and data.get("converged")):
                return True
    return False


def grade(task: dict[str, Any], journal: Path) -> TaskResult:
    """Score a final answer independently; incomplete generations always fail."""
    events = load_rows(journal)
    terminal = events[-1]
    completed = terminal["kind"] == "terminal" and terminal["payload"]["state"] == "answered"
    responses = [e["payload"] for e in events if e["kind"] == "model_response"]
    answer = (responses[-1]["choices"][0]["message"].get("content") or "") if responses else ""
    correct, verification, diagnostics = score_answer(task, answer)
    evidence = relevant_evidence(task, answer, events)
    return {
        "example_id": task["example_id"], "subfamily": task["subfamily"],
        "answer": answer, "numerical_pass": correct, "tool_evidence_pass": evidence,
        "passed": completed and correct and evidence,
        "verification": verification, "diagnostics": diagnostics,
        "journal_sha256": hashlib.sha256(journal.read_bytes()).hexdigest(),
    }


async def evaluate(args: argparse.Namespace) -> None:
    """Audit independence, run all tasks once, and fsync every scored outcome."""
    tasks = load_rows(args.tasks)
    audit = audit_rows(tasks, load_rows(args.exclude))
    if not audit["clean"] or len(tasks) != DOMAIN_TASK_COUNT:
        raise ValueError(f"Expected the complete independent domain suite: {audit}")
    args.out.mkdir(parents=True, exist_ok=False)
    manifest = {
        "model": args.model, "base_url": args.base_url,
        "independence_audit": audit,
        "inputs": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.tasks, args.exclude)},
        "max_turns": MAX_TURNS, "max_tool_calls": MAX_TOOL_CALLS, "max_tokens": MAX_TOKENS,
        "inference_timeout_s": INFERENCE_TIMEOUT_S,
        "temperature": 0.0, "attempts_per_task": 1,
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    results: list[TaskResult] = []
    with (args.out / "results.jsonl").open("x") as scored:
        for task in tasks:
            prompt = args.out / "current-prompt.txt"
            prompt.write_text(task["task"]["prompt"])
            journal = args.out / f"{task['example_id']}.jsonl"
            options = argparse.Namespace(base_url=args.base_url, model=args.model, prompt=prompt, study_tools=True)
            with journal.open("x") as stream:
                try:
                    await probe(options, stream)
                except (ValueError, KeyError, TypeError) as error:
                    # Malformed model-selected arguments are failed attempts.
                    record(stream, "model_protocol_error", {"type": type(error).__name__, "message": str(error)})
                except Exception as error:
                    record(stream, "controller_error", {"type": type(error).__name__, "message": str(error)})
                    raise
            result = grade(task, journal)
            record(scored, "result", result)
            results.append(result)
            print(f"{args.model}: {len(results)}/{len(tasks)} pass={sum(r['passed'] for r in results)}", flush=True)
    summary = {**manifest, "complete": len(results) == len(tasks), "n_tasks": len(results),
               "n_pass": sum(r["passed"] for r in results),
               "pass_at_1": sum(r["passed"] for r in results) / len(results),
               "g5_met": False}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)


def main() -> None:
    """Require an explicit server and a fresh directory for the full benchmark."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--exclude", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    asyncio.run(evaluate(parser.parse_args()))


if __name__ == "__main__":
    main()
