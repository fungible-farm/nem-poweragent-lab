#!/usr/bin/env python3
"""Lab 5 -- see it and hear it: isometric 3D phase view + 3-channel audio
sonification of the real DPsim fault transient (KISS/DMMT -- no annotation
needed to read the anomaly).

Renders run_dpsim.py's real `dpsim_transient_log.json` (va/vb/vc at ~5 kHz):

1. `sample_transient_3d.png` -- a 3D phase-space trajectory (x=va, y=vb,
   z=vc) colored by time, fault window [trigger_time_s, clear_time_s]
   highlighted red. A balanced 3-phase signal traces a tidy 3D loop; the
   line-to-ground fault collapses/distorts it; the post-clear swell is the
   oversized loop at the end -- the anomaly is visible at a glance.
2. `dpsim_transient_3ch.wav` -- the same three phases as a 3-channel WAV,
   pitch-shifted (see PITCH_SHIFT) so the 50 Hz transient is audible on
   laptop speakers; the fault is a change you HEAR. Play with: mpv <file>
3. Prints peak-deviation-magnitude anomaly bins -- the anomaly-rate input
   for the DirectML classifier (KISS definition: peak |voltage| beyond the
   pre-fault reference peak, aggregated per 1 s and per 5 s window).

Everything drawn/played is the real recorded data; nothing is fabricated.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TypedDict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 -- registers '3d' projection
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample

LAB_DIR = Path(__file__).resolve().parent
TRANSIENT_LOG_JSON = LAB_DIR / "dpsim_transient_log.json"
OUTPUT_3D_PNG = LAB_DIR / "sample_transient_3d.png"
OUTPUT_WAV = LAB_DIR / "dpsim_transient_3ch.wav"

# Keys every dpsim_transient_log.json must carry (run_dpsim.py writes all of
# them); checked so a stale/malformed log is never plotted.
REQUIRED_LOG_KEYS: tuple[str, ...] = (
    "times", "va", "vb", "vc", "trigger_time_s", "clear_time_s", "target",
)

# The log's real sample rate (times step 200 us -> 5000 Hz).
SAMPLE_RATE_HZ: int = 5000

# Sonification pitch shift (x): the transient's fundamental is 50 Hz -- below
# comfortable laptop-speaker audibility -- so the 3-channel WAV is resampled
# 8x (duration unchanged, all frequencies x8: 50 Hz -> 400 Hz hum, clearly
# audible). Honest labeling: this is a listening aid, not the raw data rate.
PITCH_SHIFT: int = 8
# WAV output sample rate after the pitch shift.
WAV_SAMPLE_RATE_HZ: int = SAMPLE_RATE_HZ * PITCH_SHIFT

# int16 ceiling for the WAV (0.9, not 1.0, so the post-clear swell peak never
# clips -- it is ~1.4x the pre-fault peak and the normalization is global).
WAV_INT16_CEILING: float = 0.9 * 32767.0

# Anomaly-rate aggregation windows (s) for the peak-deviation bins -- the
# classifier's "anomaly rate" semantics (peak deviation magnitude per second
# and per 5 s window).
ANOMALY_WINDOWS_S: tuple[float, ...] = (1.0, 5.0)

# Phase colors: phase A blue (main), fault window red -- the same color roles
# as verify_stream.py / animate_transient.py. Post-clear (swell) uses the
# same blue as pre-fault; the fault red shading is what separates them.
COLOR_PHASE = "#2a78d6"
COLOR_FAULT = "#e34948"
COLOR_INK = "#898781"


class TransientLog(TypedDict):
    """The JSON shape written by run_dpsim.py -- same keys, same semantics.

    Attributes:
        times: simulated time (s) of each recorded sample.
        va/vb/vc: the fault substation's three phase instantaneous voltages (V).
        trigger_time_s: simulated time (s) the fault closes.
        clear_time_s: simulated time (s) the fault opens.
        target: substation the fault is scheduled at (e.g. "SUB-3").
    """

    times: list[float]
    va: list[float]
    vb: list[float]
    vc: list[float]
    trigger_time_s: float
    clear_time_s: float
    target: str


def _load_log() -> TransientLog:
    """Read and structurally validate dpsim_transient_log.json."""
    if not TRANSIENT_LOG_JSON.exists():
        print(
            f"[missing] {TRANSIENT_LOG_JSON} not found. Produce it via the Lab 5 "
            "walkthrough (see labs/05-spartan-chaosnet-transient-stream/README.md):\n"
            "  uv run labs/05-spartan-chaosnet-transient-stream/generate_topology.py --seed 42\n"
            "  uv run labs/05-spartan-chaosnet-transient-stream/run_dpsim.py "
            "--schedule chaos_schedule.yaml",
            file=sys.stderr,
        )
        sys.exit(1)
    log = json.loads(TRANSIENT_LOG_JSON.read_text())
    missing = [key for key in REQUIRED_LOG_KEYS if key not in log]
    if missing:
        print(f"[invalid] {TRANSIENT_LOG_JSON} missing keys: {missing}", file=sys.stderr)
        sys.exit(1)
    return log


def _render_3d(log: TransientLog, path: Path) -> None:
    """Render the isometric 3D phase-space trajectory (x=va, y=vb, z=vc).

    A balanced 3-phase signal is a neat 3D loop; the fault window is drawn in
    red so the collapse is readable at a glance; the post-clear swell is the
    oversized blue loop the recording ends on (see the module docstring for
    why that is a swell, not a recovery). Deterministic output, committed as
    a sample like the lab's other PNGs.

    Args:
        log: the validated transient log.
        path: output PNG path.
    """
    t = np.asarray(log["times"], dtype=float)
    va = np.asarray(log["va"], dtype=float)
    vb = np.asarray(log["vb"], dtype=float)
    vc = np.asarray(log["vc"], dtype=float)
    trigger_s = float(log["trigger_time_s"])
    clear_s = float(log["clear_time_s"])

    fault_mask = (t >= trigger_s) & (t <= clear_s)

    fig = plt.figure(figsize=(9.0, 7.0), dpi=130)
    ax = fig.add_subplot(111, projection="3d")

    for mask, color, label in (
        (~fault_mask, COLOR_PHASE, "va/vb/vc (pre + post-clear)"),
        (fault_mask, COLOR_FAULT, f"fault {trigger_s:.2f}-{clear_s:.2f} s"),
    ):
        if mask.sum() > 1:
            ax.plot(
                va[mask], vb[mask], vc[mask],
                color=color, linewidth=0.8, alpha=0.9, label=label,
            )
    ax.scatter([va[0]], [vb[0]], [vc[0]], color=COLOR_INK, s=24, label="start")
    ax.scatter([va[-1]], [vb[-1]], [vc[-1]], color=COLOR_FAULT, s=24, marker="x", label="end")

    ax.set_xlabel("va (V)", color=COLOR_INK)
    ax.set_ylabel("vb (V)", color=COLOR_INK)
    ax.set_zlabel("vc (V)", color=COLOR_INK)
    ax.set_title(
        f"Lab 5 -- {log['target']} fault, 3-phase space (isometric) -- "
        f"red = fault window, end = post-clear swell"
    )
    ax.legend(loc="upper left", fontsize=8)
    ax.tick_params(colors=COLOR_INK)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def _write_3ch_wav(log: TransientLog, path: Path) -> None:
    """Sonify va/vb/vc as a 3-channel WAV, pitch-shifted to be audible.

    The signal is resampled by PITCH_SHIFT at the same simulated duration, so
    all frequencies rise 8x (the 50 Hz power hum becomes an audible ~400 Hz
    tone) while the 0.55 s fault sequence keeps its timing -- the fault is a
    change you hear. The three phases are the three WAV channels.

    Args:
        log: the validated transient log.
        path: output WAV path.
    """
    phases = np.stack(
        [np.asarray(log[key], dtype=float) for key in ("va", "vb", "vc")], axis=1
    )
    n_out = phases.shape[0] * PITCH_SHIFT
    pitched = np.stack(
        [resample(phases[:, i], n_out) for i in range(phases.shape[1])], axis=1
    )
    # Global normalization so the post-clear swell (~1.4x pre-fault peak)
    # cannot clip any channel.
    peak = float(np.max(np.abs(pitched)))
    scaled = np.int16(np.round(pitched / peak * WAV_INT16_CEILING))
    wavfile.write(path, WAV_SAMPLE_RATE_HZ, scaled)


def peak_deviation_bins(
    log: TransientLog, window_s: float,
) -> list[tuple[float, float, float]]:
    """Peak deviation magnitude per window -- the classifier's anomaly rate.

    Deviation(t) = max over phases of max(0, |v_phase(t)| - reference_peak),
    where reference_peak is that phase's pre-fault peak (the KISS "beyond
    nominal" measure). The bin's value is the peak of deviation(t) within the
    window. With this log (~0.55 s) a 1 s bin and a 5 s window each contain
    the whole recording as one partial bin -- the metric is ready for a
    longer stream, which is when per-window anomaly rate becomes meaningful.

    Args:
        log: the validated transient log.
        window_s: aggregation window length in seconds.

    Returns:
        Sorted [(window_start_s, window_end_s, peak_deviation_V)].
    """
    t = np.asarray(log["times"], dtype=float)
    trigger_s = float(log["trigger_time_s"])
    phases = np.stack(
        [np.asarray(log[key], dtype=float) for key in ("va", "vb", "vc")], axis=1
    )
    pre = t < trigger_s
    ref_peaks = np.abs(phases[pre]).max(axis=0)
    deviation = np.max(np.maximum(0.0, np.abs(phases) - ref_peaks), axis=1)

    bins: list[tuple[float, float, float]] = []
    start = 0.0
    end = float(t[-1])
    while start < end:
        win_end = min(start + window_s, end)
        m = (t >= start) & (t < win_end)
        bins.append((start, win_end, float(deviation[m].max()) if m.any() else 0.0))
        start = win_end
    return bins


def main() -> None:
    """Render the 3D PNG + 3-channel WAV and print the anomaly bins."""
    log = _load_log()

    _render_3d(log, OUTPUT_3D_PNG)
    _write_3ch_wav(log, OUTPUT_WAV)
    print(f"[3d]    wrote {OUTPUT_3D_PNG}")
    print(f"[audio] wrote {OUTPUT_WAV} ({WAV_SAMPLE_RATE_HZ} Hz, "
          f"3 channels, pitch-shifted {PITCH_SHIFT}x for audibility)")

    for window_s in ANOMALY_WINDOWS_S:
        print(f"peak deviation magnitude, {window_s:.0f} s windows:")
        for start, win_end, peak_dev in peak_deviation_bins(log, window_s):
            note = (
                " (partial window -- log is only "
                f"{float(log['times'][-1]):.2f} s long)"
                if win_end - start < window_s
                else ""
            )
            print(f"  [{start:.2f}-{win_end:.2f}] s: {peak_dev:.0f} V{note}")


if __name__ == "__main__":
    main()
