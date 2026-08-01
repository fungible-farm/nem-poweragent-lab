# `podman kube play` manifests

> Status: `benchmark-runner-job.yaml` is **written but not podman-executed** in this build
> environment (no `podman` binary present — see its own header comment for exactly what that means
> and what's left to fully wire up). The remaining manifests are spec only. See `docs/VISION.md`
> §4 and §10.

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
- `villasnode-tap-pod.yaml` — planned: VILLASnode, one pod per tagged substation in Lab 5's
  chaos-net, native IEC 61850 Sampled Values output, replaceable per topology via
  `podman kube play --replace` the same way the llama.cpp pod's model file is swapped for Lab 3.

Each manifest is applied/torn down independently (`podman kube play <file>` /
`podman kube play --down <file>`) — see the Definition of Done for the exact checks each pod must
pass.
