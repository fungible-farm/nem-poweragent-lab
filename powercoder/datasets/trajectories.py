"""Build tool-call training trajectories in the exact shape of the evaluation.

The r4 students were trained on ``{prompt -> expected.answer}`` text: no tools,
no tool calls, another system prompt, and ``seq_len: 1024``. They were then
evaluated as multi-turn tool agents and scored 0/306 (AGENTS.md FM-19). This
builds what the evaluation actually asks for, from the training split only:

- the evaluation's own system prompt (``tool_probe.SYSTEM_PROMPT``) and the tool
  list the evaluation's MCP server advertises;
- real ``run_study_trial`` calls through that same MCP stdio server, with each
  tool message holding the response exactly as the evaluation feeds it back;
- a final answer written from the measured values: the reference report wording,
  and for fits the bare scale the prompt asks for (the reference fit sentence
  fails the benchmark's own ``extract_scale``).

Each trajectory is written as an evaluation journal and graded by
``evaluate_agent.grade``, the benchmark's own scorer; only passing trajectories
are kept and every drop is counted in the manifest.

Named stand-in (AGENTS.md "Sandbox stand-ins must be named"): the assistant
turns are scripted, not sampled from a teacher model. Fits follow the reference
generator's procedure (``labs/_shared/gridfit.bisection_fit``: try both interval
ends, then bisect); reports make one ``operation="none"`` trial. Scripted turns
carry no reasoning text, so they teach the tool protocol and the search, not a
style of thinking.

Recovery variants (failure-mode fine-tuning, user direction 2026-10-22): every
other training row (by ``example_id``) also gets a variant whose first call is
one of the measured model failures, sent to the real MCP server so the response
is genuine, followed by a one-line note and the correct procedure:

- ``none_string`` (FM-7): ``contingency_line: "None"`` -> a validation error;
- ``contingency_zero`` (FM-18): a fit trial with ``contingency_line: 0`` -> a
  measurement that names "line 0 out of service";
- ``run_power_flow_contingency`` (FM-1/FM-9): an N-1 report through
  ``run_power_flow`` -> rejected, since it has no ``contingency_line``.

The final answer still comes only from the correct calls and passes
``grade()`` (which includes the no-made-up-numbers provenance check).
``mcp-trajectory`` rows are skipped: they are narrated
``load_network``/``run_power_flow`` transcripts, a subfamily the benchmark does
not contain, and ``run_power_flow`` for reports is FM-9's wrong tool.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, TextIO, TypedDict

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from powercoder.datasets import common
from powercoder.datasets.audit import load_rows
from powercoder.inference import powermcp as pm
from powercoder.inference.evaluate_agent import grade
from powercoder.inference.tool_probe import MAX_TOOL_CALLS, MAX_TURNS, SYSTEM_PROMPT, record

# Iteration cap passed to every scripted trial; the reference generator's
# solves converged in 5 iterations on snem-sa-2000, and studies.MAX_ITERATIONS is 100.
TRIAL_MAX_ITER: int = 50
# The scorer requires the reported scale to equal a tried scale exactly, and the
# reference answers print 6 decimals ("s = 1.037500"), so trials use that grid.
SCALE_DECIMALS: int = 6
# Each MCP server is its own process with one pandapower solve at a time; this
# many rows run at once (the evaluation's own concurrency is 8).
CONCURRENCY: int = 8
FIT_OPERATIONS: dict[str, tuple[str, str]] = {
    "pf-load-scale-fit": ("load_scale", "bus_voltage"),
    "pf-line-rating-fit": ("line_rating", "line_loading"),
    "pf-gen-dispatch-fit": ("gen_dispatch", "trafo_loading"),
}
SKIPPED_SUBFAMILIES: frozenset[str] = frozenset({"mcp-trajectory"})
# One recovery variant for every RECOVERY_EVERY-th row in example_id order.
RECOVERY_EVERY: int = 2
# The note the assistant writes after each injected failure, before correcting it.
RECOVERY_NOTES: dict[str, str] = {
    "none_string": ('contingency_line must be an integer or null, not the string "None"; '
                    "for the intact network I omit it."),
    "contingency_zero": ("That trial took line 0 out of service, but the task is the intact network, "
                         "so I omit contingency_line and start the search again."),
    "run_power_flow_contingency": ("run_power_flow has no contingency_line parameter; an N-1 report "
                                   'uses run_study_trial with operation="none".'),
}


class Trajectory(TypedDict):
    """One graded conversation, ready for chat-template rendering."""

    example_id: str
    subfamily: str
    # None for the plain procedure, else the injected failure (RECOVERY_NOTES key).
    fault: str | None
    tools: list[dict[str, Any]]
    messages: list[dict[str, Any]]


class Conversation:
    """Drive the evaluation's MCP server and journal every turn as tool_probe does."""

    def __init__(self, session: ClientSession, journal: TextIO, messages: list[dict[str, Any]]) -> None:
        self.session, self.journal, self.messages = session, journal, messages
        self.calls = 0
        # Text for the next tool-call turn: the correction after an injected failure.
        self.note: str | None = None

    def respond(self, message: dict[str, Any], finish_reason: str) -> None:
        """Record an assistant turn in the shape of a chat completion."""
        record(self.journal, "model_response", {"choices": [{"index": 0, "message": message,
                                                             "finish_reason": finish_reason}]})
        self.messages.append(message)

    async def trial(self, arguments: dict[str, Any], tool: str = "run_study_trial") -> dict[str, Any]:
        """Make one tool-call turn and return the decoded tool response.

        A response that is not JSON (an MCP input-validation error) comes back
        as ``{"error": text}``.
        """
        if self.calls >= min(MAX_TOOL_CALLS, MAX_TURNS - 1):
            raise RuntimeError("Scripted trajectory would exceed the evaluation's budgets")
        call = {"id": f"call_{self.calls}", "type": "function",
                "function": {"name": tool, "arguments": json.dumps(arguments)}}
        self.respond({"role": "assistant", "content": self.note, "tool_calls": [call]}, "tool_calls")
        self.note = None
        record(self.journal, "tool_request", call)
        response = await self.session.call_tool(tool, arguments)
        observed = response.model_dump(mode="json", by_alias=True)
        record(self.journal, "tool_response", {"tool_call_id": call["id"], "result": observed})
        self.messages.append({"role": "tool", "tool_call_id": call["id"],
                              "content": json.dumps(observed, allow_nan=False)})
        self.calls += 1
        text = observed["content"][0]["text"]
        try:
            return json.loads(text)
        except ValueError:
            return {"error": text}

    def answer(self, text: str) -> None:
        """Make the final answering turn, as the evaluation's terminal state expects."""
        self.respond({"role": "assistant", "content": text}, "stop")
        record(self.journal, "terminal", {"state": "answered", "actual_tool_calls": self.calls,
                                          "accuracy_claim": False})


def first_bus(case: str) -> int:
    """The lowest bus index: run_study_trial requires an existing observation element."""
    net, _ = pm._load_network_object(case)
    return int(min(net.bus.index))


def fault_for(row: dict[str, Any], index: int) -> str:
    """The failure injected into a row's recovery variant (alternating for fits)."""
    if row["subfamily"] == "pf-report":
        return "run_power_flow_contingency" if row["task"]["inputs"].get("contingency_line") is not None else "none_string"
    return ("none_string", "contingency_zero")[(index // RECOVERY_EVERY) % 2]


async def inject(conversation: Conversation, row: dict[str, Any], fault: str) -> None:
    """Make the faulty first call for real, then queue the correcting note.

    Raises:
        RuntimeError: if the server did not respond as the failure mode predicts.
    """
    inputs = row["task"]["inputs"]
    if fault == "run_power_flow_contingency":
        observed = await conversation.trial({"network_id": inputs["case"], "contingency_line": inputs["contingency_line"]},
                                            tool="run_power_flow")
        expected = "error" in observed
    elif fault == "none_string":
        if row["subfamily"] == "pf-report":
            arguments = {"network_id": inputs["case"], "operation": "none", "scale": 1.0, "element_id": 0,
                         "observation": "bus_voltage", "observation_id": first_bus(inputs["case"])}
        else:
            operation, observation = FIT_OPERATIONS[row["subfamily"]]
            ids = [int(x) for x in re.findall(r"\d+", inputs["element"])]
            arguments = {"network_id": inputs["case"], "operation": operation, "scale": inputs["scale_lo"],
                         "element_id": ids[0], "observation": observation, "observation_id": ids[-1]}
        observed = await conversation.trial({**arguments, "contingency_line": "None", "max_iter": TRIAL_MAX_ITER})
        expected = "error" in observed
    else:
        operation, observation = FIT_OPERATIONS[row["subfamily"]]
        ids = [int(x) for x in re.findall(r"\d+", inputs["element"])]
        observed = await conversation.trial({"network_id": inputs["case"], "operation": operation,
                                             "scale": inputs["scale_lo"], "element_id": ids[0],
                                             "observation": observation, "observation_id": ids[-1],
                                             "contingency_line": 0, "max_iter": TRIAL_MAX_ITER})
        expected = (observed.get("data") or {}).get("contingency") == "line 0 out of service"
    if not expected:
        raise RuntimeError(f"Injected {fault} did not produce its failure: {str(observed)[:200]}")
    conversation.note = RECOVERY_NOTES[fault]


async def report(conversation: Conversation, row: dict[str, Any]) -> str:
    """One ``operation="none"`` trial, answered in the reference report wording."""
    inputs = row["task"]["inputs"]
    contingency = inputs.get("contingency_line")
    arguments = {"network_id": inputs["case"], "operation": "none", "scale": 1.0, "element_id": 0,
                 "observation": "bus_voltage", "observation_id": first_bus(inputs["case"]),
                 "max_iter": TRIAL_MAX_ITER}
    if contingency is not None:
        arguments["contingency_line"] = contingency
    observed = await conversation.trial(arguments)
    data = observed["data"]
    where = (f" with line {contingency} out of service (N-1 contingency)"
             if contingency is not None else " (base case)")
    return (f"Power flow on '{inputs['case']}'{where} converged in {data['iterations']} iterations. "
            f"Min bus voltage = {data['min_bus_voltage_pu']:.4f} pu, max bus voltage = "
            f"{data['max_bus_voltage_pu']:.4f} pu, max line loading = {data['max_line_loading_percent']:.2f}%, "
            f"voltage violations = {data['voltage_violations']}.")


async def fit(conversation: Conversation, row: dict[str, Any]) -> str:
    """Bracket the target at both interval ends, then bisect to the tolerance.

    Raises:
        RuntimeError: if a trial fails or the target is not bracketed.
    """
    inputs = row["task"]["inputs"]
    operation, observation = FIT_OPERATIONS[row["subfamily"]]
    ids = [int(x) for x in re.findall(r"\d+", inputs["element"])]
    target, tolerance = inputs["target"], inputs["tolerance"]

    async def measure(scale: float) -> float:
        observed = await conversation.trial({
            "network_id": inputs["case"], "operation": operation, "scale": scale, "element_id": ids[0],
            "observation": observation, "observation_id": ids[-1], "max_iter": TRIAL_MAX_ITER})
        if not (observed["data"] or {}).get("metric_valid"):
            raise RuntimeError(f"Trial at s={scale} returned no valid metric: {observed['status']}")
        return observed["data"]["metric"]

    lo, hi = inputs["scale_lo"], inputs["scale_hi"]
    f_lo, f_hi = await measure(lo) - target, await measure(hi) - target
    best = min(((lo, f_lo), (hi, f_hi)), key=lambda point: abs(point[1]))
    if f_lo * f_hi > 0:
        raise RuntimeError("Target not bracketed by the interval ends")
    while abs(best[1]) > tolerance:
        mid = round((lo + hi) / 2, SCALE_DECIMALS)
        f_mid = await measure(mid) - target
        best = (mid, f_mid)
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    # The prompt says "Return only the scale factor". The reference sentence
    # ("...s = 1.037500. At this scale...") fails extract_scale, whose pattern
    # rejects a number followed by a full stop, so the bare scale is answered.
    return f"{best[0]:.{SCALE_DECIMALS}f}"


async def build(row: dict[str, Any], journals: Path, fault: str | None = None) -> tuple[Trajectory | None, str]:
    """Script, journal and grade one row (optionally a recovery variant); return it or the drop reason."""
    parameters = StdioServerParameters(command=sys.executable,
                                       args=["-m", "powercoder.inference.mcp_server", "--study-tools"],
                                       cwd=str(common.REPO_ROOT))
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": row["task"]["prompt"]}]
    journal = journals / f"{row['example_id']}{'-' + fault if fault else ''}.jsonl"
    async with stdio_client(parameters) as (reader, writer), ClientSession(reader, writer) as session:
        await session.initialize()
        tools = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                   "parameters": t.inputSchema}}
                 for t in (await session.list_tools()).tools]
        with journal.open("x") as stream:
            record(stream, "start", {"messages": list(messages), "scripted": True})
            record(stream, "tools", tools)
            conversation = Conversation(session, stream, messages)
            try:
                if fault:
                    await inject(conversation, row, fault)
                text = await (report if row["subfamily"] == "pf-report" else fit)(conversation, row)
            except RuntimeError as error:
                return None, f"script: {error}"
            conversation.answer(text)
    result = await asyncio.to_thread(grade, row, journal)
    if not result["passed"]:
        return None, (f"grade: numerical={result['numerical_pass']} evidence={result['tool_evidence_pass']} "
                      f"provenance={result['provenance_pass']}")
    return {"example_id": row["example_id"], "subfamily": row["subfamily"], "fault": fault, "tools": tools,
            "messages": messages}, "kept"


async def build_all(jobs: list[tuple[dict[str, Any], str | None]], journals: Path) -> list[tuple[Trajectory | None, str]]:
    """Build every (row, fault) job with bounded concurrency, preserving order."""
    gate = asyncio.Semaphore(CONCURRENCY)

    async def bounded(row: dict[str, Any], fault: str | None) -> tuple[Trajectory | None, str]:
        async with gate:
            return await build(row, journals, fault)

    return await asyncio.gather(*(bounded(row, fault) for row, fault in jobs))


def write_in_order(path: Path, rows: list[Trajectory]) -> Path:
    """Write JSONL keeping every key in the order it was built.

    ``common.write_jsonl`` sorts keys. Chat templates render tool schemas with
    ``tojson`` in their stored order, so sorted keys gave the students a tool
    block ({"function": {"description": ...) the evaluation never serves
    ({"type": "function", "function": {"name": ...), for every turn of every
    trajectory (AGENTS.md FM-23).
    """
    with path.open("x") as stream:
        for row in rows:
            stream.write(json.dumps(row, allow_nan=False) + "\n")
    return path


def main() -> int:
    """Build, grade and freeze trajectories with a manifest of every drop."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", type=Path, required=True, help="Training-split examples.jsonl")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise ValueError("Refusing to overwrite a frozen trajectory directory")
    rows = load_rows(args.split)
    if any(r["lifecycle"]["split"] != "train" or r["lifecycle"]["status"] != "verified" for r in rows):
        raise ValueError("Only verified rows in the training split are permitted")
    selected = sorted((r for r in rows if r["subfamily"] not in SKIPPED_SUBFAMILIES), key=lambda r: r["example_id"])
    jobs: list[tuple[dict[str, Any], str | None]] = [(row, None) for row in selected]
    jobs += [(row, fault_for(row, index)) for index, row in enumerate(selected) if index % RECOVERY_EVERY == 0]
    journals = args.out_dir / "journals"
    journals.mkdir(parents=True)
    outcomes = asyncio.run(build_all(jobs, journals))
    kept = [trajectory for trajectory, _ in outcomes if trajectory is not None]
    examples = write_in_order(args.out_dir / "trajectories.jsonl", kept)
    manifest = {
        "dataset": "nem-powercoder-tool-trajectories",
        "split": str(args.split), "split_sha256": hashlib.sha256(args.split.read_bytes()).hexdigest(),
        "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                     cwd=common.REPO_ROOT).stdout.strip(),
        # Uncommitted generator changes make the commit alone insufficient provenance.
        "git_dirty": bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True,
                                         cwd=common.REPO_ROOT).stdout.strip()),
        "system_prompt": SYSTEM_PROMPT, "rows": len(rows),
        "skipped_subfamilies": {name: sum(r["subfamily"] == name for r in rows) for name in sorted(SKIPPED_SUBFAMILIES)},
        "kept": len(kept),
        "kept_by_subfamily": {name: sum(t["subfamily"] == name for t in kept) for name in sorted({t["subfamily"] for t in kept})},
        "kept_by_fault": {str(name): sum(t["fault"] == name for t in kept) for name in [None, *RECOVERY_NOTES]},
        "dropped": {f"{row['example_id']}:{fault}": reason for (row, fault), (_, reason) in zip(jobs, outcomes)
                    if reason != "kept"},
        "tool_calls": {f"{t['example_id']}:{t['fault']}": sum(m["role"] == "tool" for m in t["messages"]) for t in kept},
        "trajectories_sha256": hashlib.sha256(examples.read_bytes()).hexdigest(),
        "benchmark_access": False,
    }
    common.write_json(args.out_dir / "manifest.json", manifest)
    print(json.dumps({k: v for k, v in manifest.items() if k != "tool_calls"}, indent=2))
    return 0 if kept else 1


if __name__ == "__main__":
    raise SystemExit(main())
