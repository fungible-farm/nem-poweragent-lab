# `podman kube play` manifests

> Status: `villasnode-tap-pod.yaml` (Lab 5) is **written and actually podman-executed** in this
> build environment — `podman` (5.4.2) is present here, and this is the one manifest in the repo
> that specifically needed it; see its own header comment for the full real session (pod up,
> real UDP stream captured, pod torn down cleanly) and Lab 5's own `README.md` "Sandbox notes" for
> the one node-type substitution that came out of running it for real.
> `benchmark-runner-job.yaml` (Lab 3) remains **written but not podman-executed** — Lab 3's own
> `expected_scorecard.json` fixture passes via its serial reference path, so this manifest was
> never a blocker for that lab, and running it wasn't in scope for Lab 5's build. The
> LLM-server/PowerMCP manifests are still spec only. See `docs/VISION.md` §4 and §10.

- `benchmark-runner-job.yaml` — Kubernetes `Job` shape for Lab 3's provider × task-family matrix,
  intended to run as parallel pods under `podman kube play`, unchanged in shape if ever pointed at
  a real cluster later. Lab 3's own `expected_scorecard.json` fixture passes via the serial
  reference path (`uv run orchestrator.py --step sweep`); this manifest is the "farm it out instead
  of a for-loop" artifact named in `docs/VISION.md` §9, not required for that fixture to pass.
- `llamacpp-phi-pod.yaml` — planned: llama.cpp server, CPU-only, serving Phi-4-mini-instruct GGUF
  (Q4), OpenAI-compatible `/v1/chat/completions` on localhost. Model file swappable for the Lab 3
  bake-off (Gemma-4, Llama-3.2-3B) via `podman kube play --replace`.
- `powermcp-pandapower-pod.yaml` — planned: PowerMCP's pandapower MCP server, pinned version,
  reachable by the Agent Framework orchestrator over MCP.
- `villasnode-tap-pod.yaml` — **implemented and real-podman-verified.** VILLASnode
  (`registry.git.rwth-aachen.de/acs/public/villas/node:latest`), one pod tapping Lab 5's chaos-net
  fault substation (`sub-3-tap`), real DPsim transient data in, real UDP/JSON samples out (~4998 Hz
  achieved against a 5000 Hz target, confirmed by a live capture). IEC 61850 Sampled Values is
  compiled into the image but does not actually start in this sandbox (`Failed to create SV
  publisher`, reproduced even under `--privileged`) — see the manifest's own header and
  `labs/05-spartan-chaosnet-transient-stream/villas/chaos-tap.conf`'s header for the full finding
  and the commented-out config block for whoever has a suitable NIC to point it at.

Each manifest is applied/torn down independently (`podman kube play <file>` /
`podman kube play --down <file>`) — see the Definition of Done for the exact checks each pod must
pass.
