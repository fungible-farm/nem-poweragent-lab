"""Unit tests for `precursor.SecondOrderOscillator` -- fast, deterministic,
pure Python/numpy (no pandapower/DPsim dependency), matching this package's
own `test_scenario_engine.py` convention of testing dispatch/dynamics logic
directly via a stub before any end-to-end solve is involved.

Confirms the three properties `precursor.py`'s own module docstring claims:
1. Output is exactly 0.0 before `.excite()` (the stationary fixed point).
2. A step excitation produces a response whose FFT peak lands at the
   configured `natural_freq_hz`, for real -- not asserted, computed.
3. That response decays (a later window has smaller amplitude than an
   earlier one), the expected behaviour of an underdamped 2nd-order system
   with `wn^2*x` restoring toward a *fixed* target rather than persisting.
"""
import sys
from pathlib import Path

import numpy as np

SHARED_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SHARED_DIR))
from scenario_engine.precursor import SecondOrderOscillator  # noqa: E402


def _run(osc: SecondOrderOscillator, duration_s: float, dt_s: float) -> tuple[np.ndarray, np.ndarray]:
    n = int(round(duration_s / dt_s))
    t = np.arange(n + 1) * dt_s
    out = np.empty(n + 1)
    out[0] = osc.output
    for i in range(1, n + 1):
        out[i] = osc.step(dt_s)
    return t, out


def _fft_peak_hz(t: np.ndarray, signal: np.ndarray) -> float:
    detrended = signal - np.mean(signal)
    dt = float(np.mean(np.diff(t)))
    fft = np.fft.rfft(detrended * np.hanning(len(detrended)))
    freqs = np.fft.rfftfreq(len(detrended), d=dt)
    power = np.abs(fft)
    peak_idx = 1 + int(np.argmax(power[1:]))  # skip DC bin
    return float(freqs[peak_idx])


def test_output_is_exactly_zero_before_excitation():
    osc = SecondOrderOscillator(id="test", natural_freq_hz=0.63, damping_ratio=0.08)
    assert osc.output == 0.0
    for _ in range(500):
        osc.step(0.02)
    assert osc.output == 0.0


def test_step_response_recovers_local_mode_frequency():
    osc = SecondOrderOscillator(id="local", natural_freq_hz=0.63, damping_ratio=0.08)
    osc.excite(1.0)
    t, out = _run(osc, duration_s=60.0, dt_s=0.02)
    peak_hz = _fft_peak_hz(t, out)
    assert abs(peak_hz - 0.63) < 0.03


def test_step_response_recovers_inter_area_mode_frequency():
    osc = SecondOrderOscillator(id="inter-area", natural_freq_hz=0.2, damping_ratio=0.08)
    osc.excite(1.0)
    t, out = _run(osc, duration_s=120.0, dt_s=0.05)
    peak_hz = _fft_peak_hz(t, out)
    assert abs(peak_hz - 0.2) < 0.02


def test_step_response_decays():
    osc = SecondOrderOscillator(id="local", natural_freq_hz=0.63, damping_ratio=0.08)
    osc.excite(1.0)
    t, out = _run(osc, duration_s=60.0, dt_s=0.02)
    early = out[(t >= 2.0) & (t < 12.0)]
    late = out[(t >= 45.0) & (t < 55.0)]
    early_amplitude = float(np.max(np.abs(early - 1.0)))
    late_amplitude = float(np.max(np.abs(late - 1.0)))
    assert late_amplitude < early_amplitude * 0.5


def test_step_response_settles_near_target():
    osc = SecondOrderOscillator(id="local", natural_freq_hz=0.63, damping_ratio=0.08)
    osc.excite(1.0)
    _, out = _run(osc, duration_s=60.0, dt_s=0.02)
    assert abs(out[-1] - 1.0) < 0.05
