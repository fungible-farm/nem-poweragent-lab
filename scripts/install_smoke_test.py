#!/usr/bin/env python3
"""install.sh step 7 -- docs/VISION.md section 9: "one uv run call that does
a trivial power flow through the running pods and prints PASS/FAIL."

Assumes kube/llamacpp-phi-pod.yaml and kube/powermcp-pandapower-pod.yaml are
already up (install.sh's own job, not this script's). Does two checks:

1. llamacpp pod: a trivial OpenAI-compatible chat completion.
2. powermcp pod: a real MCP list_tools call, then load the CSIRO snemSA.m
   case (already fetched by scripts/fetch_csiro_nem_data.py) and run a real
   pandapower.runpp() through the pod's run_power_flow tool.

Exits 0 and prints "PASS: install smoke test" only if both succeed;
otherwise prints "FAIL: install smoke test" with the specific failure and
exits 1 -- this is the literal gate docs/VISION.md section 9 describes: "did
the install actually work" before anyone opens a lab.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import urllib.error
import urllib.request

# Matches kube/llamacpp-phi-pod.yaml's hostPort -- see that file's own header
# for why 8091, not the image's default 8080 (this sandbox is a shared
# multi-tenant host; edit both this constant and the manifest's hostPort
# together if 8091 is taken on your own machine).
LLAMACPP_URL: str = "http://127.0.0.1:8091/v1/chat/completions"

# Matches kube/powermcp-pandapower-pod.yaml's hostPort -- see that file's own
# header for the same "shared sandbox host" reasoning (8001, not the mcp SDK
# FastMCP default of 8000).
POWERMCP_URL: str = "http://127.0.0.1:8001/mcp"

# HTTP client timeout (s) for the llamacpp completion request -- CPU-only
# Phi-4-mini inference measured at ~10.5 tok/s this session (see
# kube/README.md), so even a short completion needs several real seconds,
# not a sub-second health-check timeout.
LLAMACPP_TIMEOUT_S: float = 60.0

# Path the CSIRO case file is mounted at inside the powermcp pod (see
# kube/powermcp-pandapower-pod.yaml's /data hostPath mount) -- same file
# scripts/fetch_csiro_nem_data.py writes to this repo's own data/snemSA.m.
CASE_FILE_IN_POD: str = "/data/snemSA.m"

# install.sh calls this script immediately after `podman kube play` returns,
# which is before the pod's Python process has necessarily finished
# importing pandapower/numpy and binding uvicorn's listener -- observed
# directly this session: a raw `curl` to a freshly `--replace`d pod succeeds
# (TCP accepts, gets a real HTTP response) well before the process is fully
# warmed up, and an `mcp` SDK streamable-HTTP session opened in that window
# drops mid-read (httpcore.ReadError / anyio TaskGroup exception) even
# though the *next* request, seconds later, succeeds cleanly -- measured
# this session at up to ~20s of real cold-start latency after `podman kube
# play --replace`. 8 attempts x 4s (32s worst case) comfortably covers that
# without masking a genuinely dead pod (which fails all 8).
POWERMCP_STARTUP_RETRIES: int = 8
POWERMCP_STARTUP_RETRY_DELAY_S: float = 4.0


def check_llamacpp() -> str | None:
    """Trivial chat completion against the llamacpp pod.

    Returns:
        None on success, else a short failure description.
    """
    body = json.dumps(
        {
            "model": "phi-4-mini",
            "messages": [{"role": "user", "content": "Reply with the single word: PASS"}],
            "max_tokens": 8,
        }
    ).encode()
    req = urllib.request.Request(
        LLAMACPP_URL, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=LLAMACPP_TIMEOUT_S) as resp:
            parsed = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError) as exc:
        return f"llamacpp pod unreachable at {LLAMACPP_URL}: {exc}"

    try:
        content = parsed["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return f"llamacpp pod returned an unexpected response shape: {parsed!r}"

    if not content.strip():
        return "llamacpp pod returned an empty completion"
    print(f"  llamacpp completion: {content.strip()!r}")
    return None


async def _check_powermcp_async() -> str | None:
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError:
        return "the 'mcp' package is not importable -- run via 'uv run' so pyproject.toml's pin applies"

    try:
        async with streamablehttp_client(POWERMCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = [t.name for t in (await session.list_tools()).tools]
                if "run_power_flow" not in tools:
                    return f"powermcp pod's tool list is missing run_power_flow: {tools!r}"

                await session.call_tool("load_network_from_any", {"file_path": CASE_FILE_IN_POD})
                result = await session.call_tool("run_power_flow", {})
                payload = json.loads(result.content[0].text)
                if payload.get("status") != "success":
                    return f"powermcp run_power_flow did not report success: {payload!r}"
                print(f"  powermcp tools: {tools}")
                print(f"  powermcp run_power_flow: status={payload['status']!r}")
    except Exception as exc:  # noqa: BLE001 -- surfaced as a FAIL string, not a crash
        return f"powermcp pod call failed: {exc}"
    return None


def check_powermcp() -> str | None:
    """Real MCP list_tools + a real power-flow call against the powermcp pod.

    Retries on failure (see POWERMCP_STARTUP_RETRIES) since the pod's
    uvicorn listener may not be fully bound the instant `podman kube play`
    returns -- a genuinely dead/misconfigured pod still fails every attempt.

    Returns:
        None on success, else the last attempt's failure description.
    """
    failure: str | None = None
    for attempt in range(1, POWERMCP_STARTUP_RETRIES + 1):
        failure = asyncio.run(_check_powermcp_async())
        if failure is None:
            return None
        if attempt < POWERMCP_STARTUP_RETRIES:
            print(f"  (attempt {attempt}/{POWERMCP_STARTUP_RETRIES} failed: {failure} -- retrying)")
            time.sleep(POWERMCP_STARTUP_RETRY_DELAY_S)
    return failure


def main() -> None:
    print("install smoke test: checking llamacpp-phi-pod...")
    llamacpp_failure = check_llamacpp()

    print("install smoke test: checking powermcp-pandapower-pod...")
    powermcp_failure = check_powermcp()

    failures = [f for f in (llamacpp_failure, powermcp_failure) if f]
    if failures:
        for f in failures:
            print(f"  [FAIL] {f}", file=sys.stderr)
        print("FAIL: install smoke test")
        sys.exit(1)

    print("PASS: install smoke test")


if __name__ == "__main__":
    main()
