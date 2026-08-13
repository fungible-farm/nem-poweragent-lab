# `clif_demo`

Idea-stage demo for
[`docs/backlog/0007-clif-x-grammar-constrained-generation.md`](../../../docs/backlog/0007-clif-x-grammar-constrained-generation.md):
does a tiny CLIF (Common Logic Interchange Format, ISO/IEC 24707 Annex A)
subset make a workable grammar-constrained-generation target for this
repo's self-hosted Phi-4-mini pod (`kube/llamacpp-phi-pod.yaml`)?

This directory implements exactly 0007's "Recommended scope, if picked
up" -- no more. It does **not** prove CLIF should be adopted for Lab 4's
real constraint translation, and it does not touch Lab 4's actual code
path (`explain_constraint.py` still produces plain English exactly as
before). See "Honest scope" below.

## Layout

| File | What it is |
| --- | --- |
| `grammar.py` | The CLIF-subset EBNF (as a docstring + a `CLIF_SUBSET_EBNF` string constant), hand-transcribed from cited real sources -- not invented. |
| `ast_nodes.py` | Frozen-dataclass AST node types, one per grammar production. |
| `parser.py` | Hand-rolled recursive-descent parser (`parse`) + serializer (`serialize`). |
| `fixtures.py` | Four real Lab 4 facts as hand-written CLIF axioms, each cited to the exact Lab 4 source file/line it transcribes, plus one clearly-labelled bonus non-Lab4 fixture. |
| `gbnf.py` | The same grammar re-authored as GBNF (llama.cpp's grammar dialect), `CLIF_SUBSET_GBNF`. |
| `demo_llm.py` | Runnable script: calls the **live** llama.cpp pod with `CLIF_SUBSET_GBNF` and checks the output parses. Not a pytest test -- see below. |
| `../test_clif_demo.py` | pytest suite: round-trips every fixture, checks exact parsed shapes, checks malformed input raises. |

## Running it

```bash
# Parser + grammar tests (offline, no pod needed):
uv run pytest labs/_shared/test_clif_demo.py -v

# Live-pod demo (needs kube/llamacpp-phi-pod.yaml's server reachable,
# default http://127.0.0.1:8091):
uv run python labs/_shared/clif_demo/demo_llm.py
```

## The grammar, briefly

Five sentence forms, two term forms -- exactly what the four Lab 4
fixture axioms below need, nothing else. See `grammar.py`'s docstring for
the full EBNF and its citations (ISO/IEC 24707:2007 Annex A; John F.
Sowa's "Introduction to Common Logic" tutorial, which works CLIF's real
concrete syntax through the same running example the standard uses).

```
sentence ::= atomic-sentence | (and s s+) | (if s s) | (forall b s) | (exists b s)
term     ::= name | numeral | (name term+)
```

Deliberately excluded: `not`, `or`, `iff`, `=`, string literals,
comments. None of the four Lab 4 facts below need them.

## The four Lab 4 axioms

| name | CLIF | grounded in |
| --- | --- | --- |
| `heywood_topology` | `(interconnector V-SA VIC1 SA1)` | `_lab4_shared.py` lines 100-107 |
| `murraylink_topology` | `(interconnector V-S-MNSP1 VIC1 SA1)` | `_lab4_shared.py` lines 100-107 |
| `heywood_test_constraint_limit` | `(limits VS_HEY_600_TEST V-SA 600)` | `explain_constraint.py` lines 20-23 + `_lab4_shared.py` line 95 |
| `binding_rule` | `(forall ((c Constraint) (i Interconnector) (l Limit)) (if (and (limits c i l) (exceeds (flow i) l)) (binds c)))` | generalizes `explain_constraint.py`'s `_binding_constraints()` (`MARGINALVALUE != 0`) + `nem_constraints_vendored.py`'s LHS/RHS decode |

Full citations (exact wording, why each source grounds each fact) are in
`fixtures.py`'s docstrings, not repeated here.

A fifth fixture, `BONUS_EXISTS_FIXTURE`, is **not** a Lab 4 fact -- none
of the four real facts above happens to need `exists` (Lab 4's data is
about fixed topology and a universal binding rule, not "some X exists"
claims). It exists purely so the parser's `exists` production is actually
exercised by a test, not just claimed in the EBNF comment. It is labelled
as synthetic everywhere it appears.

## What actually happened running `demo_llm.py` against the live pod

Run at implementation time (2026-08-13) against `kube/llamacpp-phi-pod.yaml`'s
server (`Phi-4-mini-instruct-Q4_K_M.gguf`, confirmed live:
`curl http://127.0.0.1:8091/health` → `{"status":"ok"}`), three prompts,
each run twice (grammar-constrained via `/v1/chat/completions`'s
`grammar` field set to `CLIF_SUBSET_GBNF`, and freeform with no grammar,
as a control). Exact output, not summarized:

**Prompt 1 (`murraylink_topology`, asks for a near-verbatim restatement
of the worked example already shown in the system prompt):**

```
grammar-constrained: (interconnector ID V-S-MNSP1 VIC1 SA1)   -- parsed OK
freeform:            (interconnector ID V-S-MNSP1 VIC1 SA1)   -- parsed OK (identical)
```

**Prompt 2 (`heywood_test_constraint_limit`):**

```
grammar-constrained: (limits VS_HEY_600_TEST V-SA 600)        -- parsed OK
freeform:            (limits VS_HEY_600_TEST V-SA 600)        -- parsed OK (identical)
```

**Prompt 3 (`exists_binding_interconnector_bonus`, deliberately harder --
asks for `exists` + `and` + a nested `flow` term combined in a shape not
shown verbatim anywhere in the prompt):**

```
grammar-constrained: (interconnector V-SA VIC1 SA1)
                     -- parsed OK, but semantically dodges the ask entirely:
                        no exists, no and, no exceeds/flow at all.
freeform:            (exists ((i Interconnector) (l Limit))
                       (and (interconnector i VIC1 SA1) (exceeds (flow i) l))))
                     -- semantically almost exactly right (both bound
                        variables, correct nesting, correct predicates)
                        but has one extra trailing ')' -- parse FAILED:
                        "trailing tokens after sentence: [')']"
```

### Findings (not a clean story -- reported as observed)

1. **On the two easy prompts, grammar constraint made no observable
   difference.** Both conditions produced byte-identical output on
   prompts 1 and 2. Phi-4-mini-instruct did not need syntactic
   hand-holding for a single flat predicate application -- 0007's
   motivating claim ("a model doesn't need to have memorized CLIF's
   syntax... it only needs to get the semantic content right") wasn't
   tested by these two prompts, because freeform syntax was never at
   risk here. A harder prompt was needed to see any contrast at all
   (added as prompt 3 for exactly this reason).
2. **On the harder prompt, the two conditions diverged in an
   unanticipated way.** Grammar constraint delivered its one guarantee
   exactly as advertised -- syntactically valid CLIF, no exception -- but
   the model used that freedom to retreat to the easiest sentence that
   satisfies the grammar rather than attempt what was actually asked.
   The freeform run did attempt the real semantic content, got the
   *structure* right (two typed bindings, correct nesting of
   `and`/`exists`/`exceeds`/`flow`), and failed on exactly the kind of
   syntax slip (one extra `)`) 0007 predicts freeform CLIF generation is
   prone to. So on this one run: constrained = syntactically guaranteed
   but semantically evasive; freeform = semantically ambitious but
   syntactically broken. Neither condition alone delivered "syntactically
   valid AND semantically on-target" for the harder prompt.
3. This is a **single run at fixed low temperature (0.2)**, not a
   statistically powered comparison -- not strong enough evidence to
   generalize "grammar constraint causes evasion" as a rule, only strong
   enough to say it happened, once, here, and that 0007's "the model only
   needs the semantics right" framing understates the risk: a constrained
   model can satisfy the grammar without attempting the requested
   semantics at all, and nothing in the grammar can catch that.
4. **Two real GBNF authoring gotchas**, found by direct trial against
   this server (neither documented in llama.cpp's own grammar README as
   skimmed this session), documented in full in `gbnf.py`'s docstring:
   - A backslash-escaped `-` inside a `[...]` character class
     (`[A-Za-z0-9_\-]`) makes the grammar fail to load; an unescaped
     trailing `-` (`[A-Za-z0-9_-]`) works.
   - Alternatives (`|`) cannot start a continuation line -- every
     alternative for a rule must be on that rule's own `::=` line, unlike
     conventional multi-line BNF pretty-printing.

## Why `demo_llm.py` isn't a pytest test

It makes a real network call to a real server this repo doesn't manage
the lifecycle of (`kube/llamacpp-phi-pod.yaml` is deployed separately,
see that file). A future clean checkout, or CI, has no guarantee the pod
is up -- unlike Lab 4's `nemweb.com.au` calls (a public, always-on AEMO
service), so it isn't given the same "real call, still a committed test"
treatment `test_lab4.py` gives Lab 4's live NEMOSIS pulls. Run it by hand
when the pod is up; `test_clif_demo.py`'s parser/grammar tests are the
part that's always safe to run in CI.

## Honest scope

What this demo shows: a five-form CLIF subset is small enough to (a)
hand-write a parser for in an afternoon and (b) compile to a GBNF grammar
that a real self-hosted small model can be constrained with, and
constraining it does deliver its one advertised guarantee (no syntax
errors) -- confirmed against a live pod, not assumed.

What it does **not** show, and was never in scope
(docs/backlog/0007.md's own "Explicitly out of scope"): that CLIF is
ready to replace Lab 4's real (plain-English) constraint translation, or
that grammar-constrained decoding alone is sufficient for reliable axiom
generation -- finding 2 above is a specific, observed reason it might not
be ("evasion": a model can satisfy any grammar with a trivial sentence
instead of the one actually asked for). Whether that's a real risk in
practice, or an artifact of this one prompt/model/temperature, is exactly
the kind of question 0007 says this cheap experiment exists to surface,
not resolve.
