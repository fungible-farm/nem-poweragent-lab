# Backlog

Deferred/gap items that are real (grounded in the actual code, not speculative), not yet worked,
and not part of any lab's current Definition of Done. This directory exists because
`docs/DEFINITION_OF_DONE.md` already has an "Out of scope for 'done'" convention for
*deliberately* deferred scope — this is the equivalent for gaps that were **not** deliberate,
found by auditing the repo after the fact. Each item is one file, numbered in discovery order,
never renumbered once merged (dropped items are marked `[status: dropped]` in place, not deleted).

`docs/VISION.md` §13 "Known gaps / backlog" is the canonical index a reader hits first; this
directory is where the detail lives so `VISION.md` doesn't bloat with implementation-level
research notes.

| # | Title | Status |
|---|-------|--------|
| [0001](0001-topology-and-results-visualization-gap.md) | No lab renders a topology diagram or a results chart — matplotlib is used in 1 of ~15 scripts | partially done (charts landed for Labs 2/3/4/5; Lab 1 visual + a `pandapower.plotting` topology diagram remain) |
| [0002](0002-pandapower-diagram-and-symbolic-representation-options.md) | Research: pandapower's own advanced diagram options, and open-source symbolic/single-line-diagram packages | done (research consumed by 0003/0004; free tier implemented, stretch tier gated on CIM/CGMES export) |
| [0003](0003-lab3-scorecard-visualization.md) | Lab 3: bake-off scorecard has zero charts despite being the one dataset built to be compared | done |
| [0004](0004-lab4-lab5-visualization-options.md) | Lab 4 & Lab 5: visualization options (reconciliation chart; chaos-net topology + symbolic single-line) | partially done (Lab 4 chart + Lab 5 topology drawing done; Lab 5 symbolic single-line still open) |
| [0005](0005-unified-notebook-playbook.md) | Suggestion: a jupytext/Jupyter playbook binding all 5 labs' visual outputs into one narrative, without becoming a second source of truth | proposed |
| [0006](0006-lab5-advanced-transient-visualization-techniques.md) | Research: advanced Lab 5 transient-visualization techniques (symmetrical components, R-X impedance trajectory, spectrogram, network-wide sag propagation) beyond the existing six views | proposed |
| [0007](0007-clif-x-grammar-constrained-generation.md) | Idea: a CLIF (Common Logic Interchange Format) x-grammar for LLM constrained generation, demoed against the self-hosted Phi-4-mini pod | proposed |
