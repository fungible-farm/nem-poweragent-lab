# 0005 — Grid-forming transient stabilizer + open renewable-generation models (Lab 5, SPARTAN's corrective-action testbed)

- **Status:** in progress — Phases 0/1/1.5/2/3 done; Phasing below now includes Phase 1.5
  (EMT→OPF headroom translation); implementation proceeding phase-by-phase, each phase its own
  stacked branch/PR
- **Depends on:** none directly; builds on Lab 5's existing `chaosnet`/`run_dpsim.py`/`phase_model.py`
  machinery and reuses the R-X/sag-propagation work from `docs/backlog/0006`
- **Touches:** `labs/05-spartan-chaosnet-transient-stream/chaosnet.py` (new generator/controller
  component types), `run_dpsim.py` (control-loop wiring), new `labs/05-.../grid_forming.py`, new
  `labs/05-.../headroom_translation.py` (Phase 1.5, reads Phase 1's mitigation output, writes an
  OPF-consumable constraint parameter), `labs/01-simple-loadflow-fit/` and/or
  `labs/04-.../` (Phase 1.5, wherever the binding-constraint check actually runs against),
  possibly a new `labs/06-.../` if the renewable-model + MBSE layer grows past Lab 5's own scope,
  `docs/VISION.md` §3 ecosystem table (proposed Modelica/FMI row)

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

- **DPsim ships no grid-forming inverter component in the version this repo has installed — but
  upstream `master` gained one on GitHub five weeks before this session, not yet released to PyPI.**
  `dir(dpsimpy.emt.ph3)` (this installed version, pinned `dpsim>=1.2.1` in `pyproject.toml`,
  `uv.lock` resolves it to the `dpsim-1.2.1` wheel published 2025-12-10) is: `AvVoltageSourceInverterDQ`,
  `Capacitor`, `ControlledVoltageSource`, `CurrentSource`, `Full_Serial_RLC`, `Inductor`,
  `NetworkInjection`, `PiLine`, `RXLoad`, `ReducedOrderSynchronGeneratorVBR`, `Resistor`,
  `SeriesResistor`, `SeriesSwitch`, `Switch`, `SynchronGenerator{3,4,5,6a,6b}OrderVBR`,
  `SynchronGeneratorDQODE`, `SynchronGeneratorDQTrapez`, `Transformer`, `VoltageSource`.
  `AvVoltageSourceInverterDQ` is **grid-following**: its own
  `set_controller_parameters(Kp_pll, Ki_pll, Kp_power_ctrl, Ki_power_ctrl, Kp_curr_ctrl, Ki_curr_ctrl,
  omega_cutoff)` signature confirms a PLL-synchronized design — it locks onto an existing grid
  reference, it does not set one.
  **`with_control(bool)`, read from the real C++ source, is a bypass flag unrelated to grid-forming
  vs. grid-following** — `dpsim-models/include/dpsim-models/EMT/EMT_Ph3_AvVoltageSourceInverterDQ.h`
  declares `void withControl(Bool controlOn) { mWithControl = controlOn; };` (bound to Python as
  `with_control` in `dpsim/src/pybind/EMTComponents.cpp`), and its only use is
  `dpsim-models/src/EMT/EMT_Ph3_AvVoltageSourceInverterDQ.cpp:446-447`:
  `if (mWithControl) mSubCtrledVoltageSource->mVoltageRef->set(PEAK1PH_TO_RMS3PH * **mVsref);` —
  i.e. it just gates whether the PLL/power-controller's computed reference gets written to the
  underlying voltage source each timestep (an open-loop/debug bypass), not a mode selector. Confirmed
  by reading the real source at `github.com/sogno-platform/dpsim`, not by guessing from the name.
  **DPsim's upstream `master` branch (not this repo's installed version) already has a real
  grid-forming component**: commit `0aa1ab99` ("Added Grid-forming Inverter, VCO and
  VoltageController", 2026-07-09, refined by `a57abe64` and `c88d3243` on 2026-07-13) added
  `CPS::EMT::Ph3::VSIVoltageControlVCO` — a separate class (not a flag on `AvVoltageSourceInverterDQ`)
  at `dpsim-models/include/dpsim-models/EMT/EMT_Ph3_VSIVoltageControlVCO.h` and
  `dpsim-models/src/EMT/EMT_Ph3_VSIVoltageControlVCO.cpp`, exposed to Python in
  `dpsim/src/pybind/EMTComponents.cpp:463-492`. It replaces the PLL (`Signal::PLL`) with a free-running
  `Signal::VCO` (`dpsim-models/src/Signal/VCO.cpp`: `signalStep` does
  `mInputCurr = mInputRef; mStateCurr = mStatePrev + mTimeStep * mInputCurr` — i.e. it integrates an
  externally-set frequency reference into a phase angle, self-clocked rather than grid-synchronized —
  the defining structural trait of grid-forming control) and replaces the power controller with
  `Signal::VoltageControllerVSI`, which regulates fixed `Vd_ref`/`Vq_ref` setpoints via cascaded
  voltage+current PI loops (`dpsim-models/include/dpsim-models/Signal/VoltageControllerVSI.h`).
  Read closely: this is grid-forming in the "self-clocked voltage source" sense, but **not** a
  droop or VSM controller — `VoltageControllerVSI`'s gains are plain PI (`Kp/Ki` on voltage and
  current), there is no P–f droop term or swing-equation/inertia coupling between measured power and
  the VCO's frequency input. Confirmed via `grep`-style search across the whole `Signal/` directory:
  no `droop`- or `VSM`-named file exists there. **This repo's installed dpsim (1.2.1, Dec 2025)
  predates this addition and does not have `VSIVoltageControlVCO`** — confirmed directly:
  `uv run python -c "import dpsimpy; print('VSIVoltageControlVCO' in dir(dpsimpy.emt.ph3))"` prints
  `False`. Per this PRD's non-goals (no vendoring/forking), this session did not upgrade the pin or
  build DPsim from source to exercise the new class — it was read from upstream GitHub source only,
  not run. Net effect on the plan: the PRD's original assumption — that grid-forming here requires
  driving `ControlledVoltageSource` with a hand-built VSM/swing-equation control law — is still
  correct for the *VSM-specific* part of Goal 1 (no droop/VSM component exists anywhere in DPsim,
  released or unreleased), but a lighter-weight "self-clocked voltage source" building block
  (`VSIVoltageControlVCO`) now exists upstream as unreleased prior art, worth revisiting in Phase 1
  if/when this repo's `dpsim` pin is ever bumped past 1.2.1.
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
  Modelica implementation of IEC 61400-27-1:2020 Type 4 exists (Carbonell, Cardozo, Cossart, Prévost,
  Torresan, Guiu — all RTE-France — *Electric Power Systems Research*, 2023,
  [S0378779622004953 on ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0378779622004953),
  validated against OpenModelica and Dynaωo). **Its source is public, and was located this session**:
  it lives in RTE's own [`dynawo/dynawo`](https://github.com/dynawo/dynawo) repository (MPL-2.0
  licensed, confirmed via `gh api repos/dynawo/dynawo/license`) — not a standalone repo of the
  authors', but folded into Dynaωo's own Modelica model library, which is exactly what "validated
  against Dynawo" meant: the authors *are* the Dynaωo team, and this model is a first-class part of
  Dynaωo's shipped library, not an external contribution to it. Confirmed live at HEAD via
  `gh api repos/dynawo/dynawo/contents/...`: the Type 4A/4B, 2015/2020-edition models sit at
  `dynawo/sources/Models/Modelica/Dynawo/Electrical/Wind/IEC/WT/WT4ACurrentSource2020.mo` and
  `WT4BCurrentSource2020.mo` (plus `2015.mo` variants), with supporting control blocks under
  `dynawo/sources/Models/Modelica/Dynawo/Electrical/Controls/IEC/IEC61400/` and the wind-power-plant
  layer under `.../Electrical/Wind/IEC/WPP/`. Full public URL for the exact model this PRD would use:
  `https://github.com/dynawo/dynawo/blob/master/dynawo/sources/Models/Modelica/Dynawo/Electrical/Wind/IEC/WT/WT4ACurrentSource2020.mo`.
  This resolves the "not located" open question below outright — no fallback wind model is needed.
  Separately, and more fundamentally: IEC 61400-27 models are explicitly scoped for RMS/positive-sequence
  stability studies, not the 200µs-timestep EMT domain Lab 5 actually runs. A literal live co-simulation
  coupling (Modelica RMS solver ↔ DPsim EMT solver, in lockstep) is a real, nontrivial research problem,
  not a glue task — the pragmatic near-term path is **one-way coupling**: a Modelica/FMU wind-turbine
  model produces a slower power-output trajectory (aerodynamics, pitch control, rotor-speed dynamics —
  all genuinely RMS-timescale phenomena), which becomes a boundary-condition input to DPsim's EMT solve,
  not a jointly-solved system.
- **`Orthogonalpub/modelica_simulation_mcp_server` currently (HEAD) contains zero installable code —
  it is marketing for a proprietary cloud SaaS, not an MCP server you can run today.** Cloned it
  directly to a scratch directory and inspected the full history (`git log --all`, 89 commits,
  2025-04-13 through 2025-07-13, HEAD `53dae484`): the repo *did* carry real installable source
  early on — `main.py` (a `FastMCP`-based server proxying a websocket connection to a hardcoded local
  Orthogonal instance), `pyproject.toml`, and `install.py`/`install_orthogonal_mcp_server.py`, present
  from the `118407e` "Initial commit" through commit `0de540a` ("update", 2025-05-23) — but commit
  `0de540a` itself deleted all four of those files (608 lines removed) with no replacement, and every
  commit since (through today's HEAD) only ever adds/edits `README.md`, `LICENSE` (MIT), and four
  screenshot PNGs. So the "no installable code" finding is accurate for what a Phase 0 evaluator
  would `git clone` today, but not for the repo's full history — the early source existed, was
  primitive (hardcoded local IP, embedded auth token, no packaging beyond a bare `pyproject.toml`),
  and was deliberately stripped out and replaced with a marketing page. The current README documents
  "ODE — a new Modelica IDE" and a cloud MCP bridge to it, gated behind creating an account and API
  token at `www.orthogonal.dev` ("orthogonal supersystems GmbH") — "secure cloud execution," not a
  local server. There is nothing to install or exercise against a trivial model at HEAD; the repo
  today is not a distribution of software, it is a landing page hosted as a GitHub repo. This directly
  resolves Phase 0's "is it genuinely usable, or just documented" question for present-day use: it is
  neither genuinely usable *nor* documentation of anything runnable — it's a product pitch with a
  signup wall, unrelated to this PRD's "compose, don't vendor" open-source
  discipline. **OpenModelica's own built-in MCP server has, in fact, shipped since the prior
  session's check.** GitHub issue
  [`OpenModelica/OpenModelica#15385`](https://github.com/OpenModelica/OpenModelica/issues/15385)
  ("Implement MCP server for OMEdit interaction with chatbots") was closed as **completed** on
  2026-06-17 — confirmed via `gh issue view 15385 --json state,stateReason` returning
  `{"state":"CLOSED","stateReason":"COMPLETED"}`. Its own body describes a working prototype
  (Linux-only so far) that can list/set component parameters, simulate and re-simulate, read GUI
  state, and read/write Modelica code directly, driven from OMEdit. Follow-on development continues
  in the still-open
  [`#15854`](https://github.com/OpenModelica/OpenModelica/issues/15854). This session did not install
  OMEdit or exercise its MCP server directly (that requires the OMEdit GUI application, not a
  pip-installable package, and doing so is Phase-0-scale exploration for a later session, not this
  one) — the "shipped, not vaguely proposed" status is the concrete, previously-missing fact. Net:
  **the Orthogonalpub path is a dead end; OpenModelica's own built-in MCP server is the real
  candidate for Phase 4**, if that phase is ever reached.
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
2. **Translate Phase 1's EMT-measured mitigation into an OPF constraint-headroom question, and answer
   it honestly.** Everything in Goal 1 lives entirely in the EMT/time-domain tier — it says nothing
   about whether the stabilizer matters to AEMO's actual dispatch/constraint layer, which is a
   steady-state OPF question (Lab 1's/Lab 4's pandapower machinery), not an EMT one. Take Phase 1's
   real measured margin recovered on the fault-adjacent line (e.g. thermal headroom not consumed
   during the fault, or a voltage-dip depth avoided) and express it as a constraint parameter Lab 1/4's
   existing OPF can actually consume (a revised thermal/voltage limit on that line), then check whether
   it changes which constraint binds in an existing OPF run. **The honest answer may be "no, it
   doesn't move anything"** — that is an acceptable, reportable outcome, not a failure to fix; a
   stabilizer that measurably shrinks an EMT transient but never approaches the margin an OPF's
   steady-state limits already tolerate is real information, not a null result to explain away.
3. **Cable-length-aware delay compensation, treated as a genuinely open sub-problem, not a known
   technique borrowed off the shelf.** The idea — using a line's known propagation delay (length ÷
   propagation velocity, the same real per-km parameters `docs/backlog/0006`'s R-X trajectory work
   already reads from `sample_topology.json`) to time-align a cancellation signal — resembles deadtime
   compensation (a Smith predictor) more than any named STATCOM/DVR feature found in this session's
   research. Prototype it small and measure whether it actually improves mitigation versus a
   naive (non-delay-compensated) controller before treating it as load-bearing.
4. **Open, standardized renewable generation, honestly scoped by domain.** Add a wind/solar generation
   source to `chaosnet`'s topology. Start with a domain-appropriate stepping stone — a power-output
   profile (from a real published wind-power curve or a simple aerodynamic model) driving DPsim's
   existing `AvVoltageSourceInverterDQ` as the grid-tied interface — before attempting the harder
   IEC 61400-27 Modelica/FMU coupling described above.
5. **Name SPARTAN's real role explicitly**, in code and docs: this PRD is not a bolt-on feature, it is
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
- **Phase 1.5 — EMT→OPF headroom translation.** Take Phase 1's real measured before/after numbers and
  express the recovered margin as a constraint parameter against the same fault-adjacent line already
  identified by `chaosnet.py`'s `fault_adjacent_line_name()` (from `docs/backlog/0006` tier 2). Run
  Lab 1's or Lab 4's existing OPF with that revised parameter and check, directly, whether any binding
  constraint changes. Report the real result either way — "moved constraint X by Y%" or "no binding
  constraint changed" are both acceptable, honestly-reported outcomes. This phase is what turns "the
  stabilizer works" (an EMT claim) into "the stabilizer is operationally meaningful to AEMO's dispatch"
  (an OPF claim) — or honestly establishes that it currently isn't, at this fault's scale.
- **Phase 2 — cable-length delay compensation.** Add the deadtime-compensation term to Phase 1's
  controller, on the same fault, and report whether it measurably helps versus Phase 1's baseline —
  a real comparison, not an assumed improvement.
- **Phase 3 — wind/solar generation, power-profile stepping stone. Done** (`renewable_source.py`,
  `run_dpsim.py --renewable`). A real Vestas V52-850kW wind turbine (cut-in/rated/cut-out/rated-power
  cited from the manufacturer's own General Specification datasheet, fetched directly this session)
  drives `AvVoltageSourceInverterDQ` at a chosen bus via its real `P_ref` attribute, from a
  deterministic wind-dropout profile timed to the schedule's own fault trigger. Two real findings
  from this phase: (1) `AvVoltageSourceInverterDQ` requires a two-stage SP-domain power-flow
  pre-init (`init_with_powerflow`), not `do_steady_state_init(True)` alone — confirmed directly,
  not assumed, via a standalone smoke test mirroring DPsim's own official example notebook; (2)
  `--renewable` cannot currently be combined with Phase 1's `--stabilizer` — splicing both and
  calling `init_with_powerflow` raises a real, reproducible `RuntimeError` at `sim.start()`, so
  `run_step()` raises a clear `ValueError` instead of allowing a silently-broken combined run. See
  `renewable_source.py`'s own module docstring for both findings in full. This alone makes the
  topology more realistic; the Goal-1 tie-in ("gives the Phase 1 stabilizer something more
  interesting to react to") is not yet realized given finding (2) above — a real open item for a
  future phase, not attempted here.
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
- [ ] Phase 1.5 reports a real yes/no on whether Phase 1's measured mitigation changes a binding
      constraint in an existing Lab 1/4 OPF run — including reporting "no" honestly if that's the
      actual result, not just when the answer is "yes."
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
- ~~Where does the IEC 61400-27 Modelica implementation's source actually live, if it's public at
  all — Phase 0's first concrete task.~~ **Resolved.** It lives in RTE's own `dynawo/dynawo` GitHub
  repository (MPL-2.0), as part of Dynaωo's shipped Modelica library, not a standalone repo — see
  `WT4ACurrentSource2020.mo`/`WT4BCurrentSource2020.mo` under
  `dynawo/sources/Models/Modelica/Dynawo/Electrical/Wind/IEC/WT/`. No fallback wind model is needed;
  Phase 4 (if reached) has a real source to point at.
- ~~Is `AvVoltageSourceInverterDQ`'s PLL-based design actually swappable/bypassable for a grid-forming
  mode at the Python-binding level, or does grid-forming control genuinely require the
  `ControlledVoltageSource`-plus-hand-built-control-law path this PRD assumes?~~ **Resolved, from the
  real C++ source, not the Python bindings alone.** `with_control(bool)` is an unrelated open-loop
  bypass flag (gates whether the controller's computed reference is written to the sub voltage source
  each step — see `EMT_Ph3_AvVoltageSourceInverterDQ.cpp:446-447`), not a mode switch — the PLL design
  is not swappable at the binding level. However, DPsim's upstream `master` (commit `0aa1ab99`,
  2026-07-09, five weeks before this session) added a real alternative component,
  `EMT::Ph3::VSIVoltageControlVCO`, that replaces the PLL with a self-clocked `Signal::VCO` — the
  structural definition of grid-forming — but it is plain-PI voltage control, not droop/VSM (no
  P–f coupling, no swing-equation/inertia term anywhere in `Signal/`). It is not in this repo's
  installed `dpsim==1.2.1` (confirmed: `'VSIVoltageControlVCO' in dir(dpsimpy.emt.ph3)` is `False`)
  and was not built from source this session (out of scope for Phase 0). Net: for VSM/droop
  specifically, the PRD's original assumption stands — `ControlledVoltageSource` plus a hand-built
  swing-equation control law is still the only path, in both the released and unreleased DPsim source.
  `VSIVoltageControlVCO` is worth a look as lighter-weight prior art *if* this repo's `dpsim` pin is
  ever bumped, but is not a substitute for the VSM math Goal 1 actually needs.
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
