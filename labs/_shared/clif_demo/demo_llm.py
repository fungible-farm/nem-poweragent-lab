#!/usr/bin/env python3
"""docs/backlog/0007's step 3, run for real: point the live self-hosted
Phi-4-mini-instruct pod (`kube/llamacpp-phi-pod.yaml`, llama.cpp server)
at `gbnf.CLIF_SUBSET_GBNF` and check it reliably emits syntactically-valid
CLIF for a Lab 4 fact, then feed the output back through this package's
own `parser.parse()` to confirm.

    uv run labs/_shared/clif_demo/demo_llm.py
    uv run labs/_shared/clif_demo/demo_llm.py --url http://127.0.0.1:8091

**This makes a real network call to a real, already-running server.** It
is a demo script, not a committed pytest test (see this package's README
"Why demo_llm.py isn't a pytest test" for why) -- it needs the pod up,
which the rest of this repo's test suite can't assume for every future
run. If the pod isn't reachable, this script says so plainly and exits
non-zero; it never fabricates a result.

What it actually checks, per prompt in DEMO_PROMPTS:

1. **Grammar-constrained**: POST to `/v1/chat/completions` with
   `grammar: CLIF_SUBSET_GBNF` set, asking the model to assert one real
   Lab 4 fact (from `fixtures.LAB4_AXIOMS`) as a CLIF sentence. Confirms
   the output parses with `parser.parse()` -- i.e. syntactically valid by
   construction, per 0007's own claim ("invalid tokens are simply
   unsamplable").
2. **Freeform (no grammar)**: the identical prompt with no `grammar`
   field, as a control -- 0007's motivating claim is that a small model
   is "reliably bad at freeform-generating" CLIF (unbalanced parens,
   malformed quantifier binding). This checks whether that claim actually
   holds for this specific model on these specific prompts, rather than
   assuming it.

Neither call's *semantic* content (did the model assert something
sensible, not just syntactically legal) is enforced -- there is no
grammar production for "is true of the NEM" -- so this script prints the
raw output plus a human-readable diff against the hand-written fixture
axiom for the same fact, and leaves the semantic judgment to whoever
reads the printed output. See this package's README for what was
actually observed running this against the live pod at implementation
time.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Final, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # .../labs
from _shared.clif_demo.fixtures import (  # noqa: E402
    BONUS_EXISTS_FIXTURE,
    LAB4_AXIOMS,
    ClifAxiom,
)
from _shared.clif_demo.gbnf import CLIF_SUBSET_GBNF  # noqa: E402
from _shared.clif_demo.parser import ParseError, parse, serialize  # noqa: E402

# kube/llamacpp-phi-pod.yaml's server, confirmed live at implementation
# time (`curl http://127.0.0.1:8091/health` -> {"status":"ok"}).
DEFAULT_SERVER_URL: Final[str] = "http://127.0.0.1:8091"

# How long to wait for one completion. Set generously (this is a small
# quantized model on CPU/modest hardware behind a pod, not a latency-
# sensitive path) rather than tuned to any measured p99 -- a demo script
# run by hand, not a service.
REQUEST_TIMEOUT_SECONDS: Final[float] = 120.0

# Enough tokens for the longest fixture axiom (the `binding_rule` forall,
# ~30 CLIF tokens) plus slack for a less compact model rendering (extra
# whitespace, a slightly longer variable-type name choice) without
# truncating mid-sentence.
MAX_COMPLETION_TOKENS: Final[int] = 120

_VOCAB_BLOCK: Final[str] = (
    "You write axioms in a small subset of CLIF (Common Logic Interchange "
    "Format), a LISP-like syntax for first-order logic: (predicate arg1 "
    "arg2 ...), nested terms like (flow V-SA), conjunction (and s1 s2), "
    "implication (if antecedent consequent), and quantifiers (forall "
    "((var Type) ...) body) / (exists ((var Type) ...) body).\n\n"
    "Worked example, a real fact about the AEMO National Electricity "
    "Market: the Heywood interconnector (ID V-SA) connects region VIC1 "
    "and region SA1, written as:\n"
    "(interconnector V-SA VIC1 SA1)\n\n"
    "Another real fact, the general rule for when a network constraint "
    "binds:\n"
    "(forall ((c Constraint) (i Interconnector) (l Limit)) "
    "(if (and (limits c i l) (exceeds (flow i) l)) (binds c)))\n\n"
    "Reply with exactly one CLIF sentence and nothing else -- no "
    "explanation, no markdown fences."
)


class DemoPrompt(NamedTuple):
    """One (English request, expected fixture) pair. `expected` is the
    hand-written axiom this prompt is asking the model to reproduce (in
    substance, not necessarily verbatim) -- used only for the printed
    side-by-side comparison, never to grade/fail the run."""

    label: str
    user_request: str
    expected: ClifAxiom


DEMO_PROMPTS: Final[tuple[DemoPrompt, ...]] = (
    DemoPrompt(
        label="murraylink_topology",
        user_request=(
            "Using the `interconnector` predicate the same way the "
            "worked example uses it for Heywood, assert in CLIF that "
            "Murraylink (interconnector ID V-S-MNSP1) connects region "
            "VIC1 and region SA1."
        ),
        expected=LAB4_AXIOMS[1],  # murraylink_topology
    ),
    DemoPrompt(
        label="heywood_test_constraint_limit",
        user_request=(
            "Assert in CLIF, using the `limits` predicate (arguments: "
            "constraint, interconnector, limit-value), that constraint "
            "VS_HEY_600_TEST limits interconnector V-SA's flow to 600."
        ),
        expected=LAB4_AXIOMS[2],  # heywood_test_constraint_limit
    ),
    # Deliberately more structurally demanding than the two prompts above
    # (which both map almost 1:1 onto a single worked example already
    # shown in _VOCAB_BLOCK): this asks for `exists` + `and` + a nested
    # function term (`flow`/`exceeds`) combined in a shape *not* shown
    # verbatim anywhere in the system prompt, to give the grammar-
    # constrained-vs-freeform comparison an actual chance to diverge --
    # see clif_demo/README.md's "What actually happened" for why the two
    # simpler prompts above did not.
    DemoPrompt(
        label="exists_binding_interconnector_bonus",
        user_request=(
            "Using `exists`, `and`, `exceeds`, and the nested term "
            "`(flow <id>)`, assert in CLIF that there exists some "
            "interconnector i (type Interconnector) between VIC1 and "
            "SA1 such that i's flow exceeds i's own limit l (type "
            "Limit) -- i.e. combine `interconnector`, `exceeds`, and "
            "`flow` under one `exists` with two bound variables."
        ),
        expected=BONUS_EXISTS_FIXTURE,
    ),
)


class CompletionResult(NamedTuple):
    """One HTTP call's outcome: the raw text (or `None` on failure), and
    the error message (or `None` on success) -- kept as two optional
    fields rather than raising, so `run_demo` can print every prompt's
    both-conditions result even if one call fails."""

    text: "str | None"
    error: "str | None"


def _call_chat_completion(
    server_url: str, user_request: str, grammar: "str | None"
) -> CompletionResult:
    """POST one `/v1/chat/completions` request to the live llama.cpp
    server. Real HTTP, stdlib `urllib` only (no new dependency for a
    single POST -- see grammar.py's docstring on this package's
    zero-new-dependency stance).

    Args:
        server_url: base URL, e.g. `http://127.0.0.1:8091`.
        user_request: the English ask (one of DEMO_PROMPTS' `user_request`).
        grammar: GBNF text to constrain decoding with, or `None` for an
            unconstrained (freeform) control call.

    Returns:
        A CompletionResult -- `.text` set on success, `.error` set (with
        `.text` `None`) on any failure (connection refused, timeout,
        non-2xx response). Never raises -- callers print `.error`
        directly and move on, so one bad call doesn't abort the whole
        demo.
    """
    payload: dict = {
        "messages": [
            {"role": "system", "content": _VOCAB_BLOCK},
            {"role": "user", "content": user_request},
        ],
        "max_tokens": MAX_COMPLETION_TOKENS,
        "temperature": 0.2,  # low but nonzero -- a semantic-content demo, not a determinism proof
    }
    if grammar is not None:
        payload["grammar"] = grammar

    req = urllib.request.Request(
        f"{server_url}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return CompletionResult(None, f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}")
    except urllib.error.URLError as e:
        return CompletionResult(None, f"connection failed: {e.reason}")
    except TimeoutError:
        return CompletionResult(None, f"timed out after {REQUEST_TIMEOUT_SECONDS}s")

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        return CompletionResult(None, f"unexpected response shape ({e}): {body}")
    return CompletionResult(content.strip(), None)


def _report_one(condition: str, result: CompletionResult) -> bool:
    """Print one call's outcome and whether it parses. Returns True iff
    the call succeeded AND the returned text parses as valid CLIF under
    this package's own `parser.parse()`."""
    print(f"  [{condition}]")
    if result.error is not None:
        print(f"    call FAILED: {result.error}")
        return False
    print(f"    raw output: {result.text!r}")
    try:
        sentence = parse(result.text)
    except ParseError as e:
        print(f"    parse: FAILED -- {e}")
        return False
    print(f"    parse: OK -- {sentence!r}")
    print(f"    re-serialized: {serialize(sentence)}")
    return True


def run_demo(server_url: str) -> bool:
    """Run every DEMO_PROMPTS entry under both conditions (grammar-
    constrained, freeform) against the live server, printing everything.

    Returns:
        True iff every grammar-constrained call both succeeded and
        parsed (the freeform control calls are informational only -- see
        module docstring -- and never affect this return value).
    """
    all_constrained_ok = True
    for prompt in DEMO_PROMPTS:
        print(f"\n=== {prompt.label} ===")
        print(f"Prompt: {prompt.user_request}")
        print(f"Hand-written fixture for comparison ({prompt.expected.name}): {prompt.expected.clif}")

        constrained = _call_chat_completion(server_url, prompt.user_request, CLIF_SUBSET_GBNF)
        ok = _report_one("grammar-constrained", constrained)
        all_constrained_ok = all_constrained_ok and ok

        freeform = _call_chat_completion(server_url, prompt.user_request, None)
        _report_one("freeform (no grammar, control)", freeform)

    return all_constrained_ok


def main() -> None:
    parser_ = argparse.ArgumentParser(description=__doc__)
    parser_.add_argument("--url", default=DEFAULT_SERVER_URL, help="llama.cpp server base URL")
    args = parser_.parse_args()

    print(f"Calling live llama.cpp server at {args.url} ...")
    ok = run_demo(args.url)

    print("\n" + "=" * 72)
    if ok:
        print("PASS: every grammar-constrained call produced text that parsed as valid CLIF.")
    else:
        print(
            "FAIL: at least one grammar-constrained call either failed outright "
            "or produced text this package's parser rejected -- see above."
        )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
