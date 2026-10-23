# 0029 — Check the G4 CIM export against a real CGMES implementation (pypowsybl)

- **Status:** open. **Merit: second** of the 2026-10-23 tool review.
- **Affects:** G4 ([0018](0018-g4-cim-semantic-network-intelligence.md)), `powercoder/semantic/`, and
  [0026](0026-walkable-path-namespace-ls-get.md)/[0027](0027-functional-data-virtualization-layer.md)'s
  naming.

## Why
G4's export is a *CGMES-shaped subset*: one merged graph, no EQ/TP/SSH/SV profile split, with
extension-namespace fields. It round-trips through our own importer, so nothing has yet checked it
against an independent implementation. pypowsybl (MPL-2.0, already used by Labs 2–3) reads and
writes CGMES.

## Scope
1. **Export with pypowsybl.** Export snemSA as CGMES with pypowsybl, from the pandapower or MATPOWER
   case, and compare its class and property usage with ours. Which classes are missing (e.g.
   Substation and VoltageLevel containment), and which properties differ?
2. **Import ours into pypowsybl,** splitting it into profiles if needed. Run its load flow and compare
   bus voltages with pandapower's.
3. **Record every difference** as either a conformance gap in our export or a modelling difference
   between the solvers.

## Acceptance
- **Gap list:** every gap is listed with the class or property and its cause.
- **Voltage agreement:** voltages agree within a stated tolerance, or the cause is named.
- **Containment:** if pypowsybl's export carries containment that ours lacks, 0027's naming plan uses
  that containment.
