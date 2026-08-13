"""Hand-rolled recursive-descent parser + serializer for the CLIF subset
in `grammar.py`. See that module's docstring for why hand-rolled rather
than a parser-generator dependency.

`parse(text)` turns one CLIF sentence into the `ast_nodes` tree;
`serialize(node)` turns a tree back into CLIF text (a canonical
single-space-separated rendering, not a whitespace-preserving
pretty-printer). docs/backlog/0007's step 2 -- "confirm it round-trips
real hand-written CLIF ... back to an AST" -- is `test_clif_demo.py`
asserting `parse(text) == parse(serialize(parse(text)))` for each fixture:
the *parsed structure* survives a serialize/re-parse cycle, which is the
meaningful round-trip property for a tree that doesn't remember source
whitespace by design.
"""
from __future__ import annotations

import re
from typing import Final

from .ast_nodes import (
    And,
    Atom,
    Binding,
    Exists,
    Forall,
    FunctionTerm,
    If,
    Numeral,
    Sentence,
    Term,
    Var,
)

# grammar.py's `name` production: a letter followed by letters/digits/
# '_'/'-'. Matches every predicate, functor, constant, and variable name
# in fixtures.py (e.g. "V-SA", "VS_HEY_600_TEST", "interconnector").
_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]*$")

# grammar.py's `numeral` production: non-negative integers only (see
# ast_nodes.Numeral's docstring for why -- no Lab 4 fixture needs more).
_NUMERAL_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9]+$")

_KEYWORDS: Final[frozenset[str]] = frozenset({"and", "if", "forall", "exists"})


class ParseError(Exception):
    """Raised on any malformed input -- unbalanced parens, an unknown
    keyword where a sentence was expected, a name that doesn't match
    `_NAME_RE`, etc. Deliberately a single exception type (not one per
    failure mode): this demo's callers (tests, `demo_llm.py`) only need
    to know "did this parse," and a single type keeps the fixture-driven
    tests in `test_clif_demo.py` simple (`pytest.raises(ParseError)`)."""


def _tokenize(text: str) -> list[str]:
    """Split CLIF text into tokens: `(`, `)`, and maximal runs of
    non-paren non-whitespace characters. CLIF (this subset) needs no
    other token boundary -- no string literals, no comments -- so a
    single regex is the whole lexer."""
    tokens = re.findall(r"\(|\)|[^\s()]+", text)
    if not tokens:
        raise ParseError("empty input: no tokens found")
    return tokens


class _Parser:
    """Recursive-descent parser over a flat token list. One instance per
    `parse()` call; `_pos` is the only mutable state, advanced by
    `_advance()`."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> str:
        if self._pos >= len(self._tokens):
            raise ParseError("unexpected end of input")
        return self._tokens[self._pos]

    def _advance(self) -> str:
        tok = self._peek()
        self._pos += 1
        return tok

    def _expect(self, literal: str) -> None:
        tok = self._advance()
        if tok != literal:
            raise ParseError(f"expected {literal!r}, got {tok!r}")

    def _parse_name(self) -> str:
        tok = self._advance()
        if not _NAME_RE.match(tok):
            raise ParseError(f"not a valid name: {tok!r}")
        return tok

    def at_end(self) -> bool:
        return self._pos >= len(self._tokens)

    # -- sentence ::= atomic-sentence | "(and" ...) | "(if" ...)
    #               | "(forall" ...) | "(exists" ...)
    def parse_sentence(self) -> Sentence:
        self._expect("(")
        head = self._peek()
        if head == "and":
            self._advance()
            conjuncts = [self.parse_sentence()]
            while self._peek() != ")":
                conjuncts.append(self.parse_sentence())
            self._expect(")")
            if len(conjuncts) < 2:
                raise ParseError("'and' needs at least two conjuncts")
            return And(tuple(conjuncts))
        if head == "if":
            self._advance()
            antecedent = self.parse_sentence()
            consequent = self.parse_sentence()
            self._expect(")")
            return If(antecedent, consequent)
        if head in ("forall", "exists"):
            self._advance()
            bindings = self._parse_bindings()
            body = self.parse_sentence()
            self._expect(")")
            return Forall(bindings, body) if head == "forall" else Exists(bindings, body)
        # Otherwise: atomic-sentence ::= "(" name term* ")"
        predicate = self._parse_name()
        if predicate in _KEYWORDS:
            # Reachable only if a keyword appears where a predicate name
            # was expected in a *nested* position, e.g. "(and (if ...))"
            # -- the outer dispatch above already handles keywords at
            # sentence-head position, so this guards malformed input like
            # "((and) foo)".
            raise ParseError(f"{predicate!r} used as a predicate name")
        args = []
        while self._peek() != ")":
            args.append(self.parse_term())
        self._expect(")")
        return Atom(predicate, tuple(args))

    # -- term ::= name | numeral | "(" name term+ ")"
    def parse_term(self) -> Term:
        if self._peek() == "(":
            self._advance()
            functor = self._parse_name()
            args = [self.parse_term()]
            while self._peek() != ")":
                args.append(self.parse_term())
            self._expect(")")
            return FunctionTerm(functor, tuple(args))
        tok = self._peek()
        if _NUMERAL_RE.match(tok):
            self._advance()
            return Numeral(int(tok))
        return Var(self._parse_name())

    # -- bindings ::= "(" binding+ ")"
    def _parse_bindings(self) -> tuple[Binding, ...]:
        self._expect("(")
        if self._peek() == ")":
            # Checked before consuming (not via an "if not bindings" check
            # after the fact): the grammar's `binding+` is one-or-more, so
            # an empty list is a real rejection, not just an edge case
            # that happens to fall out of the loop below with a confusing
            # "not a valid name: ')'" message instead.
            raise ParseError("quantifier needs at least one binding")
        bindings = [self._parse_binding()]
        while self._peek() != ")":
            bindings.append(self._parse_binding())
        self._expect(")")
        return tuple(bindings)

    # -- binding ::= name | "(" name name ")"
    def _parse_binding(self) -> Binding:
        if self._peek() == "(":
            self._advance()
            var = self._parse_name()
            type_ = self._parse_name()
            self._expect(")")
            return Binding(var, type_)
        return Binding(self._parse_name(), None)


def parse(text: str) -> Sentence:
    """Parse one CLIF sentence, raising `ParseError` on any grammar
    violation or trailing input after the sentence closes.

    Args:
        text: CLIF text, e.g. `"(interconnector V-SA VIC1 SA1)"`.

    Returns:
        The parsed `ast_nodes.Sentence`.
    """
    parser = _Parser(_tokenize(text))
    sentence = parser.parse_sentence()
    if not parser.at_end():
        raise ParseError(f"trailing tokens after sentence: {parser._tokens[parser._pos:]}")
    return sentence


def _serialize_term(term: Term) -> str:
    if isinstance(term, Var):
        return term.name
    if isinstance(term, Numeral):
        return str(term.value)
    if isinstance(term, FunctionTerm):
        return f"({term.functor} {' '.join(_serialize_term(a) for a in term.args)})"
    raise TypeError(f"not a Term: {term!r}")


def _serialize_binding(binding: Binding) -> str:
    if binding.type_ is None:
        return binding.var
    return f"({binding.var} {binding.type_})"


def serialize(sentence: Sentence) -> str:
    """Render a `Sentence` back to CLIF text (canonical single-space
    form -- see module docstring for why this isn't whitespace-
    preserving).

    Args:
        sentence: an `ast_nodes.Sentence`.

    Returns:
        CLIF text that `parse()` accepts and that parses back to a
        structurally-equal tree.
    """
    if isinstance(sentence, Atom):
        parts = [sentence.predicate, *(_serialize_term(a) for a in sentence.args)]
        return f"({' '.join(parts)})"
    if isinstance(sentence, And):
        return f"(and {' '.join(serialize(c) for c in sentence.conjuncts)})"
    if isinstance(sentence, If):
        return f"(if {serialize(sentence.antecedent)} {serialize(sentence.consequent)})"
    if isinstance(sentence, (Forall, Exists)):
        keyword = "forall" if isinstance(sentence, Forall) else "exists"
        bindings = " ".join(_serialize_binding(b) for b in sentence.bindings)
        return f"({keyword} ({bindings}) {serialize(sentence.body)})"
    raise TypeError(f"not a Sentence: {sentence!r}")
