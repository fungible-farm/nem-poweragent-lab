# 0034 — Make the G4 export importable as CGMES (profiles and headers)

- **Status:** open. Found by [0029](0029-cgmes-round-trip-with-pypowsybl.md) on 2026-10-23.
- **Affects:** `powercoder/semantic/export.py`, G4 ([0018](0018-g4-cim-semantic-network-intelligence.md)).

## Gap (measured)
pypowsybl 1.16.1 rejects our export: `Data source does not contain EquipmentCore data`. A CGMES
2.4.15 model is split into profile instances (EQ, TP, SSH, SV), each with a `md:FullModel`
header declaring:
- `Model.profile`, `modelingAuthoritySet`, `scenarioTime` and `created`;
- `DependentOn`, linking each profile to the one it builds on.

Ours writes one merged graph with one header.

## Scope
1. **Split the export into profiles:**
   - **EQ:** equipment, terminals, connectivity nodes, base voltages, limits;
   - **TP:** topological nodes and terminal-to-node links;
   - **SSH:** operating point (P/Q setpoints, regulating targets, tap steps, in-service);
   - **SV:** the solved state (`SvVoltage`, `SvPowerFlow`, …).

   Each profile gets a header and `DependentOn` links. Extension-namespace fields stay out of the
   standard profiles, or are declared as an extension.
2. **Keep the existing tests passing:** our own round trip to within 1.05e-12 pu and 0 SHACL
   violations.
3. **Acceptance:** pypowsybl imports the four files (on an x86-64 peer; no ARM64 wheel exists),
   solves AC, and agrees with pandapower within a stated tolerance.
