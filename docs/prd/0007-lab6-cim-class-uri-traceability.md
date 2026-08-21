# 0007 — Lab 6 Phase 4a: CIM class-URI traceability annotations for Track B

- **Status:** implemented
- **Depends on:** 0006 (Lab 6 SysML v2 digital-thread MVP) — Track B's `Bus`/`Generator`/`Line`
  LinkML schema and its `generate_sysml.py`/`validate_sysml.py` pipeline are what this issue
  annotates; nothing here works standalone
- **Touches:** `labs/06-sysml-digital-thread/schema/grid_topology.linkml.yaml`, `generate_sysml.py`,
  `test_lab6.py`, `docs/prd/0006-sysml-digital-thread-mvp.md` (Open Questions update),
  `docs/prd/README.md` (new row)

## Motivation

Consultant review of PRD-0006 flagged that CIM (IEC 61970 transmission / IEC 61968 distribution /
CGMES profile — the standard TNSPs and market operators actually use for network model exchange)
maps naturally onto Track B, not Track A (Track A's Agent/MCPServer/DataSource classes have no
power-systems analog). Three options were raised, explicitly not equal scope:

1. Class mapping table (`Bus`/`Generator`/`Line` → CIM classes) — small, do first.
2. Traceability annotation on generated `.sysml` text — same-day addition once (1) exists, doesn't
   touch the schema-authority architecture.
3. CIM/CGMES RDF-XML as schema-of-record, replacing LinkML for Track B — large, separate
   workstream, explicitly **not** this issue's scope.

This issue is (1) + (2) only. LinkML remains Track B's schema authority; CIM becomes referenced
metadata, not a dependency swap.

This is a sibling to, not the same as, PRD-0006's own already-open "Phase 4" question (Track B's
third downstream artifact — an equipment register or NER asset schedule shape). That question is
about a *new generated artifact*; this one is about *annotating the existing one* with a real
external standard's class identity. Numbered 4a for that reason — it can land independently of,
and before, whatever Phase 4 decides.

## What was checked before scoping this, not assumed

**The stated prerequisite blocker is already resolved — verified against current code, not
carried forward from the review.** The draft issue this PRD is based on named "the wiring fix from
PR #14 review" (`translate_iso_ir.py`/`render_diagram.py` reading `fixtures/` instead of chaining
off the previous stage's fresh output) as a blocking dependency. That bug was real, but it was
already found and fixed as part of PRD-0006 itself — see that PRD's own "What was checked this
session" section and `labs/06-sysml-digital-thread/README.md` Design notes §4. Confirmed directly
in the current code, not just the docs: `translate_iso_ir.build_iso_ir()` calls
`generate_sysml.generate(track)` in-process (`translate_iso_ir.py:420-425`, docstring names the
fixture-read version as "an earlier version of this file"), and `render_diagram.generate()` calls
`translate_iso_ir.build_iso_ir(track)` in-process (`render_diagram.py:301-306`) — neither reads
from `fixtures/` at generation time; `fixtures/` is `--step check`'s comparison target only. **This
PRD has no blocking prerequisite.**

**The draft's open implementation question ("pick the shape that survives the syntax gate") is
already answered by the current grammar — checked, not guessed.** `validate_sysml.py`'s allowed
line-shape patterns already include `attribute <ident> : <ident>;` and
`attribute <ident> = "<string>";` (`validate_sysml.py:55-56`) — the exact shapes
`generate_sysml.py` already emits for every other Bus/Generator/Line field (`voltageKV`, `bus`,
`ratedMW`, `fromBus`/`toBus`/`kind`, e.g. `generate_sysml.py:106-120,136-165`). Emitting
`attribute cimClassUri : String;` / `attribute cimClassUri = "...";` needs **zero grammar
widening** — it's the same pattern as every field already there, not a new syntax shape.

**Real CIM namespace URI, confirmed against an actual published CGMES conformity dataset, not
invented.** ENTSO-E's own CGMES v2.4 conformity test data (`itesla/CGMES` GitHub mirror,
`ENTSOE_CGMES_v2.4_ExplicitLoadFlowCalculation/bench_cim2_EQ.xml`) declares
`xmlns:cim="http://iec.ch/TC57/2013/CIM-schema-cim16#"` and uses `cim:SynchronousMachine`,
`cim:PowerTransformer`, and `cim:ACLineSegment` as real element names in that namespace — the exact
three classes the draft mapping table proposes for `Generator`, `Line(kind=transformer)`, and
`Line(kind=transmission)` respectively. This is CIM16 / CGMES 2.4, the long-established,
widely-deployed profile version; a newer `http://iec.ch/TC57/CIM100#` (CGMES 3.0) namespace also
exists and is worth checking against at implementation time, but CIM16 is the safer default citation
today given how much real published tooling and test data still targets it.

**`Bus → ConnectivityNode` vs. `Bus → TopologicalNode`: recommend `TopologicalNode`, not confirmed
by a fetched source, flagged for implementation-time verification.** IEC 61970-301's own modelling
split is between a node-breaker model's `ConnectivityNode` (a physical terminal-level connection
point, one per switch position) and its derived bus-branch model's `TopologicalNode` (the electrical
bus that results after connectivity nodes on closed switches are collapsed together) — Track B's
`Bus` class, sourced from `snemSA.m`'s own MATPOWER bus table, is already a bus-branch abstraction
(MATPOWER has no switch/breaker model at all), which structurally matches `TopologicalNode`, not
`ConnectivityNode`. This reasoning wasn't checked against a fetched CIM profile document directly —
the implementer should confirm it against the real CGMES Equipment/Topology profile split before
committing the mapping table, per this issue's own "ground every field in a real source" acceptance
bar.

## Scope — in

- [x] Class mapping table in `grid_topology.linkml.yaml`'s own header comment:
      - `Bus → cim:TopologicalNode` (confirmed, not just recommended, against IEC61970::Base::
        Topology docs and ENTSO-E's CGM Building Process guide during implementation — see
        "What was checked" below)
      - `Generator → cim:SynchronousMachine`
      - `Line(kind="transmission") → cim:ACLineSegment`
      - `Line(kind="transformer") → cim:PowerTransformer`
      - Uses the existing `kind` slot as the `Line` dispatch key — no new class or slot needed for
        dispatch itself.
- [x] Added a `cim_class_uri` slot to `Bus`/`Generator`/`Line` in `grid_topology.linkml.yaml`,
      computed from a `CIM_CLASS_BY_KIND` lookup table in `build_grid_instances.py` (the stage that
      already owns "generated, not hand-transcribed" for this schema), never hand-entered per
      instance.
- [x] `generate_sysml.py` emits `attribute cimClassUri : String;` on each of the three `part def`
      blocks and `attribute cimClassUri = "<uri>";` on each instance — confirmed to need zero
      `validate_sysml.py` grammar change, exactly as predicted.
- [x] Pinned CIM16 / `http://iec.ch/TC57/2013/CIM-schema-cim16#`, cited in
      `grid_topology.linkml.yaml`'s own header.
- [x] Added `test_grid_topology_carries_cim_class_uri_for_every_kind` to `test_lab6.py`, asserting
      all four real CIM16 URIs (`TopologicalNode`/`SynchronousMachine`/`ACLineSegment`/
      `PowerTransformer`) appear in generated `output/grid_topology.sysml`.
- [x] Regenerated and committed `fixtures/expected_grid_topology.sysml`. Confirmed
      `translate_iso_ir.py` does not capture non-reference attributes into the IR at all (only
      `fromBus`/`toBus`/`kind`/`bus`/`uses`/`next`), so `expected_grid_topology_iso_ir.json`/`.svg`
      are genuinely unaffected — verified via `--step check` on both, both still MATCH.

## Scope — out (do not do in this issue)

- CGMES RDF-XML import/export tooling.
- CIM as LinkML's replacement / schema-of-record for Track B.
- Any Track A change — Track A has no CIM analog, per the consultant's own note.
- Live CGMES model exchange with any external system.
- PRD-0006's own open "Phase 4" third-artifact question (equipment register / NER asset schedule
  shape) — related, not the same issue; see Motivation above.

## Goals

1. Give Track B's generated `.sysml` output a real, citable pointer into the CIM/CGMES standard
   TNSPs actually use for network model exchange, without adopting CIM as a dependency.
2. Keep the change small and additive: one new slot, one new generated attribute, zero changes to
   the existing schema-authority architecture or the syntax gate's grammar.
3. Every mapping and every namespace citation traces to a real, checkable source — no invented URI,
   no guessed class name.

## Non-goals

Same as "Scope — out" above; not repeated here.

## Acceptance criteria

- [x] `just check-lab6` passes with the new CIM annotation present in generated output for Bus,
      Generator, and both Line kinds.
- [x] The class mapping table and the CIM namespace/version citation are reviewable in one file
      (`grid_topology.linkml.yaml`'s header).
- [x] `docs/prd/0006-sysml-digital-thread-mvp.md`'s Open Questions section already reads correctly
      as of this PRD's implementation: CIM mapping marked resolved for the annotation layer,
      explicitly still open for schema-of-record (option 3 above) — no edit needed, it was written
      forward-looking when PRD-0007 was first scoped.
- [x] `docs/prd/README.md` row added, status flipped to implemented.

## Open questions

- **CIM16 (CGMES 2.4) vs. CIM100 (CGMES 3.0) as the pinned namespace** — CIM16 confirmed and used;
  whether CIM100 becomes the more current target for a future from-scratch mapping remains open,
  not re-checked at implementation time.
- **`ConnectivityNode` vs. `TopologicalNode` for `Bus`** — resolved during implementation via a
  direct web search against IEC61970::Base::Topology reference docs and ENTSO-E's CGM Building
  Process Implementation Guide: `ConnectivityNode` is a physical terminal-level connection point
  (one per switch position); `TopologicalNode` is the logical bus a topology processor derives
  after collapsing connectivity nodes on closed switches. `snemSA.m` (MATPOWER, no switch/breaker
  model) is already a bus-branch abstraction, confirming `TopologicalNode` as the correct choice.
- **Does this annotation layer, once real, change the calculus on PRD-0006's own open Phase-4
  third-artifact question** (equipment register / NER asset schedule shape)? Still not answered —
  worth revisiting in a future session.
