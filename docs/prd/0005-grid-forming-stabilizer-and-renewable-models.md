# 0005 — Grid-forming transient stabilizer + open renewable-generation models (Lab 5, SPARTAN's corrective-action testbed)

- **Status:** proposed
- **Depends on:** none directly; builds on Lab 5's existing `chaosnet`/`run_dpsim.py`/`phase_model.py`
  machinery and reuses the R-X/sag-propagation work from `docs/backlog/0006`
- **Touches:** `labs/05-spartan-chaosnet-transient-stream/chaosnet.py` (new generator/controller
  component types), `run_dpsim.py` (control-loop wiring), new `labs/05-.../grid_forming.py`, possibly
  a new `labs/06-.../` if the renewable-model + MBSE layer grows past Lab 5's own scope, `docs/VISION.md`
  §3 ecosystem table (proposed Modelica/FMI row)

## Problem

Lab 5 already demonstrates a real fault transient on a procedurally-generated grid, and SPARTAN — the
external edge-PMU project Lab 5 exists to feed — is not just a passive detector. Its own stated design
is a **micro-PMU based on OpenPMU, sampling at 4 kHz or better, that classifies/logs/alerts anomalies
and takes corrective or assistive action when feasible: a distributed emergency response coordinator.**
Lab 5 today only builds the "classify/log/alert" half (the six-plus views in `docs/backlog/0006`); it
has no simulation of the "take corrective action" half at all. This PRD is that other half: a
grid-forming, actively-controlled inverter that reads a real disturbance and demonstrably reduces it —
plus the open, standardized renewable-generation models (wind, solar) that make the scenario realistic
rather than a bare fault on a passive network.

## What was checked this session, not assumed

- **DPsim ships no grid-forming inverter component.** `dir(dpsimpy.emt.ph3)` (this installed version)
  is: `AvVoltageSourceInverterDQ`, `Capacitor`, `ControlledVoltageSource`, `CurrentSource`,
  `Full_Serial_RLC`, `Inductor`, `NetworkInjection`, `PiLine`, `RXLoad`,
  `ReducedOrderSynchronGeneratorVBR`, `Resistor`, `SeriesResistor`, `SeriesSwitch`, `Switch`,
  `SynchronGenerator{3,4,5,6a,6b}OrderVBR`, `SynchronGeneratorDQODE`, `SynchronGeneratorDQTrapez`,
  `Transformer`, `VoltageSource`. `AvVoltageSourceInverterDQ` is **grid-following**: its own
  `set_controller_parameters(Kp_pll, Ki_pll, Kp_power_ctrl, Ki_power_ctrl, Kp_curr_ctrl, Ki_curr_ctrl,
  omega_cutoff)` signature confirms a PLL-synchronized design — it locks onto an existing grid
  reference, it does not set one. There is no shipped droop/VSM/dispatchable-virtual-oscillator
  component. Building grid-forming control here means driving DPsim's primitive
  `ControlledVoltageSource` with a hand-built control law, not configuring an existing component
  differently.
- **The elegant part: DPsim already has the right math, just attached to the wrong device.** A
  virtual-synchronous-machine (VSM) grid-forming controller's whole design is "make a power-electronic
  converter obey a synchronous generator's swing equation." DPsim's own
  `SynchronGenerator{3,4,5,6a,6b}OrderVBR` models are real, already-validated implementations of
  exactly that swing-equation/damping math (see Lab 4/5's own use of them). The plan below reuses that
  *mathematical structure*, driving a `ControlledVoltageSource` instead of a literal rotating machine —
  not a new physics model, a new use of physics this repo already trusts.
- **PowerMCP has no Modelica integration.** Confirmed by listing `Power-Agent/PowerMCP`'s actual repo
  tree directly (`ANDES`, `Egret`, `HOPE`, `LTSpice`, `OpenDSS`, `PSCAD`, `PSLF`, `PSSE`,
  `PowerFactory`, `PowerWorld`, `PyPSA`, `pandapower`, `powerio`, `surge` — no Modelica anywhere) and
  `gh search code "modelica"` against both the upstream org and the `fungible-farm` fork (zero
  results). Any Modelica path is new integration work, not something to wire into.
- **IEC 61400-27 is an RMS/stability-domain standard, not EMT.** A real, peer-reviewed open-source
  Modelica implementation of IEC 61400-27-1:2020 Type 4 exists (Carbonell, Cardozo, et al., *Electric
  Power Systems Research*, 2023 — validated against OpenModelica and Dynawo), but **its actual public
  source repository was not located this session** — the paper and its abstracts were found, a
  citable GitHub URL was not. This is an open question (below), not a resolved fact. Separately, and
  more fundamentally: IEC 61400-27 models are explicitly scoped for RMS/positive-sequence stability
  studies, not the 200µs-timestep EMT domain Lab 5 actually runs. A literal live co-simulation coupling
  (Modelica RMS solver ↔ DPsim EMT solver, in lockstep) is a real, nontrivial research problem, not a
  glue task — the pragmatic near-term path is **one-way coupling**: a Modelica/FMU wind-turbine model
  produces a slower power-output trajectory (aerodynamics, pitch control, rotor-speed dynamics — all
  genuinely RMS-timescale phenomena), which becomes a boundary-condition input to DPsim's EMT solve,
  not a jointly-solved system.
- **A generic Modelica MCP server already exists, unrelated to Power-Agent.**
  [`Orthogonalpub/modelica_simulation_mcp_server`](https://github.com/Orthogonalpub/modelica_simulation_mcp_server)
  is a public, general-purpose (not power-specific) MCP server for running Modelica simulations.
  OpenModelica itself has an open GitHub issue proposing a built-in MCP server in its OMEdit GUI —
  not yet shipped as of this session. Neither has been installed or exercised here; both are Phase 0
  candidates, not confirmed working paths.
- **Negative Imaginary (NI) systems theory is real, established, and directly applied to
  grid-forming inverter control.** NI theory is a robust-control framework originally developed for
  vibration suppression in flexible structures with collocated sensor/actuator pairs — the same
  shape as a local stabilizer measuring a disturbance and injecting a compensating signal at (or
  near) the same point. It gives real passivity/dissipativity guarantees for stable interconnection
  under positive feedback, which a hand-tuned PID/VSM loop does not. Confirmed directly applied to
  this PRD's exact problem: *"A grid-forming control method based on negative imaginary theory for
  distributed energy resource"* (ScienceDirect/Energy Reports, 2023). Broader power-system
  applications confirmed via several 2023-2024 papers: nonlinear NI systems for networked power
  systems, angle-based feedback control, and passivity/NI properties of synchronous-machine systems
  itself (relevant since Phase 1 below reuses DPsim's synchronous-generator swing-equation
  structure) — search terms and titles in Open questions below. **Institutional attribution
  unconfirmed**: this session's research attributes this line of work to Australian National
  University, not CSIRO specifically — a direct check of CSIRO's own GPST-Roadmap "Topic 2:
  Analytical methods for determination of stable operation" report (the most relevant CSIRO-hosted
  document found) turned up no mention of negative imaginary systems at all. Not treated as
  confirmed either way; see Open questions.
- **Modelica and KerML/SysML v2 are complementary, different layers, with a real bridge.** KerML/SysML
  v2 is a systems-architecture/requirements modeling language (structure, interfaces, requirements);
  Modelica is equation-based physical/behavioral simulation. The established bridge is **FMI**
  (Functional Mock-up Interface) — Modelica models export as FMUs that a SysML model references for
  co-simulation. This pattern is mature for SysML v1 (SysPhS); tooling for SysML v2/KerML specifically
  is newer and less proven (SysML v2 itself is a recent OMG standard). If this repo ever wants an
  MBSE-flavored system description of "SPARTAN + grid-forming inverter + wind farm + grid," the honest
  stack is three separate layers — KerML/SysML v2 for architecture, Modelica/FMU for component
  behavior, DPsim for EMT grid physics — not one tool doing all three.

## Goals

1. **A grid-forming stabilizer that measurably reduces a real Lab 5 transient — reported as a
   percentage, never claimed as elimination.** Build the controller against a swing-equation-structured
   plant (reused from DPsim's own synchronous-generator math) driving a `ControlledVoltageSource` at a
   chosen bus, reading the same real-time measurement Lab 5's own detectors already compute
   (`phase_model.py`'s phasor frames), and injecting a compensating voltage. **Proposed control-design
   framework: Negative Imaginary systems theory**, not an ad-hoc hand-tuned PID/VSM loop — NI's
   passivity/dissipativity conditions give a real stability guarantee for a collocated
   sensor/actuator loop interconnected with the (NI or passive) grid, which a tuned-until-it-looks-
   stable PID gain set does not. This is a proposal to evaluate in Phase 1, not a settled choice: if
   fitting the plant to NI's required conditions (e.g. the sign/phase conditions on the transfer
   function) proves impractical against DPsim's actual component model, a conventional VSM/PID
   fallback is acceptable and should be stated as such, honestly, rather than forcing NI theory to fit.
   Success is measured, not assumed: run the existing `chaos_schedule.yaml` fault with and without the
   stabilizer active, and report the real before/after deviation (peak sag depth, recovery time,
   RoCoF) — the same honesty discipline every `docs/backlog/0006` finding this session already used.
2. **Cable-length-aware delay compensation, treated as a genuinely open sub-problem, not a known
   technique borrowed off the shelf.** The idea — using a line's known propagation delay (length ÷
   propagation velocity, the same real per-km parameters `docs/backlog/0006`'s R-X trajectory work
   already reads from `sample_topology.json`) to time-align a cancellation signal — resembles deadtime
   compensation (a Smith predictor) more than any named STATCOM/DVR feature found in this session's
   research. Prototype it small and measure whether it actually improves mitigation versus a
   naive (non-delay-compensated) controller before treating it as load-bearing.
3. **Open, standardized renewable generation, honestly scoped by domain.** Add a wind/solar generation
   source to `chaosnet`'s topology. Start with a domain-appropriate stepping stone — a power-output
   profile (from a real published wind-power curve or a simple aerodynamic model) driving DPsim's
   existing `AvVoltageSourceInverterDQ` as the grid-tied interface — before attempting the harder
   IEC 61400-27 Modelica/FMU coupling described above.
4. **Name SPARTAN's real role explicitly**, in code and docs: this PRD is not a bolt-on feature, it is
   the "take corrective or assistive action when feasible" half of SPARTAN's own stated design,
   simulated end-to-end on the chaos-net topology Lab 5 already generates.

## Non-goals

- **Not claiming full transient nullification anywhere** — in docs, chart labels, or code comments.
  Report a measured percentage reduction, with the honest physical reasons a real system can't reach
  100% (finite control bandwidth, propagation delay, actuator/converter rating limits).
- **Not building or claiming a certified IEC 61400-27-compliant model.** Any wind-turbine behavior
  built directly in this repo (as opposed to a properly-sourced upstream Modelica implementation) is
  "generic, in the spirit of the standard's Type 4 structure," stated as such — the same honesty this
  repo already applies to the SA 2016/Iberian scenarios' own "structurally faithful, not literal"
  framing.
- **Not attempting a live Modelica↔DPsim co-simulation in this PRD's first pass.** One-way coupling
  (Modelica/FMU produces a trajectory, DPsim consumes it as a boundary condition) is the acceptance
  bar; true lockstep co-simulation is a follow-on if the simpler version proves valuable.
- **Not vendoring or forking any Modelica MCP server, OpenModelica, or the IEC 61400-27 Modelica
  implementation (if its source is located).** Same "compose, don't rebuild" discipline as
  `docs/prd/0004`.
- **Not building the KerML/SysML v2 architecture layer in this PRD.** Named above as the honest
  three-layer picture, explicitly out of scope until Phases 1-3 below produce something real enough to
  be worth describing architecturally.

## Phasing

- **Phase 0 — locate real sources, don't assume.** Find the actual public repository for the
  Carbonell/Cardozo IEC 61400-27-1 Type 4 Modelica implementation (or confirm it isn't public, in
  which case name that and pick a different open Modelica wind model). Install and exercise
  `Orthogonalpub/modelica_simulation_mcp_server` (or check OpenModelica's own MCP server's shipping
  status by then) against a trivial Modelica model to confirm it's genuinely usable, not just
  documented. Report findings before Phase 3 depends on either.
- **Phase 1 — grid-forming stabilizer, no renewables yet.** Build the VSM-style controller against
  Lab 5's existing chaos-net and `chaos_schedule.yaml` fault (the same one `docs/backlog/0006`
  already characterized in detail — known baseline). Measure and report real before/after mitigation
  numbers. This alone delivers Goal 1 and is independent of everything else in this PRD.
- **Phase 2 — cable-length delay compensation.** Add the deadtime-compensation term to Phase 1's
  controller, on the same fault, and report whether it measurably helps versus Phase 1's baseline —
  a real comparison, not an assumed improvement.
- **Phase 3 — wind/solar generation, power-profile stepping stone.** Add a generation source to
  `chaosnet` using a real published power curve (or a simple, cited aerodynamic model) driving
  `AvVoltageSourceInverterDQ`, independent of the Modelica question — this alone makes the topology
  more realistic and gives the Phase 1 stabilizer something more interesting to react to (a renewable
  ramp/dropout, not just a bolted fault).
- **Phase 4 — IEC 61400-27 Modelica/FMU coupling (gated on Phase 0's findings).** Only attempted if
  Phase 0 finds a real, usable public source and a working Modelica MCP/FMU export path. One-way
  coupling only, per the Non-goals above.
- **Phase 5 (aspirational, not scoped further here) — KerML/SysML v2 architecture layer.** Revisit
  once Phases 1-4 produce something concrete enough to model architecturally.

## Acceptance criteria for this PRD

- [ ] Phase 1's stabilizer runs against the real `chaos_schedule.yaml` fault and reports a real,
      measured before/after mitigation number (peak sag depth and/or recovery time) — not asserted,
      computed from an actual DPsim run.
- [ ] Every claim about what DPsim mitigation traces back to a real chosen device+parameters, not a
      hand-tuned number chasing a target percentage.
- [ ] Phase 0's IEC 61400-27 source-location question is answered one way or the other before any
      Phase 4 work begins — "not found, using X instead" is an acceptable, honest outcome.
- [ ] No documentation anywhere in this PRD's implementation claims "eliminates," "nullifies," or
      "removes" the transient — only measured reduction.
- [ ] SPARTAN's corrective-action role is stated explicitly in the lab's own README once Phase 1
      lands, not left implicit.

## Open questions

- **Does the cable-length delay-compensation idea actually help, or is a simple fast PI/VSM loop
  already good enough that the extra complexity buys nothing measurable?** Phase 2 exists specifically
  to answer this with a real comparison, not to assume the idea works because it sounds plausible.
- **Where does the IEC 61400-27 Modelica implementation's source actually live**, if it's public at
  all — Phase 0's first concrete task.
- **Is `AvVoltageSourceInverterDQ`'s PLL-based design actually swappable/bypassable for a grid-forming
  mode at the Python-binding level, or does grid-forming control genuinely require the
  `ControlledVoltageSource`-plus-hand-built-control-law path this PRD assumes?** Worth a quick spike
  against DPsim's actual C++ source before committing to the harder path.
- **Single-controller vs. multi-controller scope**: this PRD assumes one stabilizer at one bus for
  Phase 1. Whether SPARTAN's "distributed emergency response coordinator" framing implies multiple
  cooperating stabilizers (a genuinely harder, later problem) is explicitly deferred, not decided here.
- **Does the Lab 5 plant actually satisfy NI/output-strictly-negative-imaginary conditions once
  reduced to a `ControlledVoltageSource` driven by DPsim's swing-equation math**, or does Phase 1
  discover it needs reshaping (e.g. a bias/feedthrough term) to fit — a real feasibility question,
  not assumed answered by the literature review above.
- **Who is the correct institutional attribution for Australian negative-imaginary-systems research
  applied to power systems — CSIRO, ANU, or both on different papers?** This session's research
  points to ANU and could not confirm CSIRO from a direct document check; flagged to the user, awaiting
  their specific source before this PRD states an attribution as fact anywhere.
