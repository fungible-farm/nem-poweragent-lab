# 0002 — SA 2016 Black System: physically-grounded cascade reproduction

- **Status:** proposed
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

## Required grounding TODO before implementing thresholds

The GPSRR paraphrase above is confirmed and sufficient for the four-stage shape, but does **not**
give the numbers a generator implementation needs: the exact fault count/timing/locations, the wind
farms' actual fault-ride-through disconnection rule (commonly summarised in public commentary as a
voltage-dip-count-based protection setting, but not verified against a primary source in this
session), the Heywood SPS's actual trigger condition, and the UFLS stage timing. AEMO's own 2017
integrated final report (already linked in `labs/04-aemo-digital-twin-reconciliation/README.md`
"References") and the AER investigation report (also already linked there) are the primary sources
to pull these from. **Do not hand-wave these numbers from general recollection** — this scenario's
entire value is being scored against real figures; an unverified threshold defeats the purpose.

- [ ] Pull the fault sequence (count, approximate locations/timing) from AEMO's 2017 report.
- [ ] Pull the wind farms' actual disconnection rule that produced the 456 MW loss (protection
      setting basis, not assumed).
- [ ] Pull the Heywood SPS's actual trigger condition/setting.
- [ ] Pull the post-islanding frequency trajectory and UFLS stage activations (timing, MW shed per
      stage) up to system collapse.
- [ ] Record each pulled figure with its citation directly in the scenario's ground-truth fixture
      (not just in this PRD) — same discipline Lab 4 already applies to its DUID mapping CSV
      ("committed, human-readable, with a rationale column").

## Composable capability mapping (using 0001's taxonomy)

- [ ] **`NetworkFaultGenerator`** — an ordered sequence of transmission-line faults on Lab 5's
      chaos-net topology (or a purpose-seeded topology approximating the mid-north SA transmission
      corridor's structure — a modelling choice to state explicitly, not the real SA network),
      timed per the grounding TODO's pulled sequence.
- [ ] **`PlantBehaviourGenerator` + `ProtectionTripGenerator`** — wind-farm fault-ride-through
      disconnection: this needs one platform capability 0001 doesn't name yet — a **counting**
      trigger condition ("N qualifying voltage dips within a rolling window," not a single
      threshold-sustained-for-a-duration condition). Add this as a `ProtectionTripGenerator`
      variant (`trigger_condition: {measurement, dip_threshold, count, window_s}`) rather than a
      new generator kind, and backport it to 0001's schema once specified here.
- [ ] **`IslandingProtectionGenerator`** — the Heywood SPS trip, conditioned on the grounded
      trigger (rate-of-change-of-power/overload, per the grounding TODO — not assumed).
- [ ] Post-islanding: frequency collapse is the *consequence* of the above generators firing on an
      islanded, generation-deficient sub-network, not itself a new generator — the existing DPsim
      solve should show it emerge from the topology change, which is itself a check on whether the
      generator chain was modelled correctly (frequency collapse should not need to be separately
      scripted).

### Detectors to validate against

- [ ] `RoCoFDetector` — the frequency collapse after islanding is this scenario's clearest,
      highest-value detection target (this is literally UFLS's own operating principle,
      cross-referenced against 2026 GPSRR §6.2's UFLS discussion).
- [ ] `CascadingFailureClassifier` — scored on whether it flags the trajectory as
      heading-to-collapse at or before the real Heywood SPS trip's timing (once grounded).
- `VoltageCascadeDetector`/`OscillationDetector`/`AngleSeparationDetector` are lower-priority here
  — SA 2016's own account (per the confirmed GPSRR summary) is a frequency/interconnector-overload
  mechanism, not a voltage-control/oscillation one (contrast with 0003's Iberian scenario, where
  those three are central) — include them only if the grounding TODO surfaces a specific voltage
  precursor worth checking.

## Where this lives

Proposed: `labs/05-spartan-chaosnet-transient-stream/scenarios/sa_2016_black_system.py`, since the
EMT/DPsim plumbing this scenario needs is Lab 5's, not Lab 4's. Lab 4 Part C's existing caveat text
(`reconcile.py`'s module docstring, `README.md`'s Part C section) should gain a "see also" pointer
to this scenario once it exists, **as a follow-up edit at that time**, not as part of this PRD —
this document does not modify Lab 4's code or wording.

## Acceptance criteria

- [ ] All four confirmed causal stages (fault sequence → 456 MW-scale wind disconnection →
      interconnector-overload-triggered SPS trip → post-islanding frequency collapse) reproduce in
      the correct causal order on a scenario topology.
- [ ] Generator-realism scoring: modelled generation-loss magnitude within a stated tolerance of the
      real 456 MW figure; SPS trip timing within a stated tolerance of the grounded real timing.
- [ ] Detector scoring: `RoCoFDetector` and `CascadingFailureClassifier` both fire before the
      scenario's own modelled system collapse, with a documented lead time.
- [ ] Scenario's own README/module docstring states, verbatim or equivalent, the same caveat class
      Lab 4 Part C already uses: **not** a claim of reproducing the real 2016 event's exact
      topology, fault locations, or protection settings — a structurally-faithful reproduction of
      the four confirmed causal stages on a procedurally-generated topology, scored against AEMO's
      own published aggregate figures where available and explicitly flagged as unverified/assumed
      wherever the grounding TODO above wasn't fully closed before implementation.

## Non-goals

- Not a replacement for or edit to Lab 4 Part C — that dispatch-reconciliation exercise and its
  caveat stand unchanged; this is the separate EMT/cascade half Lab 4 never attempted.
- Not a claim of exact SA transmission network topology, fault locations, or wind-farm protection
  settings unless and until the grounding TODO pulls and cites them from AEMO's/AER's actual
  reports — anything not grounded stays explicitly labelled as an illustrative assumption in the
  scenario's own output, never silently presented as fact.
