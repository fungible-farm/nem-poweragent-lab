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

5. **VILLASnode output node-type: `socket` (UDP/JSON), not `iec61850-9-2`.** This is the one
   real infrastructure limitation found in this sandbox, not a design choice. The image's
   `iec61850-9-2` (IEC 61850-9-2 Sampled Values) node-type **is compiled in** —
   `villas-node` accepts it in a config and logs `Initialized node type which is used by 1 nodes`.
   But actually starting it (wiring it into a live `paths` entry) fails every time:
   `err node   Failed to create SV publisher`, and that failure takes the whole `villas-node`
   process down (exit 255) — including the otherwise-working socket path. Confirmed this is not a
   simple missing-capability problem: it fails identically with `--cap-add=NET_RAW
   --cap-add=NET_ADMIN` and even with `--privileged` (full root) — see
   `villas/chaos-tap.conf`'s own header comment for the exact commented-out config block and the
   full reasoning. The node this lab's pod actually runs, and what `verify_stream.py` actually
   connects to, is `sub-3-tap`: `type = "socket", layer = "udp", format = "json"`. Real IEC 61850 SV
   framing was the target; a real, running, UDP/JSON stream verified end-to-end is what this
   sandbox could actually deliver.

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
   output, printed honestly rather than forced to match the doc's example.
   — *Backup if unavailable*: the committed `sample_topology.json` fixture (a real seed-42 run,
   not hand-written), narrated with the same framing.

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
  DPsim EMT loaders built from the exact same real topology.
- `generate_topology.py`, `run_dpsim.py`, `verify_stream.py` — the three walkthrough scripts, each
  with its own `--step check` self-check gate.
- `chaos_schedule.yaml` — the committed fault schedule (one line-to-ground fault at SUB-3).
- `villas/chaos-tap.conf` — the committed, real VILLASnode config (see Sandbox notes 4–6).
- `sample_topology.json`, `expected_topology.json`, `expected_dpsim_run.json`,
  `sample_stream_summary.json`, `sample_transient_plot.png` — committed fixtures, each a real
  output from one actual run, not hand-written.
- `test_lab5.py` — pytest wrapper around the three `--step check` gates.
