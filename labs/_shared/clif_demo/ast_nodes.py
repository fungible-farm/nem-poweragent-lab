"""AST node types for the CLIF subset defined in `grammar.py`.

Plain frozen dataclasses, not a parser-generator's generated tree -- this
grammar is small enough (five sentence forms, two term forms) that a
generated tree would add indirection without buying anything. Every node
type maps 1:1 onto a production in `grammar.CLIF_SUBSET_EBNF`, so reading
the two files side by side is enough to see the whole design.

`Term` is `Var | Numeral | FunctionTerm`; `Sentence` is `Atom | And | If |
Forall | Exists`. Frozen + eq-by-value so two independently-parsed trees
for the same axiom compare equal in tests (`parse(serialize(parse(x))) ==
parse(x)`), which is exactly the round-trip property step 3 of
docs/backlog/0007's recommended scope asks for.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class Var:
    """A name used as a term: either a constant (e.g. `V-SA`) or a bound
    variable (e.g. `x` inside a `forall`/`exists` body) -- CLIF's
    untyped/weakly-typed abstract syntax does not distinguish the two at
    the term level, only at the point a name is (or isn't) bound by an
    enclosing quantifier. See grammar.py's `name` production."""

    name: str


@dataclass(frozen=True)
class Numeral:
    """An integer literal term, e.g. the `600` in `(exceeds (flow V-SA)
    600)`. Restricted to non-negative integers -- the only numeral shape
    any Lab 4 fixture axiom needs (a rounded MW limit) -- not CLIF's full
    numeral syntax (signs, decimals, exponents)."""

    value: int


@dataclass(frozen=True)
class FunctionTerm:
    """A nested term `(functor arg arg...)`, e.g. `(flow V-SA)` standing
    for "the flow on V-SA". See grammar.py's `term` production, third
    alternative."""

    functor: str
    args: tuple["Term", ...]


Term = Union[Var, Numeral, FunctionTerm]


@dataclass(frozen=True)
class Atom:
    """An atomic sentence: a predicate applied to terms, e.g.
    `(interconnector V-SA VIC1 SA1)`. See grammar.py's
    `atomic-sentence` production."""

    predicate: str
    args: tuple[Term, ...]


@dataclass(frozen=True)
class And:
    """`(and s1 s2 ...)`, at least two conjuncts (CLIF's own grammar
    allows a single-conjunct `and`, but nothing in this subset's fixtures
    needs that degenerate case, so the parser requires >= 2, matching
    every real `and` in the fixtures)."""

    conjuncts: tuple["Sentence", ...]


@dataclass(frozen=True)
class If:
    """`(if antecedent consequent)` -- CLIF's material-conditional form
    (Sowa's clintro.pdf, "Boolean Combinations": `if p, then q`).
    Binary only (CLIF's own `if` is binary in every published example
    this module cites), not `if` with an antecedent-only or chained
    form."""

    antecedent: "Sentence"
    consequent: "Sentence"


@dataclass(frozen=True)
class Binding:
    """One variable binding inside a quantifier's binding list: either a
    bare name (untyped, e.g. `x`) or a `(name type)` pair (weakly typed,
    e.g. `(c Constraint)` -- CLIF's monadic-relation typing convention,
    Sowa's clintro.pdf "Type Constraints"/"Typed and Untyped Statements").
    `type_` is `None` for the untyped form."""

    var: str
    type_: "str | None"


@dataclass(frozen=True)
class Forall:
    """`(forall (binding...) body)` -- universal quantification. See
    grammar.py's `quantified-sentence` production."""

    bindings: tuple[Binding, ...]
    body: "Sentence"


@dataclass(frozen=True)
class Exists:
    """`(exists (binding...) body)` -- existential quantification."""

    bindings: tuple[Binding, ...]
    body: "Sentence"


Sentence = Union[Atom, And, If, Forall, Exists]
