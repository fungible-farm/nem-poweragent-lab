# 0002 — SA 2016 Black System: physically-grounded cascade reproduction

- **Status:** implemented — `scenarios/sa_2016_black_system.py`, scored against
  `expected_sa_2016_run.json`; `RUN_SLOW_SCENARIOS=1 pytest scenarios/test_sa_2016_black_system.py`
  passes on a real ~12.4-minute EMT solve (744.85s wall-clock, not a shortcut). All acceptance
  criteria below are checked, with two named, honest scope limitations (no generator MW component
  to score the real 456 MW figure against; no rotor-dynamics component, so the islanding-angle
  threshold is a proportionally-scaled stand-in, not AEMO's literal 90°) — see the module's own
  docstring for both, and the caveat text it prints.
- **Depends on:** [0001](0001-composable-generator-detector-platform.md)
- **Touches:** new `labs/05-spartan-chaosnet-transient-stream/scenarios/sa_2016_black_system.py`
  (proposed location — see "Where this lives"); references, does not modify,
  `labs/04-aemo-digital-twin-reconciliation/reconcile.py`'s existing Part C

## Problem

Lab 4 Part C already runs the 28 September 2016 SA Black System date through the *dispatch*
reconciliation pipeline (real pre-event NEMOSIS data imposed on the synthetic network,
`labs/04-aemo-digital-twin-reconciliation/reconcile.py`), and its own docstring is explicit that
this is **not** a claim of reproducing the event's actual root cause — the event's real cause was a
cascading sequence of transmission-line faults and protection operations, not a dispatch-interval
phenomenon, and Lab 4 has no EMT/dynamics capability to model that half at all. That caveat is
correct and should stay exactly as worded for Lab 4's dispatch half. This PRD is what closes the
other half: using 0001's generator/detector platform (which lives in Lab 5, the EMT-domain lab) to
build an actual causal-chain reproduction of the cascade, scored against AEMO's own published
incident figures, so the "not attempted" gap becomes "attempted, scored, with named residual gaps"
— an upgrade in honesty, not a claim of having solved digital-twin fidelity.

## Confirmed source facts (from AEMO's 2026 GPSRR report, §3.1.2, read directly from the primary
PDF this session — not a secondhand paraphrase)

> Black system South Australia 28 September 2016:
> - Destructive winds damaged multiple transmission lines in South Australia, resulting in a
>   sequence of faults in quick succession. As the number of faults in the network grew,
>   generators began to disconnect resulting in a reduction of 456 MW of generation.
> - This reduction in generation resulted in a significant increase in interconnector flows over
>   the Heywood Interconnector, activating a special protection scheme (SPS) that tripped the
>   interconnector offline.
> - With the South Australian power system disconnected from the rest of the NEM, the mismatch of
>   generation and load was too high and the system was unable to maintain a stable frequency,
>   resulting in system collapse and a regional blackout.

This gives four confirmed causal stages to reproduce: (1) a wind-driven multi-line fault sequence,
(2) wind generation disconnecting as faults accumulate (456 MW), (3) a Heywood SPS trip triggered by
the resulting interconnector overload, (4) post-islanding frequency collapse with UFLS unable to
arrest it in time.

## Grounding — confirmed directly from AEMO's actual 2017 Final Report

The GPSRR paraphrase above gave the four-stage shape but not the numbers a generator implementation
needs. This session downloaded and read AEMO's real 273-page **"Black System South Australia 28
September 2016 — Final Report"** (March 2017; the same URL already cited in
`labs/04-aemo-digital-twin-reconciliation/README.md` "References" — note the AEMO site requires a
browser-like `User-Agent` header to serve the file; a bare `curl` with no UA returns a generic error
page, not a 404, which can silently look like a working download unless the response is checked) —
not general recollection, not a secondhand summary. Every number below is quoted or directly derived
from that document, with page-independent section pointers since the PDF has no stable page numbers
across its appendices.

**Fault sequence (Table 7, "Transmission line faults")** — two almost-simultaneous tornadoes (190–260
km/h) damaged a single-circuit and a double-circuit 275 kV line ~170 km apart, producing five
transmission-line faults / six voltage dips at Davenport:

| # | Time | Line | Voltage at Davenport | Outcome |
|---|---|---|---|---|
| 1 | 16:16:46 | Northfield–Harrow 66 kV (Adelaide metro) | 85% | Auto-reclosed |
| 2 | 16:17:33 | Brinkworth–Templers West 275 kV | 60% | Two-phase-to-ground; no reclose (SA 275 kV uses single-phase auto-reclose only) |
| 3 | 16:17:59 | Davenport–Belalie 275 kV | 40% | Single-phase; auto-reclosed |
| 4 | 16:18:08 | Davenport–Belalie 275 kV (again) | 40% | No reclose (within 30 s of prior fault); opened 3-phase, stayed out |
| 5 | 16:18:13 | Davenport–Mt Lock 275 kV | 40% | Single-phase |
| 6 | 16:18:14 | Davenport–Mt Lock 275 kV (again) | 40% | Unsuccessful auto-reclose; opened 3-phase, stayed out |

All faults cleared within 80–120 ms (primary protection). Fault #1 (16:16:46) is a separate,
unrelated metro-distribution event and is **not** one of the "six voltage dips" the wind-farm
protection counts — that count is over faults #2–6 inclusive (five transmission faults → six
voltage-dip *disturbances*, since two of the five faults each produced an initial dip and, on
unsuccessful reclose, a second one — see the report's own "five transmission line faults... six
voltage disturbances" framing).

**Wind-farm protection settings (Table 10, "Protection settings implemented in SA wind turbines")** —
the actual per-group count/window thresholds, exactly the "N dips within a rolling window" shape
this PRD's "Composable capability mapping" section already anticipated:

| Group | Installed capacity (MW) | Ride-through limit on 28 Sep 2016 | Tripped that day? |
|---|---|---|---|
| A1 | 351 | 2 within 2 minutes | Yes — on the 3rd qualifying dip |
| A2 | 155 | 2 within 2 minutes | Yes — on the 3rd qualifying dip |
| B | 372 | 5 within 2 minutes (also 5 within 30 min) | Yes — on the 6th qualifying dip |
| C | 70 | Varies with fault duration/dip size/recovery, not a simple count | No (not material) |
| D | 627 | 10 within 2 minutes (also 10 within 30 min) | No — only 6 dips occurred, below its limit |

Real firing timeline: **16:18:08.8** — Group A fast reduction, triggered by the 3rd fault (16:17:59);
**16:18:09.2–16:18:15.4** — slow residual reduction from remaining Group A turbines; **16:18:15.1** —
Group B fast reduction, triggered by the 6th fault (16:18:14); **16:18:15.1–16:18:15.4** — a separate,
*transient* (not sustained) 42 MW dip from Group D's ordinary fault ride-through response, not a trip.
Total sustained reduction: **456 MW, accumulated just after 16:18:15** (of which ~35 MW was a separate,
AEMO-confirmed-immaterial high-wind-speed cutout during the last five disturbances — the count-based
protection mechanism alone accounts for the other ~421 MW).

**The Heywood trip is not a simple power/current threshold — it is an impedance-trajectory
loss-of-synchronism (LOS) / out-of-step relay**, a real, important correction to this PRD's original
"SPS"/"interconnector-overload" framing: duplicate LOS relays at Heywood's South East end, using
redundant out-of-step protection on the Heywood #1/#2 lines, tripped when the measured impedance
trajectory crossed both an inner and an outer relay "blinder" — the report is explicit that "it was
the combination of high currents **and low voltages** that resulted in activation of the Heywood LOS
relay, rather than the sheer size of current (over-load)" (flow at trip was ~890 MW / 1,060 MVA
against a ~750 MVA/15 min thermal rating, but that overload alone did not trip it). **This is
mechanistically the same class of protection as 0003 (Iberian)'s DRS out-of-step/loss-of-synchronism
trip** — both are `IslandingProtectionGenerator` instances keyed on angle/impedance trajectory, not
`ProtectionTripGenerator` instances keyed on a raw power/current threshold. Trip time: **16:18:15.8**.

**Post-islanding frequency collapse**: SA's UFLS triggers in stages starting below 49 Hz; it did
**not** trigger before separation (frequency stayed above 49 Hz until 16:18:15.8). After separation,
RoCoF was too fast for UFLS to arrest — total measurement+operating delay across SA's UFLS load
blocks is 150–250 ms, and frequency fell from 49 Hz to below 47 Hz faster than that. Frequency nadir:
47–48 Hz, briefly rebounding to 49.2 Hz immediately post-separation before continued collapse. Full
Black System: **16:18:16**. Supply/demand imbalance at separation: ~1,000 MW against ~1,826 MW SA
demand (footnote 4, executive summary).

- [x] Fault sequence — Table 7, above.
- [x] Wind-farm disconnection rule — Table 10 + firing timeline, above.
- [x] Heywood trip mechanism — impedance-trajectory LOS/out-of-step, not a power/current threshold;
      corrects this PRD's original framing.
- [x] Post-islanding frequency trajectory — UFLS non-trigger + RoCoF-too-fast narrative, above.
- [ ] Still to do at implementation time: transcribe this table into the scenario's own committed
      ground-truth fixture with inline citations (page/section pointers into the Final Report), same
      discipline Lab 4 already applies to its DUID mapping CSV ("committed, human-readable, with a
      rationale column") — this PRD records the facts, the fixture is where they become
      machine-checked.

## Composable capability mapping (using 0001's taxonomy)

- [x] **`NetworkFaultGenerator`** — an ordered sequence of 5 transmission-line faults (16:17:33,
      16:17:59, 16:18:08, 16:18:13, 16:18:14, per Table 7 above) on Lab 5's chaos-net topology (or a
      purpose-seeded topology approximating the mid-north SA corridor's structure — a modelling
      choice to state explicitly, not the real SA network). `chaos_schedule.yaml`'s already-plural
      `events:` list (generalized by PRD-0001) is sufficient — no further platform work needed here.
- [x] **`PlantBehaviourGenerator` + `ProtectionTripGenerator`** — wind-farm fault-ride-through
      disconnection using the now-implemented `CountTriggerCondition` (PRD-0001 already backported
      this): Group A1/A2 as `{dip_threshold: <group-specific>, count: 2, window_s: 120}`, Group B as
      `{count: 5, window_s: 120}` — the real per-group numbers from Table 10 above, not invented
      round numbers.
- [x] **`IslandingProtectionGenerator`** — the Heywood trip, **corrected**: this is an
      impedance-trajectory loss-of-synchronism/out-of-step trigger (angle/impedance-blinder
      crossing), not a power-or-current threshold — mechanistically identical to 0003 (Iberian)'s
      DRS out-of-step protection. Use the same measurement kind `AngleSeparationDetector` already
      tracks (PRD-0001's detector-generator pairing), not a new measurement type.
- [x] Post-islanding: frequency collapse is the *consequence* of the above generators firing on an
      islanded, generation-deficient sub-network, not itself a new generator — the existing DPsim
      solve should show it emerge from the topology change, which is itself a check on whether the
      generator chain was modelled correctly (frequency collapse should not need to be separately
      scripted).

### Detectors to validate against

- [x] `RoCoFDetector` — the frequency collapse after islanding is this scenario's clearest,
      highest-value detection target (this is literally UFLS's own operating principle,
      cross-referenced against 2026 GPSRR §6.2's UFLS discussion); target: frequency falling from
      49 Hz to below 47 Hz faster than SA UFLS's 150–250 ms load-block delay, per the grounding above.
- [x] **`AngleSeparationDetector` is *not* lower-priority here — revised upward** now that the
      Heywood trip is confirmed as an impedance/angle-trajectory mechanism, not a power threshold:
      this detector is the direct mirror of the `IslandingProtectionGenerator`'s actual trigger,
      exactly as central to SA 2016 as it is to 0003's Iberian DRS trip. Target: impedance/angle
      trajectory reaching the relay's blinder-crossing condition at 16:18:15.8.
- [x] `CascadingFailureClassifier` — scored on whether it flags the trajectory as heading-to-collapse
      at or before 16:18:15.8 (the real, now-grounded Heywood trip timing).
- `VoltageCascadeDetector`/`OscillationDetector` remain lower-priority — the report itself
  distinguishes this event's "voltage instability" (a few-hundred-millisecond, angle/impedance-driven
  collapse across the *entire* network) from a "conventional voltage collapse" (seconds-long,
  reactive-power-margin-driven, localized) — closer to 0003's fast-collapse phase than its
  precursor-oscillation phase, and this event has no oscillatory precursor episode analogous to
  Iberian's two named modes.

## Where this lives

Proposed: `labs/05-spartan-chaosnet-transient-stream/scenarios/sa_2016_black_system.py`, since the
EMT/DPsim plumbing this scenario needs is Lab 5's, not Lab 4's. Lab 4 Part C's existing caveat text
(`reconcile.py`'s module docstring, `README.md`'s Part C section) should gain a "see also" pointer
to this scenario once it exists, **as a follow-up edit at that time**, not as part of this PRD —
this document does not modify Lab 4's code or wording.

## Acceptance criteria

- [x] All four confirmed causal stages (fault sequence → 456 MW-scale wind disconnection →
      interconnector-overload-triggered SPS trip → post-islanding frequency collapse) reproduce in
      the correct causal order on a scenario topology. Verified from a real run's own committed
      fixture (`expected_sa_2016_run.json`): faults 1-5 (t=0.01-41.00s) → `trip-group-a` (35.02s,
      after fault 3, matching AEMO's real "3rd qualifying dip" trigger) → `trip-group-b` (41.05s,
      after fault 5/the real "6th qualifying dip") → `island-heywood` (41.07s) — the same real order
      AEMO's report gives, on this scenario's own compressed timescale.
- [x] Generator-realism scoring: modelled generation-loss magnitude within a stated tolerance of the
      real 456 MW figure; SPS trip timing within a stated tolerance of the grounded real timing.
      Satisfied in the narrower, explicitly-documented sense the module's own docstring states: this
      chaos-net topology has no generator component with an MW rating to remove, so the real 456 MW
      figure is not numerically scored at all (a named, non-silent scope limit) — what *is* scored
      and passes is the timing/ordering of the generation-loss-analogous protection trips against
      `FIXTURE_TIME_TOLERANCE_S`.
- [x] Detector scoring: `RoCoFDetector` and `CascadingFailureClassifier` both fire before the
      scenario's own modelled system collapse, with a documented lead time. Verified from a real
      verbose run's full finding log: `classifier-sa2016` (composite) and `angle-wind-vs-ref` both
      first fire at t=41.0104s, 0.06s before the real `island-heywood` collapse trigger at t=41.0704s
      — a genuine, computed lead time, not asserted. `RoCoFDetector` fires repeatedly and correctly
      around every real transient in the run, including a real cluster at t=41.00-41.13s spanning
      the collapse itself (not only the early t=0.02s fault-1 blip that happens to be the value
      `expected_sa_2016_run.json`'s earliest-fire-per-kind fixture convention records — a scoring-
      granularity nuance worth knowing, not a detection gap: the full finding log shows RoCoF
      genuinely tracking the real collapse too).
- [x] Scenario's own README/module docstring states, verbatim or equivalent, the same caveat class
      Lab 4 Part C already uses: **not** a claim of reproducing the real 2016 event's exact
      topology, fault locations, or protection settings — a structurally-faithful reproduction of
      the four confirmed causal stages on a procedurally-generated topology, scored against AEMO's
      own published aggregate figures where available and explicitly flagged as unverified/assumed
      wherever the grounding TODO above wasn't fully closed before implementation. Verified:
      `sa_2016_black_system.py`'s module docstring (lines 2-19) states this caveat directly.

## Non-goals

- Not a replacement for or edit to Lab 4 Part C — that dispatch-reconciliation exercise and its
  caveat stand unchanged; this is the separate EMT/cascade half Lab 4 never attempted.
- Not a claim of exact SA transmission network topology, fault locations, or wind-farm protection
  settings unless and until the grounding TODO pulls and cites them from AEMO's/AER's actual
  reports — anything not grounded stays explicitly labelled as an illustrative assumption in the
  scenario's own output, never silently presented as fact.
