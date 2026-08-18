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
import math
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


def test_lab5_headroom_translation_check():
    """PRD-0005 Phase 1.5: headroom_translation.py --step check re-derives
    Phase 1's real stabilizer_comparison.json numbers, builds a real
    pandapower net from the identical chaos-net topology (chaosnet.
    to_pandapower()), and runs two real pp.runpp() limit screens (baseline
    vs. the (b)-hypothesis rating translation on the fault-adjacent line).
    Only structural invariants are asserted (both solves converged, the
    translated max_i_ka increased, and the fault-adjacent line's own
    loading_percent did not increase after raising its own rating) -- never
    a hardcoded direction for binding_constraint_set_changed, since "no
    binding constraint changed" is an explicitly acceptable, honestly
    reportable real finding per PRD-0005 Phase 1.5, not a test failure.
    """
    result = _run_check("headroom_translation.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


def test_lab5_headroom_translation_reports_real_finding():
    """Direct check against the real headroom_translation.json the previous
    test just wrote: the fault-adjacent line's steady-state limit-screen
    numbers must be real, finite pandapower results (not placeholders), and
    the (b)-hypothesis translation must have actually been applied (a
    strictly larger max_i_ka on the translated net) -- whatever the
    resulting binding_constraint_set_changed verdict honestly turns out to
    be, per this repo's own "no, nothing changes is an acceptable outcome"
    discipline for this phase.
    """
    headroom_path = LAB_DIR / "headroom_translation.json"
    if not headroom_path.exists():
        pytest.skip(
            "headroom_translation.json not present -- headroom_translation.py "
            "hasn't run yet"
        )
    result = json.loads(headroom_path.read_text())
    baseline = result["baseline"]
    translated = result["translated"]

    assert translated["fault_adjacent_line_max_i_ka"] > baseline["fault_adjacent_line_max_i_ka"]
    assert baseline["worst_loading_percent"] >= 0.0
    assert 0.0 <= baseline["worst_voltage_pu"] <= 2.0  # sane pu range, not a placeholder
    assert isinstance(result["binding_constraint_set_changed"], bool)
    assert result["conclusion"]  # a real, non-empty honest finding was written


def test_grid_forming_delay_compensation_disabled_is_bit_identical_to_phase1():
    """PRD-0005 Phase 2 structural invariant, no dpsim needed: stepping two
    `grid_forming.GridFormingStabilizer` instances -- one with
    `delay_compensation_enabled=False` (Phase 1's default), one with it
    `True` but `delay_s=0.0` -- through the identical synthetic sagging
    3-phase voltage/current sequence must produce bit-identical
    `e_boost_v` trajectories. `delay_s=0.0` makes the Phase 2 predictor
    term an exact algebraic no-op (`v1_mag_meas + 0.0 * rate ==
    v1_mag_meas`), so this confirms Phase 1's own default configuration is
    structurally unaffected by Phase 2's new code path, without needing a
    real DPsim solve to check it (the DPsim-level reproducibility check
    lives in delay_compensation.py's own check_step()).

    A second run at this lab's real computed propagation delay
    (3.035us, `grid_forming.propagation_delay_s()`'s seed-42 SUB-3 value)
    confirms the predictor term is actually wired in and doing real
    arithmetic -- not silently inert -- against a synthetic signal with a
    large enough rate of change to make the (tiny, real) delay's effect
    detectable; this is a wiring check, not a claim about the real fault's
    own magnitude (delay_compensation.py's real DPsim run found that
    effect too small to be measurable there -- see its own conclusion).

    Nonzero alone would also pass for a sign-flipped predictor (e.g.
    `v1_mag_meas - delay_s * rate` instead of `+`), which would still be
    "wired in" but wrong -- so this also asserts the correction is
    *correctly signed*: during the synthetic sag ramp (voltage falling,
    so its measured rate of change is negative), a forward extrapolation
    must predict a *lower* voltage than the raw measurement, which the
    droop law must react to with an equal-or-larger boost than the
    uncompensated path at every single step -- never a smaller one. This
    is the actual claim README.md makes about this test ("produces a
    clearly nonzero, correctly-signed correction"), not just "produces a
    difference of unspecified direction."
    """
    import grid_forming as gf

    time_step_s = 200e-6
    nominal_peak_v = 1000.0

    def run(delay_compensation_enabled: bool, delay_s: float) -> list[float]:
        ctrl = gf.GridFormingStabilizer(
            nominal_peak_v=nominal_peak_v, time_step_s=time_step_s,
            delay_compensation_enabled=delay_compensation_enabled, delay_s=delay_s,
        )
        e_boost_trace = []
        n = gf.N_CYCLE * 20
        for i in range(n):
            t = i * time_step_s
            sag = 1.0 - 0.15 * min(1.0, i / (n / 2))  # ramps 15% sag, then holds
            theta = gf.SYSTEM_OMEGA_RAD_S * t
            peak = nominal_peak_v * sag
            va = peak * math.cos(theta)
            vb = peak * math.cos(theta - 2 * math.pi / 3)
            vc = peak * math.cos(theta + 2 * math.pi / 3)
            ia = 10.0 * math.cos(theta - 0.2)
            ib = 10.0 * math.cos(theta - 0.2 - 2 * math.pi / 3)
            ic = 10.0 * math.cos(theta - 0.2 + 2 * math.pi / 3)
            ctrl.step(t, va, vb, vc, ia, ib, ic)
            e_boost_trace.append(ctrl.e_boost_v)
        return e_boost_trace

    disabled = run(False, 0.0)
    enabled_zero_delay = run(True, 0.0)
    assert disabled == enabled_zero_delay

    enabled_real_delay = run(True, 3.035e-6)
    assert disabled != enabled_real_delay
    # Sign check: during a falling-voltage sag, forward-extrapolating by a
    # positive delay must predict a lower voltage than the raw measurement,
    # so the droop law's boost must be >= the uncompensated boost at every
    # step (never smaller) -- a sign-flipped predictor would violate this.
    assert all(b >= a for a, b in zip(disabled, enabled_real_delay))
    # And the correction must be a real anticipatory effect somewhere, not
    # merely "never negative" by coincidence (e.g. always exactly zero).
    assert any(b > a for a, b in zip(disabled, enabled_real_delay))


def test_lab5_delay_compensation_check():
    """PRD-0005 Phase 2: delay_compensation.py --step check re-runs the real
    chaos_schedule.yaml fault three ways (no stabilizer, stabilizer without
    delay compensation, stabilizer with delay compensation) against real
    DPsim solves, and asserts the no-compensation number reproduces an
    independent direct re-run of Phase 1's exact configuration -- see that
    module's check_step() docstring for the full invariant list. This is
    the slowest test in this file (four real EMT solves); it also writes
    delay_compensation.json, which the next test reads directly.
    """
    result = _run_check("delay_compensation.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


def test_lab5_delay_compensation_reports_real_finding():
    """Direct check against the real delay_compensation.json the previous
    test just wrote: the propagation-delay figure and all three peak-sag
    numbers must be real, finite computed values (never placeholders), and
    the no-compensation number must match Phase 1's own reported peak sag
    within a real float tolerance -- confirming Phase 2's new controller
    path didn't silently change Phase 1's default behavior. No assertion is
    made about whether delay compensation must outperform the uncompensated
    controller: PRD-0005 Goal 3 explicitly names that as an open question
    this phase answers honestly either way (the `conclusion` field), not a
    target to force -- "no measurable effect" is an acceptable, reportable
    real finding here, same discipline as Phase 1.5's
    binding_constraint_set_changed=False finding.
    """
    delay_path = LAB_DIR / "delay_compensation.json"
    if not delay_path.exists():
        pytest.skip(
            "delay_compensation.json not present -- delay_compensation.py "
            "hasn't run yet"
        )
    result = json.loads(delay_path.read_text())

    assert result["propagation_delay_s"] > 0.0
    assert result["propagation_velocity_km_s"] > 0.0

    sags = result["peak_sag_percent"]
    for key in ("no_stabilizer", "stabilizer_no_delay_compensation", "stabilizer_with_delay_compensation"):
        assert sags[key] > 0.0  # a real, finite, positive percentage

    # Phase 1's own comparison (grid_forming.py, run earlier in this same
    # comparison) reported the stabilizer measurably reducing peak sag
    # below the no-stabilizer baseline -- that structural fact must still
    # hold here, since this script's "stabilizer_no_delay_compensation"
    # number is Phase 1's own unmodified code path.
    assert sags["stabilizer_no_delay_compensation"] < sags["no_stabilizer"]

    assert isinstance(result["delay_compensation_measurable_effect"], bool)
    assert isinstance(result["delay_compensation_measurably_helped"], bool)
    assert result["conclusion"]  # a real, non-empty honest finding was written


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
