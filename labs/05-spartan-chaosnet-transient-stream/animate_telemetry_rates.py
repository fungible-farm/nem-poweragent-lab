#!/usr/bin/env python3
"""Lab 5 -- the same fault event as isolated, time-aligned telemetry feeds,
animated onto one screen (KISS/DMMT: watch all three feeds advance together).

Reuses the real synchrophasor / SCADA computations from view_telemetry_rates.py
to render `animate_telemetry_rates.mp4`: three isolated panels on one screen,
sharing a time axis, a moving "now" cursor, and the shaded fault window:

1. Raw 5 kHz (va/vb/vc) -- the EMT truth.
2. C37.118 PDU output at 100 Hz -- phase-A phasor magnitude + angle.
3. SCADA/EMS at a 4 s update -- one flat value (the whole ~0.55 s event lives
   inside a single interval, so this feed never moves).

A reveal edge advances all three feeds together in simulated time, so a
viewer sees the fault hit the fast feeds while the SCADA feed stays flat --
the "you can't see the transient through SCADA" lesson, animated.

Everything drawn is the real recording; the phasor is a real one-cycle DFT.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np
from matplotlib.animation import FFMpegWriter, FuncAnimation

# Sibling module in the same directory (uv run python <script> puts the
# script's dir on sys.path[0]) -- reuse the real phasor/SCADA math and the
# color/scale constants instead of duplicating them.
from view_telemetry_rates import (  # noqa: E402
    COLOR_ANGLE,
    COLOR_FAULT,
    COLOR_INK,
    COLOR_MAGNITUDE,
    COLOR_PHASE_A,
    COLOR_PHASE_B,
    COLOR_PHASE_C,
    OUTPUT_PNG,
    PHASOR_RATE_HZ,
    SCADA_UPDATE_S,
    _load_log,
    scada_4s_rms,
    synchrophasor_100hz,
)

LAB_DIR = Path(__file__).resolve().parent
OUTPUT_MP4 = LAB_DIR / "animate_telemetry_rates.mp4"

# PowerPoint-friendly render: 1280x720, 30 fps, H.264 + yuv420p + faststart
# (matches animate_transient.py's writer conventions).
ANIMATION_FPS: int = 30
FIGURE_WIDTH_IN: float = 12.8
FIGURE_HEIGHT_IN: float = 7.2
FIGURE_DPI: int = 100
VIDEO_CODEC: str = "libx264"
FFMPEG_PIX_FMT: str = "yuv420p"
ANIM_BITRATE: int = -1
EXTRA_ARG_PIX_FMT_FLAG: str = "-pix_fmt"
EXTRA_ARG_MOVFLAGS_FLAG: str = "-movflags"
FFMPEG_FASTART: str = "+faststart"

# Timeline (s of animation time): 1 s lead-in hold on the first pre-fault
# sample, an 8 s reveal sweeping the whole ~0.55 s recording (so the 0.15 s
# fault window gets ~2.2 s of screen time -- a readable dwell), then a 3 s
# hold on all feeds at the end.
LEAD_IN_HOLD_S: float = 1.0
REVEAL_SWEEP_S: float = 8.0
FINAL_HOLD_S: float = 3.0
VIDEO_DURATION_S: float = LEAD_IN_HOLD_S + REVEAL_SWEEP_S + FINAL_HOLD_S
N_FRAMES: int = round(VIDEO_DURATION_S * ANIMATION_FPS)

# Simulated time the lead-in holds at: the first recorded sample.
LEAD_HOLD_SIM_TIME_S: float = 0.0

# Status labels / colors while the reveal edge is before, inside, or past the
# fault window (honest, matching the other animations).
STATUS_PRE_FAULT: str = "pre-fault"
STATUS_FAULTED: str = "faulted"
STATUS_POST_FAULT: str = "post-fault"


def _reveal_sim_time(anim_t: float) -> float:
    """Map animation time to the reveal edge's simulated time (piecewise)."""
    if anim_t < LEAD_IN_HOLD_S:
        return LEAD_HOLD_SIM_TIME_S
    if anim_t < LEAD_IN_HOLD_S + REVEAL_SWEEP_S:
        frac = (anim_t - LEAD_IN_HOLD_S) / REVEAL_SWEEP_S
        return LEAD_HOLD_SIM_TIME_S + frac  # 0 -> ~0.55 s over the sweep
    return LEAD_HOLD_SIM_TIME_S + 1.0  # >= final simulated time


def _status_for(now: float, trigger_s: float, clear_s: float) -> tuple[str, str]:
    """(label, color) for the reveal edge's simulated time."""
    if now < trigger_s:
        return STATUS_PRE_FAULT, COLOR_INK
    if now < clear_s:
        return STATUS_FAULTED, COLOR_FAULT
    return STATUS_POST_FAULT, COLOR_INK


def animate(log: dict, output: Path) -> None:
    """Render the isolated time-aligned feeds as a 1280x720 MP4."""
    t = np.asarray(log["times"], dtype=float)
    va = np.asarray(log["va"], dtype=float)
    vb = np.asarray(log["vb"], dtype=float)
    vc = np.asarray(log["vc"], dtype=float)
    trigger_s = float(log["trigger_time_s"])
    clear_s = float(log["clear_time_s"])
    final_s = float(t[-1])

    ft, mag, ang = synchrophasor_100hz(t, va, trigger_s)
    scada = scada_4s_rms(t, va)
    scada_times = np.asarray([(s + e) / 2.0 for s, e, _ in scada])
    scada_vals = np.asarray([r for _, _, r in scada])

    fig, (ax_raw, ax_phase, ax_scada) = plt.subplots(
        3, 1, figsize=(FIGURE_WIDTH_IN, FIGURE_HEIGHT_IN), dpi=FIGURE_DPI, sharex=True
    )
    fig.subplots_adjust(hspace=0.45)

    # --- Panel 1: raw 5 kHz ----------------------------------------------
    line_va, = ax_raw.plot([], [], color=COLOR_PHASE_A, lw=0.8, label="va")
    line_vb, = ax_raw.plot([], [], color=COLOR_PHASE_B, lw=0.8, label="vb")
    line_vc, = ax_raw.plot([], [], color=COLOR_PHASE_C, lw=0.8, label="vc")
    ax_raw.set_ylabel("raw 5 kHz (kV)")
    ax_raw.legend(loc="upper right", fontsize=8, ncol=3)
    ax_raw.set_title(f"Lab 5 -- {log['target']} fault: isolated time-aligned feeds")

    # --- Panel 2: C37.118 100 Hz phasor -----------------------------------
    ax_mag = ax_phase
    line_mag, = ax_mag.plot([], [], color=COLOR_MAGNITUDE, lw=1.2, marker=".", ms=3)
    ax_mag.set_ylabel("phasor |V| (kV)", color=COLOR_MAGNITUDE)
    ax_mag.tick_params(axis="y", labelcolor=COLOR_MAGNITUDE)
    ax_ang = ax_mag.twinx()
    line_ang, = ax_ang.plot([], [], color=COLOR_ANGLE, lw=1.0, marker=".", ms=3)
    ax_ang.set_ylabel("phase angle (deg)", color=COLOR_ANGLE)
    ax_ang.tick_params(axis="y", labelcolor=COLOR_ANGLE)
    ax_phase.set_title(f"C37.118 PDU output @ {PHASOR_RATE_HZ} Hz (phase A phasor)")

    # --- Panel 3: SCADA/EMS at 4 s ----------------------------------------
    (line_scada,) = ax_scada.plot([], [], color=COLOR_FAULT, lw=2.0, marker="o", ms=5)
    ax_scada.set_ylabel(f"SCADA RMS {SCADA_UPDATE_S:.0f} s (kV)")
    ax_scada.set_xlabel("simulated time (s)")
    ax_scada.set_title(
        f"SCADA/EMS @ {SCADA_UPDATE_S:.0f} s update -- one interval covers the "
        f"whole {final_s:.2f} s event (this feed never moves)"
    )

    # Fault window shaded concurrently on all three panels + shared cursor.
    for ax in (ax_raw, ax_phase, ax_scada):
        ax.axvspan(trigger_s, clear_s, color=COLOR_FAULT, alpha=0.12)
        ax.set_xlim(0.0, final_s)
    cursor_lines = []
    for ax in (ax_raw, ax_phase, ax_scada):
        (cl,) = ax.plot([], [], color=COLOR_INK, ls=":", lw=1.2)
        cursor_lines.append(cl)
    status_text = ax_raw.text(
        0.012, 0.92, "", transform=ax_raw.transAxes, ha="left", va="top",
        fontsize=13, family="monospace",
        bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=COLOR_INK, alpha=0.9),
    )

    artists = [
        line_va, line_vb, line_vc, line_mag, line_ang, line_scada,
        *cursor_lines, status_text,
    ]

    def update(frame_index: int) -> list[plt.Artist]:
        anim_t = frame_index / ANIMATION_FPS
        now = _reveal_sim_time(anim_t)
        mask = t <= now
        line_va.set_data(t[mask], va[mask] / 1000.0)
        line_vb.set_data(t[mask], vb[mask] / 1000.0)
        line_vc.set_data(t[mask], vc[mask] / 1000.0)
        pmask = ft <= now
        line_mag.set_data(ft[pmask], mag[pmask] / 1000.0)
        line_ang.set_data(ft[pmask], ang[pmask])
        smask = scada_times <= now
        line_scada.set_data(scada_times[smask], scada_vals[smask] / 1000.0)
        for cl in cursor_lines:
            cl.set_data([now, now], [0, 1])
            cl.set_transform(cl.axes.transAxes)
        label, color = _status_for(now, trigger_s, clear_s)
        status_text.set_text(f"t = {now:.3f} s\n{label}")
        status_text.set_color(color)
        return artists

    anim = FuncAnimation(fig, update, frames=range(N_FRAMES), blit=False)
    writer = FFMpegWriter(
        fps=ANIMATION_FPS, codec=VIDEO_CODEC, bitrate=ANIM_BITRATE,
        extra_args=[EXTRA_ARG_PIX_FMT_FLAG, FFMPEG_PIX_FMT,
                    EXTRA_ARG_MOVFLAGS_FLAG, FFMPEG_FASTART],
    )
    anim.save(output, writer=writer)
    plt.close(fig)


def main() -> None:
    """Load the real log, render the MP4, and print the per-rate summary."""
    log = _load_log()
    animate(log, OUTPUT_MP4)
    t = np.asarray(log["times"], dtype=float)
    va = np.asarray(log["va"], dtype=float)
    _, mag, _ = synchrophasor_100hz(t, va, float(log["trigger_time_s"]))
    print(
        f"[feeds] wrote {OUTPUT_MP4}: {N_FRAMES} frames, "
        f"{VIDEO_DURATION_S:.1f}s at {ANIMATION_FPS} fps"
    )
    print(f"  raw 5 kHz:        {len(t)} samples over {t[-1]:.2f} s")
    print(f"  C37.118 @100 Hz:  {len(mag)} phasor frames")
    print(f"  SCADA @{SCADA_UPDATE_S:.0f} s:   {len(scada_4s_rms(t, va))} "
          f"update interval(s) -- the whole event fits inside one")
    print(f"  static still:     {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
