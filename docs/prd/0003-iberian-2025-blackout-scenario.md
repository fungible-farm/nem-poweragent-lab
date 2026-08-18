# 0003 — Iberian Peninsula 2025 blackout scenario

- **Status:** proposed
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

- [ ] **`PlantBehaviourGenerator`** (factors 1, 2, 4, 5, 6) — the scenario's dominant generator kind,
      reflecting that this event has no initiating fault at all; get these five continuous-behaviour
      models right before anything else, since they are what turns "operator action raised voltage
      a bit" into "cascade."
- [ ] **`ProtectionTripGenerator`** (factors 8, 9, 11) — overvoltage disconnection at the report's
      three documented waves (355 MW / 727 MW / 928 MW) with thresholds set from the report's own
      cited voltage levels (417.9 kV, ~432.4 kV) rather than invented round numbers.
- [ ] **`OperatorActionGenerator`** (factor 3) — the shunt-reactor/export-reduction/HVDC-mode-change
      actions, with the report's own stated latency ("typically less than 5 minutes," and critically
      **not completed in time** in the final episode) as the generator's latency parameter — this
      is the scenario's one deliberate near-miss/failure-mode to reproduce, not an idealised
      instant-response operator.
- [ ] **`IslandingProtectionGenerator`** — DRS out-of-step protection + ES-FR/ES-MA trips, condition
      grounded in the report's own angle-separation/loss-of-synchronism account.

### Detectors to validate against

- [ ] `OscillationDetector` — must recover both the 0.63 Hz (12:03–12:08) and 0.2 Hz (12:19–12:22)
      modes from the reconstructed phasor stream; this is the scenario's cleanest, most literal
      detector acceptance test since the report states both frequencies explicitly.
- [ ] `VoltageCascadeDetector` — reproduce the report's own Figure 1-8 relationship (cumulative
      generation-loss-plus-net-load-increase vs. 400 kV Carmona-substation voltage) and flag the
      accelerating cascade at or before the 12:33:16–12:33:18 wave.
- [ ] `RoCoFDetector` — flag the >1 Hz/s RoCoF excursion at/after 12:33:20.560, the report's own
      literal numeric threshold.
- [ ] `AngleSeparationDetector` — flag the widening ES/PT-vs-CESA angle difference before the
      12:33:19 loss-of-synchronism onset — the detector-side mirror of the
      `IslandingProtectionGenerator`'s trigger.
- [ ] `CascadingFailureClassifier` — composite score across all four, checked for lead time ahead of
      the 12:33:23.960 final collapse.

## Two-phase simulation approach

The precursor window (12:03–12:32:00, ~30 minutes of grid time) is a slow, quasi-static
oscillation-and-operator-response phenomenon — full 200 µs-class EMT solving for 30 minutes of
simulated time is not the right tool and 0001's "Open questions" already flags this trade-off.
Recommended split:

- [ ] **Precursor phase (12:03–12:32:00)**: `pandapower`-based quasi-static snapshots stepping
      through the oscillation episodes and operator actions, sufficient to produce the slowly
      rising voltage trend and the two named oscillation-mode signatures at the snapshot cadence
      `OscillationDetector` needs.
- [ ] **Collapse phase (12:32:00–12:33:23.960, ~84 s of grid time)**: full DPsim EMT solve at Lab
      5's existing 200 µs-class timestep, since this is exactly the sub-2-minute fast-dynamics
      window Lab 5's engine already targets, carrying the precursor phase's end-state as its
      initial condition.

## Where this lives

Proposed: `labs/05-spartan-chaosnet-transient-stream/scenarios/iberian_2025_blackout.py`, alongside
0002's SA scenario module, both built on 0001's shared `labs/_shared/scenario_engine/`.

## Acceptance criteria

- [ ] Both named oscillation modes (0.63 Hz, 0.2 Hz) reproduce within a stated frequency tolerance.
- [ ] The three documented overvoltage-trip waves (355 MW / 727 MW / 928 MW) reproduce in the
      correct order with cumulative loss reaching the report's own ">2.5 GW by 12:33:18.020" figure
      within a stated tolerance.
- [ ] RoCoF crosses the ±1 Hz/s threshold within a stated time tolerance of 12:33:20.560.
- [ ] `IslandingProtectionGenerator` fires (ES-FR/ES-MA separation) within a stated time tolerance
      of the 12:33:19–12:33:21.535 window.
- [ ] All four precursor detectors fire with a documented lead time ahead of their corresponding
      generator event, and the composite classifier's score crosses its alarm threshold before the
      scenario's own modelled 12:33:23.960 final collapse.
- [ ] Scenario's own README/module docstring states explicitly: this is **not** a claim of
      reproducing the real Spanish/Portuguese network's actual topology, generator fleet,
      protection settings, or SCADA data — the report itself states most underlying data was
      anonymised/aggregated by asset group for confidentiality (§ "Treatment of confidential
      information"), so no public source could grounds-truth that level of detail even in
      principle. This scenario is a structurally-faithful reproduction of the report's own named
      causal mechanism and published aggregate figures on a procedurally-generated topology.

## Non-goals

- Not a real-time or predictive tool — retrospective reproduction and detector-scoring only, same
  posture as 0002.
- Not an attempt to adjudicate the report's own stated open question ("the Expert Panel was not
  able to establish the cause of most of these trips") — where the report itself says the cause is
  unconfirmed, this scenario's generator should use the report's own stated *hypothesis* (settings
  diverging from requirements) and say so, not invent a more specific mechanism the source document
  doesn't support.
