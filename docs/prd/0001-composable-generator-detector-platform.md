# 0001 — Composable generator/detector simulation platform

- **Status:** proposed
- **Depends on:** none (foundation for 0002, 0003, and any future scenario)
- **Touches:** `labs/05-spartan-chaosnet-transient-stream/` (chaos_schedule.yaml, run_dpsim.py,
  phase_model.py), `rust/phase-model/`, new `labs/_shared/scenario_engine/`

## Problem

Lab 5 today can run exactly one kind of event: a single `line-to-ground` fault, at one target, at
one scheduled time, cleared after a fixed duration (`chaos_schedule.yaml`'s whole schema is
`{target, type, trigger_time_s, clearing_duration_s}`, and `run_dpsim.py` turns it into exactly one
`dpsimpy.event.SwitchEvent3Ph`). That is a *physical fault generator* and nothing else. No real
blackout this repo's own docs reference — not the 2016 SA Black System (`docs/LAB4_AEMO_REAL_DATA.md`,
Lab 4 Part C), not the 28 April 2025 Iberian blackout (cited in the 2026 GPSRR review as the
reference international voltage-control incident) — is a single fault. Both are a network or
control-system trigger followed by a *chain* of protection/plant responses, each response changing
the conditions that drive the next one, over tens of seconds to a few minutes. Lab 5 has no
primitive for "this local measurement crossing a threshold causes this asset to trip," no
primitive for "this plant type behaves this way under disturbance" (fixed power factor, ride-
through settings, absence of a power system stabiliser), and nothing that *reads* the resulting
stream to flag the precursor pattern — Lab 5's own Definition of Done explicitly defers "SPARTAN's
anomaly-detection logic" as "a subsequent phase," i.e. there is a named, accepted gap where a
detector layer should be.

This PRD is that subsequent phase, generalized: two small composable interfaces — **Generator**
(produces timed, conditional events into a running solve) and **Detector** (consumes the resulting
telemetry stream and emits scored, timestamped findings) — plus a scenario schedule format that can
express a causal chain instead of one event, plus a scoring harness that checks a scenario's
generator outputs and detector findings against a small versioned ground-truth fixture built from
a real incident report's own published numbers. 0002 and 0003 are the first two scenarios that
prove the platform is actually general, not just re-fitted to Lab 5's one existing fault.

## Goals

1. A `Generator` interface general enough to express every mechanism named in the SA 2016 and
   Iberian 2025 root-cause accounts (see 0002/0003) without a new interface per scenario.
2. A `Detector` interface that consumes exactly the views `phase_model.py` already produces
   (raw waveform, phasor frames, positive sequence, SCADA RMS) plus the higher-rate ring-buffer
   feed `rust/phase-model` exists to serve, so detectors are transforms of the one source of truth,
   the same discipline `docs/PSCADOSSE.md` already applies to waveform views.
3. A scenario schedule format that replaces `chaos_schedule.yaml`'s flat `events:` list with an
   ordered, causally-linked timeline (an event can be conditioned on another event or on a
   detector/threshold firing, not just on a fixed `trigger_time_s`) — backward compatible: today's
   one-event schedule is a one-node degenerate case of the new format, not a breaking change.
4. A scoring harness that scores **generator physical realism** (did the modelled cascade's
   timing/magnitude land within a documented tolerance of the real report's own numbers) and
   **detector performance** (precision/recall/lead-time against the same ground truth) separately,
   because a scenario can get the physics right and the detection wrong, or vice versa, and the
   report should say which.

## Non-goals

- Not a claim that any scenario built on this platform is a digital twin of the real Spanish,
  Portuguese, or South Australian network — same caveat class Lab 4 already carries for its 2016
  SA Black System Part C, extended here to cover the new EMT-domain cascade work. See 0002/0003 for
  each scenario's own explicit statement of this.
- Not a real-time/online detector deployment — detectors here run against a completed or
  in-progress simulated stream for scoring purposes, the same posture Lab 5's `verify_stream.py`
  already takes toward SPARTAN (a stub/mock receiver, not production anomaly-detection hardware).
- Not a rewrite of `phase_model.py`'s existing views — `Detector`s consume them as-is.
- Not a general-purpose protection-relay simulator (no attempt at IEC 61850 logical-node fidelity,
  distance-relay zone coordination, etc.) — generators model *only* the threshold/latency behaviour
  needed to reproduce the two named scenarios' documented mechanisms, nothing broader.

## Composable capability: Generators

A `Generator` is anything that can inject a discrete event into a running solve, conditioned on
simulated time and/or the current measurement state. Five kinds cover both target scenarios:

- [x] **`NetworkFaultGenerator`** — today's capability, generalized from "one fault" to "an ordered
      list of faults, each with its own target/type/timing," so a wind-driven multi-line fault
      sequence (SA 2016) is expressible without inventing a new generator kind.
      - [x] Extend `chaos_schedule.yaml`'s `events:` list to accept N entries (it already accepts a
        list; today's script and fixtures just never exercise N>1) — no schema change needed here,
        only exercising the existing plural.
      - [x] `run_dpsim.py`: loop `sim.add_event()` over every scheduled fault instead of assuming
        exactly one.
- [x] **`ProtectionTripGenerator`** — the single most important new primitive: given a named local
      measurement (bus voltage magnitude, frequency, RoCoF, or a phase angle difference) and a
      threshold + sustained-duration condition, trips a named asset (line, generator, transformer)
      the first simulated instant the condition is met. This is what neither scenario has today —
      both SA 2016 and Iberian 2025 are protection-driven cascades, not single faults, and Lab 5
      currently has no way to make a relay *react* to what the fault it just injected caused.
      - [x] Threshold config: `{measurement, comparator, limit, sustain_s, action: {asset, effect}}`.
        Implemented as a tagged union (`kind: "sustain"` for this exact shape) per PRD-0002's own
        "Composable capability mapping" instruction to backport its counting variant here now —
        see the next sub-item and `labs/_shared/scenario_engine/generators.py`'s
        `SustainTriggerCondition`/`CountTriggerCondition`.
      - [x] Must support the two concrete *mechanisms* 0002/0003 need: a sustained-threshold
        overvoltage-style trip and a counting-window fault-ride-through-style trip (both variants
        implemented and directly unit-tested in `labs/_shared/test_scenario_engine.py`). **Not**
        done here: the real Iberian `>~418-432 kV` / SA 2016 wind-farm dip-count *numbers*
        themselves — calibrating those against the primary reports is explicitly 0002/0003's own
        job, out of scope for this platform PRD.
- [x] **`PlantBehaviourGenerator`** — models a plant *type's* control response to a disturbance
      that isn't itself a discrete trip, e.g. a fixed-power-factor RES unit's reactive power
      following its active power (Iberian root-cause factor 1), or a synchronous generator's
      reactive power output saturating below its Q-reference (Iberian factor 2). Distinguished from
      `ProtectionTripGenerator` in that it changes a continuous setpoint, not a binary
      connect/disconnect state. Implemented generically via an `apply_setpoint` callback (no live
      chaosnet.py component exposes a real P/Q control today — named stand-in, see the class's own
      docstring); not exercised by this round's own demo scenario, which only needs the
      acceptance bar's named pair (see "Acceptance criteria" below).
- [x] **`OperatorActionGenerator`** — a scripted, latency-bound discrete action standing in for a
      human control-room decision (switch a shunt reactor, change an interconnector flow limit,
      change an HVDC control mode). Iberian's own final report states these typically took "less
      than 5 minutes" to execute and, in the final cascade, were **not** completed in time — the
      generator's latency parameter is there to reproduce exactly that near-miss/failure mode, not
      to assume instantaneous perfect operator response.
      - [x] Flag this as the natural place to let an *agent* (this repo's whole thesis) stand in for
        the operator decision instead of a fixed script, as a stretch extension once the
        deterministic version is scored — out of scope for 0001/0002/0003's core Definition of Done,
        named here so it isn't lost. (Flagged in the class's own docstring; the agent-driven variant
        itself remains unimplemented, as this box's own text says it should.)
- [x] **`IslandingProtectionGenerator`** — trips a tie/interconnector once an angle-separation,
      loss-of-synchronism, or SPS/RAS-style condition is met (Heywood's SPS in SA 2016; the DRS
      out-of-step protection plus the ES-FR/ES-MA AC interconnector trips in Iberian). A specialised
      `ProtectionTripGenerator` whose measurement is inter-region rather than local — kept as its
      own kind because both scenarios treat it as the "point of no return" event worth naming
      distinctly in scoring, not because the mechanism is architecturally different.

## Composable capability: Detectors

A `Detector` consumes the telemetry stream (raw waveform / phasor frames / positive sequence /
SCADA RMS from `phase_model.py`, or the ring-buffer feed) and emits `Finding{time_s, kind,
confidence, detail}` records. Five detectors, the first four feeding the fifth:

- [x] **`OscillationDetector`** — mode/frequency/damping-ratio estimate from the phasor stream.
      Iberian's report names two concrete, checkable targets: a 0.63 Hz local/converter-driven mode
      (12:03–12:08) and a 0.2 Hz inter-area mode (12:19–12:22) — a correct detector should recover
      both frequencies from the reconstructed phasor stream within a documented tolerance.
      Implemented as a real FFT-based mode estimator over `phase_model.phasor_frames()`'s own
      output and demonstrated end to end against this round's synthetic demo scenario's own
      switching-transient ringing (a real, non-fabricated mode — just not one of Iberian's two named
      historical frequencies, which is 0002/0003's own, separate job).
- [x] **`VoltageCascadeDetector`** — tracks cumulative generation-loss vs. voltage-rise correlation
      (the exact relationship the Iberian report itself charts — cumulative net-load-increase +
      generation-loss on one axis against 400 kV substation voltage on the other) and flags an
      accelerating overvoltage-disconnection cascade once the correlation and its rate of change
      exceed a threshold. **Scoped down** in this implementation: this platform round has no
      generation-loss telemetry source, so it tracks `phase_model.scada_rms()`'s own RMS-rise
      acceleration instead — named explicitly as a limitation in the class's own docstring, not
      hidden; a scenario with a real generation-loss series should extend it.
- [x] **`RoCoFDetector`** — rate-of-change-of-frequency threshold detector. Iberian's report states
      RoCoF stayed within ±1 Hz/s until 12:33:20.560 and exceeded it immediately after — a
      literal, numeric detector target, not an invented one. Same primitive AEMO's own UFLS
      schemes rely on operationally (2026 GPSRR §6.2), so this detector is reusable outside these
      two scenarios too.
- [x] **`AngleSeparationDetector`** — tracks inter-region phase-angle difference / a synchronising-
      torque proxy between two named buses, flagging the "point of no return" precursor before an
      `IslandingProtectionGenerator` fires. This is the detector-side mirror of that generator.
- [x] **`CascadingFailureClassifier`** — a composite detector combining the four signals above into
      one "trajectory is heading toward a blackout" score over time. This is, explicitly, the thing
      `docs/LAB5_SPARTAN_CHAOSNET.md`'s Definition of Done named as **out of scope** ("does not
      implement SPARTAN's anomaly-detection logic... a subsequent phase"). Building it here, scored
      against two real historical events rather than SPARTAN's actual (external, hardware-bound)
      logic, delivers that named-but-deferred item without claiming to reproduce SPARTAN itself.
      (The "scored against two real historical events" half is 0002/0003's own future work; this
      round wires the classifier itself and demonstrates it compositing real Findings.)

## Scenario composition

- [x] Extend `chaos_schedule.yaml`'s schema from a flat event list to a small DAG: each entry keeps
      its existing `target/type/trigger_time_s` fields for time-triggered events, and gains an
      optional `trigger_condition: {generator_id, measurement, comparator, limit, sustain_s}` for
      condition-triggered ones (protection trips, islanding trips). A schedule with only
      time-triggered entries — today's `chaos_schedule.yaml` — remains valid unchanged.
- [x] `run_dpsim.py` (or a new sibling module, see "Where this lives") drives the DAG: at each solve
      step, evaluate any still-pending condition-triggered generator against the current
      measurement state; fire it the instant its condition is met, exactly as DPsim already fires
      time-triggered `SwitchEvent3Ph`s. (`run_dpsim.py` wires this optionally, via
      `scenario_engine.scenario.step_generators()`, only when a schedule actually carries a
      `trigger_condition` entry — today's `chaos_schedule.yaml` never does, so this path is inert on
      the regression schedule; `scenario_engine.scenario.run_scenario()` is the full standalone
      driver `demo_scenario.py` itself uses.)
- [x] The resulting event log (every generator firing, with its actual simulated fire time) is
      committed alongside the transient log, the same "committed, human-readable, not implicit in
      code" discipline `chaos_schedule.yaml`'s own header already states for the input side.
      (`demo_scenario.py` prints and fixture-commits its own `GeneratorEvent` log; a future scenario
      writing this to its own JSON file alongside the transient log, the way `run_dpsim.py` writes
      `dpsim_transient_log.json`, is a straightforward follow-on, not done as a separate artifact
      here.)

## Scoring harness

- [x] `expected_scenario_run.json`-style fixture per scenario: for each named generator firing and
      detector finding, a `{time_s, tolerance_s, magnitude, tolerance_pct}` ground-truth entry
      sourced from the real incident report's own published figure (see 0002/0003's own tables).
      (This round's own fixture, `labs/_shared/expected_demo_scenario_run.json`, is grounded in a
      real sandbox run of the synthetic demo, not a historical report — 0002/0003's own fixtures are
      the ones sourced from AEMO's/Red Eléctrica's published figures.)
- [x] `--step check` scores a run against its fixture and prints a PASS/FAIL per entry plus a
      summary, matching every other lab's existing self-checking convention
      (`docs/DEFINITION_OF_DONE.md`).
- [x] Score generator realism and detector performance as two separate sections of the same report
      — a scenario can nail the cascade physics while a detector misses it (false negative) or
      raise a correct alarm off physics that don't match the real timing (physically wrong but
      "detected") and the report must be able to say which happened.

## Data contracts (sketch, Python-flavoured — not final API)

```python
class Generator(Protocol):
    id: str
    def ready(self, t_s: float, state: MeasurementState) -> bool: ...
    def fire(self, sim: DpsimSolve, t_s: float) -> GeneratorEvent: ...

class Detector(Protocol):
    id: str
    def consume(self, wave: ThreePhaseWaveform, up_to_s: float) -> list[Finding]: ...

class GeneratorEvent(TypedDict):
    generator_id: str
    time_s: float
    kind: str          # "fault" | "trip" | "setpoint_change" | "operator_action" | "island"
    target: str
    detail: dict

class Finding(TypedDict):
    detector_id: str
    time_s: float
    kind: str           # "oscillation" | "voltage_cascade" | "rocof" | "angle_separation" | "composite"
    confidence: float
    detail: dict
```

## Where this lives (proposal, not final)

New `labs/_shared/scenario_engine/` (`generators.py`, `detectors.py`, `scenario.py`, `scoring.py`),
imported by Lab 5's existing chaos-net (whose one fault becomes a one-`NetworkFaultGenerator`
scenario, no behaviour change) and by the two new scenario modules in 0002/0003. Shared because
neither new scenario belongs conceptually inside Lab 5's chaos-net topology generator, but both
need the same DPsim/phase_model plumbing Lab 5 already owns — `labs/_shared/` already exists for
exactly this cross-lab-reuse purpose (`gridfit.py`).

## Acceptance criteria for this PRD

- [x] `Generator`/`Detector` protocols exist, typed, with the five generator kinds and five
      detector kinds above each having at least one concrete implementation.
      (`labs/_shared/scenario_engine/generators.py`, `detectors.py`.)
- [x] Lab 5's existing single fault runs unchanged through the new scenario schedule format
      (regression: `test_lab5.py` still passes with zero schedule changes — verified both via
      `labs/05.../test_lab5.py` directly and via `labs/_shared/test_scenario_engine.py`'s own direct
      re-run of the same three checks, plus a byte-for-byte diff of `run_dpsim.py`'s own
      `expected_dpsim_run.json`-derived summary before/after this change, not just a
      within-tolerance pass).
- [x] At least one condition-triggered generator (`ProtectionTripGenerator`) and one detector
      (`OscillationDetector`) are demonstrated end-to-end on a synthetic scenario before 0002/0003
      attempt the real historical cases, so platform bugs are caught before they're entangled with
      historical-accuracy debugging. (`labs/_shared/scenario_engine/demo_scenario.py`: a
      `NetworkFaultGenerator` fault at SUB-3 causes a real, measured undervoltage at SUB-2, which
      fires a `ProtectionTripGenerator`'s sustain-kind `trigger_condition`; `OscillationDetector`
      recovers a real post-transient mode from the resulting waveform. A real causal chain, not two
      independent scripted events.)
- [x] Scoring harness produces a PASS/FAIL report with generator-realism and detector-performance
      sections, on a committed fixture, self-checkable per `AGENTS.md` convention.
      (`labs/_shared/scenario_engine/scoring.py`; fixture at
      `labs/_shared/expected_demo_scenario_run.json`.)

## Open questions

- Should condition-triggered generators be evaluated every DPsim solve step (200 µs) or at a
  coarser telemetry cadence? Every-step is correct but may cost meaningfully more wall-clock time
  across a multi-minute scenario (Iberian's precursor window is ~30 minutes of grid time at a
  4 kHz-class EMT step) — 0002/0003 may need a hybrid: quasi-static pandapower snapshots for the
  slow pre-cursor minutes, full EMT only for the fast (sub-2-minute) collapse itself, matching the
  real reports' own chapter split (system-conditions-before vs. fast dynamic collapse).
  **Resolved for this round** (a judgment call made during implementation, not left open):
  condition-triggered generators are evaluated at `phase_model.PHASOR_RATE_HZ`'s own cadence
  (100 Hz), not every raw EMT step — see `labs/_shared/scenario_engine/scenario.py`'s module
  docstring "Evaluation cadence" for the reasoning (real protection relays trip off an RMS/phasor
  estimate, never a raw instantaneous sample, and reusing `phase_model.py`'s own rate avoids
  inventing a second one). The quasi-static-pandapower-for-slow-precursor-minutes half of this
  question is unaddressed and remains genuinely open for 0002/0003's own longer scenarios.
- Where does `OperatorActionGenerator`'s scripted-vs-agent-driven split get decided — 0002/0003
  should each state explicitly which they use for their core Definition of Done.
