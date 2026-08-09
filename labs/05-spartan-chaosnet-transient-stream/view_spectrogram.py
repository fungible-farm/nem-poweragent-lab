#!/usr/bin/env python3
"""Lab 5 -- time-frequency (STFT) view of the real DPsim fault transient
(docs/backlog/0006, option 3).

Renders run_dpsim.py's real `dpsim_transient_log.json` phase-A voltage
(`va`) into `sample_spectrogram.png`: a spectrogram showing the steady 50 Hz
fundamental before/after the fault, and the broadband harmonic content the
switching event itself injects -- a fault ONSET and CLEARING are each a real
discontinuity in the waveform, and a discontinuity has energy across many
frequencies, not just the fundamental. This is the same "is this an anomaly"
signal `view_3d_audio.py`'s peak-deviation-bin printout implies, made
visible as a picture instead of only a number.

Nothing here is a new capture or a new dependency: `scipy.signal.spectrogram`
operates on the same `va` series already written by run_dpsim.py, and scipy
is already a transitive dependency of this lab (`view_3d_audio.py`'s
`scipy.io.wavfile`/`scipy.signal.resample`).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TypedDict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np
from scipy.signal import spectrogram

LAB_DIR = Path(__file__).resolve().parent
TRANSIENT_LOG_JSON = LAB_DIR / "dpsim_transient_log.json"
OUTPUT_PNG = LAB_DIR / "sample_spectrogram.png"

REQUIRED_LOG_KEYS: tuple[str, ...] = (
    "times", "va", "vb", "vc", "trigger_time_s", "clear_time_s", "target",
)

# The log's real sample rate (times step 200 us -> 5000 Hz), matching
# phase_model.SAMPLE_RATE_HZ.
SAMPLE_RATE_HZ: int = 5000

# STFT window: 250 samples (50 ms, 2.5 fundamental cycles) with 80% overlap
# (200-sample step, 10 ms) -- fine enough time resolution to see the fault
# onset/clearing edges as distinct events, coarse enough for a stable
# frequency estimate of the 50 Hz fundamental (19.5 Hz bin spacing).
STFT_NPERSEG: int = 250
STFT_NOVERLAP: int = 200

# Only the sub-kHz band is plotted -- above this, a 200 us/5 kHz recording's
# own Nyquist limit (2500 Hz) and discretization artifacts dominate over any
# real physical harmonic content DPsim's EMT model would produce.
FREQ_PLOT_CEILING_HZ: float = 1000.0

# Broadband summary threshold (Hz): energy above this is "not the
# fundamental or its first couple of harmonics" -- the KISS anomaly-rate
# figure printed alongside the plot (real computed value, never hardcoded).
BROADBAND_FLOOR_HZ: float = 200.0

# Floor added before log10 so a zero-power bin doesn't blow up -- far below
# any real spectral value in this signal (~V^2/Hz scale is >> 1e-9 here).
LOG_POWER_FLOOR: float = 1e-9

COLOR_FAULT = "#e34948"
COLOR_INK = "#898781"


class TransientLog(TypedDict):
    """The JSON shape written by run_dpsim.py -- same keys, same semantics."""

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


def compute_spectrogram(
    va: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Real STFT of the phase-A voltage via scipy.signal.spectrogram.

    Args:
        va: phase-A instantaneous voltage samples (V), at SAMPLE_RATE_HZ.

    Returns:
        (freqs_hz, frame_times_s, power) -- power is |STFT|^2 per (freq, time)
        bin, scipy's own `spectrogram` default ('density' scaling).
    """
    freqs, frame_times, power = spectrogram(
        va,
        fs=SAMPLE_RATE_HZ,
        window="hann",
        nperseg=STFT_NPERSEG,
        noverlap=STFT_NOVERLAP,
    )
    return freqs, frame_times, power


def _broadband_fraction(
    freqs: np.ndarray, frame_times: np.ndarray, power: np.ndarray, window_mask: np.ndarray,
) -> float:
    """Fraction of spectral power above BROADBAND_FLOOR_HZ, averaged over the
    frames selected by `window_mask` -- the real, computed broadband-energy
    figure (never a caption assumption).

    Args:
        freqs: STFT frequency bins (Hz).
        frame_times: STFT frame center times (s).
        power: |STFT|^2, shape (len(freqs), len(frame_times)).
        window_mask: boolean mask over frame_times selecting the window to
            average over.

    Returns:
        mean(broadband power / total power) over the selected frames, in
        [0, 1]. 0.0 if window_mask selects no frames.
    """
    if not window_mask.any():
        return 0.0
    band = power[:, window_mask]
    total = band.sum(axis=0)
    broadband = band[freqs >= BROADBAND_FLOOR_HZ].sum(axis=0)
    valid = total > 0
    if not valid.any():
        return 0.0
    return float(np.mean(broadband[valid] / total[valid]))


def render(log: TransientLog, path: Path) -> tuple[float, float]:
    """Render the spectrogram PNG and return (pre-fault, fault-window)
    broadband power fractions for the caller's printed summary.

    Args:
        log: the validated transient log.
        path: output PNG path.

    Returns:
        (pre_fault_broadband_frac, fault_window_broadband_frac).
    """
    va = np.asarray(log["va"], dtype=float)
    trigger_s = float(log["trigger_time_s"])
    clear_s = float(log["clear_time_s"])

    freqs, frame_times, power = compute_spectrogram(va)
    db = 10.0 * np.log10(power + LOG_POWER_FLOOR)

    fig, ax = plt.subplots(figsize=(11.0, 6.0), dpi=130)
    plot_mask = freqs <= FREQ_PLOT_CEILING_HZ
    mesh = ax.pcolormesh(
        frame_times, freqs[plot_mask], db[plot_mask, :],
        shading="gouraud", cmap="viridis",
    )
    ax.axvline(trigger_s, color="white", linestyle="--", linewidth=1.2, alpha=0.9)
    ax.axvline(clear_s, color="white", linestyle="--", linewidth=1.2, alpha=0.9)
    ax.set_ylabel("frequency (Hz)")
    ax.set_xlabel("simulated time (s)")
    ax.set_title(
        f"Lab 5 -- {log['target']} fault, phase-A voltage spectrogram "
        f"(STFT, {STFT_NPERSEG / SAMPLE_RATE_HZ * 1000:.0f} ms window) -- "
        f"dashed = trigger/clear"
    )
    cbar = fig.colorbar(mesh, ax=ax)
    cbar.set_label("power (dB, arbitrary ref)")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)

    pre_mask = frame_times < trigger_s
    fault_mask = (frame_times >= trigger_s) & (frame_times <= clear_s)
    pre_frac = _broadband_fraction(freqs, frame_times, power, pre_mask)
    fault_frac = _broadband_fraction(freqs, frame_times, power, fault_mask)
    return pre_frac, fault_frac


def main() -> None:
    """Render sample_spectrogram.png and print the broadband-energy summary."""
    log = _load_log()
    pre_frac, fault_frac = render(log, OUTPUT_PNG)
    print(f"[spectrogram] wrote {OUTPUT_PNG}")
    print(
        f"  broadband power (>{BROADBAND_FLOOR_HZ:.0f} Hz) fraction: "
        f"pre-fault {pre_frac * 100:.1f}% -> fault-window {fault_frac * 100:.1f}%"
    )
    if fault_frac > pre_frac:
        ratio = fault_frac / pre_frac if pre_frac > 0 else float("inf")
        print(
            f"  the fault's switching edges inject broadband content "
            f"({ratio:.1f}x the pre-fault broadband fraction) -- visible in "
            f"{OUTPUT_PNG.name} as the vertical smear at the dashed trigger/clear lines"
        )


if __name__ == "__main__":
    main()
