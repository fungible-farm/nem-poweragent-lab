#!/usr/bin/env python3
"""Lab 5 -- the same fault event as isolated, time-aligned telemetry feeds,
animated onto one screen with narration (KISS/DMMT: watch and listen, don't
decode).

Reuses the real synchrophasor / SCADA math from view_telemetry_rates.py to
render `animate_telemetry_rates.mp4`. Three isolated panels, one screen:

1. Raw 5 kHz (va/vb/vc) as a sliding *scope* window (~4 cycles visible --
   RAW_ZOOM_S) so the actual waves are readable; the window follows the reveal
   edge "now".
2. C37.118 PDU output at 100 Hz -- the SAME three phases estimated by the
   identical one-cycle DFT (|Va|,|Vb|,|Vc|) plus the full symmetrical-component
   triplet |V1|/|V2|/|V0| (dashed/dash-dot/dotted): phase A collapses, B/C
   swell, |V1| dips -- while |V0|/|V2| stay near zero, confirming this
   schedule's "line-to-ground" fault is implemented as a symmetric
   three-phase-to-ground event, not a true single-phase fault (see
   `phase_model.zero_sequence()`'s docstring; docs/backlog/0006, option 1).
3. SCADA/EMS at a 4 s update -- one flat value (the whole ~0.55 s event lives
   inside a single interval, so this feed never moves).

A narration box says what is happening (values computed from the real log,
never a caption assumption); the fault window is shaded on every panel and a
shared "now" cursor keeps the feeds time-aligned.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np
from matplotlib.animation import FFMpegWriter, FuncAnimation

from view_telemetry_rates import (  # noqa: E402
    COLOR_FAULT,
    COLOR_INK,
    COLOR_PHASE_A,
    COLOR_PHASE_B,
    COLOR_PHASE_C,
    COLOR_SEQ_NEG,
    COLOR_SEQ_ZERO,
    OUTPUT_PNG,
    _load_log,
)
from phase_model import (  # noqa: E402
    PHASOR_RATE_HZ,
    SCADA_UPDATE_S,
    ThreePhaseWaveform,
    negative_sequence,
    phasor_frames,
    positive_sequence,
    scada_rms,
    zero_sequence,
)

LAB_DIR = Path(__file__).resolve().parent
OUTPUT_MP4 = LAB_DIR / "animate_telemetry_rates.mp4"

# PowerPoint-friendly render, but a 1920x1080 frame so three stacked panels
# each get enough height for the waves to read (the 1280x720 version made
# each panel too short -- the reason this file exists).
ANIMATION_FPS: int = 30
FIGURE_WIDTH_IN: float = 19.2
FIGURE_HEIGHT_IN: float = 10.8
FIGURE_DPI: int = 100
VIDEO_CODEC: str = "libx264"
FFMPEG_PIX_FMT: str = "yuv420p"
ANIM_BITRATE: int = -1
EXTRA_ARG_PIX_FMT_FLAG: str = "-pix_fmt"
EXTRA_ARG_MOVFLAGS_FLAG: str = "-movflags"
FFMPEG_FASTART: str = "+faststart"

# Timeline (s of animation time): 1 s lead-in hold, an 8 s reveal sweeping the
# whole ~0.55 s recording (so the 0.15 s fault window gets ~2.2 s of screen
# time), then a 3 s hold on all feeds.
LEAD_IN_HOLD_S: float = 1.0
REVEAL_SWEEP_S: float = 8.0
FINAL_HOLD_S: float = 3.0
VIDEO_DURATION_S: float = LEAD_IN_HOLD_S + REVEAL_SWEEP_S + FINAL_HOLD_S
N_FRAMES: int = round(VIDEO_DURATION_S * ANIMATION_FPS)
LEAD_HOLD_SIM_TIME_S: float = 0.0

# Raw scope window (s of simulated time shown in panel 1): 4 cycles of 50 Hz
# -- enough of the actual wave to read amplitude/phase by eye.
RAW_ZOOM_S: float = 0.08

# Narration prefixes (KISS: the box says what is happening, no decoding).
NARRATION_PRE_FAULT: str = "pre-fault"
NARRATION_FAULTED: str = "FAULT"
NARRATION_POST_FAULT: str = "post-fault / cleared"


def _reveal_sim_time(anim_t: float) -> float:
    """Map animation time to the reveal edge's simulated time (piecewise)."""
    if anim_t < LEAD_IN_HOLD_S:
        return LEAD_HOLD_SIM_TIME_S
    if anim_t < LEAD_IN_HOLD_S + REVEAL_SWEEP_S:
        frac = (anim_t - LEAD_IN_HOLD_S) / REVEAL_SWEEP_S
        return LEAD_HOLD_SIM_TIME_S + frac
    return LEAD_HOLD_SIM_TIME_S + 1.0


def _narration(
    now: float, trigger_s: float, clear_s: float, final_s: float,
    pre_peak_kv: float, fault_dip_kv: float, post_peak_kv: float, v1_dip_kv: float,
    v0_peak_kv: float, v2_peak_kv: float,
) -> tuple[str, str]:
    """(narration text, color) for the reveal edge's simulated time.

    Values are the real recorded numbers (pre-fault peak, phase-A phasor dip
    inside the fault, post-clear swell peak, |V1| dip, |V0|/|V2| fault-window
    peaks) -- computed by the caller from the log, never hardcoded.
    """
    if now < trigger_s:
        return (
            f"{NARRATION_PRE_FAULT}: balanced 50 Hz, ~{pre_peak_kv:.1f} kV "
            f"peak per phase",
            COLOR_INK,
        )
    if now < clear_s:
        return (
            f"{NARRATION_FAULTED} @ {trigger_s:.2f} s: symmetric 3-phase-to-ground -- "
            f"|Va| collapses to ~{fault_dip_kv:.1f} kV, B/C swell, "
            f"|V1| dips to ~{v1_dip_kv:.1f} kV, |V0|/|V2| stay near zero "
            f"(~{v0_peak_kv:.3f}/{v2_peak_kv:.2f} kV) -- confirms this is symmetric, "
            f"not a true single-LG fault",
            COLOR_FAULT,
        )
    return (
        f"{NARRATION_POST_FAULT} @ {clear_s:.2f} s: post-fault SWELL to "
        f"~{post_peak_kv:.1f} kV peak (not a recovery); log ends at "
        f"{final_s:.2f} s before it settles",
        COLOR_INK,
    )


def animate(log: dict, output: Path) -> None:
    """Render the isolated, narrated, time-aligned feeds as a 1920x1080 MP4."""
    wave = ThreePhaseWaveform.from_log(log)
    t = wave.times
    va, vb, vc = wave.va, wave.vb, wave.vc
    trigger_s = float(log["trigger_time_s"])
    clear_s = float(log["clear_time_s"])
    final_s = wave.duration_s

    ft, ph_a, ph_b, ph_c = phasor_frames(wave)
    mag_a, mag_b, mag_c = np.abs(ph_a), np.abs(ph_b), np.abs(ph_c)
    v1 = np.abs(positive_sequence(ph_a, ph_b, ph_c))
    v2 = np.abs(negative_sequence(ph_a, ph_b, ph_c))
    v0 = np.abs(zero_sequence(ph_a, ph_b, ph_c))
    scada = scada_rms(wave)
    scada_times = np.asarray([(s + e) / 2.0 for s, e, _ in scada])
    scada_vals = np.asarray([r for _, _, r in scada])

    # Narration numbers from the real log.
    pre_peak_kv = float(np.max(np.abs(va[t < trigger_s]))) / 1000.0
    in_fault = (ft >= trigger_s) & (ft <= clear_s)
    fault_dip_kv = float(mag_a[in_fault].min()) / 1000.0
    v1_dip_kv = float(v1[in_fault].min()) / 1000.0
    post_peak_kv = float(np.max(np.abs(va[t >= clear_s]))) / 1000.0
    v0_peak_kv = float(v0[in_fault].max()) / 1000.0 if in_fault.any() else 0.0
    v2_peak_kv = float(v2[in_fault].max()) / 1000.0 if in_fault.any() else 0.0

    fig, (ax_raw, ax_phase, ax_scada) = plt.subplots(
        3, 1, figsize=(FIGURE_WIDTH_IN, FIGURE_HEIGHT_IN), dpi=FIGURE_DPI
    )
    fig.subplots_adjust(hspace=0.5)

    # --- Panel 1: raw 5 kHz, sliding scope window ---------------------------
    line_va, = ax_raw.plot([], [], color=COLOR_PHASE_A, lw=1.0, label="va")
    line_vb, = ax_raw.plot([], [], color=COLOR_PHASE_B, lw=1.0, label="vb")
    line_vc, = ax_raw.plot([], [], color=COLOR_PHASE_C, lw=1.0, label="vc")
    ax_raw.set_ylabel("raw 5 kHz (kV)")
    ax_raw.legend(loc="upper left", fontsize=10, ncol=3)
    ax_raw.set_title(
        f"Lab 5 -- {log['target']} fault: isolated time-aligned feeds "
        f"(raw = sliding {RAW_ZOOM_S * 1000:.0f} ms scope)"
    )

    # --- Panel 2: C37.118 100 Hz, three phases + positive sequence ----------
    line_mag_a, = ax_phase.plot([], [], color=COLOR_PHASE_A, lw=1.4, marker=".", ms=4, label="|Va|")
    line_mag_b, = ax_phase.plot([], [], color=COLOR_PHASE_B, lw=1.4, marker=".", ms=4, label="|Vb|")
    line_mag_c, = ax_phase.plot([], [], color=COLOR_PHASE_C, lw=1.4, marker=".", ms=4, label="|Vc|")
    line_v1, = ax_phase.plot([], [], color=COLOR_INK, lw=2.0, ls="--", label="|V1| pos-seq")
    line_v2, = ax_phase.plot([], [], color=COLOR_SEQ_NEG, lw=2.0, ls="-.", label="|V2| neg-seq")
    line_v0, = ax_phase.plot([], [], color=COLOR_SEQ_ZERO, lw=2.0, ls=":", label="|V0| zero-seq")
    ax_phase.set_ylabel("phasor magnitude (kV)")
    ax_phase.legend(loc="upper left", fontsize=10, ncol=3)
    ax_phase.set_title(
        f"C37.118 PDU output @ {PHASOR_RATE_HZ} Hz -- three phases + full "
        f"symmetrical-component triplet"
    )

    # --- Panel 3: SCADA/EMS at 4 s ------------------------------------------
    (line_scada,) = ax_scada.plot([], [], color=COLOR_FAULT, lw=2.5, marker="o", ms=6)
    ax_scada.set_ylabel(f"SCADA RMS {SCADA_UPDATE_S:.0f} s (kV)")
    ax_scada.set_xlabel("simulated time (s)")
    ax_scada.set_title(
        f"SCADA/EMS @ {SCADA_UPDATE_S:.0f} s update -- one interval covers the "
        f"whole {final_s:.2f} s event (this feed never moves)"
    )

    # Fault shading + full-range xlim on the phasor and SCADA panels; the raw
    # panel gets a dynamic scope xlim each frame instead.
    for ax in (ax_phase, ax_scada):
        ax.axvspan(trigger_s, clear_s, color=COLOR_FAULT, alpha=0.12)
        ax.set_xlim(0.0, final_s)
    cursor_phase, = ax_phase.plot([], [], color=COLOR_INK, ls=":", lw=1.3)
    cursor_scada, = ax_scada.plot([], [], color=COLOR_INK, ls=":", lw=1.3)

    narration = ax_raw.text(
        0.012, 0.90, "", transform=ax_raw.transAxes, ha="left", va="top",
        fontsize=17, family="monospace",
        bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=COLOR_INK, alpha=0.95),
    )

    artists = [
        line_va, line_vb, line_vc, line_mag_a, line_mag_b, line_mag_c, line_v1,
        line_v2, line_v0, line_scada, cursor_phase, cursor_scada, narration,
    ]

    def update(frame_index: int) -> list[plt.Artist]:
        anim_t = frame_index / ANIMATION_FPS
        now = _reveal_sim_time(anim_t)

        mask = t <= now
        line_va.set_data(t[mask], va[mask] / 1000.0)
        line_vb.set_data(t[mask], vb[mask] / 1000.0)
        line_vc.set_data(t[mask], vc[mask] / 1000.0)
        win_lo = max(0.0, now - RAW_ZOOM_S)
        ax_raw.set_xlim(win_lo, now if now > win_lo else win_lo + RAW_ZOOM_S)

        pmask = ft <= now
        line_mag_a.set_data(ft[pmask], mag_a[pmask] / 1000.0)
        line_mag_b.set_data(ft[pmask], mag_b[pmask] / 1000.0)
        line_mag_c.set_data(ft[pmask], mag_c[pmask] / 1000.0)
        line_v1.set_data(ft[pmask], v1[pmask] / 1000.0)
        line_v2.set_data(ft[pmask], v2[pmask] / 1000.0)
        line_v0.set_data(ft[pmask], v0[pmask] / 1000.0)

        smask = scada_times <= now
        line_scada.set_data(scada_times[smask], scada_vals[smask] / 1000.0)

        cursor_phase.set_data([now, now], [0, 1])
        cursor_phase.set_transform(cursor_phase.axes.transAxes)
        cursor_scada.set_data([now, now], [0, 1])
        cursor_scada.set_transform(cursor_scada.axes.transAxes)

        text, color = _narration(
            now, trigger_s, clear_s, final_s,
            pre_peak_kv, fault_dip_kv, post_peak_kv, v1_dip_kv,
            v0_peak_kv, v2_peak_kv,
        )
        narration.set_text(f"t = {now:.3f} s\n{text}")
        narration.set_color(color)
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
    """Load the real log, render the MP4, print the per-rate summary."""
    log = _load_log()
    animate(log, OUTPUT_MP4)
    wave = ThreePhaseWaveform.from_log(log)
    ft, _, _, _ = phasor_frames(wave)
    print(
        f"[feeds] wrote {OUTPUT_MP4}: {N_FRAMES} frames, "
        f"{VIDEO_DURATION_S:.1f}s at {ANIMATION_FPS} fps (1920x1080)"
    )
    print(f"  raw 5 kHz:        {len(wave.times)} samples over "
          f"{wave.duration_s:.2f} s (scope window {RAW_ZOOM_S * 1000:.0f} ms)")
    print(f"  C37.118 @100 Hz:  {len(ft)} phasor frames x 3 phases (+ V0/V1/V2)")
    print(f"  SCADA @{SCADA_UPDATE_S:.0f} s:   {len(scada_rms(wave))} "
          f"update interval(s) -- the whole event fits inside one")
    print(f"  static still:     {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
