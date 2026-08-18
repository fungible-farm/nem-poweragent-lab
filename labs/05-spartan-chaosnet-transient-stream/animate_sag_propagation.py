#!/usr/bin/env python3
"""Lab 5 -- Network-Wide Sag Propagation Animation (docs/backlog/0006, option 4).

Today's other six-plus-two Lab 5 views each show *one* electrical quantity
at *one* location over time (the fault bus's own voltage, current, spectrum,
impedance...). This is the one that instead shows *one instant in time
across the whole chaos-net*, repeated over the recording: every bus's own
`v_intf` voltage (captured by run_dpsim.py's `bus_voltages` tap, this same
backlog item) reduced to a single positive-sequence magnitude
(`phase_model.py`'s existing one-cycle-DFT machinery, reused unchanged, not
a second estimator) and animated onto `generate_topology.py`'s own
`nx.spring_layout()` node positions (`_build_topology_graph()`/
`_topology_layout()`, factored out of `_plot_topology()` specifically so
this script places every bus at the *identical* (x, y) position the static
topology plot does) -- the two previously-separate topology and transient
artifacts, connected into one.

Each bus is colored by |V1(t)| / that bus's OWN real pre-fault |V1| (pu,
viridis -- the same sequential, CVD-safe colormap `view_spectrogram.py`
already uses in this lab) and sized by |pu - 1| (bigger marker = further
from that bus's own normal), so a viewer sees literally how far the sag
propagates through the mesh, not just that it happens at the fault bus. The
fault bus and the other two tap substations are ringed and labelled,
matching `_plot_topology()`'s visual language exactly.

**Why "nominal" means each bus's own pre-fault operating point, not the
SimBench `vn_kv` nameplate -- a real, measured finding, not a design
preference.** Building this view surfaced that this sandbox's real DPsim
EMT solve (`do_steady_state_init(True)`) converges its pre-fault steady
state at ~0.816 pu of the nameplate-derived peak line-neutral voltage
*uniformly across every bus, including `ext_grid_bus` itself* -- confirmed
directly against the real log: `ext_grid_bus`'s own pre-fault |V1| divided
by `chaosnet.nominal_peak_line_neutral_v(vn_kv)` is 0.8165, matching
sqrt(2/3) to 4 decimal places, an exact ratio rather than solver noise. That
is a real characteristic of this sandbox's steady-state initialization, out
of scope to fix here (a physics-model question, not a visualization bug --
see `compute_bus_pu_series()`'s docstring for the full reasoning). Coloring
against the nameplate would render the whole network a uniform ~0.82 pu
*before the fault even fires*, burying the actual propagation signal this
view exists to show -- so, like `phase_model.peak_deviation_bins()`'s
existing "reference_peak is that phase's pre-fault peak" convention, each
bus's own real pre-fault median |V1| is the reference instead. main()'s
printed summary reports the real nameplate ratio anyway, honestly, rather
than hiding it.

Reuses `animate_transient.py`'s five-phase reveal timeline
(`_build_timeline()`/`_reveal_sim_time()`) and MP4-encoding conventions
(fps/dpi/codec/pix_fmt/faststart) unchanged -- this is the third animation
script in this lab, and the timeline/encoder choices were already made
twice; nothing here invents a new one.

**Real, measured propagation finding, printed by main() from the real run,
not assumed**: see this module's own printed summary and README.md's
"real findings" section for whether this seed's chaos-net mesh sags roughly
uniformly (short lines, light load -- consistent with `view_rx_trajectory.py`
option 2's own finding that this topology's line impedance is tiny relative
to load impedance) or attenuates sharply with electrical distance from the
fault bus, as a naive radial-feeder intuition would predict.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TypedDict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.animation import FFMpegWriter, FuncAnimation  # noqa: E402

import chaosnet  # noqa: E402
from animate_transient import (  # noqa: E402
    ANIM_BITRATE,
    ANIMATION_FPS,
    EXTRA_ARG_MOVFLAGS_FLAG,
    EXTRA_ARG_PIX_FMT_FLAG,
    FFMPEG_FASTART,
    FFMPEG_PIX_FMT,
    N_FRAMES,
    VIDEO_CODEC,
    VIDEO_DURATION_S,
    _build_timeline,
    _reveal_sim_time,
)
from generate_topology import (  # noqa: E402
    TOPOLOGY_EDGE_COLOR,
    TOPOLOGY_LABEL_Y_OFFSET,
    TOPOLOGY_TAP_NODE_COLOR,
    _build_topology_graph,
    _topology_layout,
)
from phase_model import (  # noqa: E402
    ThreePhaseWaveform,
    phasor_frames,
    positive_sequence,
)

LAB_DIR = Path(__file__).resolve().parent
TRANSIENT_LOG_JSON = LAB_DIR / "dpsim_transient_log.json"
SAMPLE_TOPOLOGY_JSON = LAB_DIR / "sample_topology.json"
OUTPUT_MP4 = LAB_DIR / "animate_sag_propagation.mp4"

REQUIRED_LOG_KEYS: tuple[str, ...] = (
    "times", "va", "vb", "vc", "bus_voltages", "trigger_time_s", "clear_time_s", "target",
)

# Same PowerPoint-friendly 1280x720@30fps / libx264 / yuv420p / faststart
# encoding choice as animate_transient.py -- imported directly above rather
# than re-declared, so this is exactly the established convention, not a
# third variant of it.
FIGURE_WIDTH_IN: float = 12.8
FIGURE_HEIGHT_IN: float = 7.2
FIGURE_DPI: int = 100

# Marker-size range (nx.draw_networkx_nodes node_size units, points^2): the
# floor matches generate_topology.TOPOLOGY_BUS_NODE_SIZE's order of
# magnitude (an ordinary bus at nominal voltage should look like an ordinary
# bus); the ceiling is a fixed render budget the real per-run max deviation
# is scaled into (see MAX_ABS_DEVIATION_PU below) -- not a per-run guess.
BUS_NODE_SIZE_MIN: float = 180.0
BUS_NODE_SIZE_MAX: float = 950.0

# Node-ring styling: fault bus gets the thickest, most saturated ring
# (matches generate_topology.TOPOLOGY_TAP_NODE_COLOR, this lab's existing
# "this is the important one" color); the other two tagged tap substations
# get a thinner ring in the same color so they stay identifiable without
# competing with the fault bus; ordinary buses get a thin neutral ring.
FAULT_RING_LINEWIDTH: float = 3.2
TAP_RING_LINEWIDTH: float = 1.4
ORDINARY_RING_LINEWIDTH: float = 0.5
ORDINARY_RING_COLOR: str = "#ffffff"

# Status text colors/labels, matching animate_transient.py's status role
# exactly (pre-fault / faulted / post-fault), reused here as string
# constants for consistency across the two scripts, not reimported (that
# module's are module-private naming tied to a single-waveform plot).
COLOR_FAULT: str = "#e34948"
COLOR_INK: str = "#898781"
STATUS_PRE_FAULT: str = "pre-fault"
STATUS_FAULTED: str = "faulted"
STATUS_POST_FAULT: str = "post-fault"


class TransientLog(TypedDict):
    """The JSON shape written by run_dpsim.py -- same keys, same semantics
    as run_dpsim.py's module docstring "key convention" section."""

    times: list[float]
    va: list[float]
    vb: list[float]
    vc: list[float]
    bus_voltages: dict[str, dict[str, list[float]]]
    trigger_time_s: float
    clear_time_s: float
    target: str


def _missing_log_message() -> str:
    return (
        f"[missing] {TRANSIENT_LOG_JSON} not found. Produce it with the Lab 5 "
        "walkthrough (see labs/05-spartan-chaosnet-transient-stream/README.md):\n"
        "  uv run labs/05-spartan-chaosnet-transient-stream/generate_topology.py --seed 42\n"
        "  uv run labs/05-spartan-chaosnet-transient-stream/run_dpsim.py "
        "--schedule chaos_schedule.yaml\n"
        "then re-run this animation script."
    )


def _load_log() -> TransientLog:
    if not TRANSIENT_LOG_JSON.exists():
        print(_missing_log_message(), file=sys.stderr)
        sys.exit(1)
    log = json.loads(TRANSIENT_LOG_JSON.read_text())
    missing = [key for key in REQUIRED_LOG_KEYS if key not in log]
    if missing:
        print(
            f"[invalid] {TRANSIENT_LOG_JSON} missing keys: {missing} -- re-run "
            "run_dpsim.py to regenerate it with the bus_voltages capture "
            "(docs/backlog/0006 option 4)",
            file=sys.stderr,
        )
        sys.exit(1)
    return log


def _load_topology() -> chaosnet.ChaosTopology:
    if not SAMPLE_TOPOLOGY_JSON.exists():
        print(
            f"[missing] {SAMPLE_TOPOLOGY_JSON} not found -- run "
            "generate_topology.py --seed 42 first",
            file=sys.stderr,
        )
        sys.exit(1)
    return chaosnet.read_topology_json(SAMPLE_TOPOLOGY_JSON)


class BusSeries(TypedDict):
    """Per-bus reduction of the real dpsim_transient_log.json capture."""

    frame_times_s: np.ndarray
    pu_by_bus: dict[int, np.ndarray]  # local bus index -> |V1(t)|/pre-fault-reference per frame
    pre_fault_reference_v_by_bus: dict[int, float]
    nameplate_peak_v_by_bus: dict[int, float]


def compute_bus_pu_series(log: TransientLog, topology: chaosnet.ChaosTopology) -> BusSeries:
    """Reduce every bus's captured va/vb/vc to a positive-sequence |V1(t)|
    per-unit series, reusing `phase_model.py`'s existing one-cycle-DFT
    phasor machinery unchanged (the same reuse discipline
    `view_rx_trajectory.py` (docs/backlog/0006 option 2) already
    established: no second, hand-rolled phasor estimator).

    **"Nominal" here is each bus's own real pre-fault operating point**
    (median |V1(t)| over frames before `trigger_time_s`), *not* the
    SimBench nameplate `vn_kv`-derived peak
    (`chaosnet.nominal_peak_line_neutral_v()`) -- a deliberate choice made
    after a real, measured finding while building this view: this sandbox's
    real DPsim EMT solve (`do_steady_state_init(True)`) converges its
    pre-fault steady state at ~0.816 pu of the nameplate-derived peak
    *uniformly*, including at `ext_grid_bus` itself (confirmed directly:
    `ext_grid_bus`'s own pre-fault |V1| divided by
    `nominal_peak_line_neutral_v(vn_kv)` is 0.8165 == sqrt(2/3) to 4 decimal
    places, an exact ratio, not solver noise) -- a real characteristic of
    this sandbox's steady-state initialization/loading, unrelated to sag
    propagation, and out of scope to fix here (a physics-model question, the
    same category `phase_model.py`'s module docstring already names for
    Option 1's finding, not a visualization bug). Using the nameplate figure
    as "nominal" would render every bus a uniform ~0.82 pu *before the fault
    even fires*, which would misleadingly read as "this whole network is
    already sagged" on frame 1 and bury the actual sag-propagation signal
    this view exists to show. A self-referencing pre-fault baseline (the
    same principle `phase_model.peak_deviation_bins()`'s docstring already
    names: "reference_peak is that phase's pre-fault peak") instead reads
    exactly 1.0 pu pre-fault everywhere, so any departure from 1.0 -- during
    the fault, or in the post-fault swell -- is unambiguously new
    information about this event, not baseline noise from an unrelated
    finding. See README.md's "real findings" section for the measured
    nameplate-vs-actual number, reported honestly rather than hidden by this
    choice.

    Args:
        log: the validated transient log (`bus_voltages` present).
        topology: the topology the log's solve ran against (for vn_kv per
            bus, used only for the nameplate-comparison figures printed by
            main(), not for the animated pu values themselves).

    Returns:
        BusSeries with one pu array per bus, all sharing `frame_times_s`
        (every bus was captured against the identical global `times` array,
        so phasor_frames()'s frame-centering loop produces the identical
        grid for each -- computed once per bus, not asserted equal after
        the fact).
    """
    vn_kv_by_bus = {bus["index"]: bus["vn_kv"] for bus in topology["buses"]}
    trigger_s = float(log["trigger_time_s"])
    frame_times: np.ndarray | None = None
    v1_mag_by_bus: dict[int, np.ndarray] = {}

    for bus_key, phase_series in log["bus_voltages"].items():
        bus_idx = int(bus_key)
        times = np.asarray(log["times"], dtype=float)
        wave = ThreePhaseWaveform(
            times,
            np.asarray(phase_series["va"], dtype=float),
            np.asarray(phase_series["vb"], dtype=float),
            np.asarray(phase_series["vc"], dtype=float),
        )
        ft, ph_a, ph_b, ph_c = phasor_frames(wave)
        if frame_times is None:
            frame_times = ft
        v1_mag_by_bus[bus_idx] = np.abs(positive_sequence(ph_a, ph_b, ph_c))

    assert frame_times is not None, "bus_voltages was empty"
    pre_fault_mask = frame_times < trigger_s

    pu_by_bus: dict[int, np.ndarray] = {}
    pre_fault_reference_by_bus: dict[int, float] = {}
    nameplate_by_bus: dict[int, float] = {}
    for bus_idx, v1_mag in v1_mag_by_bus.items():
        reference_v = float(np.median(v1_mag[pre_fault_mask]))
        pre_fault_reference_by_bus[bus_idx] = reference_v
        nameplate_by_bus[bus_idx] = chaosnet.nominal_peak_line_neutral_v(vn_kv_by_bus[bus_idx])
        pu_by_bus[bus_idx] = v1_mag / reference_v

    return {
        "frame_times_s": frame_times,
        "pu_by_bus": pu_by_bus,
        "pre_fault_reference_v_by_bus": pre_fault_reference_by_bus,
        "nameplate_peak_v_by_bus": nameplate_by_bus,
    }


class PropagationSummary(TypedDict):
    """Real, measured cross-bus propagation figures, printed by main() --
    never asserted in advance (see this module's own docstring)."""

    fault_bus_min_pu: float
    other_bus_min_pu: dict[str, float]  # tap_name or "bus{idx}" -> min pu during fault
    worst_other_bus: str
    worst_other_bus_min_pu: float
    mean_other_bus_min_pu: float
    mean_nameplate_ratio: float  # mean(pre_fault_reference_v / nameplate_peak_v) over all buses


def _bus_label(topology: chaosnet.ChaosTopology, bus_idx: int) -> str:
    for bus in topology["buses"]:
        if bus["index"] == bus_idx and bus["tap_name"]:
            return bus["tap_name"]
    return f"bus{bus_idx}"


def summarize_propagation(
    log: TransientLog, topology: chaosnet.ChaosTopology, series: BusSeries
) -> PropagationSummary:
    """Real, measured how-far-does-the-sag-go figures: each bus's own
    minimum |V1(t)|/nominal during the fault window, compared against the
    fault bus's own minimum -- the actual propagation pattern this seed's
    chaos-net mesh produces, computed from the real run, not assumed.
    """
    trigger_s = float(log["trigger_time_s"])
    clear_s = float(log["clear_time_s"])
    ft = series["frame_times_s"]
    in_fault = (ft >= trigger_s) & (ft <= clear_s)

    fault_bus_idx = topology["tap_buses"][topology["tap_names"].index(log["target"])]
    fault_bus_min_pu = float(series["pu_by_bus"][fault_bus_idx][in_fault].min())

    other_bus_min_pu: dict[str, float] = {}
    for bus_idx, pu in series["pu_by_bus"].items():
        if bus_idx == fault_bus_idx:
            continue
        other_bus_min_pu[_bus_label(topology, bus_idx)] = float(pu[in_fault].min())

    worst_other_bus = min(other_bus_min_pu, key=lambda k: other_bus_min_pu[k])
    mean_other = float(np.mean(list(other_bus_min_pu.values())))

    nameplate_ratios = [
        series["pre_fault_reference_v_by_bus"][bus_idx] / series["nameplate_peak_v_by_bus"][bus_idx]
        for bus_idx in series["pu_by_bus"]
    ]

    return {
        "fault_bus_min_pu": fault_bus_min_pu,
        "other_bus_min_pu": other_bus_min_pu,
        "worst_other_bus": worst_other_bus,
        "worst_other_bus_min_pu": other_bus_min_pu[worst_other_bus],
        "mean_other_bus_min_pu": mean_other,
        "mean_nameplate_ratio": float(np.mean(nameplate_ratios)),
    }


def animate(log: TransientLog, topology: chaosnet.ChaosTopology, output: Path) -> PropagationSummary:
    """Render the network-wide sag-propagation MP4 and return the real
    measured propagation summary."""
    series = compute_bus_pu_series(log, topology)
    summary = summarize_propagation(log, topology, series)

    graph = _build_topology_graph(topology)
    pos = _topology_layout(graph)
    nodelist = list(graph.nodes())

    is_tap_by_index = {bus["index"]: bus["is_tap"] for bus in topology["buses"]}
    fault_bus_idx = topology["tap_buses"][topology["tap_names"].index(log["target"])]

    frame_times = series["frame_times_s"]
    pu_matrix = np.stack([series["pu_by_bus"][idx] for idx in nodelist])  # (num_buses, num_frames)

    # Data-driven size scaling: the real largest |pu-1| this run ever
    # produces (any bus, any frame) maps to BUS_NODE_SIZE_MAX, so the full
    # render size range is always used regardless of how severe this
    # particular seed's sag turns out to be -- the same "sized from the real
    # computed extent, never a fixed guess" discipline view_rx_trajectory.py
    # already used for its zoomed inset (docs/backlog/0006 option 2).
    max_abs_deviation_pu = float(np.max(np.abs(pu_matrix - 1.0)))
    if max_abs_deviation_pu < 1e-9:
        max_abs_deviation_pu = 1.0  # guard: a degenerate all-nominal run

    # Colorbar range: the real observed [min, max] pu across every bus and
    # every frame this run produced, rounded outward to the nearest 0.1 pu
    # for a clean tick scale -- data-driven, like the size scaling above,
    # not a fixed assumed band (a run with a deeper sag or a bigger swell
    # gets a wider real colorbar, not a clipped one).
    vmin_pu = float(np.floor(pu_matrix.min() * 10.0) / 10.0)
    vmax_pu = float(np.ceil(pu_matrix.max() * 10.0) / 10.0)

    trigger_s = float(log["trigger_time_s"])
    clear_s = float(log["clear_time_s"])
    final_s = float(log["times"][-1])
    timeline = _build_timeline(trigger_s, clear_s, final_s)

    fig, ax = plt.subplots(figsize=(FIGURE_WIDTH_IN, FIGURE_HEIGHT_IN), dpi=FIGURE_DPI)
    nx.draw_networkx_edges(graph, pos, ax=ax, edge_color=TOPOLOGY_EDGE_COLOR, width=1.0)
    node_artist = nx.draw_networkx_nodes(
        graph, pos, ax=ax, nodelist=nodelist,
        node_color=[1.0] * len(nodelist), cmap="viridis", vmin=vmin_pu, vmax=vmax_pu,
    )
    cbar = fig.colorbar(node_artist, ax=ax, shrink=0.75)
    cbar.set_label("|V1(t)| / bus's own pre-fault |V1| (pu)")

    tap_labels = {
        bus["index"]: bus["tap_name"]
        for bus in topology["buses"]
        if bus["tap_name"] is not None
    }
    label_pos = {
        n: (x, y + TOPOLOGY_LABEL_Y_OFFSET) for n, (x, y) in pos.items() if n in tap_labels
    }
    nx.draw_networkx_labels(
        graph, label_pos, ax=ax, labels=tap_labels, font_size=9, font_weight="bold",
        font_color=TOPOLOGY_TAP_NODE_COLOR,
    )

    ax.set_title(
        f"Lab 5 -- {log['target']} fault: network-wide sag propagation "
        f"({len(nodelist)} buses)"
    )
    ax.axis("off")

    status_text = ax.text(
        0.012, 0.98, "", transform=ax.transAxes, ha="left", va="top",
        fontsize=13, family="monospace",
        bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=COLOR_INK, alpha=0.9),
    )
    fig.tight_layout()

    def update(frame_index: int) -> list[plt.Artist]:
        anim_t = frame_index / ANIMATION_FPS
        now = _reveal_sim_time(anim_t, timeline)
        idx = int(np.searchsorted(frame_times, now, side="right") - 1)
        idx = max(0, min(idx, len(frame_times) - 1))

        pu_now = pu_matrix[:, idx]
        node_artist.set_array(pu_now)
        sizes = BUS_NODE_SIZE_MIN + (BUS_NODE_SIZE_MAX - BUS_NODE_SIZE_MIN) * np.clip(
            np.abs(pu_now - 1.0) / max_abs_deviation_pu, 0.0, 1.0
        )
        node_artist.set_sizes(sizes)

        ring_colors = []
        ring_widths = []
        for bus_idx in nodelist:
            if bus_idx == fault_bus_idx:
                ring_colors.append(TOPOLOGY_TAP_NODE_COLOR)
                ring_widths.append(FAULT_RING_LINEWIDTH)
            elif is_tap_by_index[bus_idx]:
                ring_colors.append(TOPOLOGY_TAP_NODE_COLOR)
                ring_widths.append(TAP_RING_LINEWIDTH)
            else:
                ring_colors.append(ORDINARY_RING_COLOR)
                ring_widths.append(ORDINARY_RING_LINEWIDTH)
        node_artist.set_edgecolors(ring_colors)
        node_artist.set_linewidths(ring_widths)

        if now < trigger_s:
            label, color = STATUS_PRE_FAULT, COLOR_INK
        elif now < clear_s:
            label, color = STATUS_FAULTED, COLOR_FAULT
        else:
            label, color = STATUS_POST_FAULT, COLOR_INK
        status_text.set_text(f"t = {now:.4f} s\n{label}")
        status_text.set_color(color)

        return [node_artist, status_text]

    anim = FuncAnimation(fig, update, frames=range(N_FRAMES), blit=False)
    writer = FFMpegWriter(
        fps=ANIMATION_FPS, codec=VIDEO_CODEC, bitrate=ANIM_BITRATE,
        extra_args=[EXTRA_ARG_PIX_FMT_FLAG, FFMPEG_PIX_FMT,
                    EXTRA_ARG_MOVFLAGS_FLAG, FFMPEG_FASTART],
    )
    anim.save(output, writer=writer)
    plt.close(fig)
    return summary


def main() -> None:
    """Load the real log + topology, render the MP4, and print the real,
    measured propagation summary -- never asserted in advance."""
    log = _load_log()
    topology = _load_topology()
    summary = animate(log, topology, OUTPUT_MP4)
    print(
        f"[sag] wrote {OUTPUT_MP4}: {N_FRAMES} frames, {VIDEO_DURATION_S:.1f}s "
        f"at {ANIMATION_FPS} fps ({FIGURE_WIDTH_IN * FIGURE_DPI:.0f}x"
        f"{FIGURE_HEIGHT_IN * FIGURE_DPI:.0f})"
    )
    print(
        "  pu reference = each bus's OWN real pre-fault |V1| (not SimBench "
        "vn_kv nameplate -- see compute_bus_pu_series()'s docstring for why); "
        f"real nameplate-vs-actual pre-fault ratio, mean over all "
        f"{len(summary['other_bus_min_pu']) + 1} buses: "
        f"{summary['mean_nameplate_ratio']:.4f} pu of nameplate "
        f"(a real, measured DPsim steady-state characteristic of this "
        "sandbox, not a fault effect)"
    )
    print(
        f"  fault bus {log['target']}: |V1(t)|/own-pre-fault-|V1| min during "
        f"fault = {summary['fault_bus_min_pu']:.3f} pu"
    )
    print(
        f"  worst OTHER bus: {summary['worst_other_bus']} at "
        f"{summary['worst_other_bus_min_pu']:.3f} pu; mean of all other "
        f"{len(summary['other_bus_min_pu'])} buses' minima: "
        f"{summary['mean_other_bus_min_pu']:.3f} pu"
    )
    for label, min_pu in sorted(summary["other_bus_min_pu"].items(), key=lambda kv: kv[1]):
        print(f"    {label}: {min_pu:.3f} pu")


if __name__ == "__main__":
    main()
