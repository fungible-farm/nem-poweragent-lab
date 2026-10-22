"""Generate the grammar that forces an agent's first turn to be a solver call.

The problem. An agent asked for a power-flow number can answer before calling
the solver, and then the number can only be a guess: the first r6 Qwen student
answered reports that way, with invented voltages (user rule, 2026-10-22: an
agent must never make up a number). provenance.py fails such answers after the
fact. Constrained decoding removes the possibility: on the first turn the model
can only emit a tool call.

What a structural tag is. vLLM 0.31 decodes with a grammar backend, xgrammar
(Apache-2.0, mlc-ai). At every step it masks out tokens that would break the
grammar. A *structural tag* is xgrammar's JSON description of such a grammar
for tool calls: literal text the model must emit around the call (the model's
own tool-call markup) plus, inside it, the JSON schema each argument must
satisfy. xgrammar ships one for the Qwen XML tool-call format
(``<tool_call><function=NAME><parameter=KEY>value</parameter>...``), model key
``qwen_3_5``; both the Qwen3.5 and the Granite 4.2 chat templates emit exactly
that format, and both students were trained on it.

Why not vLLM's ``tool_choice="required"``. vLLM implements it as a JSON-array
schema (``[{"name": ..., "parameters": ...}]``), a different output format from
the trained XML, so a forced arm built on it would change two things at once.

What this script writes. ``forced_first_turn.structural_tag.json``, built from
``served_tools.json`` (a snapshot of the tool list the MCP server serves; the
grammar embeds those schemas, so it is only valid while they are unchanged, and
tool_probe.ensure_structural_tag_current refuses a run otherwise). vLLM applies
the grammar only after the model's ``</think>`` (``enable_in_reasoning`` is
False), so the grammar has no reasoning part: 0-2 newlines (Qwen emits two,
Granite one), then at least one tool call. Measured against all 357 r6
trajectories: every trained tool-call turn accepted; every final answer and
every malformed call (FM-7 ``"None"``, FM-1 unknown argument) rejected; the
FM-18 ``contingency_line: 0`` calls accepted, because 0 is a valid value.

Requirements: AGENTS.md PC-REQ-2 and PC-REQ-3.

Usage (xgrammar is in the inference image, not this repo's environment)::

    podman run --rm --network none -v "$PWD":/w -w /w --entrypoint /opt/venv/bin/python \\
        <INFERENCE_IMAGE> powercoder/inference/grammars/build_structural_tag.py
"""

from __future__ import annotations

import json
from pathlib import Path

from xgrammar.builtin_structural_tag import get_model_structural_tag

HERE: Path = Path(__file__).resolve().parent
# Newlines allowed between </think> and <tool_call>: Qwen emits 2, Granite 1.
LEADING_NEWLINES: str = "\n{0,2}"


def main() -> None:
    """Write forced_first_turn.structural_tag.json from served_tools.json."""
    tools = json.loads((HERE / "served_tools.json").read_text())
    inner = get_model_structural_tag("qwen_3_5", tools=tools, tool_choice="required",
                                     reasoning="disabled").model_dump()["format"]
    tag = {"type": "structural_tag",
           "format": {"type": "sequence", "elements": [{"type": "regex", "pattern": LEADING_NEWLINES}, inner]}}
    (HERE / "forced_first_turn.structural_tag.json").write_text(json.dumps(tag, indent=1) + "\n")


if __name__ == "__main__":
    main()
