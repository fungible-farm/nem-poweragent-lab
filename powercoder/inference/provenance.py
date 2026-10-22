"""Refuse answers whose numbers did not come from the solver.

User rule, 2026-10-22: an agent must never guess or make up a number. The
first r6 Qwen student answered report tasks with invented voltages and no tool
call, and the solver-verified metric (``domain_scorecard`` v1) would have
counted a lucky or memorised value as a pass, because it checks only the final
numbers. This makes provenance part of every score:

a number in the final answer is *traced* when a number from one of this
attempt's tool responses, or from the task prompt (case names, element ids,
targets), equals it at the precision the answer printed (half a unit in its
last printed digit). An answer with any untraced number is ``fabricated``,
whatever its accuracy. Arithmetic the model did itself (a residual, a
difference) is untraced too: only software outputs count.
"""

from __future__ import annotations

import json
import re
from typing import Any, TypedDict

# Numbers as an answer prints them: unsigned, optional decimals or exponent.
# The sign is ignored on both sides ("N-1" must not read as minus one).
ANSWER_NUMBER: re.Pattern[str] = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)(?![\w])")
SOURCE_NUMBER: re.Pattern[str] = re.compile(r"\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
# Float noise allowance on top of half a unit in the last printed digit.
RELATIVE_SLACK: float = 1e-9


class Provenance(TypedDict):
    """Which of an answer's numbers trace to the solver or prompt."""

    numbers: list[str]
    untraced: list[str]
    traced: bool


def printed_tolerance(text: str) -> float:
    """Half a unit in the last digit ``text`` prints (``1.0941`` -> 5e-5, ``39`` -> 0.5)."""
    mantissa, _, exponent = text.lower().partition("e")
    decimals = len(mantissa.partition(".")[2])
    return 0.5 * 10.0 ** (-decimals + (int(exponent) if exponent else 0))


def json_numbers(value: Any) -> list[float]:
    """Numeric leaves of a decoded tool payload, plus numbers inside non-hash strings.

    Evidence hashes (``sha256:...``) are skipped: their hex digit runs would let a
    small invented integer trace by coincidence. A string leaf that is itself
    JSON (the MCP text content) is decoded and walked.
    """
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, dict):
        return [n for item in value.values() for n in json_numbers(item)]
    if isinstance(value, list):
        return [n for item in value for n in json_numbers(item)]
    if isinstance(value, str):
        if value.startswith("sha256:"):
            return []
        try:
            decoded = json.loads(value)
        except ValueError:
            return [float(match) for match in SOURCE_NUMBER.findall(value)]
        return json_numbers(decoded) if isinstance(decoded, (dict, list)) else [float(match) for match in SOURCE_NUMBER.findall(value)]
    return []


def source_numbers(events: list[dict[str, Any]], prompt: str) -> list[float]:
    """Every number in the attempt's tool responses and in the task prompt."""
    numbers = [float(match) for match in SOURCE_NUMBER.findall(prompt)]
    for event in events:
        if event["kind"] == "tool_response":
            numbers += json_numbers(event["payload"]["result"])
    return numbers


def check(answer: str, events: list[dict[str, Any]], prompt: str) -> Provenance:
    """Trace each number in ``answer`` to the attempt's own tool responses or prompt."""
    printed = ANSWER_NUMBER.findall(answer)
    sources = source_numbers(events, prompt)
    untraced = []
    for text in printed:
        value, tolerance = float(text), printed_tolerance(text)
        slack = tolerance + RELATIVE_SLACK * abs(value)
        if not any(abs(abs(source) - value) <= slack for source in sources):
            untraced.append(text)
    return {"numbers": printed, "untraced": untraced, "traced": not untraced}
