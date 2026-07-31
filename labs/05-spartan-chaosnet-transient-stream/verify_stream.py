#!/usr/bin/env python3
"""Lab 5, step 4 -- Stream Verification (stub receiver).

See README.md in this directory for the full walkthrough.

    podman kube play kube/villasnode-tap-pod.yaml
    uv run labs/05-spartan-chaosnet-transient-stream/verify_stream.py --node sub-3-tap
    podman kube play --down kube/villasnode-tap-pod.yaml

    uv run labs/05-spartan-chaosnet-transient-stream/verify_stream.py --step check

This is the stub/mock receiver named in docs/LAB5_SPARTAN_CHAOSNET.md's
Definition of Done ("verified by a stub/mock receiver (not real SPARTAN
hardware)") -- not a fabricated result: it opens a real UDP socket and
captures real packets from the real, separately-running VILLASnode pod
(kube/villasnode-tap-pod.yaml), which is itself replaying
run_dpsim.py's real DPsim EMT output. See this lab's README "Sandbox
notes" for the one thing this script does *not* attempt: decoding raw
IEC 61850-9-2 Sampled Values frames, since that node-type does not
actually start in this sandbox (see villas/chaos-tap.conf's header) --
this script verifies the `sub-3-tap` UDP/JSON node that does.

If the pod isn't reachable, this script does not fabricate a result: it
prints the exact command to start the pod and narrates from the committed
sample_stream_summary.json + sample_transient_plot.png fixtures instead,
matching docs/LAB5_SPARTAN_CHAOSNET.md step 4's own documented backup path.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from pathlib import Path
from typing import TypedDict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

LAB_DIR = Path(__file__).resolve().parent
TRANSIENT_LOG_JSON = LAB_DIR / "dpsim_transient_log.json"
SAMPLE_SUMMARY_FILE = LAB_DIR / "sample_stream_summary.json"
SAMPLE_PLOT_FILE = LAB_DIR / "sample_transient_plot.png"

# Matches villas/chaos-tap.conf's `sub-3-tap` socket node's `out.address`.
# hostNetwork: true in kube/villasnode-tap-pod.yaml means this really is
# the host's own loopback, not a container-internal address.
STREAM_HOST: str = "127.0.0.1"
STREAM_PORT: int = 12000

# Real capture window (s). Long enough to span several loops of the
# ~0.55s-long replayed transient (chaos_stream.csv's rate=5000Hz /
# 2750 samples, see villas/chaos-tap.conf's `eof = "rewind"` comment) so
# the achieved-rate measurement isn't dominated by one rewind's startup
# jitter. Confirmed empirically in this sandbox: a 4s capture against a
# live pod yields ~19,900 packets (~4973 Hz achieved, see this lab's
# README "Sandbox notes" for the full session log).
CAPTURE_DURATION_S: float = 4.0

# Matches villas/chaos-tap.conf's `chaos_stream_in.in.rate`. Expected
# achieved rate should land close to this (real network/scheduling jitter
# means "close", not exact).
EXPECTED_RATE_HZ: float = 5000.0

# How many channels chaos_stream.csv (run_dpsim.py's _write_villas_csv)
# carries: va, vb, vc -- the fault substation's 3-phase instantaneous
# voltage.
EXPECTED_CHANNEL_COUNT: int = 3

# Tolerance bands for check_step's structural validation of the committed
# sample_stream_summary.json fixture (no live pod required -- see module
# docstring / AGENTS.md self-checking convention). Generous on rate
# (real UDP + container scheduling jitter is not tightly bounded) but exact
# on channel count (a structural property, not a timing measurement).
FIXTURE_RATE_TOLERANCE_HZ: float = 1500.0


class StreamSummary(TypedDict):
    """Diffable summary of one verify_stream.py run."""

    node: str
    live_pod: bool
    packets_captured: int
    capture_duration_s: float
    achieved_rate_hz: float
    channel_count: int


def _capture_udp(duration_s: float) -> tuple[int, int]:
    """Capture real UDP packets from the running VILLASnode pod for a fixed
    wall-clock window.

    Args:
        duration_s: how long to listen.

    Returns:
        (packets_captured, channel_count). channel_count is read from the
        first packet's real JSON payload (VILLASnode's own `format = "json"`
        shape, confirmed by direct experiment: `[{"ts": ..., "sequence":
        ..., "data": [v1, v2, v3]}]`); 0 if no packets arrived.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((STREAM_HOST, STREAM_PORT))
    except OSError:
        return 0, 0
    sock.settimeout(0.2)

    count = 0
    channel_count = 0
    deadline = time.time() + duration_s
    while time.time() < deadline:
        try:
            data, _addr = sock.recvfrom(4096)
        except socket.timeout:
            continue
        count += 1
        if channel_count == 0:
            try:
                payload = json.loads(data.decode())
                channel_count = len(payload[0]["data"])
            except (ValueError, KeyError, IndexError):
                pass
    sock.close()
    return count, channel_count


def _plot_transient(path: Path) -> None:
    """Render the real fault transient's voltage sag/recovery from
    run_dpsim.py's committed transient log.

    Plots the fault substation's phase-A instantaneous voltage against
    simulated time, shading the real fault window
    (trigger_time_s..clear_time_s) read straight out of the same log --
    not a hand-picked window. Uses TRANSIENT_LOG_JSON if this run produced
    one; otherwise falls back to re-deriving nothing (raises, since a
    forged plot would violate the "physics results ... never be fabricated"
    rule in AGENTS.md) -- callers must run_dpsim.py first, or use the
    committed sample_transient_plot.png as the backup artifact.

    Args:
        path: output PNG path.
    """
    log = json.loads(TRANSIENT_LOG_JSON.read_text())
    times = log["times"]
    va = log["va"]
    trigger_t = log["trigger_time_s"]
    clear_t = log["clear_time_s"]

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(times, va, linewidth=1.0, color="#3b6fa0")
    ax.axvspan(trigger_t, clear_t, color="#c0392b", alpha=0.12)
    ax.axvline(trigger_t, color="#c0392b", linestyle="--", linewidth=1.0)
    ax.axvline(clear_t, color="#c0392b", linestyle="--", linewidth=1.0)
    ax.text(
        (trigger_t + clear_t) / 2,
        ax.get_ylim()[1] * 0.92,
        f"fault: {log['target']}",
        ha="center",
        color="#c0392b",
        fontsize=9,
    )
    ax.set_xlabel("simulated time (s)")
    ax.set_ylabel("phase-A instantaneous voltage (V)")
    ax.set_title(
        f"Lab 5 chaos-net fault transient -- {log['target']} line-to-ground"
    )
    ax.grid(True, linewidth=0.4, alpha=0.4)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def run_step(node: str, verbose: bool = True) -> StreamSummary:
    """Capture real UDP samples from the VILLASnode pod for CAPTURE_DURATION_S,
    plot the real fault transient from run_dpsim.py's output, and write the
    committed fixtures.

    Args:
        node: --node value (informational; villas/chaos-tap.conf currently
            wires exactly one tap, "sub-3-tap").
        verbose: if True, print the walkthrough's documented summary.

    Returns:
        A StreamSummary of this run.
    """
    if verbose:
        print(f"Listening on udp://{STREAM_HOST}:{STREAM_PORT} for {CAPTURE_DURATION_S:.0f}s...")
    count, channel_count = _capture_udp(CAPTURE_DURATION_S)
    live_pod = count > 0

    if not live_pod:
        print(
            "[no live samples] the sub-3-tap pod does not appear to be "
            "running. Start it with:\n"
            "  podman kube play kube/villasnode-tap-pod.yaml\n"
            "then re-run this command. Falling back to the committed "
            f"{SAMPLE_SUMMARY_FILE.name} / {SAMPLE_PLOT_FILE.name} fixtures "
            "(docs/LAB5_SPARTAN_CHAOSNET.md step 4's documented backup path)."
        )
        if SAMPLE_SUMMARY_FILE.exists():
            fixture = json.loads(SAMPLE_SUMMARY_FILE.read_text())
            print(json.dumps(fixture, indent=2))
            return fixture
        raise SystemExit(
            f"no live pod and no fixture at {SAMPLE_SUMMARY_FILE} -- run "
            "run_dpsim.py first to produce dpsim_transient_log.json, then "
            "start the pod and re-run this script once to seed the fixture."
        )

    achieved_rate = count / CAPTURE_DURATION_S
    summary: StreamSummary = {
        "node": node,
        "live_pod": True,
        "packets_captured": count,
        "capture_duration_s": CAPTURE_DURATION_S,
        "achieved_rate_hz": round(achieved_rate, 1),
        "channel_count": channel_count,
    }

    if verbose:
        print(
            f"node '{node}': {count} samples in {CAPTURE_DURATION_S:.0f}s "
            f"-> {summary['achieved_rate_hz']:.0f} Hz achieved "
            f"(target {EXPECTED_RATE_HZ:.0f} Hz), {channel_count} channels"
        )

    if TRANSIENT_LOG_JSON.exists():
        _plot_transient(SAMPLE_PLOT_FILE)
        if verbose:
            print(f"[plot] wrote {SAMPLE_PLOT_FILE.name}")

    SAMPLE_SUMMARY_FILE.write_text(json.dumps(summary, indent=2))
    return summary


def check_step() -> bool:
    """Validate the committed sample_stream_summary.json fixture without
    requiring a live pod (see AGENTS.md self-checking convention -- a
    network capture against a container that may or may not be running is
    not something a CI/pytest run should depend on).

    Returns:
        True if the fixture's node/channel_count are exact and
        achieved_rate_hz is within FIXTURE_RATE_TOLERANCE_HZ of
        EXPECTED_RATE_HZ; False otherwise.
    """
    if not SAMPLE_SUMMARY_FILE.exists():
        print(f"[FAIL] no fixture at {SAMPLE_SUMMARY_FILE}", file=sys.stderr)
        return False
    fixture = json.loads(SAMPLE_SUMMARY_FILE.read_text())

    ok = True
    if fixture["channel_count"] != EXPECTED_CHANNEL_COUNT:
        print(
            f"FAIL: channel_count: expected={EXPECTED_CHANNEL_COUNT} "
            f"actual={fixture['channel_count']}"
        )
        ok = False
    if abs(fixture["achieved_rate_hz"] - EXPECTED_RATE_HZ) > FIXTURE_RATE_TOLERANCE_HZ:
        print(
            f"FAIL: achieved_rate_hz {fixture['achieved_rate_hz']} outside "
            f"+/-{FIXTURE_RATE_TOLERANCE_HZ} Hz of target {EXPECTED_RATE_HZ}"
        )
        ok = False
    if not SAMPLE_PLOT_FILE.exists():
        print(f"FAIL: no plot at {SAMPLE_PLOT_FILE}")
        ok = False

    if ok:
        print(
            f"MATCH: sample_stream_summary.json (node="
            f"{fixture['node']}, {fixture['achieved_rate_hz']} Hz, "
            f"{fixture['channel_count']} channels) within documented "
            "tolerance"
        )
    return ok


def main() -> None:
    """CLI entry point. --step run (default) captures a real live window
    against the pod (falling back to fixtures if unreachable); --step check
    validates the committed fixture without needing a live pod."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default="sub-3-tap")
    parser.add_argument("--step", choices=["run", "check"], default="run")
    args = parser.parse_args()

    if args.step == "run":
        run_step(args.node)
    elif args.step == "check":
        ok = check_step()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
