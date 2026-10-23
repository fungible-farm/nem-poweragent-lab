# 0033 — Audit an engineer's study workbook: every number traced, re-derived or flagged

- **Status:** prototype measured 2026-10-23 (scratchpad, not committed); open. **Merit: above
  0030–0032,** because it needs no blocked data.
- **Affects:**
  - PC-REQ-004 provenance, applied to the engineer's own artefacts;
  - [0026](0026-walkable-path-namespace-ls-get.md) (cells addressable as `/xlsx/<file>/<sheet>/<cell>`);
  - G6 investigations.

## Why
Engineers keep study inputs, tool exports, hand calculations and deliverables in Excel. Spreadsheet
risk research (EuSpRIG) attributes its error figures to the original studies; these are quoted
from EuSpRIG's research page, not measured here:
- most spreadsheets contain errors (Panko 2006; Pryor 2004);
- about 50% of operational models in large businesses have material defects (Powell, Baker &
  Lawson 2007; Croll 2008).

Thorne & Collins ([arXiv:2609.31815](https://arxiv.org/abs/2609.31815), v1, 2026-09-25) classify
121 incidents in the EuSpRIG horror-story archive into 12 categories:
- formula errors, data-entry slips and data handling account for 71;
- hidden or embedded data is the category with the clearest rise.

It is a corpus of *reported* incidents, not an error rate. A study workbook fails in exactly the
way the provenance rule guards against: a number with no source, or one that no longer
reproduces.

## Prototype (measured)
Built a workbook from 10 real snemSA N-1 solves (`run_study_trial`) plus a per-unit sheet, and
seeded 6 errors. A scanner (openpyxl to read; `formulas`, EUPL-1.1+, to recalculate; no LibreOffice,
by user decision) found **6 of 6, each by at least one independent check, with 0 findings off the
seeded cells** (12 findings, 5.6 s including the re-solves):

| Seeded error | Caught by |
|---|---|
| S1 copy-paste drift (line 5's violation count copied from line 2: 36 vs 39) | re-derivation (solver says 39) |
| S2 unit slip (a pu voltage entered as kV) | unit plausibility ("1.0941 pu at 275 kV") + re-derivation |
| S3 a flag typed over its formula | column formula pattern + flag recomputed from the solver |
| S4 a limit hard-coded in one formula (0.9, not the 0.95 limit cell) | pattern break + literal in a formula + flag recomputed |
| S5 a hidden row holding data | hidden-data check |
| S6 the wrong MVA base in a per-unit formula (10 vs the case's 100) | pattern break + literal + base check against the case |

**A finding about the test itself.** The first S1 (a minimum voltage copied from the neighbouring
outage) was correctly *not* flagged. On snemSA, lines 4 and 5 give minimum voltages 1.8e-7 pu
apart, below the tolerance and far below engineering significance (backlog 0023). Seeded errors
must be material for the network they're seeded into.

## Limits of the prototype (why it is not yet evidence of an agent skill)
- **Circular.** I seeded the errors and wrote the checks, so 6/6 shows that the checks work, not
  that they find unknown errors. It needs errors seeded by someone else, and real engineer
  workbooks.
- **The layout was given to it.** Its column-to-quantity map (`"Min V (pu)" → min_bus_voltage_pu`,
  `"Line out"` → the contingency) is hard-coded. Mapping an arbitrary workbook's headers, units and
  row meanings onto solver quantities is the hard, open-ended part, and that is where a model
  earns its place. Every mapping it proposes must then be checked by the deterministic layers.
- **Coverage.** It knows N-1 voltage and loading, and per-unit bases. Fault levels (0028), ratings,
  impedance from conductor data, and multi-sheet links come next.

## Next
1. **A lab** with the generator, the scanner and a held-out seed set (errors seeded by a separate
   process or person). Score it as recall and precision per error class, against a fixture.
2. **Model-proposed layout mapping:** headers and units → quantities and contingencies. The
   deterministic layers check each mapping, and each finding cites a cell and a solver result.
3. **A report** an engineer would accept: each cell's source (tool result, cited input, formula,
   unsourced), with re-derived values and their solver citations.
