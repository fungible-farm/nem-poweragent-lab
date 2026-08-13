#!/usr/bin/env python3
"""Lab 5 -- the classic hand-drawn phasor diagram, rendered as an actual 3D
vector plot instead of a flat 2D polar sketch (docs/backlog/0004/0006 family
of "generated views", same one-state-machine principle as every other view_*
script here -- see phase_model.py's module docstring).

Every other 3D view in this lab already exists and is deliberately NOT
duplicated here:

- `view_3d_audio.py` plots a 3D *trajectory* (x=va, y=vb, z=vc) of the raw
  instantaneous waveform over the whole recording -- a phase-space portrait,
  not a phasor diagram.
- `view_rx_trajectory.py` plots apparent impedance Z(t)=V1(t)/I1(t) on a flat
  2D R-X plane.
- `view_telemetry_rates.py` / `animate_telemetry_rates.py` plot |V1|/|V0|/|V2|
  magnitude-vs-time panels -- magnitude only, phase angle is discarded.

None of them show what a protection engineer actually draws by hand on a
whiteboard: three phasors (Va, Vb, Vc), each a 2D complex vector from a common
origin, at ONE instant, with their 120-degree separation and relative
magnitude both visible at once. This module draws exactly that -- three
`phase_model.phasor_frames()` complex phasors as real 3D arrows in the x=Re,
y=Im complex plane -- but adds a third axis to make a single static PNG show
the fault's whole story instead of just one frozen instant.

**Why the third (vertical) axis is simulated time, not something else**: the
two horizontal axes (Re, Im) are already spoken for by the phasor's own
complex plane -- that pair is what makes it recognizably "the phasor
diagram." The only genuinely informative choice left for the vertical axis is
time: stacking several phasor-diagram snapshots at their own real simulated
time gives one static picture of how the diagram itself deforms through the
fault (collapse at fault onset, partial recovery mid-fault, the post-clear
swell, settling back down) -- literally a "phasor diagram through time," not
an arbitrary 3rd dimension bolted on for the sake of using mplot3d. Using
magnitude, or frequency, or an unrelated fourth quantity for the vertical
axis would either duplicate information already encoded in the vector's own
length, or need a signal this waveform doesn't carry.

**Why only 5 snapshots, not every frame**: `phase_model.phasor_frames()`
produces ~54 frames over this recording's ~0.55 s at its default 100 Hz rate
-- plotting all of them as stacked phasor triads would be an unreadable wall
of overlapping arrows, not a presenter-usable figure. Instead this module
picks 5 representative instants (pre-fault steady state, fault onset,
mid-fault, post-clear, post-fault recovery -- see `_representative_instants()`),
the same handful of moments a protection engineer would narrate a fault
event by.

Nothing here is a second phasor estimator: `phase_model.phasor_frames()` is
reused unchanged, exactly like every other view_*.py script in this lab.
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

from phase_model import (  # noqa: E402
    FUNDAMENTAL_HZ,
    ThreePhaseWaveform,
    phasor_frames,
)

LAB_DIR = Path(__file__).resolve().parent
TRANSIENT_LOG_JSON = LAB_DIR / "dpsim_transient_log.json"
OUTPUT_PNG = LAB_DIR / "sample_phasor_3d.png"

REQUIRED_LOG_KEYS: tuple[str, ...] = (
    "times", "va", "vb", "vc", "trigger_time_s", "clear_time_s", "target",
)

# Same reasoning as view_rx_trajectory.py's SWITCHING_EXCLUSION_CYCLES: a
# one-cycle DFT phasor estimate (phase_model.phasor_frames()) is only a
# physically meaningful snapshot when its analysis window doesn't straddle a
# real switching discontinuity (the fault trigger/clear instants). Snapshot
# instants placed "just after" a switching event are offset by one full
# fundamental cycle so the frame nearest that instant has already cleared
# the contaminated window, not landed inside it.
SNAPSHOT_MARGIN_CYCLES: int = 1

# Ordered (label, fraction-of-schedule) recipe for the 5 representative
# instants -- see the module docstring for why 5, not every frame. Times are
# derived from this run's own real trigger_time_s/clear_time_s/duration
# (never hard-coded seconds), so the snapshot set stays correct if the
# fault schedule ever changes.
SNAPSHOT_LABELS: tuple[str, ...] = (
    "pre-fault steady state",
    "fault onset",
    "mid-fault",
    "post-clear",
    "post-fault recovery",
)

# Standard isometric-projection viewing angles for mplot3d: elevation =
# arcsin(tan(30 deg)) ~= 35.264 deg, azimuth = 45 deg -- the textbook
# construction that puts all three axes at equal foreshortening (each of the
# +/-x, +/-y, +/-z directions reads at the same visual scale), unlike
# mplot3d's default (elev=30, azim=-60) which was tuned for x/y/z trajectory
# plots like view_3d_audio.py's, not for a vector diagram where all three
# axes need to look comparably readable at once.
ISO_ELEV_DEG: float = 35.264
ISO_AZIM_DEG: float = 45.0

# Circle point count for the per-snapshot magnitude reference ring (cosmetic
# smoothness only, not a physical quantity).
REFERENCE_CIRCLE_POINTS: int = 91

# Phase colors: same hex values as view_telemetry_rates.py's
# COLOR_PHASE_A/B/C (CVD-validated there via the dataviz skill's
# validate_palette.js) -- kept in sync by eye since this lab has no shared
# plotting-constants module; fault red / axis ink also match every other
# view_*.py script here.
COLOR_PHASE_A = "#2a78d6"
COLOR_PHASE_B = "#4e9a63"
COLOR_PHASE_C = "#c07a2b"
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


def _representative_instants(
    trigger_s: float, clear_s: float, duration_s: float,
) -> list[tuple[str, float]]:
    """The 5 named target times (s), derived from this run's own real
    schedule -- see SNAPSHOT_LABELS and the module docstring for why these 5.

    Args:
        trigger_s: fault trigger time (s).
        clear_s: fault clearing time (s).
        duration_s: recording duration (s).

    Returns:
        Ordered [(label, target_time_s), ...] matching SNAPSHOT_LABELS.
    """
    margin_s = SNAPSHOT_MARGIN_CYCLES / FUNDAMENTAL_HZ
    targets = (
        max(0.0, trigger_s - margin_s),           # pre-fault steady state
        trigger_s + margin_s,                      # fault onset
        (trigger_s + clear_s) / 2.0,                # mid-fault
        clear_s + margin_s,                         # post-clear
        max(clear_s + margin_s, duration_s - margin_s),  # post-fault recovery
    )
    return list(zip(SNAPSHOT_LABELS, targets))


def _nearest_frame_indices(
    frame_times: np.ndarray, targets: list[tuple[str, float]],
) -> list[tuple[str, int]]:
    """Map each (label, target_time_s) to the nearest real phasor frame index.

    Args:
        frame_times: phasor_frames()'s frame_times_s array.
        targets: output of `_representative_instants()`.

    Returns:
        [(label, frame_index), ...] -- same order as `targets`.
    """
    return [(label, int(np.argmin(np.abs(frame_times - t)))) for label, t in targets]


def _reference_circle(radius: float, z: float, n: int = REFERENCE_CIRCLE_POINTS) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Points (x, y, z) tracing a constant-radius circle at height `z` -- the
    pre-fault magnitude drawn at every snapshot height so a reader can see
    each phase's collapse/swell relative to the same fixed baseline, without
    needing to compare numbers across panels.

    Args:
        radius: reference circle radius (kV) -- the pre-fault snapshot's own
            measured |Va| (never an assumed nameplate value).
        z: snapshot height (simulated time, s).
        n: point count (cosmetic smoothness).

    Returns:
        (x, y, z) arrays tracing the circle.
    """
    theta = np.linspace(0.0, 2.0 * np.pi, n)
    return radius * np.cos(theta), radius * np.sin(theta), np.full(n, z)


def render(log: TransientLog, path: Path) -> dict[str, float]:
    """Render the isometric 3D phasor-diagram-through-time PNG.

    Args:
        log: the validated transient log.
        path: output PNG path.

    Returns:
        {label: |Va| kV} at each snapshot -- the real, measured magnitudes
        used to draw the figure (printed by main(), never fabricated).
    """
    wave = ThreePhaseWaveform.from_log(log)
    trigger_s = float(log["trigger_time_s"])
    clear_s = float(log["clear_time_s"])

    frame_times, ph_a, ph_b, ph_c = phasor_frames(wave)
    targets = _representative_instants(trigger_s, clear_s, wave.duration_s)
    snapshots = _nearest_frame_indices(frame_times, targets)

    fig = plt.figure(figsize=(10.0, 8.5), dpi=130)
    ax = fig.add_subplot(111, projection="3d")

    # Pre-fault |Va| (kV) is the fixed reference-circle radius for every
    # snapshot -- the real measured pre-fault magnitude, not an assumed
    # nameplate value.
    _, pre_fault_idx = snapshots[0]
    reference_kv = float(abs(ph_a[pre_fault_idx])) / 1000.0

    # Plotted z-height is the snapshot's ORDINAL position (0..4), not its
    # duration-scaled real time: the 5 real snapshot times are unevenly
    # spaced (2 of them only SNAPSHOT_MARGIN_CYCLES/FUNDAMENTAL_HZ = 20 ms
    # apart, straddling the 150 ms fault, while pre-fault and post-fault-
    # recovery sit much further out) -- duration-scaling the z-axis would
    # cram the fault-onset/mid-fault/post-clear fans into a visually
    # unreadable stack. Evenly spacing them by rank keeps every fan legible
    # while staying honest about the real times: each z-tick is labeled with
    # its own real, measured `frame_times_s` value (see the printed summary
    # too), so nothing about *when* each snapshot was taken is hidden or
    # fabricated -- only its on-screen spacing is chosen for legibility, the
    # same "same physics, different axis extent" move view_rx_trajectory.py's
    # zoomed inset already makes.
    magnitudes_kv: dict[str, float] = {}
    z_ticks: list[float] = []
    z_ticklabels: list[str] = []
    for i, (label, idx) in enumerate(snapshots):
        t = float(frame_times[idx])
        z = float(i)
        z_ticks.append(z)
        z_ticklabels.append(f"{t:.3f}s")
        in_fault = trigger_s <= t <= clear_s
        circle_color = COLOR_FAULT if in_fault else COLOR_INK
        cx, cy, cz = _reference_circle(reference_kv, z)
        ax.plot(
            cx, cy, cz, color=circle_color, lw=0.8, ls="--", alpha=0.55,
            label=f"pre-fault |Va| reference ({reference_kv:.2f} kV)" if i == 0 else None,
        )
        magnitudes_kv[label] = float(abs(ph_a[idx])) / 1000.0
        # Label placed behind the circle (negative-y) so it clears the
        # phasor arrows, which for this balanced pre-fault system start near
        # the +x axis (Va's own reference angle).
        ax.text(
            0.0, -reference_kv * 1.35, z,
            f"{label}\nt={t:.3f}s", color=circle_color, fontsize=7.5,
            ha="center", va="center",
        )

    # Vertical guide line through the common origin -- makes the "stacked at
    # different times, same electrical origin" reading explicit.
    ax.plot(
        [0.0, 0.0], [0.0, 0.0], [0.0, float(len(snapshots) - 1)],
        color=COLOR_INK, lw=0.6, ls=":", alpha=0.5,
    )

    # Each phasor is drawn as a plain 3D line segment (origin -> tip) plus a
    # tip marker, not mplot3d's Axes3D.quiver(): quiver's arrowhead
    # construction degenerates (produces huge phantom shafts) when many
    # vectors share a zero z-component, which every phasor here does by
    # construction (each snapshot's Va/Vb/Vc all lie flat at that snapshot's
    # own height) -- confirmed by direct experiment against this exact data.
    # A plain line + marker is the same convention view_3d_audio.py already
    # uses for its 3D trajectory, just applied per-vector instead of as one
    # continuous path.
    for ph, color, name in (
        (ph_a, COLOR_PHASE_A, "Va"), (ph_b, COLOR_PHASE_B, "Vb"), (ph_c, COLOR_PHASE_C, "Vc"),
    ):
        for i, (_, idx) in enumerate(snapshots):
            z = float(i)
            re_kv = float(ph[idx].real) / 1000.0
            im_kv = float(ph[idx].imag) / 1000.0
            ax.plot(
                [0.0, re_kv], [0.0, im_kv], [z, z],
                color=color, lw=1.8, alpha=0.9,
                label=name if i == 0 else None,
            )
            ax.scatter([re_kv], [im_kv], [z], color=color, s=22, marker="o")

    ax.set_xlabel("Re(V) (kV)", color=COLOR_INK)
    ax.set_ylabel("Im(V) (kV)", color=COLOR_INK)
    ax.set_zlabel("simulated time (snapshot order; real times labeled)", color=COLOR_INK)
    ax.set_zticks(z_ticks)
    ax.set_zticklabels(z_ticklabels)
    ax.set_title(
        f"Lab 5 -- {log['target']} fault, 3D isometric phasor diagram through "
        f"time -- Va/Vb/Vc at 5 representative instants"
    )
    ax.view_init(elev=ISO_ELEV_DEG, azim=ISO_AZIM_DEG)
    ax.tick_params(colors=COLOR_INK)
    ax.legend(loc="upper left", fontsize=8)
    # bbox_inches="tight" (not fig.tight_layout()) trims the saved PNG's
    # whitespace here: the per-snapshot text labels are placed in 3D data
    # coordinates outside the axes' own data limits (deliberately, to clear
    # the phasor arrows -- see the ax.text() call above), which
    # fig.tight_layout() cannot account for and warns about on every run.
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)

    return magnitudes_kv


def main() -> None:
    """Render sample_phasor_3d.png and print the real per-snapshot |Va|."""
    log = _load_log()
    magnitudes_kv = render(log, OUTPUT_PNG)
    print(f"[phasor3d] wrote {OUTPUT_PNG}")
    for label, kv in magnitudes_kv.items():
        print(f"  {label}: |Va| = {kv:.3f} kV")


if __name__ == "__main__":
    main()
