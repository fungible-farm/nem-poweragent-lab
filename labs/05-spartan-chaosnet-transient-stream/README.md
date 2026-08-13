# Lab 5 — SPARTAN Chaos-Net: Transient Streams via DPsim + VILLASnode

> Status: **implemented** (laptop-portable core Definition of Done). Full concept, architecture,
> and the split Definition of Done live in
> [`docs/LAB5_SPARTAN_CHAOSNET.md`](../../docs/LAB5_SPARTAN_CHAOSNET.md). This README is the
> lab-local summary plus the sandbox-specific findings from actually building it.

## What you'll do (summary)

- Procedurally generate a new "chaos-net" grid topology each run: a real SimBench seed grid
  (`1-MV-rural--0-sw`) restructured by a NetworkX Watts-Strogatz graph perturbation, checked with a
  real `pandapower.runpp()`.
- Run a real network-wide EMT-domain transient solve in
  [DPsim](https://github.com/sogno-platform/dpsim) at a 200µs timestep, driven by a scheduled fault
  file (`chaos_schedule.yaml`) that counts down before the fault fires — a real
  `dpsimpy.event.SwitchEvent3Ph`, not a sleep-and-print.
- Stream the fault substation's voltage/current samples out via a real, running
  [VILLASnode](https://github.com/VILLASframework/node) pod (`podman kube play
  kube/villasnode-tap-pod.yaml`), verified by a real UDP capture in `verify_stream.py`.

**Definition of Done is split**: the full pipeline here runs on a laptop with no physical
hardware (a stub UDP receiver stands in for SPARTAN's data recorder). Validation against a real
Radxa Dragon Q8B is a separate, optional, hardware-gated extension — **not attempted here**, see
the design doc for why.

**Two things this lab does not claim**: it does not implement or reproduce SPARTAN's
anomaly-detection logic — that is explicitly a subsequent phase, out of scope here. It also does
not claim any of the generated "chaos-net" topologies correspond to a real substation network —
they are procedurally generated stress scenarios, not a model of any specific real asset.

## Why an AEMO modeller should care

Every other lab in this repo works at the dispatch-interval timescale. This one is the waveform
timescale — the level actual protection and PMU-based monitoring systems operate at — and it shows
the same "deterministic scripting" discipline (a readable fault schedule, not a random crash;
composed, not hand-built, tooling) applied to generating labeled stress-test data for an edge
anomaly detector, rather than to an LLM-agent workflow.

## SPARTAN's corrective-action half: the grid-forming stabilizer (PRD-0005 Phase 1)

Every other view in this lab implements the "classify/log/alert" half of SPARTAN's own stated
design (a micro-PMU-based distributed emergency response coordinator). `grid_forming.py`
(`docs/prd/0005-grid-forming-stabilizer-and-renewable-models.md` Phase 1) is the other half: it
actively injects a compensating voltage at the fault bus and measures, for real, whether it helps.

**Honest scope**: this is the conventional VSM/PID fallback the PRD explicitly allows, not the
Negative-Imaginary (NI) systems-theoretic controller it names as the first choice — fitting DPsim's
real `ControlledVoltageSource` plant to NI's sign/phase conditions is a genuinely open feasibility
question this phase did not attempt to resolve rigorously (see `grid_forming.py`'s own module
docstring for why). What is kept from the PRD's framing: the controller's angle/frequency state
obeys the same second-order swing-equation structure DPsim's own `SynchronGenerator*VBR` models use
(inertia + damping opposing a measured power imbalance), with a separate voltage-magnitude droop
loop — the same "swing equation + exciter" shape a real synchronous generator model has, driving
`ControlledVoltageSource` instead of a literal rotating machine.

**Circuit placement**: a shunt-connected voltage-behind-impedance source (like a real STATCOM/DVR),
coupled through a small series R+jX filter to the fault bus itself — the same bus
`chaosnet.fault_adjacent_line_name()`/`fault_adjacent_lines` already identify, reused rather than
re-derived. Sensor and actuator are collocated at that one bus (the shape NI theory itself targets,
and also the standard real-world STATCOM/DVR placement — support the bus that's actually sagging).

**Real measured result** (seed 42, `chaos_schedule.yaml`'s committed SUB-3 fault, `1.0 MVA`-rated
device, `grid_forming.py --step run`): peak positive-sequence sag depth (`phase_model`'s
`phasor_frames()`/`positive_sequence()`, a stricter measure than `run_dpsim.py`'s own RMS-window
`sag_percent`) went from **16.62% (baseline) to 16.42% (stabilized)** — a real, reproducible
**+0.20 percentage-point (≈1.2% relative) reduction**, not an assumed or tuned-to-a-target number.
Recovery time (time after fault clearance until |V1| settles within 2% of its pre-fault level) was
identical in both runs (~0.0104s) — the stabilizer's droop correction is small enough here that it
doesn't measurably change how fast the network itself recovers once the fault clears. Peak RoCoF
(derived from the same |V1| phasor's unwrapped phase angle) was ~9999–10000 Hz/s in *both* runs,
nearly identical with/without the stabilizer — see the honesty note below for why this number is not
a real frequency-stability measurement.

**Why the effect is small, reported honestly rather than tuned away**: this network's fault switch
is a 0.5 Ω near-bolted short directly at the same bus the stabilizer is coupled to. By simple
voltage-divider reasoning, the parallel combination of a 0.5 Ω short and a source sitting behind the
stabilizer's own ~4+j40 Ω coupling filter is dominated by the 0.5 Ω path almost regardless of how
hard the controller drives its commanded EMF — most of the stabilizer's injected current splits
through the fault itself rather than raising the bus voltage. This is a real, physically-grounded
structural limit of a single-feeder-scale shunt device fighting a low-impedance bolted-through fault
at its own terminal, not a controller-tuning failure — it is also why real-world Dynamic Voltage
Restorers are usually connected in *series*, not shunt, when the job is specifically to block a
bolted fault's propagation (Phase 2's cable-length delay-compensation work and any future series-
compensation variant are the natural next step here, not attempted in this phase).

**RoCoF honesty note**: this network has one ideal, fixed-frequency `NetworkInjection` source and
otherwise only passive RLC branches — there is no rotating-mass/generator dynamics for a genuine
system-frequency excursion to occur against. The ~10,000 Hz/s figure above is an *apparent* RoCoF
from the DFT-estimated fundamental's phase jitter right at the fault-switching instant (where the
one-cycle window briefly spans a near-discontinuity), not evidence of a real frequency event —
included because it's a real, reproducible number derivable from the existing phasor machinery
(the PRD's own instruction: check what's computable before building new machinery), reported for
what it actually is rather than oversold.

**Never claimed**: this controller does not eliminate, nullify, or remove the transient — it
measurably shrinks its peak depth by a modest, real, honestly-reported percentage, for the
physically-grounded reason above. `docs/prd/0005-...md`'s Non-goals name this explicitly; this
section follows it.

`grid_forming.py --step run` (or `just lab5-stabilizer`) re-runs both configurations and writes
`dpsim_transient_log_stabilized.json` and `stabilizer_comparison.json` (both gitignored, regenerated
every run — the latter is the real before/after numbers in a form a later phase, e.g. Phase 1.5's
EMT→OPF headroom translation, can consume without re-running the simulation).

## From EMT margin to steady-state headroom (PRD-0005 Phase 1.5)

Phase 1 above is entirely an EMT/time-domain result: it says nothing about whether the stabilizer's
measured sag-depth reduction matters to AEMO's actual steady-state dispatch/constraint layer, which
is a `pandapower` load-flow question, not a DPsim one. `headroom_translation.py` answers that
honestly, staying entirely inside Lab 5's own topology (`chaosnet.to_pandapower()`, built from the
*identical* seed-42 `ChaosTopology` object Phase 1's DPsim run solved — not Lab 1/2/4's unrelated
fixed real-world network, which would be an arbitrary correspondence for this line-specific result).

**Not literal OPF**: this reuses `labs/02-medium-interconnection-screening/workflow.py`'s
`check_limits()` pattern exactly — a `pandapower.runpp()` steady-state loadflow compared against a
100%-of-nameplate thermal `loading_percent` limit and a 0.90–1.10 pu voltage band. That is a limit
*screen*, not a cost-optimizing `pandapower.runopp()` dispatch, and is called a "limit screen"
throughout `headroom_translation.py`'s own code/output for exactly that reason.

**Translation hypothesis, stated explicitly (there is no established technique for this step)**:
`headroom_translation.py` applies Phase 1's real measured
`peak_sag_reduction_percent_of_baseline` (currently **+1.19%**, i.e. the *relative* sag-depth
improvement, not the raw percentage-point difference) as an equal fractional increase to the
fault-adjacent line's `max_i_ka` thermal rating — on the simplified engineering premise that if
transient voltage-sag depth was itself a factor in how conservatively that line's short-term/dynamic
rating was set beneath its true continuous limit, a stabilizer that reduces the sag could support a
proportionally higher continuous rating on that same asset. This is explicitly **not** a computed
engineering-standard derivation. The equally defensible alternative — that sag depth (a voltage
quantity, timescale ~150ms) and steady-state thermal loading (a continuous-current quantity) are
different physical quantities that simply don't translate at all — is named in the script's own
module docstring and was not chosen only so the binding-constraint question could actually be tested
end to end rather than left abstract.

**Real result** (seed 42, fault-adjacent line `line0_12`, `headroom_translation.py --step run`):
the baseline steady-state `pp.runpp()` limit screen shows this chaos-net topology nowhere close to
any binding constraint under normal conditions — worst line loading **6.12%** (on `line0_12` itself,
the fault-adjacent line, `max_i_ka` 0.2200 kA), worst bus voltage **0.9994 pu**, both far inside the
100% thermal / 0.90–1.10 pu voltage limits, and **zero** lines or buses breaching either limit.
Applying the +1.19% translation raises that line's `max_i_ka` to 0.2226 kA, dropping its own loading
to 6.05% — a real, measured, honest movement of a fraction of a percentage point, nowhere near
flipping any breach status anywhere in the network.

**Binding-constraint verdict: NO.** `binding_constraint_set_changed = False` — the breaching-line and
breaching-bus sets are identical (both empty) before and after the translation. This is the PRD's own
explicitly acceptable, honestly-reportable outcome, not a failure requiring more tuning: this small,
lightly-loaded, procedurally-generated 14-bus/28-line chaos-net simply isn't stressed anywhere near a
steady-state limit under normal conditions, so a sub-2%-relative rating adjustment on one line — even
under the most generous of the two translation hypotheses above — has nowhere to show up as a changed
binding constraint. That is real information about *this* network/fault combination's scale, not
evidence that the underlying stabilizer-to-headroom idea is wrong in general (a larger, more heavily
loaded network, or a fault-adjacent line already sitting close to its thermal limit, could plausibly
show a different answer — not attempted here).

`headroom_translation.py --step run` (or `--step check`) regenerates `headroom_translation.json`
(gitignored, same convention as `stabilizer_comparison.json`) with the full baseline/translated limit
screens, both breach sets, and the conclusion string quoted above.

## Cable-length propagation-delay compensation (PRD-0005 Phase 2)

Goal 3 of `docs/prd/0005-...md` names this a genuinely open sub-problem, not a known technique borrowed
off the shelf: does adding a deadtime/Smith-predictor compensation term to Phase 1's controller,
time-aligned using the fault-adjacent line's own real propagation delay, measurably improve mitigation
over Phase 1's uncompensated baseline — or is a simple fast swing/droop loop already good enough that
the extra complexity buys nothing measurable? `delay_compensation.py` implements the compensation term
as an additive, opt-in extension of `grid_forming.GridFormingStabilizer` (its new
`delay_compensation_enabled`/`delay_s` fields — False/0.0 by default, reproducing Phase 1 exactly, not
just approximately: with `delay_s=0.0` the predictor term is an exact algebraic no-op) and answers the
question with a real three-way comparison.

**Real propagation-delay figure, computed, not assumed.** The fault-adjacent line for seed 42's SUB-3
fault (`line0_12`, the same line `docs/backlog/0006`'s R-X trajectory view already reports the real
impedance of) has `length_km=0.6`, `r_ohm_per_km=0.443`, `x_ohm_per_km=0.132`, `c_nf_per_km≈190` — real
SimBench per-km parameters, not invented. Those figures are textbook *underground-cable* signatures
(`x_ohm_per_km` roughly a third of a typical overhead line's ~0.3–0.4 Ω/km; `c_nf_per_km` roughly twenty
times a typical overhead line's ~10 nF/km), consistent with `chaosnet.SIMBENCH_CODE`'s real source,
`"1-MV-rural--0-sw"` — German MV distribution is predominantly underground cable even in "rural" SimBench
classifications. The propagation-velocity assumption used, stated honestly: `v = c / sqrt(er)` (the
standard TEM-mode cable propagation velocity), with XLPE's commonly-cited relative permittivity
`er ≈ 2.3` — giving `v ≈ 299792.458 / sqrt(2.3) ≈ 197,677 km/s`, deliberately *not* the ~275,000–300,000
km/s figure that applies to overhead lines (a bare conductor in air, `er≈1`), which would be the wrong
physical regime for this topology's real per-km parameters. `0.6 km / 197,677 km/s ≈ 3.035 µs`.

**Honesty note on what this delay represents in this circuit.** Phase 1's stabilizer is deliberately
coupled at the *same* bus as the fault switch (collocated sensor/actuator — see Phase 1's section
above). In that literal circuit, the physical separation between the fault point and the stabilizer's
own coupling point is zero, not this line's length. `delay_s` is used here as this phase's own named
prototype-scale deadtime parameter — "prototype it small and measure" — the real, computed
propagation-delay figure this line's own real length/impedance would produce, applied as the
Smith-predictor's assumed measurement-to-actuation deadtime. A genuinely remote/series-coupled
stabilizer (named as a future variant in Phase 1's section above, not attempted here) is where this
delay would apply literally, without this caveat.

**The compensation term itself**: a first-order forward extrapolation of each control-tick measurement
(the positive-sequence voltage magnitude feeding the droop loop, the measured active power feeding the
swing equation) by `delay_s`, using the measured rate of change between this control tick and the last
one — `x_predicted = x_measured + delay_s * (x_measured - x_previous) / dt_control` — the simplest
honest predictor that time-aligns the controller's correction with the disturbance rather than reacting
to an already-lagged measurement naively. See `grid_forming.GridFormingStabilizer.step()`'s own
control-tick block.

**Real three-way comparison** (seed 42, `chaos_schedule.yaml`'s committed SUB-3 fault,
`delay_compensation.py --step run`), all three real, computed peak positive-sequence sag depths:

| Configuration                              | Peak sag depth |
|---------------------------------------------|----------------|
| No stabilizer (baseline)                     | **16.62%**    |
| Stabilizer, no delay compensation (Phase 1)   | **16.42%**    |
| Stabilizer, with delay compensation (Phase 2) | **16.42%**    |

The middle row reproduces Phase 1's own committed 16.62%→16.42% result exactly (it *is* Phase 1's own
`grid_forming.run_comparison()`, re-run unmodified, not a re-derivation) — confirming Phase 2's new code
didn't silently change Phase 1's default behavior. The delay-compensated run's peak sag differs from the
uncompensated run's by **+0.0003 percentage points** — below this script's own 0.001 pp reporting
precision, i.e. not distinguishable from numerical noise.

**Verdict: NO MEASURABLE EFFECT**, reported honestly rather than tuned toward either answer — one of the
two explicitly acceptable outcomes PRD-0005's Open questions section names. This makes direct physical
sense once the delay is put in context against the controller's own time constants: the real computed
propagation delay (**3.035 µs**) is about **0.03%** of the controller's own control-tick period
(`1/phase_model.PHASOR_RATE_HZ` = 10 ms — the swing/droop loop only updates this often, matching a real
PMU/controller's update rate) and about **0.002%** of the fault's own 150 ms duration. A first-order
predictor driven by measurements that only update every 10 ms simply cannot resolve a 3 µs time shift —
the compensation term's own arithmetic (`delay_s * rate_of_change`) evaluates to a correction on the
order of millivolts against a droop loop already only correcting single-digit volts, itself clipped by
`ACTUATOR_HEADROOM_FRAC`. This is not evidence the Smith-predictor idea is implemented wrong (a fast,
synthetic-signal unit test in `test_lab5.py` confirms the same code path produces a clearly nonzero,
correctly-signed correction once the underlying signal's rate of change is large enough relative to
`delay_s` to matter) — it is a real, physically-grounded finding about *this* line length and *this*
controller's update rate: a 0.6 km MV cable's propagation delay is simply too small, at these time
scales, for deadtime compensation to matter. A much longer line (tens of km) or a controller with a much
faster (sub-microsecond-class) update rate could plausibly show a different answer — not attempted here.

`delay_compensation.py --step run` (or `--step check`) regenerates `delay_compensation.json` (gitignored,
same convention as `stabilizer_comparison.json`/`headroom_translation.json`) with the full three-way
comparison, the propagation-delay figure and its assumptions, and the conclusion string quoted above.

## Sandbox notes (read this before the walkthrough)

Unlike Labs 1–4, this sandbox actually has everything the full spec calls for: `podman` (5.4.2),
the real VILLASnode OCI image
(`registry.git.rwth-aachen.de/acs/public/villas/node:latest`, 2.24 GB, confirmed pulled and real —
`docker.io/villas/node` does not exist, it 403s), and `dpsim`/`simbench`/`networkx` all pip-install
and import cleanly via `uv add`. So most of this lab is *not* a stand-in — it is real
infrastructure, actually run. The few places something had to be substituted are named here
explicitly, per `AGENTS.md`.

1. **Balanced/decoupled 3-phase line and load model.** `chaosnet.py`'s
   `to_dpsim_emt_system()` builds each `dpsimpy.emt.ph3.PiLine`/`RXLoad` from a *diagonal* 3×3
   R/L/C matrix (no phase-to-phase mutual coupling), derived directly from SimBench's real per-km
   R/X/C columns — the same positive-sequence single-phase equivalent pandapower's own power-flow
   model already uses, just extended into 3 (symmetric) phases rather than fabricated. A full
   untransposed-line model would need a real conductor-geometry-derived mutual-impedance matrix,
   which SimBench does not supply. Named in `chaosnet.py`'s own module docstring.

2. **Fault severity: 0.5 Ω line-to-ground, not bolted.** Swept 0.2 / 0.5 / 1.0 / 2.0 Ω against the
   real seed-42 14-bus/28-line chaos-net at 200µs EMT timestep in this sandbox: 0.2 Ω gave a
   dramatic 33% sag but a ~4.3×-nominal switching spike; 0.5 Ω gives a clean, numerically stable
   16.4% sag with a ~2.7×-nominal spike, no NaNs. Documented in `chaosnet.py`'s
   `FAULT_CLOSED_RESISTANCE_OHM`.

3. **Bounded simulated duration + a wall-clock, not simulated-time, countdown.** `run_dpsim.py`
   simulates ~0.55s of grid time (pre-fault settle → fault → clearing → post-fault recovery), not
   an open-ended stream — a deliberate scoping choice, not a sandbox limitation (DPsim itself has
   no problem running longer; a real 4kHz stream for SPARTAN would just keep going). The "in 8s...
   7... 6..." countdown the design doc shows is real wall-clock time (`time.sleep`), separate from
   the schedule's simulated `trigger_time_s` — DPsim's own event system fires the fault at the
   scheduled *simulated* time inside the solve that follows. Both clocks are real; they're just
   different clocks. `run_dpsim.py --step check` uses a 0-second countdown (documented as
   `FAST_COUNTDOWN_SECONDS`) so pytest doesn't spend 8 real seconds per run — the interactive
   walkthrough command always gets the full 8-second countdown.

4. **DPsim → VILLASnode transport: a file, not a live socket/shmem interface.** DPsim ships its
   own native VILLASnode interface (`dpsimpyvillas.InterfaceVillas`, confirmed importable and used
   in DPsim's own `examples/villas/*.py`), which can stream directly from a *running* DPsim process
   to a *running* VILLASnode process over MQTT/file/etc without an intermediate file. This lab uses
   a simpler, more robust wiring instead: `run_dpsim.py` writes the real per-timestep fault-tap
   voltage waveform to `villas/chaos_stream.csv` in VILLASnode's own native `file`/`csv` format
   (format confirmed by direct experiment against the real image, not guessed — see
   `_write_villas_csv()`'s docstring), and the separately-running VILLASnode pod reads that file.
   This decouples the DPsim run's lifecycle from the pod's (the pod can be started/stopped
   independently, any number of times, against the same captured real transient) at the cost of not
   being a live, indefinite stream — consistent with point 3's bounded-duration choice. Wiring
   `dpsimpyvillas.InterfaceVillas` directly is the documented next step for a true live tap.

5. **VILLASnode output node-type: `socket` (UDP/JSON), not `iec61850-9-2`.** This is a genuine,
   root-caused infrastructure limitation of rootless Podman, not a design choice, not a missing
   flag, and not a config mistake — see the full investigation below and `villas/chaos-tap.conf`'s
   header comment for the complete technical trail (image source pulled and read directly, exact
   syscall identified, three separate escape routes tried and each ruled out with a cited, precise
   reason).

   The image's `iec61850-9-2` (IEC 61850-9-2 Sampled Values) node-type **is compiled in** —
   `villas-node` accepts it in a config and logs `Initialized node type which is used by 1 nodes`.
   But actually starting it (wiring it into a live `paths` entry) fails every time:
   `err node   Failed to create SV publisher`, and that failure takes the whole `villas-node`
   process down (exit 255) — including the otherwise-working socket path.

   **Root cause, confirmed by reading the image's own shipped source** (`/villas/lib/nodes/
   iec61850_sv.cpp` inside the image): `iec61850_sv_start()` calls libiec61850's
   `SVPublisher_createEx()`, which bottoms out in `Ethernet_createSocket()`
   (`hal/ethernet/linux/ethernet_linux.c`) doing `socket(AF_PACKET, SOCK_RAW, htons(ETH_P_ALL))`.
   Reproduced directly (a Python one-liner making the identical syscall inside the identical image)
   with `--network host --privileged`: `PermissionError(1, 'Operation not permitted')`, every time.

   **Why `--privileged` doesn't help**: this sandbox's Podman is rootless (`podman info` →
   `rootless: true`). The kernel checks `CAP_NET_RAW` for `AF_PACKET` raw sockets against the *user
   namespace that owns the network namespace* the socket is opened in — not just the calling
   process's own capability set. With `hostNetwork: true`, the socket call executes in the host's
   *real* network namespace, owned by the host's initial (root) user namespace — not this
   container's private, subuid-mapped rootless user namespace. Rootless `--privileged` can only
   grant capabilities effective inside the container's own private user namespace; it structurally
   cannot grant `CAP_NET_RAW` against the host's initial user namespace, because the real
   underlying host user (uid 1000, genuinely unprivileged) never had it to delegate. This is a
   deliberate kernel security boundary — see
   [containers/podman discussion #19009](https://github.com/containers/podman/discussions/19009)
   and [#21079](https://github.com/containers/podman/discussions/21079): "CAP_NET_RAW is network
   namespace aware... this can never be done on the host network namespace... rootless podman
   cannot gain more privileges than your user already has."

   **Isolated the variable for real**: re-ran the identical `--privileged` image *without*
   `hostNetwork` (a private netns owned by this container's own rootless user namespace) with the
   same SV config — the raw socket succeeds, `villas-node` logs `Starting node
   sv_out(iec61850-9-2): ...` and runs cleanly with no error. This confirms the failure is
   specifically about *host netns ownership*, not "rootless can never do raw sockets," and not a
   VILLASnode/libiec61850 bug.

   **But a private netns doesn't give a working stream either**, for a second, independent reason:
   this sandbox's rootless network backend is `pasta` (confirmed via `podman info`), documented at
   [passt.top](https://passt.top/passt/about/) as "a translation layer between a Layer-2 network
   interface and native Layer-4 sockets (TCP, UDP, ICMP/ICMPv6 echo)" — it does not forward
   arbitrary non-IP EtherTypes. IEC 61850-9-2 SV uses EtherType `0x88BA` (raw L2 multicast, not
   IP), so a private-netns SV publisher would start clean but silently black-hole every frame — a
   worse, silent failure mode than today's crash-on-start.

   **Also tried macvlan** (a genuinely L2-native podman network driver): `podman network create -d
   macvlan -o parent=enp3s0 ...` succeeds even rootless, and a container attached to it gets a
   raw-socket-capable `eth0`. But watching the *host's* `ip -d link show` while that container runs
   shows no macvlan slave device ever attached to the real parent NIC — rootless podman cannot
   create a genuine macvlan slave of a physical interface (that also needs `CAP_NET_ADMIN` against
   the host's real netns), so it's silently backed by the same rootless-netns/pasta plumbing. Same
   root cause, same dead end.

   **One more real finding, named for whoever picks this up next**: libiec61850 in this exact
   image *is* built with Routable SV/GOOSE support (IEC 61850-90-5) — `nm -D
   libiec61850.so.1.6.1` shows `SVPublisher_createRemote` and the `RSession_*` family (ordinary
   UDP/IP sockets, no raw socket needed, would work fine under this sandbox's rootless networking).
   But VILLASnode's own `lib/nodes/iec61850_sv.cpp` never calls any of them — only the raw/local
   `SVPublisher_createEx` path is wired up, so Routable SV is unreachable from config alone; it
   would need a VILLASnode source patch and rebuild. VILLASnode's `iec61850-8-1` (GOOSE) node-type,
   by contrast, *does* wire up a routable path (`lib/nodes/iec61850_goose.cpp`, `routed = true`
   with `local_address`/`remote_address`/`multicast_groups` + mandatory session `keys` — ordinary
   UDP, no raw socket) — real, working, IEC-61850-lineage, and IP-routable in this sandbox. But it
   is GOOSE (event/status), not Sampled Values (continuous waveform), so swapping to it would not
   honestly satisfy this lab's "Sampled Values" claim — named here as an option for a future
   contributor, deliberately not silently substituted in.

   **Net conclusion**: a genuine, three-way-confirmed rootless-Podman infrastructure limitation
   (host netns raw socket: denied by the kernel's namespace-capability model; private/pasta netns:
   raw socket allowed but L2 frames never forwarded; macvlan: not actually attached to the physical
   NIC under rootless) — not a config mistake, not fixable by any flag or node-type substitution
   available here. Closing it for real needs genuine root (rootful Podman, not just `--privileged`
   rootless) with `--network host` and a real dedicated NIC — exactly what IEC 61850-9-2 SV assumes
   in production anyway — or running `villas-node` directly on bare metal outside any container.

   The node this lab's pod actually runs, and what `verify_stream.py` actually connects to, is
   `sub-3-tap`: `type = "socket", layer = "udp", format = "json"`. Real IEC 61850 SV framing was
   the target; a real, running, UDP/JSON stream verified end-to-end is what this sandbox could
   actually deliver.

6. **`hostNetwork: true` in `kube/villasnode-tap-pod.yaml`.** VILLASnode's socket node sends
   *outbound* UDP to `127.0.0.1:12000`; a bridged/port-published pod network only forwards
   *inbound* connections in, so a plain `-p 12000:12000/udp` port mapping silently drops every
   outbound packet before it leaves the pod's own network namespace (confirmed: zero packets
   received under bridge networking, all packets received once switched to `--network host`).
   `hostNetwork: true` is the documented fix, along with moving VILLASnode's own embedded
   web/API server off its default port 80 (`http = { port = 8761 }` in `chaos-tap.conf` — port 80
   isn't bindable under `hostNetwork` without root, confirmed by direct experiment).

## Command

```
uv run labs/05-spartan-chaosnet-transient-stream/generate_topology.py --seed 42
uv run labs/05-spartan-chaosnet-transient-stream/generate_topology.py --step check

uv run labs/05-spartan-chaosnet-transient-stream/run_dpsim.py --schedule labs/05-spartan-chaosnet-transient-stream/chaos_schedule.yaml
uv run labs/05-spartan-chaosnet-transient-stream/run_dpsim.py --step check

podman kube play kube/villasnode-tap-pod.yaml
uv run labs/05-spartan-chaosnet-transient-stream/verify_stream.py --node sub-3-tap
podman kube play --down kube/villasnode-tap-pod.yaml

uv run labs/05-spartan-chaosnet-transient-stream/verify_stream.py --step check

uv run labs/05-spartan-chaosnet-transient-stream/grid_forming.py --step run
uv run labs/05-spartan-chaosnet-transient-stream/grid_forming.py --step check

uv run labs/05-spartan-chaosnet-transient-stream/headroom_translation.py --step run
uv run labs/05-spartan-chaosnet-transient-stream/headroom_translation.py --step check

uv run python -m pytest labs/05-spartan-chaosnet-transient-stream/ -v
```

`run_dpsim.py` must be run at least once before `podman kube play` — it writes the real
`villas/chaos_stream.csv` the pod reads (see Sandbox note 4 above; gitignored, regenerated on
every run, same pattern as Labs 1–4's fetched/derived data).

## Step-by-step walkthrough (presenter / backup script)

1. **`uv run labs/05-spartan-chaosnet-transient-stream/generate_topology.py --seed 42`**
   — Real output from this sandbox:
   `Seeded from simbench code 1-MV-rural--0-sw, perturbed: 14 buses, 28 lines, 3 substations
   tagged as tap points (SUB-1, SUB-2, SUB-3)`, followed by
   `pandapower.runpp() converged: True (mean bus voltage 0.9997 pu)`. The edge count (28, not the
   design doc's illustrative 17) is this seed's real `nx.connected_watts_strogatz_graph(k=4)`
   output, printed honestly rather than forced to match the doc's example. It also renders the
   generated graph structure itself — an `nx.spring_layout()` drawing of the 14 buses/28 lines,
   with the 3 tagged tap substations (SUB-1/2/3) drawn larger and labelled so the fault target
   (SUB-3, see step 2) is visible at a glance — to `sample_topology_plot.png`, closing the "the
   generated topology is never drawn" gap (`docs/backlog/0004-lab4-lab5-visualization-options.md`
   Lab 5 item 1).
   — *Backup if unavailable*: the committed `sample_topology.json` fixture (a real seed-42 run,
   not hand-written) plus the pre-rendered `sample_topology_plot.png`, narrated with the same
   framing.

2. **`uv run labs/05-spartan-chaosnet-transient-stream/run_dpsim.py --schedule chaos_schedule.yaml`**
   — Real output from this sandbox:
   `EMT solve running at 200us timestep`, then `[T+00:00] fault scheduled at substation SUB-3 in
   8s...` counting down `... 7... 6... 5... 4... 3... 2... 1...` (real wall-clock seconds — see
   Sandbox note 3), then `FAULT INJECTED: SUB-3 line-to-ground, clearing in 150ms`, then
   `FAULT CLEARED: SUB-3 restored to pre-fault topology`, then
   `Pre-fault 9425 V -> during-fault 7875 V (16.4% sag) -> post-fault 9886 V, 2750 samples,
   finite=True`.
   — Why it matters: this is "problems spawn and countdown" made literal — a deterministic,
   readable schedule file driving a real DPsim EMT physics solve (real
   `dpsimpy.event.SwitchEvent3Ph`), not a random crash.

3. **`podman kube play kube/villasnode-tap-pod.yaml`**
   — Real output from this sandbox (`podman ps`):
   `sub-3-tap-pod-villasnode ... Up ...`, and `podman logs sub-3-tap-pod-villasnode` shows
   `Starting node sub-3-tap(socket): ... out.address=127.0.0.1:12000`.
   — Why it matters: this is the same "one pod per tap, scale with the topology" pattern as every
   other lab's fan-out, just applied to substations instead of contingencies or providers — and
   here, unlike Labs 1–3's kube manifest, it is actually running via real `podman kube play`, not
   just written and unexecuted.

4. **`uv run labs/05-spartan-chaosnet-transient-stream/verify_stream.py --node sub-3-tap`**
   — Real output from this sandbox: `node 'sub-3-tap': 19991 samples in 4s -> 4998 Hz achieved
   (target 5000 Hz), 3 channels`, plus a rendered plot of the real fault transient's voltage sag
   and recovery (`sample_transient_plot.png`) — confirming the stream is real 3-phase voltage data
   at close to the DPsim solve's own 5 kHz sample rate (1 / 200µs), streamed through a real,
   separately-running container, without needing the physical SPARTAN board present.
   — *Backup if the live pod isn't reachable*: the committed `sample_stream_summary.json` plus the
   pre-rendered `sample_transient_plot.png`, narrated the same way; `verify_stream.py` itself falls
   back to these automatically and prints the exact `podman kube play` command needed instead of
   fabricating a result.

5. **(hardware-validated extension only)**: point the VILLASnode tap at the real Radxa Dragon Q8B
   endpoint and confirm SPARTAN's recorder ingests the stream unmodified — this step needs the
   physical board and is not part of the laptop-portable walkthrough above, and was not attempted.

## Files

- `chaosnet.py` — shared chaos-net topology model: SimBench + NetworkX generation, pandapower and
  DPsim EMT loaders built from the exact same real topology. Also picks the fault-adjacent `PiLine`
  tapped for current (`_fault_adjacent_line()`/`fault_adjacent_line_name()`, docs/backlog/0006
  option 2): the line directly connecting `ext_grid_bus` to the fault bus, or the first adjacent
  line in topology order if no such direct line exists for a given seed. `nominal_peak_line_neutral_v()`
  (docs/backlog/0006 option 4) is the public real-nameplate-peak-voltage helper factored out of
  `_phase_voltage_ref()` so other modules can reuse the identical formula.
- `generate_topology.py`, `run_dpsim.py`, `verify_stream.py` — the three walkthrough scripts, each
  with its own `--step check` self-check gate. `generate_topology.py`'s `_build_topology_graph()`/
  `_topology_layout()` (docs/backlog/0006 option 4) are factored out of `_plot_topology()` so
  `animate_sag_propagation.py` places every bus at the identical layout position the static topology
  plot does. `run_dpsim.py`'s `bus_voltages` capture (same backlog item) taps every bus in
  `dsys["nodes"]`, not just the fault bus.
- `chaos_schedule.yaml` — the committed fault schedule (one line-to-ground fault at SUB-3).
- `grid_forming.py` — PRD-0005 Phase 1's grid-forming transient stabilizer (see the dedicated
  section above): the VSM/PID-style control law, the DPsim circuit-splicing helper
  (`add_stabilizer_to_system()`), and the baseline-vs-stabilized comparison driver
  (`run_comparison()`/`--step run`/`--step check`). Writes `dpsim_transient_log_stabilized.json`
  and `stabilizer_comparison.json` (both gitignored, regenerated every run).
- `headroom_translation.py` — PRD-0005 Phase 1.5's EMT→steady-state headroom translation (see the
  dedicated section above): builds a real `pandapower` net from the identical chaos-net topology via
  `chaosnet.to_pandapower()`, runs a Lab 2-pattern `pp.runpp()` limit screen before/after applying the
  stated translation hypothesis to the fault-adjacent line's `max_i_ka`, and reports the real
  binding-constraint verdict (`run_translation()`/`--step run`/`--step check`). Writes
  `headroom_translation.json` (gitignored, regenerated every run).
- `delay_compensation.py` — PRD-0005 Phase 2's cable-length propagation-delay compensation (see the
  dedicated section above): the real propagation-delay figure for the fault-adjacent line
  (`grid_forming.propagation_delay_s()`, added to `grid_forming.py` alongside the
  `delay_compensation_enabled`/`delay_s` fields on `GridFormingStabilizer` itself) and the real
  three-way (no stabilizer / stabilizer without / stabilizer with delay compensation) comparison driver
  (`run_three_way_comparison()`/`--step run`/`--step check`). Writes `delay_compensation.json`
  (gitignored, regenerated every run).
- `villas/chaos-tap.conf` — the committed, real VILLASnode config (see Sandbox notes 4–6).
- `sample_topology.json`, `expected_topology.json`, `sample_topology_plot.png`,
  `expected_dpsim_run.json`, `sample_stream_summary.json`, `sample_transient_plot.png` — committed
  fixtures, each a real output from one actual run, not hand-written.
- `test_lab5.py` — pytest wrapper around the three `--step check` gates, plus unit/render coverage
  for the generated-view scripts below.

**Generated views** (docs/backlog/0004 items 1–2, docs/backlog/0006): every script below renders
some transform of the same real `dpsim_transient_log.json`/`sample_topology.json`, never
independently-fabricated data — see `phase_model.py`'s module docstring for the "one state machine,
many generated views" principle they all share.

- `phase_model.py` — the shared 3-phase waveform state machine (PSCADOSSE): synchrophasor DFT
  estimation, the full V0/V1/V2 symmetrical-component triplet, SCADA RMS aggregation, and
  peak-deviation anomaly bins, all generated from the one recorded state sequence.
- `view_telemetry_rates.py` → `sample_telemetry_rates.png` — the same fault at three telemetry
  rates (raw 5 kHz / C37.118 100 Hz synchrophasor + V0/V1/V2 / SCADA 4 s), stacked on one time axis.
- `animate_telemetry_rates.py` → `animate_telemetry_rates.mp4` (gitignored) — the same three feeds,
  narrated and time-aligned.
- `animate_transient.py` → `animate_transient.mp4` (gitignored) — a growing-reveal animation of the
  raw fault waveform.
- `view_3d_audio.py` → `sample_transient_3d.png`, `dpsim_transient_3ch.wav` — a 3D phase-space
  trajectory plot plus a pitch-shifted 3-channel sonification of the same event.
- `view_phasor_3d.py` → `sample_phasor_3d.png` — a direct request (not a docs/backlog item): the
  classic hand-drawn phasor diagram (Va/Vb/Vc as 2D complex vectors from a common origin), rendered
  as an actual 3D isometric vector plot rather than a flat polar sketch. The two horizontal axes are
  the phasor's own complex plane (Re/Im); the vertical axis is simulated time, stacking 5
  representative snapshots (pre-fault steady state, fault onset, mid-fault, post-clear, post-fault
  recovery, chosen from the run's own real `trigger_time_s`/`clear_time_s`) so a single static PNG
  shows how the diagram itself deforms through the fault, not just one frozen instant. Each
  snapshot's z-position is its ordinal rank, not its duration-scaled real time (the 5 real times are
  unevenly spaced — two of them only one fundamental cycle apart, straddling the 150 ms fault —
  which would otherwise cram the fault-window fans into an unreadable stack); every z-tick is
  labeled with that snapshot's real, measured time so nothing is hidden. A dashed reference circle
  (the real pre-fault \|Va\|) at every height, colored red during the fault window, makes the
  collapse/recovery visible without cross-referencing numbers between panels.
- `view_spectrogram.py` → `sample_spectrogram.png` — a time-frequency (STFT) view of the phase-A
  voltage; the fault's switching edges show up as broadband vertical smears distinct from the
  steady 50 Hz fundamental (docs/backlog/0006, option 3).
- `view_rx_trajectory.py` → `sample_rx_trajectory.png` — the R-X apparent-impedance trajectory
  Z(t)=V1(t)/I1(t) on the fault-adjacent `PiLine`, against a real, documented mho relay
  characteristic (80% Zone-1 reach of that line's own real impedance) — the distance-relay engineer's
  view: "where, electrically, is this fault" rather than "what does the voltage do over time"
  (docs/backlog/0006, option 2). Needs `run_dpsim.py` to have captured the newer
  `ia_line`/`ib_line`/`ic_line` fields (see below).
- `animate_sag_propagation.py` → `animate_sag_propagation.mp4` (gitignored) — every bus's own
  `v_intf` voltage (`run_dpsim.py`'s `bus_voltages` capture), reduced to |V1(t)| per bus and animated
  onto `generate_topology.py`'s own topology layout, colored/sized by each bus's deviation from its
  own real pre-fault operating point — the network-wide sag-propagation view connecting the topology
  and transient artifacts into one (docs/backlog/0006, option 4). Needs `run_dpsim.py` to have
  captured the newer `bus_voltages` field (see below) and `sample_topology.json` to exist.

**A real finding from the symmetrical-component view, worth knowing before reading the charts**:
despite `chaos_schedule.yaml` labeling its event `type: line-to-ground`, `chaosnet.py`'s fault
switch shorts all three phases to ground with an identical resistance (`np.eye(3) *
FAULT_CLOSED_RESISTANCE_OHM`, a diagonal matrix) — electrically a symmetric three-phase-to-ground
fault, not a true single-line-to-ground fault. Measured directly: |V0| stays at numerical zero
throughout, and |V1| dips while |V2| shows only a small switching-transient blip — the correct
signature for what this model actually simulates. This is the same limitation Sandbox note 1 above
already named ("balanced/decoupled 3-phase line and load model"), now independently confirmed by
the sequence-component math rather than only by reading the switch code. See `phase_model.py`'s
module docstring and `test_lab5.py::test_phase_model_sequence_components_confirm_lab5_fault_is_symmetric`
for the regression check.

**Two real findings from the R-X impedance-trajectory view, worth knowing before reading that
chart** (`view_rx_trajectory.py`, docs/backlog/0006 option 2): (1) a one-cycle DFT phasor estimate
is only valid when its analysis window doesn't span a real switching discontinuity — the frame
whose window straddled the fault-clearing instant produced a wrong-quadrant, order-of-magnitude
outlier (`Z ≈ 148+324j` ohm against every neighbour's ~1–1000 ohm), excluded by definition
(`SWITCHING_EXCLUSION_CYCLES`), not tuned away. (2) For seed 42/SUB-3, apparent impedance does
collapse sharply toward the origin during the fault (median `|Z|` ~854 ohm pre-fault → minimum
~1.34 ohm during) but never crosses inside the tapped line's own 80%-reach mho circle (~0.22 ohm),
because `line0_12` is a very short (0.6 km), low-impedance line and `FAULT_CLOSED_RESISTANCE_OHM`
is a partial 0.5 ohm fault at the fault bus itself, not a bolted fault at the line's remote end —
reported as measured, not forced to claim a Zone-1 trip that didn't happen. The rendered PNG
includes a zoomed inset at the reach-circle's own scale for exactly this reason (load and fault
impedance differ from the reach circle by ~3 orders of magnitude on this seed's topology).

**Three real findings from the network-wide sag-propagation view, worth knowing before reading
that animation** (`animate_sag_propagation.py`, docs/backlog/0006 option 4): (1) this sandbox's real
DPsim EMT solve (`do_steady_state_init(True)`) converges its pre-fault steady state at ~0.816 pu of
the SimBench `vn_kv` nameplate *uniformly across every bus, including `ext_grid_bus` itself*
(confirmed: `ext_grid_bus`'s own pre-fault |V1| ÷ nameplate peak = 0.8165, matching sqrt(2/3) to 4
decimal places) — a real characteristic of this sandbox's steady-state initialization, unrelated to
the fault, so the animation's pu reference is each bus's own real pre-fault |V1|, not the nameplate
(see `compute_bus_pu_series()`'s docstring). (2) The sag propagates almost network-wide rather than
attenuating sharply with distance from the fault, as a naive radial-feeder intuition would predict:
for seed 42/SUB-3, the fault bus itself dips to 0.834 pu of its own pre-fault level (a 16.6% dip,
consistent with `run_dpsim.py`'s already-reported 16.4% RMS sag), the worst *other* bus dips to
0.859 pu, and the mean of all 13 other buses' minima is 0.909 pu — most of the mesh sags to within a
few percentage points of the fault bus's own severity, not a sharply localized dip. This is
consistent with `view_rx_trajectory.py` (option 2)'s own finding that this topology's line
impedances are tiny relative to load impedance (median `|Z|` ~854 ohm vs. line impedance ~0.27 ohm):
with line drops this small, most buses sit electrically close to the fault regardless of hop count.
(3) The one bus that stays essentially untouched (SUB-1, 1.000 pu — no measurable dip) is *not* a
general "hub buses are shielded" result: `sample_topology.json` confirms `tap_buses = [0, 11, 12]`
for `["SUB-1", "SUB-2", "SUB-3"]`, i.e. **SUB-1 is `ext_grid_bus` itself** (local bus index 0), the
fixed-voltage swing bus the whole solve is referenced to — its immunity is definitional (it is the
source), not an emergent property of the mesh, and is named here explicitly so this finding isn't
misread as "well-connected buses resist sag propagation" when the real mechanism is simpler and
narrower than that.
