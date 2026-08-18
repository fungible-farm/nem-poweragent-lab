"""Real, hand-written CLIF axioms for Lab 4 facts -- docs/backlog/0007's
"Recommended scope" step: "A handful of real axioms -- Lab 4 already has
real AEMO binding network constraints ... that today are only translated
one-way into plain English -- would make a grounded, small test case."

Every axiom below cites the exact Lab 4 source (file + line, current at
implementation time 2026-08-13) it transcribes. None of these facts were
invented for this demo -- they are exactly what
`labs/04-aemo-digital-twin-reconciliation/_lab4_shared.py` and
`explain_constraint.py`'s own docstrings already assert in prose; this
module is a second, formal encoding of the same facts, not new claims
about the NEM.

LAB4_AXIOMS holds the four facts this demo actually targets (matching
0007's "2-4 real axioms"). BONUS_EXISTS_FIXTURE is a fifth, clearly-
non-Lab4 fixture kept separately: none of the four real facts below
happens to need `exists` (Lab 4's constraint data is about universal
binding behaviour and fixed interconnector topology, not "some X exists"
claims), but grammar.py's grammar still needs to parse `exists` --
0007 itself asks for quantifiers "like `(forall (x) ...)`/`(exists (x)
...)`" in the grammar -- so this fixture exists purely to exercise that
production, and is labelled as such everywhere it's used (never claimed
as one of the "real" Lab 4 axioms).
"""
from __future__ import annotations

from typing import Final, NamedTuple


class ClifAxiom(NamedTuple):
    """One fixture: the CLIF text, plus where the fact it encodes comes
    from and a plain-English gloss, so `test_clif_demo.py` failures and
    `demo_llm.py`'s printed output are self-explaining without needing
    this docstring open."""

    name: str
    clif: str
    source: str
    gloss: str


LAB4_AXIOMS: Final[tuple[ClifAxiom, ...]] = (
    ClifAxiom(
        name="heywood_topology",
        clif="(interconnector V-SA VIC1 SA1)",
        source=(
            "labs/04-aemo-digital-twin-reconciliation/_lab4_shared.py "
            "lines 100-107: 'V-SA is the Heywood interconnector "
            "(VIC1<->SA1, AC)' -- from a real DISPATCHINTERCONNECTORRES "
            "pull for LAB4_DATE."
        ),
        gloss="V-SA (Heywood) is an interconnector between region VIC1 and region SA1.",
    ),
    ClifAxiom(
        name="murraylink_topology",
        clif="(interconnector V-S-MNSP1 VIC1 SA1)",
        source=(
            "labs/04-aemo-digital-twin-reconciliation/_lab4_shared.py "
            "lines 100-107: 'V-S-MNSP1 is Murraylink (VIC1<->SA1, DC)'."
        ),
        gloss="V-S-MNSP1 (Murraylink) is an interconnector between region VIC1 and region SA1.",
    ),
    ClifAxiom(
        name="heywood_test_constraint_limit",
        clif="(limits VS_HEY_600_TEST V-SA 600)",
        source=(
            "labs/04-aemo-digital-twin-reconciliation/explain_constraint.py "
            "lines 20-23: LAB4_DATE's 'Heywood-interconnector-limit test "
            "constraint (VS_HEY_600_TEST) binds at several intervals in "
            "the mid-afternoon'; the '600' in its own GENCONID and "
            "_lab4_shared.py line 95's 'Heywood's ~600 MW rating' "
            "together ground the limit value -- this repo did not "
            "independently re-fetch VS_HEY_600_TEST's GENCONDATA "
            "CONSTRAINTVALUE this session (that would need a live "
            "NEMOSIS pull), so treat 600 as the constraint's own naming "
            "convention plus the repo's documented rating figure, not a "
            "freshly-reconfirmed exact RHS."
        ),
        gloss="Constraint VS_HEY_600_TEST limits interconnector V-SA's flow to 600 (MW).",
    ),
    ClifAxiom(
        name="binding_rule",
        clif=(
            "(forall ((c Constraint) (i Interconnector) (l Limit)) "
            "(if (and (limits c i l) (exceeds (flow i) l)) (binds c)))"
        ),
        source=(
            "labs/04-aemo-digital-twin-reconciliation/explain_constraint.py "
            "`_binding_constraints()` (MARGINALVALUE != 0 filter) "
            "together with `nem_constraints_vendored.get_LHS_terms`/"
            "`get_RHS_terms` (a constraint's LHS interconnector-flow "
            "term compared against its RHS limit) -- generalizes "
            "`heywood_test_constraint_limit` above into the general rule "
            "those two vendored functions jointly implement: a "
            "constraint binds exactly when the flow its LHS references "
            "exceeds the RHS limit it defines."
        ),
        gloss=(
            "For any constraint c limiting interconnector i to l: if i's "
            "flow exceeds l, c binds. (heywood_test_constraint_limit is "
            "one instantiation of this rule, with c=VS_HEY_600_TEST, "
            "i=V-SA, l=600.)"
        ),
    ),
)

# NOT a Lab 4 fact -- see module docstring. Kept out of LAB4_AXIOMS so
# nothing here is mistaken for "real repo data," but still round-tripped
# by the same tests, to prove the `exists` production in grammar.py's
# grammar actually parses, not just appears in the EBNF comment.
BONUS_EXISTS_FIXTURE: Final[ClifAxiom] = ClifAxiom(
    name="bonus_exists_not_a_lab4_fact",
    clif="(exists ((i Interconnector)) (interconnector i VIC1 SA1))",
    source="Not from Lab 4 -- synthetic, added only to exercise the `exists` grammar production.",
    gloss="There exists some interconnector between VIC1 and SA1 (true of both real axioms above, but asserted here only to test the parser, not as an independently-sourced fact).",
)
