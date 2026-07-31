# Definition of Done

This lab (all three exercises + supporting plumbing) is done when every item below is true and
checkable by someone who has never seen this repo, on a machine with nothing pre-installed but
`curl` and Podman.

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
      download, and localhost traffic to the two pods above. This is checked, not assumed
      (e.g. run one lab with network egress blocked except to localhost and confirm it still
      passes).

## The three labs

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
