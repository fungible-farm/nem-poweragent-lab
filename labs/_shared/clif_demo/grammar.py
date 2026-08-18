"""The tiny CLIF subset this demo parses and constrains generation with.

docs/backlog/0007-clif-x-grammar-constrained-generation.md's "Recommended
scope, if picked up" is explicit: **not** the full ISO/IEC 24707 spec --
"a handful of real axioms" grounded in Lab 4's own constraint data, and
"a tiny CLIF subset's grammar," nothing more. This file is that subset:
exactly the five sentence forms and two term forms `fixtures.py`'s Lab 4
axioms actually use, no `or`/`iff`/`not`/`=`/string-literal/comment forms
CLIF also has, because none of the four Lab 4 facts this demo transcribes
need them (see `fixtures.py` for which fact needs which form).

Grounding, not invention: ISO/IEC 24707:2007 Annex A specifies CLIF as one
of Common Logic's three normative concrete dialects (the other two being
CGIF and XCL) -- confirmed directly against the standard's own front
matter this session (https://www.iso.org/standard/39175.html;
https://cdn.standards.iteh.ai/samples/39175/.../ISO-IEC-24707-2007.pdf).
The ISO PDF itself renders as an unextracted binary sample (no plain-text
Annex A available without purchasing the full standard), so the concrete
forms below are transcribed instead from John F. Sowa's own tutorial on
the same standard -- Sowa co-edited ISO/IEC 24707 and this talk works the
*same* running example (`Cat`/`Mat`/`On`) through predicate calculus,
existential graphs, CGIF, and CLIF side by side, i.e. it is a primary
source demonstrating the standard's own CLIF dialect, not a paraphrase:

    John F. Sowa, "Introduction to Common Logic," 10 Jan 2011,
    http://www.jfsowa.com/talks/clintro.pdf -- slides "Common Logic
    Interchange Format" (p.17, untyped `exists`/`and`/predicate-application
    forms), "Type Constraints" + "Typed and Untyped Statements" (pp.20-21,
    typed `(x Cat)` quantifier-binding form), and "A Logically Equivalent
    Variation" (p.25, `forall`/`if` together: `(forall ((x Cat) (y Mat))
    (if (On x y) (and (Pet x) (exists ((z Happy)) (Attr x z)))))`).
    (Page numbers here are the PDF's own page index, re-verified this
    session by extracting and reading those pages directly -- the exact
    CLIF text quoted above matches the "A Logically Equivalent Variation"
    slide verbatim, and "A Family of Logics" (p.2) independently confirms
    the "three normative dialects: CLIF, CGIF, XCL" claim above.)

Every production below is a direct restriction of a form shown on those
slides -- nothing here is guessed CLIF syntax.

    text                ::= sentence

    sentence            ::= atomic-sentence
                           | "(" "and" sentence sentence+ ")"
                           | "(" "if" sentence sentence ")"
                           | "(" "forall" bindings sentence ")"
                           | "(" "exists" bindings sentence ")"

    atomic-sentence     ::= "(" name term* ")"

    term                ::= name
                           | numeral
                           | "(" name term+ ")"          (* function term *)

    bindings            ::= "(" binding+ ")"
    binding             ::= name                          (* untyped *)
                           | "(" name name ")"             (* typed: (var type) *)

    name                ::= letter (letter | digit | "_" | "-")*
    numeral             ::= digit+

Deliberately excluded (real CLIF forms, just not needed by any Lab 4
fixture axiom, so out of scope per the backlog item's own "not the full
spec" instruction): `not`, `or`, `iff`, `=`, string-literal terms,
comments, sequence markers, and CLIF's module/importation syntax.

Why a hand-rolled recursive-descent parser (`parser.py`) instead of a
grammar-generator library (Lark, `pyparsing`, a PEG library): the whole
grammar is five sentence productions and two term productions -- small
enough that a ~150-line hand-written tokenizer + recursive-descent parser
is easier to read start-to-finish than a new build-time dependency would
be to onboard, and this item is explicitly framed as a cheap kill-or-keep
experiment (0007's own "[p]roves or kills the idea cheaply before any
commitment"), so keeping the dependency footprint at zero matters more
than the marginal convenience a parser-generator would buy for a grammar
this size. `pyproject.toml` gains nothing from this module.
"""
from __future__ import annotations

from typing import Final

CLIF_SUBSET_EBNF: Final[str] = """\
text                ::= sentence

sentence            ::= atomic-sentence
                       | "(" "and" sentence sentence+ ")"
                       | "(" "if" sentence sentence ")"
                       | "(" "forall" bindings sentence ")"
                       | "(" "exists" bindings sentence ")"

atomic-sentence     ::= "(" name term* ")"

term                ::= name
                       | numeral
                       | "(" name term+ ")"

bindings            ::= "(" binding+ ")"
binding             ::= name
                       | "(" name name ")"

name                ::= letter (letter | digit | "_" | "-")*
numeral             ::= digit+
"""
