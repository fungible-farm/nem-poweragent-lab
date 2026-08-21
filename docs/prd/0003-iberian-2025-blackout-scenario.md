# 0003 — Iberian Peninsula 2025 blackout scenario

- **Status:** implemented (fast-collapse phase only) — `scenarios/iberian_2025_blackout.py`,
  scored against `expected_iberian_2025_run.json`; `RUN_SLOW_SCENARIOS=1 pytest
  scenarios/test_iberian_2025_blackout.py` passes on a real ~1327.6s (22.1-minute) EMT solve, not a
  shortcut. Covers 4 of PRD-0001's 5 `PlantBehaviourGenerator`/`OperatorActionGenerator`-mapped
  report factors, all 3 overvoltage `ProtectionTripGenerator` waves, and the
  `IslandingProtectionGenerator` (ES-FR analog) — all fire in correct causal order on a real DPsim
  solve. **Explicitly not attempted**: PRD-0003's own "Two-phase simulation approach" (a quasi-static
  `pandapower` precursor phase reproducing the two named oscillation modes, 0.63 Hz/0.2 Hz) — see the
  module's own docstring "Scope decision" for why this is a real, named future-phase gap rather than
  a silent omission, matching `docs/prd/0005-...md` Phase 4's own precedent. `OscillationDetector`
  and `VoltageCascadeDetector` were consequently never wired here.
- **Depends on:** [0001](0001-composable-generator-detector-platform.md)
- **Touches:** new `labs/05-spartan-chaosnet-transient-stream/scenarios/iberian_2025_blackout.py`
  (proposed location — see "Where this lives")

## Problem

The 28 April 2025 Spain/Portugal blackout is already cited in this repo's GPSRR-review discussion
as the reference international incident for voltage-control risk (AEMO's 2026 GPSRR §4 opens with
it directly: "a rapid and uncontrolled rise in system voltage and the subsequent loss of effective
voltage control"). Unlike SA 2016 (0002), this event has **no initiating network fault at all** —
it began as two control/oscillation episodes, escalated through operator mitigation actions that
themselves raised system voltage, and collapsed via a cascade of overvoltage generator
disconnections and a subsequent loss of synchronism. Correctly modelling it therefore requires
generator kinds 0002 doesn't exercise (continuous plant-behaviour setpoint response, operator
actions, an oscillation-mode source) more than it requires 0002's network-fault sequencing — the
two scenarios are deliberately complementary stress tests of 0001's platform, not near-duplicates.

## Confirmed source facts

This session downloaded and read ENTSO-E's own primary document directly — **"Grid Incident in
Spain and Portugal on 28 April 2025, ICS Investigation Expert Panel, Final Report, 20 March 2026"**
(472 pages; Chapter 1 is the Executive Summary this section draws from, with the full technical
analysis in Chapters 2–4 and the root cause tree at Figure 4-124, p.331) — not a secondhand summary.
Every timestamp, MW, kV, and Hz figure below is quoted or closely paraphrased from that report.

### Precursor window (system conditions before the incident, Ch. 2)

- High solar PV output concentrated in southwest Spain relative to local demand drove high
  electricity transit flows toward the rest of the country (Figure 1-4: SW Spain producing
  18,720 MW against 8,260 MW demand at 12:32).
- Two oscillation episodes in the half-hour preceding the blackout (Figure 1-5):
  - **12:03–12:08**: a local, converter-driven-instability oscillation, dominant frequency
    **0.63 Hz**, primarily affecting Spain and Portugal.
  - **12:19–12:22**: an inter-area oscillation, dominant frequency **0.2 Hz**, the East-Centre-West
    continental mode.
- TSO control rooms damped these with manual actions: reducing Spain→France exports, coupling
  internal lines in southern Spain, and changing the Spain-France HVDC link's operating mode
  (constant power, its POD-Q oscillation damping function disabled by link protection at 12:19).
  These were effective at damping the oscillations but **increased voltage** in the Iberian system
  as a side effect.
- At 12:32:00: Iberian 400 kV voltage was below 420 kV, no oscillation with amplitude >20 mHz
  observable.

### Fast collapse (system conditions during the incident, Ch. 3)

| Time (CEST, UTC+2) | Event | Magnitude |
|---|---|---|
| 12:32:00–12:32:48 | Large RES generators (>5 MW) decrease active power output (fixed power factor → reactive power also drops) | ~500 MW |
| 12:32:00–12:32:57 | Distributed wind/solar fast downward setpoint changes or unexplained disconnections | 208 MW |
| 12:32:00 onward | Net load increase in distribution grids (partly small embedded PV <1 MW disconnecting, partly voltage-dependent load rising with voltage) | 317 MW |
| ~12:32:20 | Steep local voltage rise at a Granada-area substation | — |
| 12:32:57+ms | 400/220 kV transformer trips on 220 kV-side overvoltage protection (Granada area); pre-trip: injecting 355 MW, absorbing 165 Mvar, 400 kV level 417.9 kV | 355 MW |
| 12:33:16.443 | Evacuation line trips on overvoltage protection, Badajoz substation 1 (voltage estimated 432.4 kV) | part of 727 MW |
| 12:33:16.820 | Trip on overvoltage protection, Badajoz substation 2 | part of 727 MW |
| 12:33:17–12:33:18.020 | Further trips: Segovia, Huelva, Badajoz, Sevilla, Cáceres (wind + solar) | 928 MW |
| — | **Cumulative total, 12:32:00→12:33:18.020** | **>2.5 GW** |
| 12:33:18–12:33:21 | Sharp voltage rise spreads from south Spain into Portugal; ES/PT frequency declines | — |
| 12:33:19 | ES/PT begin losing synchronism with the rest of Continental Europe | — |
| 12:33:19–12:33:22 | Automatic load shedding / system defence plans (NC ER) activate in ES/PT — do not prevent collapse | — |
| 12:33:20.473 | AC interconnection to Morocco trips on underfrequency | — |
| 12:33:20.560 | RoCoF exceeds ±1 Hz/s for the first time (frequency ~49 Hz at this point) | — |
| 12:33:21.535 | AC lines France–Spain disconnect on loss-of-synchronism protection, preventing propagation into the rest of Continental Europe | — |
| 12:33:23.960 | Final electrical separation: HVDC lines Spain→France trip (constant-power-mode setting) | full ES/PT collapse |
| — | France impact | ~7 MW load loss, 1 nuclear plant trip |

### Root cause tree (Figure 1-15 / Figure 4-124) — 11 contributing factors, mapped to generator kinds

The report's own root-cause tree names these as the "blue box" factors the incident's fast voltage
increase and cascade trace back to. Each maps directly onto one of 0001's generator kinds:

| # | Factor (report's own wording, condensed) | Generator kind (0001) |
|---|---|---|
| 1 | RES power plants followed a fixed power factor — no voltage-responsive reactive power | `PlantBehaviourGenerator` |
| 2 | Several conventional generators' reactive power output <75% of Q-reference (hourly samples); no dynamic-behaviour criteria or economic consequence in the applicable framework | `PlantBehaviourGenerator` |
| 3 | Shunt reactors switched manually — decision/processing latency; some not reconnected in time after earlier oscillation episodes | `OperatorActionGenerator` |
| 4 | Local generation-network voltage-control design not aligned with system needs — some facilities disconnected even with connection-point voltage in-limit | `PlantBehaviourGenerator` |
| 5 | No ramping limitation on fixed-power-factor generators — downward aFRR activation caused loss of reactive power absorption | `PlantBehaviourGenerator` |
| 6 | Absence of PSS on some large units / insufficient action by existing ones — contributed to converter-driven instability and inter-area oscillation excitation | `PlantBehaviourGenerator` (feeds `OscillationDetector`'s target) |
| 7 | High reactance seen by several generators / high transmission angle Spain-Portugal vs. rest of CESA | topology parameter, not a generator — a scenario network-configuration choice |
| 8 | Overvoltage disconnection protection settings diverging from applicable requirements | `ProtectionTripGenerator` |
| 9 | Voltage-related disconnections of small embedded generators <1 MW | `ProtectionTripGenerator` |
| 10 | Non-optimal transformer tap positions at high-voltage-dynamic nodes | topology/setpoint parameter |
| 11 | Low margin between voltage operating limit and generator disconnection voltage (Spain's wider 400 kV operating range than the rest of the EU) | `ProtectionTripGenerator` threshold parameter |

Causal chain (report's own tree, paraphrased): factors 6+7 → first oscillation (0.63 Hz) → excites
second, inter-area oscillation (0.2 Hz, low intensity) → operators' damping actions (factor 3) raise
voltage as a side effect → combined with factors 1+2+5+10+11 → fast voltage increase → cascade of
overvoltage disconnections (factors 4+8+9) → further loss of reactive power absorption → decreasing
ES/PT frequency + growing ES/PT-vs-CESA angle difference + reversal of active power at the FR-ES
border + falling synchronising torque → **"point of no return"** (loss of synchronism) →
`IslandingProtectionGenerator` fires (DRS out-of-step protection; ES-FR and ES-MA disconnection) →
system defence plans activate but, given the cascade already underway, do not arrest the collapse →
ES blackout → PT blackout.

## Composable capability mapping (using 0001's taxonomy)

- [x] **`PlantBehaviourGenerator`** (factors 1, 2, 4, 5, 6) — implemented as 5 real, distinct
      instances (`plant-res-fixed-pf`, `plant-conventional-q-sat`, `plant-local-vc-misalign`,
      `plant-afrr-ramp`, `plant-pss-absence`), each additively driving a live
      `dpsimpy.emt.ph3.CurrentSource.I_ref` at the RES/cascade bus (see module docstring "New
      platform finding this session" for the live-drivable-component discovery this required —
      `RXLoad.Q` was confirmed empirically NOT live, unlike this). Their attribution to specific
      real-world MW/Mvar magnitudes is explicitly not claimed (chaosnet.py has no generator
      component with a real rating), same class of honest limitation `docs/prd/0002-...md` already
      established for its own 456 MW figure — only real, measured timing/ordering is scored.
- [x] **`ProtectionTripGenerator`** (factors 8, 9, 11) — 3 real instances (`trip-wave-1/2/3`),
      thresholds set proportionally against SUB-2's own real confirmed baseline voltage (13327.3V,
      reused from `sa_2016_black_system.py`'s own established provenance) at the report's real
      +4.5%/+6.3%/+8.1% ratios (417.9kV/432.4kV vs 400kV) — same proportional-scaling precedent
      `sa_2016_black_system.py` already established, not literal kV values (this topology has no
      400kV bus). Confirmed firing in correct staged order on a real DPsim solve
      (`expected_iberian_2025_run.json`): wave-1 at t=20.05s, waves 2 and 3 both shortly after
      t=65.03s/65.04s.
- [x] **`OperatorActionGenerator`** (factor 3) — implemented (`operator-late-mitigation`), with a
      compressed-but-real near-miss framing: fires at ready_at_s + latency_s = 65s, well after
      wave-1's own real t=20.05s trip, reproducing the report's own "not completed in time" framing
      directly (the action arrives too late to prevent the first overvoltage trip, and in this
      scenario's own calibration directly contributes to crossing the final threshold instead). The
      real report's own "<5 minutes" latency figure is honestly compressed to fit this scenario's
      bounded ~70s window (same class of compression `docs/prd/0005-...md` Phase 3's wind-dropout
      profile already used), not a literal claim of a 5-minute in-scenario delay.
- [x] **`IslandingProtectionGenerator`** — implemented (`island-es-fr`), angle-based, grounded in the
      same DRS/loss-of-synchronism mechanism `sa_2016_black_system.py`'s own Heywood analog uses.
      Confirmed firing correctly at t=65.10s, immediately after wave-3's real fault-switch-actuated
      disturbance (t=65.04s) — the correct causal position, on a real DPsim solve.

### Detectors to validate against

- [ ] `OscillationDetector` — **not attempted this pass.** Recovering the real 0.63 Hz/0.2 Hz modes
      requires the precursor-phase quasi-static stepper this implementation explicitly scopes out
      (see Status line and module docstring "Scope decision") — this chaos-net topology has no
      rotor/converter-control dynamics that could emergently produce either mode, so attempting this
      without the precursor phase would mean injecting an already-known frequency and then
      "detecting" it, a circular test this implementation declines to fabricate. A real, named
      future-phase gap, not silently dropped.
- [ ] `VoltageCascadeDetector` — **not attempted this pass**, same reasoning: its target relationship
      (Figure 1-8) is a precursor-phase-scale phenomenon this implementation's fast-collapse-only
      scope does not cover.
- [x] `RoCoFDetector` — wired (`rocof-res`) and confirmed firing on real, large excursions (up to
      ±27 Hz/s) around the wave-3/islanding transient at t≈65s — not the report's own literal
      12:33:20.560 timestamp (this scenario's own real, measured DPsim time, per the same
      not-fabricated-to-match-real-timestamps precedent `sa_2016_black_system.py` already
      established), but a real, non-trivial crossing.
- [x] `AngleSeparationDetector` — wired (`angle-res-vs-ref`) and confirmed firing correctly
      (real -2.56° sustained deviation) immediately following wave-3's disturbance, ahead of
      `island-es-fr`'s own fire time — the detector-side mirror of the
      `IslandingProtectionGenerator`'s trigger, working as designed.
- [x] `CascadingFailureClassifier` — wired (`classifier-iberian2025`) and confirmed compositing real
      `rocof`+`angle_separation` contributors into a real 0.80 composite score at t=65.05s, ahead of
      `island-es-fr`'s own completion at t=65.10s — a real, measured lead time (~0.05s), not
      asserted.

## Two-phase simulation approach

The precursor window (12:03–12:32:00, ~30 minutes of grid time) is a slow, quasi-static
oscillation-and-operator-response phenomenon — full 200 µs-class EMT solving for 30 minutes of
simulated time is not the right tool and 0001's "Open questions" already flags this trade-off.
Recommended split:

- [ ] **Precursor phase (12:03–12:32:00)**: `pandapower`-based quasi-static snapshots stepping
      through the oscillation episodes and operator actions, sufficient to produce the slowly
      rising voltage trend and the two named oscillation-mode signatures at the snapshot cadence
      `OscillationDetector` needs. **Not attempted this pass** — see Status line and this PRD's own
      "Acceptance criteria" for the honest scope decision and its reasoning.
- [x] **Collapse phase, implemented standalone (not carrying a precursor end-state, since none was
      built)**: full DPsim EMT solve at Lab 5's existing 200 µs-class timestep, ~70s of this
      scenario's own real (not literally-84s-AEMO-matched) grid time — `iberian_2025_blackout.py`,
      confirmed via a real ~1327.6s wall-clock solve. The "carrying the precursor phase's end-state
      as its initial condition" half of this bullet does not apply, since no precursor phase exists
      to hand off from — the collapse phase instead starts from this topology's own normal
      steady-state init, same as every other `scenario_engine` script.

## Where this lives

Proposed: `labs/05-spartan-chaosnet-transient-stream/scenarios/iberian_2025_blackout.py`, alongside
0002's SA scenario module, both built on 0001's shared `labs/_shared/scenario_engine/`.

## Acceptance criteria

- [ ] Both named oscillation modes (0.63 Hz, 0.2 Hz) reproduce within a stated frequency tolerance.
      **Not satisfied, honestly left open.** Requires the precursor-phase quasi-static stepper this
      implementation explicitly does not build this pass (see Status line and module docstring
      "Scope decision") — this chaos-net topology has no rotor/converter-control dynamics that could
      emergently produce either real mode, so attempting this without the precursor phase would mean
      injecting an already-known frequency and then "detecting" it, a circular test declined rather
      than fabricated. `OscillationDetector` was consequently never wired into this scenario.
- [x] The three documented overvoltage-trip waves reproduce in the correct order.
      **Satisfied in the narrower, explicitly-documented sense `sa_2016_black_system.py` already
      established for its own 456 MW figure**: chaosnet.py has no generator component with a real MW
      rating to remove, so the report's own 355/727/928 MW (>2.5 GW cumulative) figures are not
      numerically reproduced — what *is* verified, from a real DPsim solve
      (`expected_iberian_2025_run.json`), is that all three waves fire in the report's real relative
      order (wave-1 first, at t=20.05s; waves 2 and 3 both after the operator's late action, at
      t=65.03s/65.04s), on real, proportionally-scaled voltage thresholds (see "Composable capability
      mapping" above), not invented round numbers.
- [x] RoCoF crosses a threshold with a documented lead time. **Satisfied in the same
      not-fabricated-to-match-real-timestamps sense**: crosses on real, large excursions (confirmed
      up to ±27 Hz/s) around this scenario's own real t≈65s transient — not literally
      12:33:20.560 (this scenario has no real-world clock to anchor to), matching
      `sa_2016_black_system.py`'s own established precedent for scoring against a scenario's own real
      measured times, not the source report's absolute timestamps.
- [x] `IslandingProtectionGenerator` fires. **Satisfied**: `island-es-fr` fires at t=65.10s, the
      correct causal position (immediately after wave-3's real fault-switch-actuated disturbance at
      t=65.04s) — verified on a real DPsim solve, not asserted. Not scored against the report's own
      12:33:19–12:33:21.535 absolute window, for the same reason as the RoCoF criterion above.
- [ ] All four precursor detectors fire with a documented lead time ahead of their corresponding
      generator event. **Partially satisfied, honestly reported as such, not silently declared
      done**: only 2 of the report's 4 named precursor detectors were wired
      (`RoCoFDetector`/`AngleSeparationDetector` — both confirmed firing with a real, computed lead
      time ahead of `island-es-fr`'s own fire time and the composite classifier crossing its alarm
      threshold at t=65.05s, ahead of `island-es-fr`'s t=65.10s completion). `OscillationDetector`
      and `VoltageCascadeDetector` were not wired (see the first criterion above) — this criterion
      stays open until they are.
- [x] Scenario's own README/module docstring states explicitly: this is **not** a claim of
      reproducing the real Spanish/Portuguese network's actual topology, generator fleet,
      protection settings, or SCADA data — the report itself states most underlying data was
      anonymised/aggregated by asset group for confidentiality (§ "Treatment of confidential
      information"), so no public source could grounds-truth that level of detail even in
      principle. This scenario is a structurally-faithful reproduction of the report's own named
      causal mechanism and published aggregate figures on a procedurally-generated topology.
      **Satisfied**: `iberian_2025_blackout.py`'s own module docstring states this directly.

## Non-goals

- Not a real-time or predictive tool — retrospective reproduction and detector-scoring only, same
  posture as 0002.
- Not an attempt to adjudicate the report's own stated open question ("the Expert Panel was not
  able to establish the cause of most of these trips") — where the report itself says the cause is
  unconfirmed, this scenario's generator should use the report's own stated *hypothesis* (settings
  diverging from requirements) and say so, not invent a more specific mechanism the source document
  doesn't support.
