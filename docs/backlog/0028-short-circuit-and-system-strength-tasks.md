# 0028 — Short-circuit and system-strength tasks on snemSA (IEC 60909)

- **Status:** open. **Merit: first** of the 2026-10-23 tool review (0028–0032).
- **Affects:**
  - G2's engineering tools (`powercoder/engineering/`);
  - G3's task generator;
  - a new subfamily for the benchmark and the trajectories.

## Why
AEMO and network service providers assess fault levels and system strength for connections and
for operating-envelope decisions. That is a different study from power flow, and it is the kind
AEMO actually runs. pandapower (BSD, already a dependency) implements IEC 60909 short-circuit
calculation, so there is no new dependency. Its results are deterministic and checkable by a
solver.

## Scope
1. A `run_short_circuit` tool: three-phase maximum and minimum fault currents and fault level (MVA)
   at a bus, with the IEC 60909 case (max/min) and voltage factor stated in the response.
2. Short-circuit ratio at a connection point (fault level / plant MW) as a system-strength
   *proxy*, named as a proxy. It is not AEMO's system strength framework, which needs EMT models.
3. Task families:
   - fault level at bus X;
   - SCR for a hypothetical plant of P MW at bus X;
   - the change in fault level after an N-1 outage.
4. An independent check, as G2's proof records require (e.g. Thevenin impedance from the bus
   admittance matrix, compared with pandapower's `sc` result).

## Preconditions
- **Check snemSA's short-circuit data before building tasks.** It may lack generator subtransient
  reactances and the other short-circuit parameters. If it does, record that like backlog 0023
  rather than invent values.

## Acceptance
- **Cross-check:** pandapower `sc` and the independent check agree within a stated tolerance on
  every bus.
- **No invented inputs:** tasks are generated only where the case has the data the method needs,
  and a test asserts it.
