"""pytest wrapper for `labs/_shared/clif_demo`
(docs/backlog/0007-clif-x-grammar-constrained-generation.md), following
`labs/_shared/test_scenario_engine.py`'s own sibling-test-file convention
for this directory.

Covers docs/backlog/0007's step 2 -- "confirm it round-trips real
hand-written CLIF for those constraints back to an AST" -- for every
fixture in `fixtures.LAB4_AXIOMS` (the four real Lab 4 axioms) plus the
bonus non-Lab4 `exists` fixture, plus targeted parser-robustness checks
(malformed input actually raises `ParseError`, not silently accepted or a
different exception).

**Does not** call the live llama.cpp pod -- that is `demo_llm.py`, a
runnable-by-hand demo script, not a committed test, because it needs a
server that isn't guaranteed to be running for every future test run (see
that script's own module docstring and `clif_demo/README.md`'s "Why
demo_llm.py isn't a pytest test").
"""
import sys
from pathlib import Path

import pytest

SHARED_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SHARED_DIR.parent))
from _shared.clif_demo.ast_nodes import (  # noqa: E402
    And,
    Atom,
    Binding,
    Forall,
    FunctionTerm,
    If,
    Numeral,
    Var,
)
from _shared.clif_demo.fixtures import BONUS_EXISTS_FIXTURE, LAB4_AXIOMS  # noqa: E402
from _shared.clif_demo.gbnf import CLIF_SUBSET_GBNF  # noqa: E402
from _shared.clif_demo.grammar import CLIF_SUBSET_EBNF  # noqa: E402
from _shared.clif_demo.parser import ParseError, parse, serialize  # noqa: E402

ALL_FIXTURES = (*LAB4_AXIOMS, BONUS_EXISTS_FIXTURE)


@pytest.mark.parametrize("axiom", ALL_FIXTURES, ids=lambda a: a.name)
def test_fixture_parses(axiom):
    """Every fixture axiom -- the four real Lab 4 facts plus the bonus
    exists-only fixture -- parses without error."""
    parse(axiom.clif)


@pytest.mark.parametrize("axiom", ALL_FIXTURES, ids=lambda a: a.name)
def test_fixture_round_trips(axiom):
    """docs/backlog/0007 step 2's round-trip property: parse -> serialize
    -> re-parse yields a structurally-identical AST (frozen dataclasses
    compare by value, so `==` here really is a structural-equality
    check, not identity)."""
    tree = parse(axiom.clif)
    reserialized = serialize(tree)
    tree_again = parse(reserialized)
    assert tree == tree_again, (
        f"{axiom.name}: round-trip mismatch\n  original:  {tree!r}\n  "
        f"after re-parse: {tree_again!r}"
    )


def test_heywood_topology_structure():
    """Spot-check one fixture's exact parsed shape, not just "it
    parsed" -- `heywood_topology` is the simplest fixture (a single
    atomic sentence, three constant terms), so a wrong parse here would
    be a real tokenizer/predicate-vs-term confusion, not just an
    edge case."""
    tree = parse(LAB4_AXIOMS[0].clif)
    assert tree == Atom("interconnector", (Var("V-SA"), Var("VIC1"), Var("SA1")))


def test_heywood_test_constraint_limit_has_numeral_term():
    """`limits` takes a numeral (600) as its third argument -- confirms
    `parse_term` actually distinguishes numerals from names, not just
    that some Term comes back."""
    tree = parse(LAB4_AXIOMS[2].clif)
    assert tree == Atom(
        "limits", (Var("VS_HEY_600_TEST"), Var("V-SA"), Numeral(600))
    )


def test_binding_rule_structure():
    """The `binding_rule` fixture is the grammar's most complex Lab 4
    fixture -- forall over three typed bindings, wrapping an `if` whose
    antecedent is an `and` of two nested-function-term atoms. Checking
    its exact shape exercises every non-atomic production in
    grammar.CLIF_SUBSET_EBNF in one fixture."""
    tree = parse(LAB4_AXIOMS[3].clif)
    assert isinstance(tree, Forall)
    assert tree.bindings == (
        Binding("c", "Constraint"),
        Binding("i", "Interconnector"),
        Binding("l", "Limit"),
    )
    assert isinstance(tree.body, If)
    assert isinstance(tree.body.antecedent, And)
    assert len(tree.body.antecedent.conjuncts) == 2
    limits_atom, exceeds_atom = tree.body.antecedent.conjuncts
    assert limits_atom == Atom("limits", (Var("c"), Var("i"), Var("l")))
    assert exceeds_atom == Atom(
        "exceeds", (FunctionTerm("flow", (Var("i"),)), Var("l"))
    )
    assert tree.body.consequent == Atom("binds", (Var("c"),))


@pytest.mark.parametrize(
    "bad_text,why",
    [
        ("", "empty input"),
        ("(interconnector V-SA VIC1 SA1", "unbalanced -- missing close paren"),
        ("interconnector V-SA VIC1 SA1)", "missing open paren -- no leading '('"),
        ("(interconnector V-SA VIC1 SA1))", "trailing tokens after the sentence closes"),
        ("(and (foo x))", "'and' with only one conjunct"),
        ("(if (foo x))", "'if' with only one sub-sentence (missing consequent)"),
        ("(forall () (foo x))", "quantifier with an empty binding list"),
        ("(foo 1x)", "term that isn't a valid name or a valid numeral"),
        ("(foo -bar)", "name can't start with '-' (grammar.py's `name` production)"),
    ],
)
def test_malformed_clif_raises_parse_error(bad_text, why):
    with pytest.raises(ParseError):
        parse(bad_text)


def test_grammar_constants_are_nonempty_and_mention_the_forms_they_claim():
    """Not a parser test -- a documentation-drift guard: if someone edits
    `parser.py` to add/remove a form but forgets the EBNF/GBNF doc
    strings, this at least catches the grossest case (a keyword
    disappearing from the written grammar entirely)."""
    for keyword in ("forall", "exists", "and", "if"):
        assert keyword in CLIF_SUBSET_EBNF, f"{keyword!r} missing from CLIF_SUBSET_EBNF"
        assert keyword in CLIF_SUBSET_GBNF, f"{keyword!r} missing from CLIF_SUBSET_GBNF"
    assert "root" in CLIF_SUBSET_GBNF, "GBNF must define a 'root' rule (llama.cpp's entry point)"
