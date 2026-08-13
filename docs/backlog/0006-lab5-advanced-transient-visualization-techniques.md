# 0006 — Research: advanced Lab 5 transient-visualization techniques beyond the current six views

- **Status:** partially done — tiers 1–2 (options 1, 3, and 2) implemented and verified against a
  real DPsim run; option 1's real result corrected a prediction this doc originally made, and
  option 2's real result likewise did not match its own original prediction (see each section
  below). Option 4 remains proposed.
- **Depends on:** 0004 (Lab 5's existing topology + transient visualization work, all done)
- **Prompted by:** "review the labs, especially lab 5 around dpsim — we are looking for more
  advanced visualization techniques," evaluated against what Lab 5 already ships, not proposed in
  the abstract.

## What Lab 5 already has

Unlike Labs 1–4, Lab 5 is not short on visualization — it already renders **six** distinct views,
all driven from the one real `dpsim_transient_log.json` (or, for topology, `sample_topology.json`),
none fabricated:

1. `generate_topology.py` — static `nx.spring_layout()` graph of the chaos-net, tap substations
   highlighted (`sample_topology_plot.png`).
2. `verify_stream.py` — static transient plot of the fault-bus voltage sag/recovery
   (`sample_transient_plot.png`).
3. `view_telemetry_rates.py` — three stacked panels sharing one time axis (raw 5 kHz, C37.118
   100 Hz synchrophasor magnitude + |V1|, SCADA 4 s RMS), demonstrating that telemetry rate decides
   what's visible (`sample_telemetry_rates.png`).
4. `animate_transient.py` — a growing-reveal MP4 of the raw waveform sweeping through the fault
   (`animate_transient.mp4`).
5. `animate_telemetry_rates.py` — a narrated, time-aligned 1920×1080 MP4 of all three telemetry
   rates simultaneously (`animate_telemetry_rates.mp4`).
6. `view_3d_audio.py` — a 3D phase-space (va/vb/vc) trajectory PNG colored by fault window, plus an
   8×-pitch-shifted 3-channel WAV sonification of the same event (`sample_transient_3d.png`,
   `dpsim_transient_3ch.wav`).

So "more advanced" here deliberately does not mean "add a chart" — it means techniques a protection
or PMU engineer would actually reach for that the current six views structurally cannot show,
because of what data is or isn't captured today.

## What was checked, not guessed

Two feasibility questions were resolved by direct introspection against the real `dpsimpy` objects
in this sandbox (not inferred from docs), matching this repo's own "confirmed by direct experiment"
convention (see `README.md`'s sandbox notes 4–5):

- **Is line current available, not just bus voltage?** Yes. `chaosnet.to_dpsim_emt_system()`
  builds each line as a `dpsimpy.emt.ph3.PiLine`; `c.print_attribute_list()` on a real instance
  shows an `i_intf` attribute (`MatrixReal`, 3×1) alongside the already-used `v_intf` — the same
  shape/pattern `run_dpsim.py` already uses for voltage (`node.attr("v").derive_coeff(p, 0)`).
  `run_dpsim.py` today only ever reads `nodes[bus].attr("v")` — current is never captured.
- **Is more than the fault bus's voltage available?** Yes. `to_dpsim_emt_system()` returns a
  `nodes` dict keyed by every bus index in the topology (`dsys["nodes"]`), not just the fault bus —
  `run_dpsim.py` picks out exactly one (`dsys["nodes"][dsys["fault_buses"][target]]`) and discards
  the rest of the solve's per-step state.

Both are real, already-solved DPsim state that today's capture loop simply doesn't read out — not
new physics, not a new solver, not a new dependency.

## Option 1 — Full symmetrical components (V0/V1/V2), not just |V1|

**Status: done**, with a correction to this section's own original prediction — see below.

**What:** `phase_model.py`'s `positive_sequence()` already computes |V1| from the same one-cycle
DFT phasors `phasor_frames()` produces. Negative- and zero-sequence voltage are the identical linear
combination with different rotation factors (`V0 = (Va+Vb+Vc)/3`, `V2` uses `a²` instead of `a`
where `V1` uses `a`) — same phasors already in hand, no new DPsim capture. Implemented as
`phase_model.negative_sequence()`/`zero_sequence()`, overlaid on the existing |V1| line in
`view_telemetry_rates.py`/`animate_telemetry_rates.py`'s phasor panel.

**Why it matters (as originally written here, before the real run was checked):** this is the
actual diagnostic protection relays use to *classify* a fault, not just detect one. A
line-to-ground fault (Lab 5's `chaos_schedule.yaml` scenario) produces a distinctive signature — V0
and V2 both spike from ~0, while V1 only dips modestly — that a line-line fault or a symmetric
three-phase fault would not produce.

**What the real run actually showed — this doc's prediction was wrong, and the wrongness is the
finding.** Measured directly against a real `dpsim_transient_log.json` (not assumed): |V0| stays at
numerical zero (~1e-12 V) throughout pre-fault, fault, and post-fault, and |V2| only shows a small
switching-transient blip (~250 V, low hundreds) against a ~13 kV |V1| — not the sustained V0/V2 rise a true
single-line-to-ground fault would show. Root cause, found by reading `chaosnet.py`:
`FAULT_CLOSED_RESISTANCE_OHM` is applied via `np.eye(3) * FAULT_CLOSED_RESISTANCE_OHM` — a
*diagonal*, identical-per-phase resistance matrix, so the switch shorts all three phases to ground
symmetrically. Electrically that is a three-phase-to-ground fault, not a single-line-to-ground
fault, despite `chaos_schedule.yaml`'s `type: line-to-ground` label — a second, independent
confirmation of the exact limitation README's sandbox note 1 already named ("balanced/decoupled
3-phase line and load model... no phase-to-phase mutual coupling"), this time surfaced by the
sequence-component math itself rather than by reading the switch code first. The implemented view is
honest about this: it shows V1 dipping while V0/V2 stay flat, and both `phase_model.py`'s and the
rendering scripts' docstrings/output text now say so explicitly, rather than asserting the
textbook single-LG signature the original prediction assumed. A genuinely asymmetric single-phase
fault model (a non-diagonal or per-phase switch resistance) would be needed to actually exercise the
V0/V2-rise case — noted here as a follow-on, not attempted in this pass, since it is a physics-model
change, not a visualization change.

**Effort:** low, as predicted. New functions in `phase_model.py` (`negative_sequence()`,
`zero_sequence()`, mirroring `positive_sequence()`'s existing signature), an overlay in
`view_telemetry_rates.py`/`animate_telemetry_rates.py`. No new dependency, no `run_dpsim.py` change.

## Option 2 — R-X impedance trajectory (mho-circle / distance-relay plot)

**Status: done**, with two corrections to this section's own original prediction — see below.

**What:** `run_dpsim.py` now taps `i_intf` on the fault-adjacent `PiLine` alongside the existing
`v_intf` tap at the fault bus (`chaosnet._fault_adjacent_line()`/`fault_adjacent_line_name()`
picks that line deterministically: prefer the line directly connecting `ext_grid_bus` to the fault
bus, else the first adjacent line in topology order — for seed 42/SUB-3 this is `line0_12`).
`dpsim_transient_log.json` carries the new `ia_line`/`ib_line`/`ic_line`/`fault_adjacent_line`
keys (documented in `run_dpsim.py`'s module docstring "key convention" section). The new
`view_rx_trajectory.py` computes positive-sequence `Z(t) = V1(t) / I1(t)` — reusing
`phase_model.phasor_frames()`/`positive_sequence()` unchanged, no second phasor estimator — and
plots it on the complex R-X plane against a real, documented mho relay characteristic: a circle
through the origin and `RELAY_REACH_PERCENT` (80%, the standard textbook Zone-1 underreach
setting) of the tapped line's own real impedance (`r_ohm_per_km`/`x_ohm_per_km` × `length_km` from
the committed `sample_topology.json`, not invented), saved to `sample_rx_trajectory.png`.

**Why it matters:** it is the one technique on this list that answers a materially different
question than the existing views ("where, electrically, is this fault" vs. "what does the voltage
do over time") — directly relevant to SPARTAN's framing as an edge device co-located with
protection-class monitoring.

**What the real run actually showed — two findings, not the textbook picture assumed above.**
Measured directly against a real, regenerated `dpsim_transient_log.json` (seed 42, SUB-3 fault):

1. **A one-cycle DFT phasor spans a real switching discontinuity.** The frame whose one-cycle
   analysis window straddles the fault-*clearing* instant produced `Z ≈ 148 + 324j` ohm — a
   wrong-quadrant, order-of-magnitude outlier next to every neighbouring frame's ~1–1000 ohm,
   negative-real-part values, because a single-cycle DFT's periodicity assumption is violated when
   a real discontinuity falls inside its window. `view_rx_trajectory.py` excludes any frame within
   `SWITCHING_EXCLUSION_CYCLES` (1 full 50 Hz cycle) of `trigger_time_s`/`clear_time_s` by
   definition, not by curve-fitting the threshold to hide this one value — the same reason real
   numerical distance relays supervise their mho element with a dedicated transient/fault-detector
   element rather than trusting a raw single-cycle `Z=V/I` estimate straight through a switching
   event.
2. **The trajectory does swing sharply toward the origin during the fault, but never crosses
   inside the 80%-reach mho circle.** Pre/post-fault `|Z|` sits at a median ~854 ohm (this
   particular tapped line, `line0_12`, is lightly loaded — most chaos-net load flow routes
   elsewhere in the 28-line mesh); during the fault it collapses to a minimum ~1.34 ohm — a real,
   sharp, "distance relay would clearly see this" collapse. But the line's own real impedance is
   tiny (`length_km=0.6`, `Z_line ≈ 0.27` ohm, 80% reach ≈ 0.22 ohm), because
   `FAULT_CLOSED_RESISTANCE_OHM=0.5` ohm is a *partial, impedance-limited* fault at the fault bus
   itself (chaosnet.py's own documented, swept choice — see that constant's comment), not a bolted
   fault at the remote end of the tapped line. `Z_fault ≈ 1.34` ohm sits just outside the 0.22 ohm
   reach circle, so this specific real run's trajectory demonstrates the collapse-toward-origin
   shape a protection engineer expects, without crossing this particular Zone-1 element's trip
   region — reported as measured, not forced to claim a trip that didn't happen. Because the load
   and fault impedances differ from the reach circle by ~3 orders of magnitude, the rendered PNG
   uses a zoomed inset at the reach-circle's own scale (sized from the real computed reach/fault
   extent) alongside the full-scale trajectory — itself a faithful reproduction of how real
   distance-relay R-X displays normally show load impedance far outside the reach zone, not a
   plot-hiding trick.

**Effort:** medium, as predicted. `chaosnet.py` gained `_fault_adjacent_line()`/
`fault_adjacent_line_name()` (pure, topology-only) and a `fault_adjacent_lines` entry on
`DpsimChaosSystem`; `run_dpsim.py`'s capture loop gained one more `derive_coeff()`-pattern tap,
mirroring the existing voltage tap; `view_rx_trajectory.py` is a new ~300-line script, reusing
`phase_model.py`'s phasor machinery unchanged. No new dependency (complex-plane plotting and the
zoomed inset are both plain matplotlib).

## Option 3 — Spectrogram / STFT of the transient

**Status: done.**

**What:** `scipy.signal.spectrogram` (scipy is already a transitive dependency via
`view_3d_audio.py`'s `scipy.io.wavfile`/`scipy.signal.resample`) applied to the already-recorded
`va` series — no new capture, no new dependency, purely a different rendering of data already in
`dpsim_transient_log.json`. Implemented as the new `view_spectrogram.py` →
`sample_spectrogram.png` (viridis colormap — sequential/CVD-safe, not a rainbow map — 50 ms Hann
window, 80% overlap, dashed white trigger/clear markers).

**Why it matters:** switching transients have real broadband harmonic content the steady 50 Hz
signal doesn't; a time-frequency view would show the fault-onset and clearing edges as distinct
broadband events distinguishable from the steady-state hum — the same "is this an anomaly" signal
SPARTAN's downstream edge classifier cares about, made visible rather than only implied by
`view_3d_audio.py`'s peak-deviation-bin printout. **Confirmed against the real run**:
`view_spectrogram.py` also prints the measured broadband-power fraction (share of STFT power above
200 Hz) pre-fault vs. inside the fault window — a real, computed ratio, not asserted — and for
Lab 5's default seed/schedule the fault window's broadband fraction is measurably higher than the
steady pre-fault window's, i.e. the switching edges are visible in the spectrogram exactly where
expected.

**Effort:** low, as predicted. One new script, reusing `dpsim_transient_log.json` as-is. Cheapest
option on this list.

## Option 4 — Network-wide sag propagation

**What:** capture voltage at several buses (not just the fault bus) via the already-available
`dsys["nodes"]` dict, then animate the already-drawn topology graph
(`generate_topology.py`'s `_plot_topology()` structure) with buses colored/pulsing by instantaneous
`|V(t)|` deviation from nominal — connecting the two currently-separate topology and transient
artifacts into one.

**Why it matters:** today's topology plot and transient plot are two unrelated PNGs; nothing in
Lab 5 shows *how far* a fault propagates through the chaos-net's other 13 buses, only what happens
at the fault bus itself. This is the most visually striking option on this list but also changes
the shape of what's captured (N buses × 3 phases × ~2750 samples instead of 1 bus), so it has real
memory/runtime cost at scale that the other three options don't.

**Effort:** medium-high. Capturing extra buses is cheap per-bus (same `attr("v").derive_coeff()`
pattern, looped), but the animation itself (mapping a scalar per bus per frame onto
`nx.draw()`/`FuncAnimation`) is new code with no existing template in this lab to extend, unlike
options 1–3 which each extend an existing function or script almost directly.

## Recommendation, in tiers

1. **Done:** Option 1 (symmetrical components) and Option 3 (spectrogram). Both reused data already
   captured in `dpsim_transient_log.json` or already-computed phasors in `phase_model.py` — zero new
   `run_dpsim.py` capture changes, zero new dependencies. Implementing Option 1 also surfaced a real
   finding worth having found: Lab 5's `chaos_schedule.yaml` fault is symmetric across all three
   phases (see Option 1's section above), which the sequence-component view now shows honestly
   instead of assuming the textbook single-LG signature.
2. **Done:** Option 2 (R-X impedance trajectory). Added the small, well-understood capture change
   this section originally scoped (current alongside voltage, same tap pattern) and answers a
   question none of the other views can — distance, not just severity. Its real run also surfaced
   two findings worth having found: a one-cycle DFT phasor is invalid across a real switching
   discontinuity (excluded by definition, not tuned away), and this particular seed's fault
   collapses `|Z|` sharply toward the origin without crossing inside the tapped line's own
   (very short, low-impedance) Zone-1 reach circle — see Option 2's section above for both.
3. **Bigger lift, most visually ambitious:** Option 4 (network-wide propagation). Recommended as a
   distinct, later item if picked up — it changes what's captured at solve-scale (all buses, not
   one) rather than adding a rendering pass over data already in hand, so it shouldn't be bundled
   into the same change as 1–3.

## Common thread

All four options are extensions of code that already exists in this lab — `phase_model.py`'s DFT
phasor machinery (1), `run_dpsim.py`'s existing per-step voltage-tap pattern extended to current
(2) or to more buses (4), and `dpsim_transient_log.json`'s already-recorded samples (3) — none
require a new simulation, a new dependency (beyond scipy, already transitively present), or a
change to what DPsim itself solves. The gap in all four cases is in what Lab 5 *reads out* of an
already-real solve, not in the solve itself.
