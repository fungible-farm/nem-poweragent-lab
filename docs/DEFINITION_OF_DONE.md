# Definition of Done

This lab (all five exercises + supporting plumbing) is done when every item below is true and
checkable by someone who has never seen this repo, on a machine with nothing pre-installed but
`curl` and Podman. Lab 5 is the one exception with a split DoD — see its own section below.

## Install

- [ ] `./install.sh` runs to completion on a clean Ubuntu 24.04 (or Fedora) VM with only
      `curl` + `podman` present beforehand, and exits 0.
- [ ] The script never silently overwrites an existing `uv`, `cargo`, or `podman` install — it
      detects and skips.
- [ ] Total wall-clock for install (excluding the one-time Phi-4-mini GGUF download) is stated in
      the README and holds within 2x on a re-run.
- [ ] The install smoke test (step 7 in `docs/VISION.md` §9) prints an unambiguous `PASS` line.

## Data & Rust/Python bridge

- [ ] `scripts/fetch_csiro_nem_data.py` pulls the CSIRO Synthetic-NEM-2000-Bus MATPOWER files,
      verifies a checksum, and is idempotent (second run does nothing but confirm).
- [ ] `powerio` (Rust, via its Python binding) parses at least `snem1803.m` and `snemSA.m` without
      error and the resulting case, once handed to pandapower, solves a base-case AC power flow
      that converges.
- [ ] If `powerio` cannot cover a given `.m` variant, the fallback path (pandapower's own MATPOWER
      converter) is documented inline, not silently swapped in.

## Composition

- [ ] `podman kube play kube/llamacpp-phi-pod.yaml` starts a working OpenAI-compatible endpoint on
      localhost serving Phi-4-mini-instruct, CPU only (`--n-gpu-layers 0` or equivalent), verified
      with a single curl/`httpx` call in CI or the smoke test.
- [ ] `podman kube play kube/powermcp-pandapower-pod.yaml` starts a reachable PowerMCP
      pandapower MCP server, verified by a trivial MCP `list_tools` call.
- [ ] Both pods can be torn down (`--down`) and replaced (`--replace`) without touching the other.
- [ ] No lab, at any point, makes an outbound network call other than: the one-time model/data
      download (CSIRO case files, the GGUF model, — Lab 4 only — the NEMOSIS pull from AEMO's
      NEMWeb, and — Lab 5 only — the one-time SimBench seed-grid download), all cached exactly
      like the others after first run, plus localhost traffic to the two pods above and (Lab 5's
      laptop-portable core only) between the DPsim and VILLASnode pods. This is checked, not
      assumed (e.g. run Labs 1–3 with network egress blocked except to localhost and confirm they
      still pass; Labs 4 and 5's laptop-portable core each need one documented one-time-fetch
      exception. Lab 5's optional hardware-validated extension is explicitly exempt — it talks to
      a real Radxa board by design.)

## The five labs

- [ ] Lab 1 (simple): runs via a single `uv run` command, performs the described load-flow
      parameter fit against `snemSA.m`, and its printed result matches
      `expected_results.json` within the documented tolerance on every run (fixed seed).
- [ ] Lab 2 (medium): the Agent Framework Sequential+Concurrent workflow runs end to end against
      `snem1803.m`, produces a pass/fail table for the N-1 screen, and the human-in-the-loop
      checkpoint actually blocks until acknowledged (not a no-op).
- [ ] Lab 3 (advanced): the provider bake-off runs at least 2 local model providers (Phi-4-mini +
      one other, e.g. Gemma-4 or Llama-3.2-3B) across at least 3 task families, produces a
      scorecard file under `benchmarks/power-agent-bench-lite/results/`, and the
      `kube/benchmark-runner-job.yaml` Job manifest can run the same matrix as parallel pods, not
      only as the serial reference implementation.
- [ ] Lab 3's scorecard includes the non-agentic PowerFM (OpenPowerBench) load-forecasting
      baseline row alongside the LLM-agent providers, scored on the same held-out-window metric,
      with the README explaining why it is a baseline rather than a competing provider.
- [x] Lab 4 (real AEMO data): the NEMOSIS pull for the chosen day is cached and idempotent; the
      DUID → synthetic-generator mapping is a committed, human-readable CSV with a rationale
      column, not implicit in code; the reconciliation tolerance (and why it's looser than Lab 1's)
      is stated in the lab's own README; the constraint-decode step uses `NEM_constraints` (or an
      equivalent cited public library) rather than a hand-rolled parser; and both required
      caveats — "not a digital twin of the real network" and "not a fault-reproduction claim" for
      the optional 2016 case study — appear verbatim (or equivalent) in the lab's own README, not
      only in `docs/LAB4_AEMO_REAL_DATA.md`.
- [x] Lab 5 (SPARTAN chaos-net), **laptop-portable core, required** — **partially met, gap named
      below, not silently checked off**: a procedurally generated topology (SimBench seed +
      NetworkX perturbation) loads in both pandapower and DPsim — done, real; DPsim runs a
      network-wide EMT solve at a 4kHz-class (≤250µs, achieved 200µs) timestep with a scheduled
      fault/switching event firing mid-run and its countdown logged beforehand — done, real
      (`dpsimpy.event.SwitchEvent3Ph`, 16.4% voltage sag). **Not met as literally specified:** a
      VILLASnode pod does run for real via `podman kube play` and does re-emit the per-substation
      tap as a live stream verified against a stub receiver (4998 Hz measured, real UDP capture)
      — but the transport is `socket`/UDP/JSON, not IEC 61850 Sampled Values. The image's
      `iec61850-9-2` node-type is compiled in but fails to start a working SV publisher even under
      `--privileged` in this sandbox; see `labs/05-spartan-chaosnet-transient-stream/README.md`
      "Sandbox notes" #5 and `villas/chaos-tap.conf`'s header for the exact failure and the
      ready-to-uncomment SV config for whoever picks this back up. Everything else about this pod
      is real, running infrastructure, not a stand-in.
- [ ] Lab 5, **hardware-validated extension, optional and separately gated**: the same pipeline
      validated end to end against a real Radxa Dragon Q8B running SPARTAN's actual data recorder.
      Not required for this repo's core Definition of Done to be met. Not attempted.
- [x] Lab 5's README states, verbatim or equivalent, both caveats: it does not implement or
      reproduce SPARTAN's anomaly-detection logic (a subsequent phase, out of scope here), and no
      generated topology represents a real substation network.
- [ ] Every lab's README includes a "step-by-step walkthrough (presenter/backup script)" section
      detailed enough that someone could talk through the demo from it even if the live run fails
      on the day.
- [ ] Every lab's `README.md` is written MEA137A-style: numbered steps, an explicit "you should
      see" for each step, and one paragraph per lab tying the mechanic back to a real AEMO
      modelling task (no unexplained jargon, no marketing language).

## Recording

- [ ] `scripts/record_asciinema_demo.sh` produces a `.cast` file covering install → Lab 1 → Lab 2 →
      Lab 3 summary, playable with `asciinema play`, regenerable on demand (not hand-edited).

## Governance / non-goals held

- [ ] No `b00t` reference anywhere in the repo (code, docs, or kube manifests).
- [ ] No commercial power-system engine required for the golden path (PSS/E, PowerFactory,
      PowerWorld, PSCAD may appear only as clearly-marked optional extras).
- [ ] No cloud LLM API key required or read by any script.
- [ ] Every artifact referenced in this document (kube YAML, lab scripts, fetch script, benchmark
      results, recording) is committed to the repo — nothing the audience needs lives outside
      `git clone` + `./install.sh`.

## Out of scope for "done" (explicitly deferred, not silently dropped)

- A real multi-node Kubernetes deployment (only `podman kube play` manifests are in scope).
- PowerMCP servers for commercial tools (PSS/E, PowerFactory, etc.) — the ecosystem supports them,
  this lab does not exercise them.
- Any dataset beyond the CSIRO Synthetic-NEM-2000-Bus family.
- Automated CI running the full install on every commit (nice-to-have, not required for v1) —
  note this explicitly if it isn't done, rather than implying it is.
