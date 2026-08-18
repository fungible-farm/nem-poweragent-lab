# 0007 — Idea: a CLIF x-grammar for constrained generation, demonstrated against the self-hosted mini-model

- **Status:** demo done, idea *not* adopted -- the "Recommended scope, if picked up" section below was
  implemented in full (`labs/_shared/clif_demo/`, 2026-08-13): a tiny CLIF-subset grammar transcribing
  four real Lab 4 facts, a hand-rolled parser round-tripping all of them (23 passing pytest cases,
  `labs/_shared/test_clif_demo.py`), the same grammar re-authored as GBNF, and a real call against the
  live `kube/llamacpp-phi-pod.yaml` Phi-4-mini pod confirming grammar-constrained output always parses.
  **This is a completed cheap experiment, not a decision to adopt CLIF** — see
  `labs/_shared/clif_demo/README.md`'s "What actually happened" for the full, not-entirely-clean result:
  on easy prompts grammar constraint made no observable difference (freeform matched it exactly); on one
  harder prompt, the grammar-constrained call satisfied the grammar by retreating to a trivially simple
  sentence that dodged the actual semantic ask, while the freeform call attempted the real semantic
  content correctly but broke on one extra unbalanced paren. That "constrained decoding can be
  semantically evasive" finding is new information this item did not have before, and is itself a reason
  to slow down before adopting CLIF+GBNF as a reliability mechanism, not a green light. Rewiring Lab 4's
  real constraint translation to depend on this remains explicitly out of scope (unchanged from below),
  and nothing here is `k0mmand3r` — that project was not touched, per the item's own scoping.
- **Depends on:** none directly; touches the same local LLM infra as `kube/llamacpp-phi-pod.yaml`
  (Phi-4-mini-instruct) and, loosely, Lab 4's constraint-translation work and PRD-0002's protection
  `trigger_condition` logic
- **Prompted by:** a conversation about whether Common Logic Interchange Format (CLIF — ISO/IEC
  24707's LISP-like first-order-logic interchange syntax) could be a good target for `k0mmand3r`, an
  external winnow-based parser project (from the author's own `b00t` toolkit, not part of this
  repo) whose stated goal is an "x-grammar syntax for constrained generation" — i.e. grammar-
  constrained LLM token sampling, not a power-flow capability.

## The actual idea

CLIF is a small, fully-specified, LISP-like grammar for first-order-logic statements — the kind of
format LLMs are reliably bad at freeform-generating (unbalanced parens, malformed quantifier
binding) but that grammar-constrained decoding handles by construction, since invalid tokens are
simply unsamplable. The obscurity that makes CLIF "foreign" to an agent is exactly the case
constrained generation exists for: a model doesn't need to have memorized CLIF's syntax if the
grammar constrains the output, it only needs to get the *semantic content* — which axioms to
assert — right.

Concretely: define a CLIF (or CLIF-subset) grammar, use it to constrain an LLM's output, and
demonstrate it reliably emitting syntactically-valid CLIF axioms it could not reliably produce
freeform. **Self-hosted mini-model** here should mean the model this repo already runs locally —
`kube/llamacpp-phi-pod.yaml`'s Phi-4-mini-instruct — since `llama.cpp`'s server already supports
grammar-constrained sampling natively (a GBNF grammar per request), no new inference infra needed.

## Open questions this item is honestly unresolved on

- **`k0mmand3r` isn't in this repo and wasn't independently verified this session** — no public
  repo was found, so whether its x-grammar definition and its winnow parser are actually the same
  compiled artifact (grammar-in → both a parser and a constrained-decoding grammar out) or two
  separately-maintained things is unconfirmed. That distinction matters: if unified, one CLIF
  grammar file does double duty (parse existing CLIF *and* constrain LLM-generated CLIF); if not,
  this is really two separate builds sharing one name.
- **No off-the-shelf CLIF parser exists in Rust or Python** (checked this session — `crates.io`'s
  `clif` is unrelated/Cranelift-adjacent, not Common Logic; general logic-expression crates like
  `logic-parser`/`rustlogic` don't implement CL's actual abstract syntax). Whoever picks this up
  writes the grammar from ISO 24707's published EBNF regardless of which tool authors it.
- **`llama.cpp`'s own constrained-decoding dialect is GBNF, not k0mmand3r's x-grammar** — so either
  k0mmand3r needs to compile down to GBNF, or this item bypasses k0mmand3r for the demo and authors
  GBNF directly, validating the CLIF-as-target-format idea independent of whether k0mmand3r itself
  is ready to carry it. Worth deciding explicitly rather than assuming the two are interchangeable.

## Recommended scope, if picked up

Not the full ISO 24707 spec. A handful of real axioms — Lab 4 already has real AEMO binding network
constraints (`nem_constraints_vendored.py`) that today are only translated one-way into plain
English — would make a grounded, small test case: (1) hand-transcribe a tiny CLIF subset's grammar
(whichever tool authors it), (2) confirm it round-trips real hand-written CLIF for those constraints
back to an AST, (3) point Phi-4-mini's constrained generation at the same grammar and check it
reliably asserts new, syntactically-valid axioms. Proves or kills the idea cheaply before any
commitment to CLIF as a flagship k0mmand3r use case, or to formalizing Lab 4's constraints this way
for real.

## Explicitly out of scope for this item

- Full CLIF/Common Logic spec coverage.
- Actually rewiring Lab 4's constraint translation to depend on this (a possible *consequence* if
  the demo works, not part of this item).
- Any `k0mmand3r` implementation work — that project lives outside this repo; this item is scoped to
  evaluating CLIF as a target grammar, with or without k0mmand3r.
