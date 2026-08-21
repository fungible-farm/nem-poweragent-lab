# `podman kube play` manifests

> Status: `villasnode-tap-pod.yaml` (Lab 5) is **written and actually podman-executed** — `podman`
> (5.4.2) is present, and this is the one manifest in the repo that specifically needed it; see its
> own header comment for the full real session (pod up, real UDP stream captured, pod torn down
> cleanly) and Lab 5's own `README.md` "Design notes" for the one node-type substitution that came
> out of running it for real.
> `llamacpp-phi-pod.yaml` and `powermcp-pandapower-pod.yaml` are also now **written and actually
> podman-executed**, each with one real, disclosed limitation of its own — see their own entries
> below and each manifest's own header. `llamacpp-phi-pod.yaml` is a local-LLM inference pod built
> and tested as part of this repo's kube infrastructure; no lab currently calls it (Labs 1 and 3 use
> deterministic search policies instead of a live model — see their own READMEs).
> `benchmark-runner-job.yaml` (Lab 3) is now **written and podman-executed**, with one real,
> documented limitation: `podman kube play` 5.4.2 does not implement Kubernetes Job's
> `completions`/`parallelism`/`completionMode`/`backoffLimit` fields (`man podman-kube-play`'s own
> support table lists all four as "no"), so `podman kube play` on this manifest runs exactly one
> pod, not 3. The actual point of the manifest — partitioning the 3-provider matrix across
> concurrent processes via a `PROVIDER_FILTER` env var — *is* real and podman-verified, just via 3
> directly-launched `podman run` containers sharing the manifest's own results volume rather than
> through `podman kube play`'s Job support; see the manifest's own header for the full session and
> exact commands. Lab 3's own `expected_scorecard.json` fixture still passes via the serial
> reference path regardless. See `docs/VISION.md` §4 and §10.

- `benchmark-runner-job.yaml` — **implemented and real-podman-verified (with a documented `podman
  kube play` Job-support caveat).** Kubernetes `Job` shape for Lab 3's provider × task-family
  matrix, built from the repo root's `Containerfile.bakeoff` into `power-agent-bench-lite:local`.
  Each pod runs `orchestrator.py --step sweep` with `PROVIDER_FILTER` sourced from the Job's
  completion-index annotation, scoring exactly one of the 3 providers and writing a distinct
  `scorecard.partial.<provider>.json` to a shared `hostPath` results volume;
  `orchestrator.py --step collect` merges the partial files (+ a freshly-computed PowerFM row)
  back into one scorecard, verified identical (modulo wall-clock) to `expected_scorecard.json`.
  `podman kube play` 5.4.2 itself doesn't implement Job's `completions`/`parallelism`/
  `completionMode` fields, so it runs this manifest as a single pod rather than 3 — the
  partitioning was instead verified via 3 concurrent `podman run` containers using the same env
  var/volume shape; see the manifest's own header for the full finding and exact commands. Lab 3's
  own `expected_scorecard.json` fixture still passes via the unrelated serial reference path
  (`uv run orchestrator.py --step sweep`, no `PROVIDER_FILTER` set) either way.
- `llamacpp-phi-pod.yaml` — **implemented and real-podman-verified.** `ghcr.io/ggml-org/llama.cpp:
  server` (CPU-only), serving `unsloth/Phi-4-mini-instruct-GGUF`'s `Phi-4-mini-instruct-Q4_K_M.gguf`
  (2,491,874,272 bytes, sha256 `88c00229914083cd112853aab84ed51b87bdf6b9ce42f532d8c85c7c63b1730a`,
  verified byte-for-byte against Hugging Face's own LFS metadata after download — this is the
  one-time model-download exception named in `docs/DEFINITION_OF_DONE.md`'s Composition section;
  the file lives at `data/models/`, gitignored like the CSIRO case files). Real completion verified:
  ```
  podman kube play kube/llamacpp-phi-pod.yaml
  curl http://127.0.0.1:8091/v1/chat/completions -H "Content-Type: application/json" \
    -d '{"model":"phi-4-mini","messages":[{"role":"user","content":"In one short sentence, what is a power flow study in electrical engineering?"}],"max_tokens":80}'
  # -> "A power flow study is an analysis used to determine the voltage, current, and flow of
  #     electricity in an electrical power system under a given set of conditions." (real model
  #     output, CPU-only, ~10.5 tokens/sec on this build's hardware)
  podman kube play --down kube/llamacpp-phi-pod.yaml
  ```
  Published on host port 8091, not the image's default 8080 — this host runs several unrelated
  containers already bound to 8080 (confirmed by a first attempt failing with "address already in
  use"); pick whatever's free on your own machine. This pod is a real, tested local-LLM capability,
  not currently wired into any lab's own pipeline.
- `powermcp-pandapower-pod.yaml` — **implemented and real-podman-verified.** Built from
  `Containerfile.powermcp` (repo root — no pre-built upstream PowerMCP image exists) into
  `powermcp-pandapower:local`. **Named limitation:** PowerMCP's shipped `powermcp run pandapower`
  CLI only starts the pandapower MCP server over **stdio** (`pandapower/panda_mcp.py`'s own
  `if __name__ == "__main__": mcp.run(transport="stdio")`), which cannot be dialled from outside the
  container — so this pod does not run that CLI. It runs `kube/powermcp_serve_http.py` instead, a
  small committed wrapper (does **not** modify PowerMCP's own source) that loads the real
  `panda_mcp.py` via PowerMCP's own `powermcp.registry` API, skips its stdio-launching `__main__`
  guard, and calls the already-tool-registered `FastMCP` server's `.run(transport=
  "streamable-http")` directly. See that file's module docstring and the pod manifest's own header
  for the full rationale. A second, independent finding pinned in the same Containerfile: PowerMCP's
  `pyproject.toml` declares `mcp>=1.0` unbounded, but `mcp>=2.0.0` (the current PyPI `LATEST`)
  renamed away the `mcp.server.fastmcp` module `panda_mcp.py` imports — verified by bisection that
  `mcp==1.12.2` is the newest release that still works; pinned explicitly rather than left to float.
  Real MCP `list_tools` + a real power-flow tool call, verified against the pod over its published
  HTTP port using the official `mcp` Python SDK client:
  ```
  podman build -t powermcp-pandapower:local -f Containerfile.powermcp .
  podman kube play kube/powermcp-pandapower-pod.yaml   # mounts data/ at /data (read-only)
  uv run --with mcp==1.12.2 python - <<'PY'
  import asyncio, json
  from mcp import ClientSession
  from mcp.client.streamable_http import streamablehttp_client

  async def main():
      async with streamablehttp_client("http://127.0.0.1:8001/mcp") as (r, w, _):
          async with ClientSession(r, w) as s:
              await s.initialize()
              print([t.name for t in (await s.list_tools()).tools])
              await s.call_tool("load_network_from_any", {"file_path": "/data/snemSA.m"})
              res = await s.call_tool("run_power_flow", {})
              print(json.loads(res.content[0].text)["status"])

  asyncio.run(main())
  PY
  podman kube play --down kube/powermcp-pandapower-pod.yaml
  ```
  Real output: `['create_empty_network', 'load_network', 'run_power_flow',
  'run_contingency_analysis', 'get_network_info', 'load_network_from_any', 'load_network_from_json',
  'export_network_to_format']`, then a real `pandapower.runpp()` solve of the real CSIRO `snemSA.m`
  case (503 buses) via `load_network_from_any` → `run_power_flow`, returning real per-bus `vm_pu`
  voltages — `status: success`. Published on host port 8001 (same "shared host" reasoning as the
  llamacpp pod above).
- `villasnode-tap-pod.yaml` — **implemented and real-podman-verified.** VILLASnode
  (`registry.git.rwth-aachen.de/acs/public/villas/node:latest`), one pod tapping Lab 5's chaos-net
  fault substation (`sub-3-tap`), real DPsim transient data in, real UDP/JSON samples out (~4998 Hz
  achieved against a 5000 Hz target, confirmed by a live capture). IEC 61850 Sampled Values is
  compiled into the image but does not actually start in this build (`Failed to create SV
  publisher`, reproduced even under `--privileged`) — see the manifest's own header and
  `labs/05-spartan-chaosnet-transient-stream/villas/chaos-tap.conf`'s header for the full finding
  and the commented-out config block for whoever has a suitable NIC to point it at.

Each manifest is applied/torn down independently (`podman kube play <file>` /
`podman kube play --down <file>`) — see the Definition of Done for the exact checks each pod must
pass. `llamacpp-phi-pod.yaml` and `powermcp-pandapower-pod.yaml` were confirmed independently
torn-down/replaced this session: both pods brought up together, `--down` on the llamacpp pod alone
left the powermcp pod running and reachable, then `--replace` on the llamacpp pod brought it back
without touching the powermcp pod, both reachable together again, then both torn down cleanly with
no orphaned containers left running (`podman ps -a` confirmed clean).
