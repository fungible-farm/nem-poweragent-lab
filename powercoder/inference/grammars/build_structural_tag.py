"""Build the forced-first-turn structural tag from the served tool list (run in the vLLM image).

xgrammar (Apache-2.0, mlc-ai) is vLLM 0.31's structured-output backend and
ships a structural tag for the Qwen XML tool-call format (``qwen_3_5``), which
both Qwen3.5 and Granite 4.2's chat templates emit. A structural tag constrains
only the content of the model's own tags, so unlike ``tool_choice="required"``
(which vLLM turns into a JSON-array schema) it keeps the trained format.

vLLM applies structured outputs after ``</think>`` (``enable_in_reasoning`` is
False by default), so the tag has no reasoning prefix; it is wrapped to allow
the 0-2 newlines both trained models emit after ``</think>``, then requires at
least one tool call. Checked against all 357 r6 trajectories: every trained
tool-call turn is accepted, every final answer and every malformed injected
call (FM-7, FM-1) rejected.

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
