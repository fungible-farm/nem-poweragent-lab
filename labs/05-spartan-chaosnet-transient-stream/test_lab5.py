"""pytest wrapper around Lab 5's three --step check gates, following
labs/01-simple-loadflow-fit/test_lab1.py's pattern.

None of these tests requires a running podman pod: generate_topology.py and
run_dpsim.py's --step check re-derive their real result from scratch (a real
pandapower.runpp() and a real DPsim EMT solve, respectively) and diff against
their committed fixtures; verify_stream.py's --step check validates the
committed sample_stream_summary.json fixture structurally (see its own
module docstring for why a live-pod network capture is not something a
pytest run should depend on -- the pod is verified separately, for real,
during interactive/manual runs of the walkthrough).

Also covers docs/backlog/0006's tier-1 additions (phase_model's symmetrical
components, view_spectrogram.py): a unit-level check of
negative_sequence()/zero_sequence() against synthetic waveforms (no dpsim
needed), a regression check of the real, measured finding against Lab 5's
actual fault run (V0/V2 stay near zero because chaos_schedule.yaml's
"line-to-ground" fault is implemented as symmetric 3-phase-to-ground -- see
phase_model.py's module docstring), and a render check for
view_spectrogram.py.

Also covers option 2 (view_rx_trajectory.py: a synthetic Z=V/I math check,
plus a real-data render check) and option 4 (animate_sag_propagation.py: a
synthetic compute_bus_pu_series() math check against a known per-bus
amplitude drop, plus a real-data render check that produces a real MP4).
The real-data tests below rely on dpsim_transient_log.json (and, for option
4, sample_topology.json) already existing, written as a side effect of
test_lab5_dpsim_run_matches_fixture / test_lab5_topology_matches_fixture
running earlier in this file (pytest runs a module's tests in definition
order).

Also covers view_phasor_3d.py (a direct request, not a docs/backlog item): a
real-data render check for the 3D isometric phasor-diagram-through-time view.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB_DIR))

from phase_model import (  # noqa: E402
    ThreePhaseWaveform,
    negative_sequence,
    phasor_frames,
    positive_sequence,
    zero_sequence,
)


def _run_check(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LAB_DIR / script), "--step", "check"],
        capture_output=True,
        text=True,
    )


def test_lab5_topology_matches_fixture():
    result = _run_check("generate_topology.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


def test_lab5_dpsim_run_matches_fixture():
    result = _run_check("run_dpsim.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


def test_lab5_stream_summary_matches_fixture():
    result = _run_check("verify_stream.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


def test_lab5_grid_forming_stabilizer_check():
    """PRD-0005 Phase 1: grid_forming.py --step check re-runs the real
    chaos_schedule.yaml fault twice (stabilizer off, then on) and asserts
    the stabilized run's peak sag is smaller than the baseline's -- both
    numbers freshly computed from a real DPsim solve each time, never
    hardcoded (see grid_forming.check_step()'s own docstring). This is the
    slowest test in this file (two real ~0.55s EMT solves back to back);
    it also writes stabilizer_comparison.json, which the next test reads
    directly for a second, independent numeric assertion.
    """
    result = _run_check("grid_forming.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


def test_lab5_grid_forming_reduces_peak_sag():
    """Direct numeric-outcome check against the real
    stabilizer_comparison.json the previous test just wrote: the
    stabilized run's peak |V1| sag (phase_model.phasor_frames()-derived,
    not the RMS-window sag_percent DpsimRunSummary already reports) must
    be measurably smaller than the baseline's -- asserted from the real
    computed numbers in that file, no hardcoded expected percentage
    anywhere in this test (per PRD-0005's own "measured, not assumed"
    discipline -- the actual reduction, whatever it turns out to be on a
    given run, is asserted to exist, not asserted to match a target).
    """
    comparison_path = LAB_DIR / "stabilizer_comparison.json"
    if not comparison_path.exists():
        pytest.skip(
            "stabilizer_comparison.json not present -- grid_forming.py "
            "hasn't run yet"
        )
    comparison = json.loads(comparison_path.read_text())
    baseline_sag = comparison["baseline"]["peak_sag_percent"]
    stabilized_sag = comparison["stabilized"]["peak_sag_percent"]
    assert stabilized_sag < baseline_sag, (
        f"stabilizer did not reduce peak sag: baseline={baseline_sag}% "
        f"stabilized={stabilized_sag}%"
    )
    # Non-goal guardrail (PRD-0005): never claim elimination -- a real
    # controller with finite bandwidth/actuator headroom cannot drive the
    # sag to exactly zero, so a suspiciously-perfect result would itself
    # be evidence something is wrong (e.g. the comparison silently
    # reading the same log twice), not evidence of a better controller.
    assert stabilized_sag > 0.0


def _synthetic_wave(va_scale: float, vb_scale: float, vc_scale: float) -> ThreePhaseWaveform:
    """A 0.1 s, 5 kHz synthetic 3-phase 50 Hz cosine set with independently
    scaled per-phase peak amplitudes -- va_scale=vb_scale=vc_scale=1.0 is a
    balanced set; scaling one phase down mimics (crudely, not a real DPsim
    solve) the kind of imbalance a genuine single-line-to-ground fault would
    put onto the waveform, exercising negative_sequence()/zero_sequence()
    without needing dpsim installed.
    """
    fs = 5000.0
    f0 = 50.0
    t = np.arange(0, 0.1, 1.0 / fs)
    peak = 100.0
    va = va_scale * peak * np.cos(2 * np.pi * f0 * t)
    vb = vb_scale * peak * np.cos(2 * np.pi * f0 * t - 2 * np.pi / 3)
    vc = vc_scale * peak * np.cos(2 * np.pi * f0 * t + 2 * np.pi / 3)
    return ThreePhaseWaveform(t, va, vb, vc)


def test_phase_model_symmetrical_components_balanced_signal():
    """A balanced 3-phase set: |V1| ~ the phase peak amplitude, |V0|/|V2|
    numerically ~ 0 -- the textbook baseline negative_sequence()/
    zero_sequence() must reproduce before trusting them on real DPsim data.
    """
    wave = _synthetic_wave(1.0, 1.0, 1.0)
    _, ph_a, ph_b, ph_c = phasor_frames(wave)
    v1 = np.abs(positive_sequence(ph_a, ph_b, ph_c))
    v2 = np.abs(negative_sequence(ph_a, ph_b, ph_c))
    v0 = np.abs(zero_sequence(ph_a, ph_b, ph_c))
    assert np.allclose(v1, 100.0, atol=0.5)
    assert np.all(v2 < 1e-6)
    assert np.all(v0 < 1e-6)


def test_phase_model_symmetrical_components_unbalanced_signal():
    """An unbalanced set (phase A collapsed to 20% of nominal, B/C at
    nominal): |V1| dips and, unlike the symmetric case above, |V2| and |V0|
    both become clearly nonzero -- the actual classification signal a real
    single-line-to-ground fault would produce, confirming these functions can
    tell the two cases apart (Lab 5's real fault schedule happens to be the
    symmetric case -- see phase_model.py's module docstring -- so this
    synthetic case is what exercises the "genuinely unbalanced" branch of the
    math).
    """
    wave = _synthetic_wave(0.2, 1.0, 1.0)
    _, ph_a, ph_b, ph_c = phasor_frames(wave)
    v1 = np.abs(positive_sequence(ph_a, ph_b, ph_c))
    v2 = np.abs(negative_sequence(ph_a, ph_b, ph_c))
    v0 = np.abs(zero_sequence(ph_a, ph_b, ph_c))
    assert np.all(v1 < 95.0)  # dipped from the balanced case's ~100
    assert np.all(v2 > 10.0)  # clearly nonzero, unlike the balanced case
    assert np.all(v0 > 10.0)  # clearly nonzero, unlike the balanced case


def test_phase_model_sequence_components_confirm_lab5_fault_is_symmetric():
    """Regression check of the real, measured finding this backlog item's
    implementation surfaced (docs/backlog/0006, option 1): against Lab 5's
    actual dpsim_transient_log.json, |V0| stays at numerical zero and |V2|
    stays small relative to |V1|'s dip throughout the fault window, because
    chaosnet.py's switch shorts all three phases to ground identically
    (a diagonal resistance matrix) despite chaos_schedule.yaml's
    "line-to-ground" label. If this ever fails, either the fault model
    changed (chaosnet.py's switch is no longer symmetric -- update the
    module docstrings that describe this) or phase_model's sequence math
    regressed.
    """
    log_path = LAB_DIR / "dpsim_transient_log.json"
    if not log_path.exists():
        pytest.skip("dpsim_transient_log.json not present -- run_dpsim.py hasn't run yet")
    log = json.loads(log_path.read_text())
    wave = ThreePhaseWaveform.from_log(log)
    ft, ph_a, ph_b, ph_c = phasor_frames(wave)
    trigger_s, clear_s = float(log["trigger_time_s"]), float(log["clear_time_s"])
    in_fault = (ft >= trigger_s) & (ft <= clear_s)
    assert in_fault.any()

    v1 = np.abs(positive_sequence(ph_a, ph_b, ph_c))
    v2 = np.abs(negative_sequence(ph_a, ph_b, ph_c))
    v0 = np.abs(zero_sequence(ph_a, ph_b, ph_c))

    assert v0[in_fault].max() < 1.0  # numerical zero (measured ~1e-12 V)
    # |V2|'s fault-window peak stays a small fraction of |V1|'s dip level --
    # nowhere near the same order of magnitude a genuine single-LG fault's
    # negative-sequence rise would be.
    assert v2[in_fault].max() < 0.05 * v1[in_fault].min()


def test_lab5_spectrogram_renders():
    """docs/backlog/0006 option 3: view_spectrogram.py runs against the real
    dpsim_transient_log.json and writes sample_spectrogram.png."""
    log_path = LAB_DIR / "dpsim_transient_log.json"
    if not log_path.exists():
        pytest.skip("dpsim_transient_log.json not present -- run_dpsim.py hasn't run yet")
    output_png = LAB_DIR / "sample_spectrogram.png"
    result = subprocess.run(
        [sys.executable, str(LAB_DIR / "view_spectrogram.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[spectrogram] wrote" in result.stdout
    assert output_png.exists()


def test_rx_trajectory_z_math_synthetic():
    """docs/backlog/0006 option 2: sanity-check view_rx_trajectory.py's
    compute_trajectory() -- Z(t) = V1(t)/I1(t), reusing phase_model's DFT/
    phasor machinery -- against a synthetic balanced 3-phase voltage/current
    pair with a known magnitude ratio and phase offset (no dpsim needed).
    Current lagging voltage by a known angle must recover exactly that
    R+jX impedance (positive X = inductive, the correct sign convention).
    """
    import view_rx_trajectory as rx

    fs = 5000.0
    f0 = 50.0
    t = np.arange(0, 0.5, 1.0 / fs)
    v_peak = 1000.0
    i_peak = 10.0
    phase_offset = np.deg2rad(30.0)  # current lags voltage by 30 deg

    def three_phase(peak: float, phase: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        a = peak * np.cos(2 * np.pi * f0 * t + phase)
        b = peak * np.cos(2 * np.pi * f0 * t + phase - 2 * np.pi / 3)
        c = peak * np.cos(2 * np.pi * f0 * t + phase + 2 * np.pi / 3)
        return a, b, c

    va, vb, vc = three_phase(v_peak, 0.0)
    ia, ib, ic = three_phase(i_peak, -phase_offset)

    log = {
        "times": t.tolist(),
        "va": va.tolist(), "vb": vb.tolist(), "vc": vc.tolist(),
        "ia_line": ia.tolist(), "ib_line": ib.tolist(), "ic_line": ic.tolist(),
        "fault_adjacent_line": "line0_1",
        # No real switching event in this synthetic signal -- trigger/clear
        # set far outside [0, 0.5] so SWITCHING_EXCLUSION_CYCLES never masks
        # a frame here.
        "trigger_time_s": -1.0,
        "clear_time_s": -1.0,
        "target": "TEST",
    }
    frame_times, z = rx.compute_trajectory(log)
    finite = np.isfinite(z.real) & np.isfinite(z.imag)
    assert finite.sum() > 10

    z_mid = z[finite][finite.sum() // 2]
    expected_mag = v_peak / i_peak
    expected = complex(
        expected_mag * np.cos(phase_offset), expected_mag * np.sin(phase_offset)
    )
    assert abs(z_mid - expected) < 0.5


def test_lab5_rx_trajectory_renders():
    """docs/backlog/0006 option 2: view_rx_trajectory.py runs against the
    real dpsim_transient_log.json (extended with the ia_line/ib_line/ic_line
    fault-adjacent-line current tap) and writes sample_rx_trajectory.png."""
    log_path = LAB_DIR / "dpsim_transient_log.json"
    if not log_path.exists():
        pytest.skip("dpsim_transient_log.json not present -- run_dpsim.py hasn't run yet")
    log = json.loads(log_path.read_text())
    if "ia_line" not in log:
        pytest.skip(
            "dpsim_transient_log.json predates the ia_line/ib_line/ic_line "
            "current tap (docs/backlog/0006 option 2) -- re-run run_dpsim.py "
            "to regenerate it"
        )
    output_png = LAB_DIR / "sample_rx_trajectory.png"
    result = subprocess.run(
        [sys.executable, str(LAB_DIR / "view_rx_trajectory.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[rx] wrote" in result.stdout
    assert output_png.exists()


def test_lab5_phasor_3d_renders():
    """3D isometric phasor-diagram-through-time view: view_phasor_3d.py runs
    against the real dpsim_transient_log.json and writes sample_phasor_3d.png
    (see view_phasor_3d.py's module docstring for why this is a new, distinct
    view from view_3d_audio.py's 3D trajectory / view_rx_trajectory.py's 2D
    R-X plane / view_telemetry_rates.py's magnitude-vs-time panels)."""
    log_path = LAB_DIR / "dpsim_transient_log.json"
    if not log_path.exists():
        pytest.skip("dpsim_transient_log.json not present -- run_dpsim.py hasn't run yet")
    output_png = LAB_DIR / "sample_phasor_3d.png"
    result = subprocess.run(
        [sys.executable, str(LAB_DIR / "view_phasor_3d.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[phasor3d] wrote" in result.stdout
    assert output_png.exists()


def test_sag_propagation_pu_math_synthetic():
    """docs/backlog/0006 option 4: sanity-check
    animate_sag_propagation.compute_bus_pu_series() -- |V1(t)| normalized by
    each bus's OWN real pre-fault |V1| (not the SimBench vn_kv nameplate --
    see that function's docstring for why) -- against a synthetic 2-bus log
    with a known per-bus amplitude drop, no dpsim needed. Bus "0" never
    changes amplitude (pu should stay ~1.0 throughout); bus "1" drops to 40%
    of its own pre-fault amplitude inside [trigger_time_s, clear_time_s]
    (pu should dip to ~0.4 there and return to ~1.0 after).
    """
    import animate_sag_propagation as sag

    fs = 5000.0
    f0 = 50.0
    t = np.arange(0.0, 0.3, 1.0 / fs)
    trigger_s, clear_s = 0.1, 0.15
    in_fault = (t >= trigger_s) & (t < clear_s)

    def three_phase(peak: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        a = peak * np.cos(2 * np.pi * f0 * t)
        b = peak * np.cos(2 * np.pi * f0 * t - 2 * np.pi / 3)
        c = peak * np.cos(2 * np.pi * f0 * t + 2 * np.pi / 3)
        return a, b, c

    peak_bus0 = np.full_like(t, 1000.0)
    peak_bus1 = np.where(in_fault, 400.0, 1000.0)  # 40% dip during the fault window
    va0, vb0, vc0 = three_phase(peak_bus0)
    va1, vb1, vc1 = three_phase(peak_bus1)

    log = {
        "times": t.tolist(),
        "va": va0.tolist(), "vb": vb0.tolist(), "vc": vc0.tolist(),
        "bus_voltages": {
            "0": {"va": va0.tolist(), "vb": vb0.tolist(), "vc": vc0.tolist()},
            "1": {"va": va1.tolist(), "vb": vb1.tolist(), "vc": vc1.tolist()},
        },
        "trigger_time_s": trigger_s,
        "clear_time_s": clear_s,
        "target": "TEST",
    }
    topology = {
        "buses": [
            {"index": 0, "vn_kv": 20.0, "is_tap": False, "tap_name": None},
            {"index": 1, "vn_kv": 20.0, "is_tap": False, "tap_name": None},
        ],
    }

    series = sag.compute_bus_pu_series(log, topology)
    ft = series["frame_times_s"]
    fault_frames = (ft >= trigger_s) & (ft <= clear_s)
    pre_frames = ft < trigger_s

    assert np.allclose(series["pu_by_bus"][0][pre_frames], 1.0, atol=0.02)
    assert np.allclose(series["pu_by_bus"][0][fault_frames], 1.0, atol=0.02)
    assert np.allclose(series["pu_by_bus"][1][pre_frames], 1.0, atol=0.02)
    # 40% amplitude -> ~0.4 pu once the DFT window is fully inside the drop --
    # check the frame closest to the fault window's midpoint, since frames
    # near trigger_s/clear_s themselves straddle the amplitude step (their
    # one-cycle window spans both the pre-drop and dropped samples).
    mid_s = (trigger_s + clear_s) / 2.0
    mid_idx = int(np.argmin(np.abs(ft - mid_s)))
    assert series["pu_by_bus"][1][mid_idx] < 0.5


def test_lab5_sag_propagation_renders():
    """docs/backlog/0006 option 4: animate_sag_propagation.py runs against
    the real dpsim_transient_log.json (extended with the per-bus
    bus_voltages capture) and the committed sample_topology.json, and writes
    a real animate_sag_propagation.mp4 (gitignored by *.mp4, matching this
    lab's other two animation scripts)."""
    log_path = LAB_DIR / "dpsim_transient_log.json"
    if not log_path.exists():
        pytest.skip("dpsim_transient_log.json not present -- run_dpsim.py hasn't run yet")
    log = json.loads(log_path.read_text())
    if "bus_voltages" not in log:
        pytest.skip(
            "dpsim_transient_log.json predates the bus_voltages capture "
            "(docs/backlog/0006 option 4) -- re-run run_dpsim.py to "
            "regenerate it"
        )
    if not (LAB_DIR / "sample_topology.json").exists():
        pytest.skip("sample_topology.json not present -- generate_topology.py hasn't run yet")
    output_mp4 = LAB_DIR / "animate_sag_propagation.mp4"
    result = subprocess.run(
        [sys.executable, str(LAB_DIR / "animate_sag_propagation.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[sag] wrote" in result.stdout
    assert output_mp4.exists()
