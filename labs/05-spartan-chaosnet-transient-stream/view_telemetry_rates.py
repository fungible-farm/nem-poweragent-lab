#!/usr/bin/env python3
"""Lab 5 -- the same fault event at three telemetry rates, stacked concurrently
(KISS: one picture shows why telemetry rate decides what you can see).

Renders run_dpsim.py's real `dpsim_transient_log.json` into
`sample_telemetry_rates.png`, three panels sharing one time axis with the
fault window shaded across all of them:

1. Raw 5 kHz recording (va/vb/vc) -- the EMT truth.
2. C37.118-style synchrophasor (PDU output) at 100 Hz -- magnitude + phase
   angle of phase A computed by a one-cycle DFT at the 50 Hz fundamental
   (what a PMU actually estimates), so the fault is visible as a magnitude
   dip and an angle step.
3. SCADA/EMS telemetry at a 4 s update cadence -- RMS per 4 s interval. With
   this ~0.55 s log the entire event lands inside a single 4 s interval, so
   SCADA sees one point: the transient is invisible at this rate. That is the
   point of the view (the 2016 SA Black System was exactly this class of
   lesson -- fast transients hidden from slow telemetry).

Everything is computed from the real recording: the phasor is a real DFT
estimate, the SCADA value is a real RMS. Nothing fabricated.
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

LAB_DIR = Path(__file__).resolve().parent
TRANSIENT_LOG_JSON = LAB_DIR / "dpsim_transient_log.json"
OUTPUT_PNG = LAB_DIR / "sample_telemetry_rates.png"

REQUIRED_LOG_KEYS: tuple[str, ...] = (
    "times", "va", "vb", "vc", "trigger_time_s", "clear_time_s", "target",
)

# Log sample rate (200 us step -> 5000 Hz).
SAMPLE_RATE_HZ: int = 5000
# C37.118 synchrophasor reporting rate (frames per second) -- the PDU output
# the user asked to compare against SCADA. 100 Hz > the 50 Hz fundamental, so
# one-cycle DFT frames overlap (50 samples of frame stride).
PHASOR_RATE_HZ: int = 100
# Power-system fundamental (NEM is 50 Hz); the phasor DFT is evaluated at this
# bin, one full cycle of N samples.
FUNDAMENTAL_HZ: float = 50.0
# SCADA/EMS update cadence (s) -- the classic control-center telemetry rate.
SCADA_UPDATE_S: float = 4.0

# Color roles match the rest of the lab: blue = phase A/main, red = fault,
# muted gray = axis ink. Phase B/C are green/amber (same as animate_transient).
COLOR_PHASE_A = "#2a78d6"
COLOR_PHASE_B = "#4e9a63"
COLOR_PHASE_C = "#c07a2b"
COLOR_FAULT = "#e34948"
COLOR_INK = "#898781"
# Phasor magnitude vs angle use separate axes colors on panel 2.
COLOR_MAGNITUDE = "#2a78d6"
COLOR_ANGLE = "#898781"


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
            "walkthrough (see labs/05-spartan-chaosnet-transient-stream/README.md).",
            file=sys.stderr,
        )
        sys.exit(1)
    log = json.loads(TRANSIENT_LOG_JSON.read_text())
    missing = [key for key in REQUIRED_LOG_KEYS if key not in log]
    if missing:
        print(f"[invalid] {TRANSIENT_LOG_JSON} missing keys: {missing}", file=sys.stderr)
        sys.exit(1)
    return log


def synchrophasor_100hz(
    times: np.ndarray, phase: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """C37.118-style synchrophasor estimates at 100 Hz (complex phasors).

    One-cycle DFT at the 50 Hz fundamental, frame centered every 1/100 s
    (overlapping windows -- a PMU's standard estimate, not naive decimation):
    X = (2/N) * sum(x[n] * exp(-j*2*pi*(n - n0)/N)) over one cycle. Magnitude
    = |X| (V, peak), angle = arg(X). Returned as complex so callers derive
    magnitude/angle and compute sequence components (positive-sequence) from
    the same complex values -- every phase goes through the identical
    estimator, so the phasor view is literally the same data as the raw view.

    Args:
        times: recorded sample times (s).
        phase: one phase's instantaneous voltage (V).

    Returns:
        (frame_times_s, complex_phasors).
    """
    fs = SAMPLE_RATE_HZ
    n_cycle = int(round(fs / FUNDAMENTAL_HZ))  # 100 samples/cycle @ 5 kHz
    stride = max(1, int(round(fs / PHASOR_RATE_HZ)))  # 50 samples/frame
    n0 = n_cycle // 2
    k_cycle = np.arange(n_cycle)
    weights = np.exp(-2j * np.pi * k_cycle / n_cycle)

    frame_times: list[float] = []
    phasors: list[complex] = []
    for center in range(n0, len(times) - n0, stride):
        win = phase[center - n0: center - n0 + n_cycle]
        frame_times.append(float(times[center]))
        phasors.append(complex(np.sum(win * weights)) * (2.0 / n_cycle))
    return np.asarray(frame_times), np.asarray(phasors)


def positive_sequence_magnitude(
    va: np.ndarray, vb: np.ndarray, vc: np.ndarray,
) -> np.ndarray:
    """Positive-sequence phasor magnitude (symmetrical components).

    V1 = (Va + a*Vb + a^2*Vc) / 3 with a = e^(j 120 deg) -- the standard
    C37.118 sequence quantity. A balanced system keeps |V1| at the phase
    amplitude; a line-to-ground fault drops it (the faulted phase collapses
    while the others swell), so |V1| is the cleanest single anomaly signal.

    Args:
        va/vb/vc: complex phasor arrays for the three phases (same frame
            times, as returned by synchrophasor_100hz()).

    Returns:
        |V1| per frame (V, peak).
    """
    a = np.exp(2j * np.pi / 3)
    return np.abs((va + a * vb + a**2 * vc) / 3.0)


def scada_4s_rms(
    times: np.ndarray, phase: np.ndarray,
) -> list[tuple[float, float, float]]:
    """SCADA/EMS telemetry at a 4 s update: RMS per 4 s interval.

    One (start, end, rms_V) per 4 s interval that overlaps the recording.
    With this ~0.55 s log that is a single interval containing the whole
    event -- which is exactly the honesty the view needs: SCADA at 4 s cannot
    resolve the transient.

    Args:
        times: recorded sample times (s).
        phase: one phase's instantaneous voltage (V).

    Returns:
        Sorted [(interval_start_s, interval_end_s, rms_V)].
    """
    end_t = float(times[-1])
    out: list[tuple[float, float, float]] = []
    start = 0.0
    while start < end_t:
        stop = start + SCADA_UPDATE_S
        m = (times >= start) & (times < stop)
        rms = float(np.sqrt(np.mean(phase[m] ** 2))) if m.any() else 0.0
        out.append((start, min(stop, end_t), rms))
        start = stop
    return out


def render(log: TransientLog, path: Path) -> None:
    """Stack the raw / 100 Hz phasor / 4 s SCADA views with a shared time axis."""
    t = np.asarray(log["times"], dtype=float)
    va = np.asarray(log["va"], dtype=float)
    vb = np.asarray(log["vb"], dtype=float)
    vc = np.asarray(log["vc"], dtype=float)
    trigger_s = float(log["trigger_time_s"])
    clear_s = float(log["clear_time_s"])
    final_s = float(t[-1])

    ft_a, ph_a = synchrophasor_100hz(t, va)
    ft_b, ph_b = synchrophasor_100hz(t, vb)
    ft_c, ph_c = synchrophasor_100hz(t, vc)
    v1 = positive_sequence_magnitude(ph_a, ph_b, ph_c)
    scada = scada_4s_rms(t, va)

    fig, (ax_raw, ax_phase, ax_scada) = plt.subplots(
        3, 1, figsize=(11.0, 10.0), dpi=130, sharex=True
    )

    # --- Panel 1: raw 5 kHz -------------------------------------------------
    ax_raw.plot(t, va / 1000.0, color=COLOR_PHASE_A, lw=0.8, label="va")
    ax_raw.plot(t, vb / 1000.0, color=COLOR_PHASE_B, lw=0.8, label="vb")
    ax_raw.plot(t, vc / 1000.0, color=COLOR_PHASE_C, lw=0.8, label="vc")
    ax_raw.set_ylabel("raw 5 kHz (kV)")
    ax_raw.set_title(
        f"Lab 5 -- same {log['target']} fault at three telemetry rates"
    )
    ax_raw.legend(loc="upper right", fontsize=8)

    # --- Panel 2: C37.118 synchrophasor at 100 Hz, all three phases ---------
    # Same three phases as panel 1, estimated by the identical one-cycle DFT:
    # |Va|,|Vb|,|Vc| plus the positive-sequence magnitude |V1| (dashed). The
    # fault collapses phase A and swells B/C, so |V1| dips -- one number that
    # sees the event.
    ax_phase.plot(ft_a, np.abs(ph_a) / 1000.0, color=COLOR_PHASE_A, lw=1.2, marker=".", ms=3, label="|Va|")
    ax_phase.plot(ft_b, np.abs(ph_b) / 1000.0, color=COLOR_PHASE_B, lw=1.2, marker=".", ms=3, label="|Vb|")
    ax_phase.plot(ft_c, np.abs(ph_c) / 1000.0, color=COLOR_PHASE_C, lw=1.2, marker=".", ms=3, label="|Vc|")
    ax_phase.plot(ft_a, v1 / 1000.0, color=COLOR_INK, lw=1.6, ls="--", label="|V1| pos-seq")
    ax_phase.set_ylabel("phasor magnitude (kV)")
    ax_phase.legend(loc="lower left", fontsize=8)
    ax_phase.set_title(
        f"C37.118 PDU output @ {PHASOR_RATE_HZ} Hz -- three phases + "
        f"positive sequence"
    )

    # --- Panel 3: SCADA/EMS at 4 s ------------------------------------------
    for start, stop, rms in scada:
        ax_scada.step([start, stop], [rms / 1000.0] * 2,
                      where="post", color=COLOR_FAULT, lw=2.0)
        ax_scada.plot((start + stop) / 2.0, rms / 1000.0,
                      color=COLOR_FAULT, marker="o", ms=5)
    ax_scada.set_ylabel(f"SCADA RMS {SCADA_UPDATE_S:.0f} s (kV)")
    ax_scada.set_xlabel("simulated time (s)")
    ax_scada.set_title(
        f"SCADA/EMS @ {SCADA_UPDATE_S:.0f} s update -- one interval covers "
        f"the whole {final_s:.2f} s event (invisible at this rate)"
    )

    # Fault window shaded concurrently on all three panels.
    for ax in (ax_raw, ax_phase, ax_scada):
        ax.axvspan(trigger_s, clear_s, color=COLOR_FAULT, alpha=0.12)
    ax_scada.set_xlim(0.0, final_s)

    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main() -> None:
    """Render sample_telemetry_rates.png and print the per-rate summary."""
    log = _load_log()
    render(log, OUTPUT_PNG)
    t = np.asarray(log["times"], dtype=float)
    va = np.asarray(log["va"], dtype=float)
    vb = np.asarray(log["vb"], dtype=float)
    vc = np.asarray(log["vc"], dtype=float)
    ft, ph_a = synchrophasor_100hz(t, va)
    _, ph_b = synchrophasor_100hz(t, vb)
    _, ph_c = synchrophasor_100hz(t, vc)
    print(f"[rates] wrote {OUTPUT_PNG}")
    print(f"  raw 5 kHz:        {len(t)} samples over {t[-1]:.2f} s")
    print(f"  C37.118 @100 Hz:  {len(ft)} phasor frames x 3 phases "
          f"(+ pos-seq |V1|)")
    print(f"  SCADA @{SCADA_UPDATE_S:.0f} s:   {len(scada_4s_rms(t, va))} "
          f"update interval(s) -- the whole event fits inside one")


if __name__ == "__main__":
    main()
