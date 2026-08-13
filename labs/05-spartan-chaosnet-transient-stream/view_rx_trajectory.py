#!/usr/bin/env python3
"""Lab 5 -- R-X apparent-impedance trajectory (mho-circle / distance-relay)
view of the real DPsim fault transient (docs/backlog/0006, option 2).

Renders run_dpsim.py's real `dpsim_transient_log.json` (extended by this same
backlog item to also capture `ia_line`/`ib_line`/`ic_line` -- the
fault-adjacent PiLine's real `i_intf` current, alongside the fault bus's
already-captured `va`/`vb`/`vc` `v_intf` voltage) into
`sample_rx_trajectory.png`: the apparent impedance

    Z(t) = V1(t) / I1(t)

plotted on the complex R-X plane, together with a standard self-polarized
mho relay characteristic circle for context. This is literally the plot a
distance-relay engineer looks at -- nothing like it exists in Lab 5's other
six views (all voltage/time or phase-space, never impedance).

Positive-sequence V1/I1 (`phase_model.positive_sequence()`, reused directly,
not reimplemented) are used rather than a single raw phase because
docs/backlog/0006 option 1's real, measured finding is that Lab 5's actual
fault is symmetric across all three phases (chaosnet.py's fault switch is a
diagonal per-phase resistance matrix, not a genuine single-line-to-ground
model -- see phase_model.py's module docstring). For a symmetric fault every
phase and every sequence quantity carries the same magnitude information, so
positive-sequence impedance -- the standard, fault-type-independent
quantity a real distance relay computes -- is the correct, general choice
here, not an arbitrary one.

**What this view actually measures, honestly**: the fault-adjacent line is
selected as the line directly connecting the network's source bus
(`ext_grid_bus`) to the fault bus (chaosnet._fault_adjacent_line()), so the
apparent impedance here approximates what a relay CT/PT pair co-located with
the fault bus itself (looking back up the source line) would compute -- not
the more textbook "relay at the sending/source end looking down the line",
since run_dpsim.py only ever captures voltage at the fault bus, never at the
source bus. See this module's own printed summary for what the real seed-42
run's trajectory actually does (its shape is reported as measured, not
assumed to match the textbook load-to-fault swing).

Nothing here is a new capture path beyond run_dpsim.py's small i_intf
addition, and no new dependency: complex-plane plotting is plain matplotlib,
reusing phase_model.py's existing DFT/phasor machinery unchanged.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import TypedDict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np

import chaosnet  # noqa: E402
from phase_model import (  # noqa: E402
    FUNDAMENTAL_HZ,
    ThreePhaseWaveform,
    phasor_frames,
    positive_sequence,
)

LAB_DIR = Path(__file__).resolve().parent
TRANSIENT_LOG_JSON = LAB_DIR / "dpsim_transient_log.json"
SAMPLE_TOPOLOGY_JSON = LAB_DIR / "sample_topology.json"
OUTPUT_PNG = LAB_DIR / "sample_rx_trajectory.png"

REQUIRED_LOG_KEYS: tuple[str, ...] = (
    "times", "va", "vb", "vc", "ia_line", "ib_line", "ic_line",
    "fault_adjacent_line", "trigger_time_s", "clear_time_s", "target",
)

# Zone-1 distance-relay reach setting: RELAY_REACH_PERCENT of the protected
# line's own real positive-sequence impedance (R + jX, computed the same way
# chaosnet.to_dpsim_emt_system() derives its own PiLine parameters from real
# SimBench r_ohm_per_km/x_ohm_per_km * length_km -- never invented). 80% (not
# 100%) is the standard textbook underreach convention for a first-zone mho
# element: set below the full line impedance so relay/CT/VT measurement
# tolerance can never cause the element to "see" past the line's own far bus
# into the next line section (a real overreach/misoperation risk at 100%).
# See e.g. Blackburn & Domin, "Protective Relaying: Principles and
# Applications" (distance-protection chapter), or IEEE Std C37.113 ("IEEE
# Guide for Protective Relay Applications to Transmission Lines") for this
# convention.
RELAY_REACH_PERCENT: float = 0.80

# Guard against a divide-by-zero blowup if a frame's positive-sequence
# current magnitude ever underflows to exactly zero -- shouldn't happen with
# a real solve's continuous load current, but keeps Z(t) finite (masked out
# of the plotted trajectory and the printed summary) rather than raising or
# silently plotting inf/NaN as if it were real data.
MIN_I1_A: float = 1e-9

# Real, measured finding (not fixed by tuning, excluded by definition): a
# one-cycle DFT phasor estimate (phase_model.phasor_frames()) is only valid
# when its analysis window contains one full, undisturbed fundamental cycle.
# Whenever a real switching discontinuity (this schedule's fault trigger or
# clear instant) falls inside that window, the DFT's periodicity assumption
# is violated and the resulting Z(t)=V1(t)/I1(t) can be an artifact with no
# physical meaning -- confirmed directly against this lab's own real seed-42
# run: the frame whose window straddles the clearing instant produces
# Z ~ (148+324j) ohm, a wrong-quadrant, order-of-magnitude outlier next to
# every neighbouring frame's ~1-1000 ohm, negative-real-part values. Frames
# within one full fundamental cycle (phase_model.FUNDAMENTAL_HZ) of either
# switching instant are excluded from the trajectory and summary stats below
# -- the same reason real numerical distance relays supervise their mho
# element with a dedicated transient/fault-detector element rather than
# trusting a raw single-cycle Z=V/I estimate straight through a switching
# event.
SWITCHING_EXCLUSION_CYCLES: int = 1

COLOR_TRAJ = "#2a78d6"
COLOR_FAULT = "#e34948"
COLOR_INK = "#898781"
# Mho-circle color: a violet distinct from the trajectory blue and fault red
# (same hue family already validated CVD-safe for this lab's other overlay
# use, view_telemetry_rates.py's COLOR_SEQ_NEG).
COLOR_RELAY = "#4a3aa7"


class TransientLog(TypedDict):
    """The JSON shape written by run_dpsim.py -- same keys, same semantics.
    See run_dpsim.py's module docstring "key convention" section."""

    times: list[float]
    va: list[float]
    vb: list[float]
    vc: list[float]
    ia_line: list[float]
    ib_line: list[float]
    ic_line: list[float]
    fault_adjacent_line: str
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
        print(
            f"[invalid] {TRANSIENT_LOG_JSON} missing keys: {missing} -- "
            "re-run run_dpsim.py to regenerate it with the ia_line/ib_line/"
            "ic_line current tap (docs/backlog/0006 option 2)",
            file=sys.stderr,
        )
        sys.exit(1)
    return log


def _load_fault_adjacent_line_impedance(line_name: str) -> complex:
    """Real per-line R/X (ohm) of the tapped fault-adjacent PiLine, read
    from the committed `sample_topology.json` fixture -- the same topology
    run_dpsim.py solved against -- never invented.

    Args:
        line_name: dpsimpy component name, e.g. "line0_12" (matches
            chaosnet.fault_adjacent_line_name()'s naming exactly).

    Returns:
        Z_line = R_total + jX_total (ohm), computed the same way
        chaosnet.to_dpsim_emt_system() derives its own PiLine parameters.

    Raises:
        FileNotFoundError: if sample_topology.json is missing.
        ValueError: if line_name doesn't match any line in that topology.
    """
    if not SAMPLE_TOPOLOGY_JSON.exists():
        raise FileNotFoundError(
            f"{SAMPLE_TOPOLOGY_JSON} not found -- run generate_topology.py "
            "--seed 42 first"
        )
    topology = chaosnet.read_topology_json(SAMPLE_TOPOLOGY_JSON)
    m = re.fullmatch(r"line(\d+)_(\d+)", line_name)
    if not m:
        raise ValueError(f"unrecognized line component name: {line_name!r}")
    from_bus, to_bus = int(m.group(1)), int(m.group(2))
    for line in topology["lines"]:
        if line["from_bus"] == from_bus and line["to_bus"] == to_bus:
            r_total = line["r_ohm_per_km"] * line["length_km"]
            x_total = line["x_ohm_per_km"] * line["length_km"]
            return complex(r_total, x_total)
    raise ValueError(f"{line_name!r} not found in {SAMPLE_TOPOLOGY_JSON}")


def compute_trajectory(log: TransientLog) -> tuple[np.ndarray, np.ndarray]:
    """Positive-sequence apparent impedance Z(t) = V1(t)/I1(t), at the
    phasor-estimator's own frame rate, reusing phase_model.py's existing
    DFT/phasor machinery (`phasor_frames()`/`positive_sequence()`) --
    no second, hand-rolled phasor estimator.

    Args:
        log: the validated transient log.

    Returns:
        (frame_times_s, z_ohm) -- z_ohm is complex apparent impedance per
        frame (R = z.real, X = z.imag); entries where the positive-sequence
        current magnitude underflows MIN_I1_A, or whose one-cycle analysis
        window falls within SWITCHING_EXCLUSION_CYCLES of a real switching
        instant (trigger_time_s/clear_time_s), are NaN -- see MIN_I1_A and
        SWITCHING_EXCLUSION_CYCLES's module-level docstrings for why.
    """
    times = np.asarray(log["times"], dtype=float)
    v_wave = ThreePhaseWaveform(
        times,
        np.asarray(log["va"], dtype=float),
        np.asarray(log["vb"], dtype=float),
        np.asarray(log["vc"], dtype=float),
    )
    i_wave = ThreePhaseWaveform(
        times,
        np.asarray(log["ia_line"], dtype=float),
        np.asarray(log["ib_line"], dtype=float),
        np.asarray(log["ic_line"], dtype=float),
    )
    # Both waveforms share the identical `times` array, so phasor_frames()'s
    # frame-centering loop (driven only by len(wave.times)) produces the
    # identical frame_times_s grid for both -- one frame-time array is
    # reused below rather than asserted equal twice.
    frame_times, va_ph, vb_ph, vc_ph = phasor_frames(v_wave)
    _, ia_ph, ib_ph, ic_ph = phasor_frames(i_wave)

    v1 = positive_sequence(va_ph, vb_ph, vc_ph)
    i1 = positive_sequence(ia_ph, ib_ph, ic_ph)

    i1_mag = np.abs(i1)
    exclusion_s = SWITCHING_EXCLUSION_CYCLES / FUNDAMENTAL_HZ
    trigger_s = float(log["trigger_time_s"])
    clear_s = float(log["clear_time_s"])
    near_switch = (
        (np.abs(frame_times - trigger_s) < exclusion_s)
        | (np.abs(frame_times - clear_s) < exclusion_s)
    )

    z = np.full(v1.shape, np.nan + 1j * np.nan, dtype=complex)
    ok = (i1_mag >= MIN_I1_A) & ~near_switch
    z[ok] = v1[ok] / i1[ok]
    return frame_times, z


def _mho_circle(z_reach: complex, n: int = 361) -> tuple[np.ndarray, np.ndarray]:
    """Points (R, X) on the standard self-polarized mho relay
    characteristic: the circle whose diameter is the segment from the
    origin (the relay's own location, 0+0j) to `z_reach` -- center =
    z_reach/2, radius = |z_reach|/2. Textbook mho circle construction (see
    e.g. Blackburn & Domin, "Protective Relaying," distance-protection
    chapter): the relay's zone-1 element operates for any measured Z
    strictly inside this circle.

    Args:
        z_reach: the relay's reach-point impedance (ohm) --
            RELAY_REACH_PERCENT of the protected line's own real impedance.
        n: number of points used to trace the circle.

    Returns:
        (r_ohm, x_ohm) arrays tracing the circle.
    """
    center = z_reach / 2.0
    radius = abs(z_reach) / 2.0
    theta = np.linspace(0.0, 2.0 * np.pi, n)
    circle = center + radius * np.exp(1j * theta)
    return circle.real, circle.imag


class RxSummary(TypedDict):
    """Real, computed figures from one render() call -- printed by main(),
    never asserted/assumed."""

    z_line_ohm: complex
    z_reach_ohm: complex
    pre_fault_median_abs_z: float
    fault_window_min_abs_z: float | None
    fault_window_entered_mho: bool | None


def render(log: TransientLog, path: Path) -> RxSummary:
    """Render the R-X trajectory PNG and return the real, measured summary
    figures (never fabricated -- see docs/backlog/0006 option 2's own
    honesty note about not forcing this to look like the textbook shape).

    Args:
        log: the validated transient log.
        path: output PNG path.

    Returns:
        RxSummary of this render.
    """
    frame_times, z = compute_trajectory(log)
    trigger_s = float(log["trigger_time_s"])
    clear_s = float(log["clear_time_s"])
    fault_mask = (frame_times >= trigger_s) & (frame_times <= clear_s)
    finite = np.isfinite(z.real) & np.isfinite(z.imag)

    line_name = log["fault_adjacent_line"]
    z_line = _load_fault_adjacent_line_impedance(line_name)
    z_reach = z_line * RELAY_REACH_PERCENT
    circle_r, circle_x = _mho_circle(z_reach)
    center = z_reach / 2.0
    radius = abs(z_reach) / 2.0

    pre_mask = finite & ~fault_mask
    dur_mask = finite & fault_mask
    pre_abs = np.abs(z[pre_mask])
    dur_abs = np.abs(z[dur_mask])
    fault_window_min_abs_z = float(dur_abs.min()) if dur_abs.size else None
    fault_window_entered_mho = (
        bool(np.any(np.abs(z[dur_mask] - center) <= radius)) if dur_abs.size else None
    )

    fig, ax = plt.subplots(figsize=(9.0, 8.0), dpi=130)
    ax.set_aspect("equal", adjustable="datalim")

    def _draw(a: plt.Axes, show_labels: bool) -> None:
        a.plot(
            circle_r, circle_x, color=COLOR_RELAY, lw=1.6, ls="--",
            label=(
                f"mho reach ({RELAY_REACH_PERCENT * 100:.0f}% of {line_name}'s "
                f"Z={abs(z_line):.2f} ohm -> {abs(z_reach):.2f} ohm)"
                if show_labels else None
            ),
        )
        a.plot(
            [0.0, z_reach.real], [0.0, z_reach.imag],
            color=COLOR_RELAY, lw=0.8, ls=":", alpha=0.7,
        )
        for mask, color, label in (
            (pre_mask, COLOR_TRAJ, "Z(t) pre + post-clear"),
            (dur_mask, COLOR_FAULT, f"Z(t) fault {trigger_s:.2f}-{clear_s:.2f} s"),
        ):
            if mask.sum() > 1:
                a.plot(
                    z.real[mask], z.imag[mask], color=color, lw=1.0,
                    marker=".", ms=3, alpha=0.9,
                    label=label if show_labels else None,
                )
        a.scatter(
            [0.0], [0.0], color=COLOR_INK, s=36, marker="+",
            label="relay location (origin)" if show_labels else None,
        )
        if finite.any():
            first_i = int(np.argmax(finite))
            last_i = len(finite) - 1 - int(np.argmax(finite[::-1]))
            a.scatter(
                [z.real[first_i]], [z.imag[first_i]], color=COLOR_INK, s=24,
                label="start" if show_labels else None,
            )
            a.scatter(
                [z.real[last_i]], [z.imag[last_i]], color=COLOR_FAULT, s=24, marker="x",
                label="end" if show_labels else None,
            )
        a.axhline(0.0, color=COLOR_INK, lw=0.5, alpha=0.5)
        a.axvline(0.0, color=COLOR_INK, lw=0.5, alpha=0.5)

    _draw(ax, show_labels=True)
    ax.set_xlabel("R (ohm)")
    ax.set_ylabel("X (ohm)")
    ax.set_title(
        f"Lab 5 -- {log['target']} fault, apparent impedance Z(t)=V1(t)/I1(t) "
        f"on {line_name} -- R-X plane"
    )
    ax.legend(loc="lower left", fontsize=7)

    # Real-scale finding, not a plot-hiding trick: normal load impedance
    # (~hundreds of ohm on this lightly-loaded line) sits orders of
    # magnitude outside the mho reach circle (a fraction of an ohm, since
    # this line is only length_km=0.6 km), so the full-scale axes above
    # compress the reach circle and the fault-window trajectory into an
    # unreadable dot -- exactly what a real distance-relay display also
    # shows (load impedance is normally far outside the reach zone; that
    # separation is the point of a distance element). The zoomed inset below
    # shows the same real data at the reach-circle's own scale, sized from
    # the real computed reach/fault-window extent (never a fixed guess).
    zoom_candidates = [radius]
    if dur_abs.size:
        zoom_candidates.append(float(dur_abs.max()))
    zoom_extent = max(zoom_candidates) * 1.5
    ax_inset = ax.inset_axes([0.55, 0.55, 0.42, 0.42])
    _draw(ax_inset, show_labels=False)
    ax_inset.set_xlim(-zoom_extent, zoom_extent)
    ax_inset.set_ylim(-zoom_extent, zoom_extent)
    ax_inset.set_aspect("equal", adjustable="box")
    ax_inset.set_title("zoom: reach-circle scale", fontsize=8)
    ax_inset.tick_params(labelsize=6)
    ax.indicate_inset_zoom(ax_inset, edgecolor=COLOR_INK)

    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)

    return {
        "z_line_ohm": z_line,
        "z_reach_ohm": z_reach,
        "pre_fault_median_abs_z": float(np.median(pre_abs)) if pre_abs.size else float("nan"),
        "fault_window_min_abs_z": fault_window_min_abs_z,
        "fault_window_entered_mho": fault_window_entered_mho,
    }


def main() -> None:
    """Render sample_rx_trajectory.png and print the real, measured R-X
    summary -- including whether the fault-window trajectory actually
    entered the mho reach circle, reported as measured rather than assumed."""
    log = _load_log()
    summary = render(log, OUTPUT_PNG)
    print(f"[rx] wrote {OUTPUT_PNG}")
    print(
        f"  fault-adjacent line {log['fault_adjacent_line']}: "
        f"Z_line={summary['z_line_ohm']:.3f} ohm, "
        f"{RELAY_REACH_PERCENT * 100:.0f}% mho reach={summary['z_reach_ohm']:.3f} ohm "
        f"(|Z_reach|={abs(summary['z_reach_ohm']):.2f} ohm)"
    )
    print(f"  |Z| pre/post-fault median: {summary['pre_fault_median_abs_z']:.2f} ohm")
    if summary["fault_window_min_abs_z"] is not None:
        print(f"  |Z| fault-window minimum: {summary['fault_window_min_abs_z']:.2f} ohm")
        if summary["fault_window_entered_mho"]:
            print(
                "  the fault-window trajectory DID cross inside the mho reach "
                f"circle -- the textbook 'relay would trip' picture, measured, "
                "not assumed"
            )
        else:
            print(
                "  the fault-window trajectory did NOT cross inside the mho "
                f"reach circle at {RELAY_REACH_PERCENT * 100:.0f}% reach -- see "
                f"{OUTPUT_PNG.name} for the real measured shape (reported "
                "honestly, not forced to match the textbook swing; this fault "
                "is a partial 0.5 ohm impedance-limited three-phase fault at "
                "the fault bus itself, not a bolted remote fault along the "
                "tapped line -- see chaosnet.FAULT_CLOSED_RESISTANCE_OHM and "
                "docs/backlog/0006 option 2's own honesty note)"
            )
    else:
        print("  no finite fault-window samples (positive-sequence current underflowed MIN_I1_A)")


if __name__ == "__main__":
    main()
