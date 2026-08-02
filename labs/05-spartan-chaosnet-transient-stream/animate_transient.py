#!/usr/bin/env python3
"""Lab 5 -- Animate the Real DPsim Fault Transient into a PowerPoint-ready MP4.

Renders run_dpsim.py's real `dpsim_transient_log.json` (the ~5 kHz EMT
voltage recording from the real DPsim solve -- see run_dpsim.py) as a
"waveform drawing itself across time" animation: a growing reveal sweeps
from the first sample through the scheduled fault's dip and recovery, then
holds on the full waveform so a presenter can narrate the pre-fault
oscillation, the fault onset at `trigger_time_s`, and the recovery at
`clear_time_s` before the clip ends.

Everything drawn is the real recorded data: the reveal mask is
`times <= current_reveal_time` over the actual `times`/`va`/`vb`/`vc`
arrays read from the log; the fault-window shading and the dashed
trigger/clear lines are the log's own `trigger_time_s`/`clear_time_s`; the
y-extent is the real min/max of the recorded samples. If the log is missing
the script prints the exact commands to produce it (see this lab's README)
and exits non-zero -- it never fabricates or interpolates a waveform.

The MP4 is a rendered artifact (gitignored by `*.mp4`); this script is the
committed artifact. Headless: sets the Agg backend before pyplot and
encodes with the system ffmpeg on PATH via matplotlib's FFMpegWriter.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import NamedTuple, TypedDict

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.animation import FFMpegWriter, FuncAnimation

LAB_DIR = Path(__file__).resolve().parent
TRANSIENT_LOG_JSON = LAB_DIR / "dpsim_transient_log.json"
OUTPUT_MP4 = LAB_DIR / "animate_transient.mp4"

# ---------------------------------------------------------------------------
# Output / rendering constants
# ---------------------------------------------------------------------------
# Common 16:9 PowerPoint-friendly frame rate: the smallest "smooth" rate
# every slide-deck player handles natively.
ANIMATION_FPS: int = 30
# 12.8in x 7.2in at 100 dpi = 1280x720 px, the standard 16:9 PowerPoint
# slide canvas (the MP4 therefore matches a full-frame slide).
FIGURE_WIDTH_IN: float = 12.8
FIGURE_HEIGHT_IN: float = 7.2
FIGURE_DPI: int = 100
# H.264: the one codec PowerPoint/Keynote/QuickTime all accept natively.
VIDEO_CODEC: str = "libx264"
# yuv420p: 4:2:0 planar YUV, the broadly-compatible pixel format for H.264
# playback (FFMpegBase's own comment: yuv444p "is not compatible with
# quicktime... Specifying yuv420p fixes playback on iOS, as well as HTML5
# video in firefox and safari"). matplotlib would auto-add this only for the
# codec name "h264", not "libx264", so it is passed explicitly.
FFMPEG_PIX_FMT: str = "yuv420p"
# +faststart: moves the moov atom to the file head so a slide-deck player
# can begin playback before the whole file is buffered.
FFMPEG_FASTART: str = "+faststart"
# Encoder-selected bitrate: FFMpegBase emits a `-b <kbps>` flag only when
# bitrate > 0, and matplotlib's MovieWriter docstring documents "-1 lets the
# underlying movie encoder select the bitrate" -- the right choice for a
# short, mostly-flat animation where a fixed bitrate would waste bytes.
ANIM_BITRATE: int = -1
# ffmpeg flag tokens paired with the two constants above, passed verbatim.
EXTRA_ARG_PIX_FMT_FLAG: str = "-pix_fmt"
EXTRA_ARG_MOVFLAGS_FLAG: str = "-movflags"

# ---------------------------------------------------------------------------
# Colors (mirror verify_stream.py's plot conventions exactly)
# ---------------------------------------------------------------------------
# Phase-A main-series blue -- the same hex verify_stream.py's
# _plot_transient() uses for the phase-A line.
COLOR_PHASE_A: str = "#3b6fa0"
# Phase-B / Phase-C secondaries: muted green/amber chosen to stay distinct
# from the phase-A blue, the fault red, and the axis-ink gray on screen.
COLOR_PHASE_B: str = "#4e9a63"
COLOR_PHASE_C: str = "#c07a2b"
# Fault-window highlight red -- the same hex verify_stream.py uses for its
# axvspan / axvline fault markers.
COLOR_FAULT: str = "#c0392b"
# Muted gray for gridlines and axis ink -- the lab's plot axis tone.
COLOR_INK: str = "#898781"

# ---------------------------------------------------------------------------
# Animation timeline (design durations, all in *animation* seconds)
# ---------------------------------------------------------------------------
# Lead-in hold: freezes the first full cycle of the pre-fault 50 Hz
# oscillation on screen before the reveal starts sweeping, so a viewer sees
# the steady-state "before" picture first (see LEAD_HOLD_SIM_TIME_S).
LEAD_IN_HOLD_S: float = 0.8
# Pre-fault sweep: reveals the rest of the pre-fault window at ~350 recorded
# samples/s of animation time (~11.7 samples/frame at 30 fps) -- slow enough
# to watch the 50 Hz oscillation draw itself in.
PRE_FAULT_SWEEP_S: float = 2.5
# Fault dwell: the interesting part, so it gets the slowest sweep -- ~200
# recorded samples/s (~6.7 samples/frame) -- letting the sag dip and the
# clearing step unfold gradually inside the shaded window instead of flashing
# past.
FAULT_DWELL_SWEEP_S: float = 4.0
# Post-fault sweep: ~488 recorded samples/s (~16.3 samples/frame) -- fast,
# since this section is the plain recovery back to nominal.
POST_FAULT_SWEEP_S: float = 2.0
# Ending hold: freezes the fully revealed, recovered waveform so the
# presenter can narrate the final state; keeps the whole clip ~12 s.
FINAL_HOLD_S: float = 2.7
# Total animation length (s): the sum of the five phases above.
VIDEO_DURATION_S: float = (
    LEAD_IN_HOLD_S
    + PRE_FAULT_SWEEP_S
    + FAULT_DWELL_SWEEP_S
    + POST_FAULT_SWEEP_S
    + FINAL_HOLD_S
)
# Total frames to render.
N_FRAMES: int = round(VIDEO_DURATION_S * ANIMATION_FPS)
# Simulated time the lead-in hold stops revealing at: one full 50 Hz cycle
# of the NEM grid (period = 1/50 s). At the log's real 200 us sample step
# that is ~100 recorded samples -- enough waveform to read the steady-state
# amplitude.
LEAD_HOLD_SIM_TIME_S: float = 0.02
# Reveal edges (s of simulated time) around trigger/clear: the fault-dwell
# segment starts 5 ms before `trigger_time_s` and ends 5 ms after
# `clear_time_s`, so the moving reveal edge always crosses the red shading's
# boundaries mid-segment rather than jumping over them between frames.
PRE_FAULT_EDGE_S: float = 0.005
POST_FAULT_EDGE_S: float = 0.005

# Vertical headroom (fraction of the real peak) added above/below the
# recorded samples' max absolute voltage so the waveform never touches the
# axes; the range is kept symmetric about 0 like a real oscilloscope
# phase-to-ground view.
Y_HEADROOM_FRACTION: float = 0.08

# ---------------------------------------------------------------------------
# On-screen status text
# ---------------------------------------------------------------------------
# Status label shown while the reveal edge is before `trigger_time_s`.
STATUS_PRE_FAULT: str = "pre-fault"
# Status label while the reveal edge is inside [trigger_time_s, clear_time_s).
STATUS_FAULTED: str = "faulted"
# Status label once the reveal edge has passed `clear_time_s`.
STATUS_POST_FAULT: str = "post-fault"
# Decimal places for the on-screen simulated-time readout: 4 places resolves
# the log's real 200 us sample stepping (0.0004 s, 0.0006 s, ...).
SIM_TIME_DECIMALS: int = 4

# Keys every dpsim_transient_log.json must carry (run_dpsim.py writes all
# of them); checked structurally so a stale/malformed log is never plotted.
REQUIRED_LOG_KEYS: tuple[str, ...] = (
    "times", "va", "vb", "vc", "trigger_time_s", "clear_time_s", "target",
)


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


class TimelinePhase(NamedTuple):
    """One segment of the reveal timeline.

    Attributes:
        name: human-readable phase name (informational).
        anim_start: animation time (s) this segment starts at.
        anim_end: animation time (s) this segment ends at.
        sim_start: simulated time (s) the reveal edge starts at.
        sim_end: simulated time (s) the reveal edge ends at (== sim_start
            for holds).
    """

    name: str
    anim_start: float
    anim_end: float
    sim_start: float
    sim_end: float


def _missing_log_message() -> str:
    """Return the exact commands that produce dpsim_transient_log.json.

    Printed verbatim when the log is absent so the script never draws a
    fake waveform; matches this lab's README "Command" section.
    """
    return (
        f"[missing] {TRANSIENT_LOG_JSON} not found. Produce it with the Lab 5 "
        "walkthrough (see labs/05-spartan-chaosnet-transient-stream/README.md):\n"
        "  uv run labs/05-spartan-chaosnet-transient-stream/generate_topology.py --seed 42\n"
        "  uv run labs/05-spartan-chaosnet-transient-stream/run_dpsim.py "
        "--schedule chaos_schedule.yaml\n"
        "then re-run this animation script."
    )


def _build_timeline(trigger_s: float, clear_s: float, final_s: float) -> list[TimelinePhase]:
    """Build the reveal timeline from the log's real fault times.

    The five segments tile [0, VIDEO_DURATION_S] contiguously with no gaps
    or overlaps, and reveal a monotonically growing simulated-time prefix of
    the recording (holds have sim_start == sim_end). The pre/post sweep ends
    sit PRE_FAULT_EDGE_S / POST_FAULT_EDGE_S outside the fault window so the
    red shading's edges are always crossed mid-segment.

    Args:
        trigger_s: the log's trigger_time_s.
        clear_s: the log's clear_time_s.
        final_s: the log's last recorded sample time.

    Returns:
        Ordered segments covering animation time [0, VIDEO_DURATION_S].
    """
    pre_end = trigger_s - PRE_FAULT_EDGE_S
    dwell_end = clear_s + POST_FAULT_EDGE_S
    a = LEAD_IN_HOLD_S
    b = a + PRE_FAULT_SWEEP_S
    c = b + FAULT_DWELL_SWEEP_S
    d = c + POST_FAULT_SWEEP_S
    return [
        TimelinePhase("lead-in hold", 0.0, a, LEAD_HOLD_SIM_TIME_S, LEAD_HOLD_SIM_TIME_S),
        TimelinePhase("pre-fault sweep", a, b, LEAD_HOLD_SIM_TIME_S, pre_end),
        TimelinePhase("fault dwell", b, c, pre_end, dwell_end),
        TimelinePhase("post-fault sweep", c, d, dwell_end, final_s),
        TimelinePhase("final hold", d, VIDEO_DURATION_S, final_s, final_s),
    ]


def _reveal_sim_time(anim_t: float, phases: list[TimelinePhase]) -> float:
    """Map an animation time to the simulated time of the moving reveal edge.

    Piecewise-linear over the timeline: within a segment the edge advances
    at that segment's constant sweep speed; inside a hold it stays put.

    Args:
        anim_t: animation time (s), in [0, VIDEO_DURATION_S].
        phases: the timeline from _build_timeline().

    Returns:
        The simulated time (s) up to which samples are revealed.
    """
    for phase in phases:
        if anim_t <= phase.anim_end:
            if phase.anim_end == phase.anim_start:
                return phase.sim_start
            frac = (anim_t - phase.anim_start) / (phase.anim_end - phase.anim_start)
            return phase.sim_start + frac * (phase.sim_end - phase.sim_start)
    return phases[-1].sim_end


def _status_for(now: float, trigger_s: float, clear_s: float) -> tuple[str, str]:
    """Classify the reveal-edge simulated time against the log's fault window.

    Args:
        now: current reveal-edge simulated time (s).
        trigger_s: the log's trigger_time_s.
        clear_s: the log's clear_time_s.

    Returns:
        (status_label, status_color): the label is pre-fault / faulted /
        post-fault; the color is fault red while inside the window and axis
        ink otherwise, matching verify_stream.py's color roles.
    """
    if now < trigger_s:
        return STATUS_PRE_FAULT, COLOR_INK
    if now < clear_s:
        return STATUS_FAULTED, COLOR_FAULT
    return STATUS_POST_FAULT, COLOR_INK


def animate_transient(log: TransientLog, output: Path) -> None:
    """Render the real fault transient as a growing-reveal MP4.

    Builds the static scene (phase lines, red fault shading, dashed
    trigger/clear lines, fault label -- the same visual language as
    verify_stream.py's _plot_transient, plus phase B/C) and animates a
    moving reveal edge that uncovers samples whose time is <= the current
    edge time, with a live time/status readout and a cursor marker.

    Args:
        log: the parsed dpsim_transient_log.json.
        output: MP4 path to write.
    """
    times = np.asarray(log["times"], dtype=float)
    phase_series = {
        "va": np.asarray(log["va"], dtype=float),
        "vb": np.asarray(log["vb"], dtype=float),
        "vc": np.asarray(log["vc"], dtype=float),
    }
    trigger_s = float(log["trigger_time_s"])
    clear_s = float(log["clear_time_s"])
    final_s = float(times[-1])
    timeline = _build_timeline(trigger_s, clear_s, final_s)

    fig, ax = plt.subplots(figsize=(FIGURE_WIDTH_IN, FIGURE_HEIGHT_IN), dpi=FIGURE_DPI)
    ax.set_xlim(0.0, final_s)
    peak_abs = float(np.max(np.abs(np.concatenate(list(phase_series.values())))))
    y_half = peak_abs * (1.0 + Y_HEADROOM_FRACTION)
    ax.set_ylim(-y_half, y_half)

    line_va, = ax.plot([], [], color=COLOR_PHASE_A, linewidth=1.0, label="va")
    line_vb, = ax.plot([], [], color=COLOR_PHASE_B, linewidth=1.0, label="vb")
    line_vc, = ax.plot([], [], color=COLOR_PHASE_C, linewidth=1.0, label="vc")
    ax.axvspan(trigger_s, clear_s, color=COLOR_FAULT, alpha=0.12)
    ax.axvline(trigger_s, color=COLOR_FAULT, linestyle="--", linewidth=1.0)
    ax.axvline(clear_s, color=COLOR_FAULT, linestyle="--", linewidth=1.0)
    ax.text(
        (trigger_s + clear_s) / 2.0,
        y_half * 0.92,
        f"fault: {log['target']}",
        ha="center",
        color=COLOR_FAULT,
        fontsize=11,
    )
    now_line, = ax.plot([], [], color=COLOR_INK, linestyle=":", linewidth=1.2)
    now_line.set_ydata([-y_half, y_half])
    now_dot, = ax.plot(
        [], [], marker="o", markersize=5, color=COLOR_PHASE_A, linestyle="None"
    )
    status_text = ax.text(
        0.012,
        0.95,
        "",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=14,
        family="monospace",
        bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=COLOR_INK, alpha=0.9),
    )
    ax.set_xlabel("simulated time (s)", color=COLOR_INK)
    ax.set_ylabel("phase voltage (V)", color=COLOR_INK)
    ax.set_title(
        f"Lab 5 \u2014 chaos-net fault transient, {log['target']} line-to-ground"
    )
    ax.grid(True, color=COLOR_INK, linewidth=0.4, alpha=0.4)
    ax.legend(loc="upper right", fontsize=10, framealpha=0.9)
    for spine in ax.spines.values():
        spine.set_color(COLOR_INK)
    ax.tick_params(colors=COLOR_INK)

    artists: list[plt.Artist] = [line_va, line_vb, line_vc, now_line, now_dot, status_text]

    def init() -> list[plt.Artist]:
        """Empty first frame: clear every animated artist."""
        line_va.set_data([], [])
        line_vb.set_data([], [])
        line_vc.set_data([], [])
        now_line.set_xdata([])
        now_dot.set_data([], [])
        status_text.set_text("")
        return artists

    def update(frame_index: int) -> list[plt.Artist]:
        """Reveal all samples with time <= the edge's current simulated time."""
        anim_t = frame_index / ANIMATION_FPS
        now = _reveal_sim_time(anim_t, timeline)
        mask = times <= now
        line_va.set_data(times[mask], phase_series["va"][mask])
        line_vb.set_data(times[mask], phase_series["vb"][mask])
        line_vc.set_data(times[mask], phase_series["vc"][mask])
        now_line.set_xdata([now, now])
        last_idx = int(np.searchsorted(times, now, side="right") - 1)
        if last_idx >= 0:
            now_dot.set_data([times[last_idx]], [phase_series["va"][last_idx]])
        else:
            now_dot.set_data([], [])
        label, color = _status_for(now, trigger_s, clear_s)
        status_text.set_text(f"t = {now:.{SIM_TIME_DECIMALS}f} s\n{label}")
        status_text.set_color(color)
        return artists

    anim = FuncAnimation(
        fig,
        update,
        init_func=init,
        frames=range(N_FRAMES),
        blit=False,
    )
    writer = FFMpegWriter(
        fps=ANIMATION_FPS,
        codec=VIDEO_CODEC,
        bitrate=ANIM_BITRATE,
        extra_args=[
            EXTRA_ARG_PIX_FMT_FLAG,
            FFMPEG_PIX_FMT,
            EXTRA_ARG_MOVFLAGS_FLAG,
            FFMPEG_FASTART,
        ],
    )
    anim.save(output, writer=writer)
    plt.close(fig)


def main() -> None:
    """CLI entry point: load the real log (or print the exact commands to
    produce it and exit non-zero), then render the MP4."""
    if not TRANSIENT_LOG_JSON.exists():
        print(_missing_log_message(), file=sys.stderr)
        sys.exit(1)
    log = json.loads(TRANSIENT_LOG_JSON.read_text())
    missing_keys = [key for key in REQUIRED_LOG_KEYS if key not in log]
    if missing_keys:
        print(
            f"[invalid] {TRANSIENT_LOG_JSON} is missing keys: {missing_keys}",
            file=sys.stderr,
        )
        sys.exit(1)
    animate_transient(log, OUTPUT_MP4)
    print(
        f"[animate] wrote {OUTPUT_MP4}: {N_FRAMES} frames, "
        f"{VIDEO_DURATION_S:.1f}s at {ANIMATION_FPS} fps "
        f"({log['target']} fault, trigger {log['trigger_time_s']}s / "
        f"clear {log['clear_time_s']}s, {len(log['times'])} samples)"
    )


if __name__ == "__main__":
    main()
