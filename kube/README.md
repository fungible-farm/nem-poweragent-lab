# `podman kube play` manifests

> Status: **spec only**. See `docs/VISION.md` §4 and §10.

Planned manifests:

- `llamacpp-phi-pod.yaml` — llama.cpp server, CPU-only, serving Phi-4-mini-instruct GGUF (Q4),
  OpenAI-compatible `/v1/chat/completions` on localhost. Model file swappable for the Lab 3
  bake-off (Gemma-4, Llama-3.2-3B) via `podman kube play --replace`.
- `powermcp-pandapower-pod.yaml` — PowerMCP's pandapower MCP server, pinned version, reachable by
  the Agent Framework orchestrator over MCP.
- `benchmark-runner-job.yaml` — Kubernetes `Job` shape for Lab 3's provider × task-family matrix,
  runnable as parallel pods under `podman kube play` today, and unchanged in shape if ever pointed
  at a real cluster later.

Each manifest will be applied/torn down independently (`podman kube play <file>` /
`podman kube play --down <file>`) — see the Definition of Done for the exact checks each pod must
pass.
