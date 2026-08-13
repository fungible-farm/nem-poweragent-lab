"""`labs/_shared/clif_demo` -- idea-stage demo for
docs/backlog/0007-clif-x-grammar-constrained-generation.md: does a tiny
CLIF (Common Logic Interchange Format, ISO/IEC 24707 Annex A) subset make
a workable grammar-constrained-generation target for this repo's
self-hosted Phi-4-mini pod?

This package is exactly 0007's "Recommended scope, if picked up," three
steps:

1. `grammar.py` -- a tiny, hand-transcribed CLIF-subset EBNF (cited to
   ISO/IEC 24707 and Sowa's own tutorial on it), covering only the forms
   `fixtures.py`'s real Lab 4 axioms need: predicate application, nested
   function terms, `and`, `if`, `forall`/`exists`.
2. `ast_nodes.py` + `parser.py` -- a hand-rolled recursive-descent parser
   for that grammar, round-tripped against `fixtures.py`'s axioms in
   `../test_clif_demo.py`.
3. `gbnf.py` -- the same grammar re-authored as GBNF (llama.cpp's own
   constrained-decoding dialect), plus `demo_llm.py`, a script that
   actually calls the live `kube/llamacpp-phi-pod.yaml` server with that
   grammar and checks the model's output parses with this package's own
   parser.

What this package does **not** claim (see docs/backlog/0007.md's own
"Explicitly out of scope" and this package's README): it is not a CLIF
implementation of any completeness, it does not touch Lab 4's real
constraint-translation code path, and a working demo here is not itself a
decision to adopt CLIF for anything -- it is the cheap kill-or-keep
experiment 0007 asks for, nothing more.
"""
from .ast_nodes import (
    And,
    Atom,
    Binding,
    Exists,
    Forall,
    FunctionTerm,
    Numeral,
    Sentence,
    Term,
    Var,
)
from .fixtures import LAB4_AXIOMS, BONUS_EXISTS_FIXTURE, ClifAxiom
from .gbnf import CLIF_SUBSET_GBNF
from .grammar import CLIF_SUBSET_EBNF
from .parser import ParseError, parse, serialize

__all__ = [
    "And",
    "Atom",
    "BONUS_EXISTS_FIXTURE",
    "Binding",
    "CLIF_SUBSET_EBNF",
    "CLIF_SUBSET_GBNF",
    "ClifAxiom",
    "Exists",
    "Forall",
    "FunctionTerm",
    "LAB4_AXIOMS",
    "Numeral",
    "ParseError",
    "Sentence",
    "Term",
    "Var",
    "parse",
    "serialize",
]
