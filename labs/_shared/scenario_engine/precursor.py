"""Precursor-phase quasi-static stepper + minimal control-loop oscillator
model (docs/prd/0003-iberian-2025-blackout-scenario.md's precursor phase:
the two real named oscillation modes -- a 0.63 Hz local/converter mode,
12:03-12:08 CEST, and a 0.2 Hz inter-area mode, 12:19-12:22 CEST --
`iberian_2025_blackout.py`'s own module docstring explicitly left open when
it implemented only the ~84s fast-collapse phase).

**Why not a directly-injected sinusoid (the circularity this module exists
to avoid)**: dialing a setpoint straight to `sin(2*pi*0.63*t)` and having
`OscillationDetector`'s FFT recover 0.63 Hz proves nothing -- the detector
would just be reading back a frequency this code chose. `SecondOrderOscillator`
below is excited by a plain STEP (`excite()`), not a designed sinusoid; its
oscillatory response is the genuine transient behaviour any underdamped
second-order system produces after a step disturbance (the textbook way real
inter-area oscillation modes are demonstrated: excite with a disturbance,
observe the system's own natural response). Its `natural_freq_hz` is dialed
to the report's own cited value -- that makes it a **named reduced-order
stand-in** for the real converter/PLL/AVR dynamics behind that number (same
"sandbox stand-in, named not hidden" convention as every other constant in
`iberian_2025_blackout.py`), not a claim of literally modelling Iberian's
hardware -- but the non-circularity comes from *input* being a step and
*output* being a real FFT-recovered transient, not from the frequency being
unknown in advance.

`PandapowerQuasiStaticStepper` is the other new piece: no pandapower
time-stepping utility existed anywhere in this repo before this module
(confirmed via repo-wide grep) -- `chaosnet.to_pandapower()` only builds a
single unsolved net. The precursor window is ~29 real minutes; a 200us-step
DPsim EMT solve over that span is the wrong tool (the fast-collapse phase
already established EMT is only warranted for the final ~70s), so this
stepper drives repeated `pandapower.runpp()` snapshots instead, reusing the
existing `Generator` protocol (`PlantBehaviourGenerator`/
`OperatorActionGenerator` from `generators.py`, unmodified -- both already
take a generic callback, so a pandapower-targeted closure works exactly like
a dpsimpy-targeted one) to drive real, non-fabricated `net.sgen` setpoint
changes and produce a genuine monotonic pre-collapse voltage-rise trend.

`synthesize_precursor_waveform()` combines that trend with each oscillator's
own stepped output into a real `phase_model.ThreePhaseWaveform` (the exact
same type the fast-collapse phase's DPsim output already produces), so
`OscillationDetector`/`VoltageCascadeDetector` need zero changes -- PRD-0001
Goal 2's "detectors are thin transforms" requirement holds.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandapower as pp

_LAB5_DIR = Path(__file__).resolve().parent.parent.parent / "05-spartan-chaosnet-transient-stream"
if str(_LAB5_DIR) not in sys.path:
    sys.path.insert(0, str(_LAB5_DIR))

import chaosnet  # noqa: E402  (nominal_peak_line_neutral_v -- reused, not re-derived)
from phase_model import FUNDAMENTAL_HZ, SAMPLE_RATE_HZ, ThreePhaseWaveform  # noqa: E402

from .generators import Generator, GeneratorEvent, MeasurementState  # noqa: E402


@dataclass
class SecondOrderOscillator:
    """A minimal underdamped 2nd-order control loop:
    `x'' + 2*zeta*wn*x' + wn^2*x = wn^2*target`, RK4-integrated.

    `target` starts at 0 and `x`/`v` start at (0, 0), a stationary fixed
    point (zero derivative), so `.output` is exactly 0.0 until `.excite()`
    is called -- confirmed by `test_precursor.py`. After excitation, `x`
    relaxes toward `target` via a decaying oscillation at (approximately,
    for zeta << 1) `natural_freq_hz`, the standard step response of an
    underdamped 2nd-order system.

    Attributes:
        id: unique oscillator id.
        natural_freq_hz: the emergent oscillation frequency, dialed to a
            real report-cited value (0.63 or 0.2 Hz here) -- see module
            docstring for why this is not circular despite being a chosen
            constant.
        damping_ratio: zeta. Lightly damped (zeta << 1) keeps the response
            visibly oscillatory for several cycles before decaying below
            `OscillationDetector.min_confidence` -- tuned empirically per
            mode (see `iberian_2025_blackout.py`'s own calibration notes),
            not guessed.
    """

    id: str
    natural_freq_hz: float
    damping_ratio: float
    _x: float = field(default=0.0, repr=False)
    _v: float = field(default=0.0, repr=False)
    _target: float = field(default=0.0, repr=False)

    @property
    def output(self) -> float:
        """Current per-unit response (0.0 pre-excitation, relaxing toward
        the last `excite()` magnitude thereafter)."""
        return self._x

    def excite(self, magnitude: float = 1.0) -> None:
        """Apply a step input -- NOT a sinusoid (see module docstring)."""
        self._target = magnitude

    def _deriv(self, x: float, v: float) -> tuple[float, float]:
        wn = 2.0 * math.pi * self.natural_freq_hz
        zeta = self.damping_ratio
        dx = v
        dv = wn * wn * (self._target - x) - 2.0 * zeta * wn * v
        return dx, dv

    def step(self, dt_s: float) -> float:
        """Advance one RK4 step of size `dt_s` and return the new `.output`."""
        x0, v0 = self._x, self._v
        k1x, k1v = self._deriv(x0, v0)
        k2x, k2v = self._deriv(x0 + 0.5 * dt_s * k1x, v0 + 0.5 * dt_s * k1v)
        k3x, k3v = self._deriv(x0 + 0.5 * dt_s * k2x, v0 + 0.5 * dt_s * k2v)
        k4x, k4v = self._deriv(x0 + dt_s * k3x, v0 + dt_s * k3v)
        self._x = x0 + (dt_s / 6.0) * (k1x + 2 * k2x + 2 * k3x + k4x)
        self._v = v0 + (dt_s / 6.0) * (k1v + 2 * k2v + 2 * k3v + k4v)
        return self._x


@dataclass
class PrecursorRunResult:
    """Coarse (pandapower-cadence) precursor trend -- the raw material
    `synthesize_precursor_waveform()` interpolates up to full sample rate.

    Attributes:
        times_s: tick times (s), one per `PandapowerQuasiStaticStepper.run()`
            iteration.
        vm_pu: measurement-bus voltage magnitude (per-unit), aligned to
            `times_s`.
        va_degree: measurement-bus voltage angle (degrees), aligned to
            `times_s`.
        oscillator_times_s: oscillator sample times (s), at the finer
            `oscillator_dt_s` cadence -- DELIBERATELY separate from
            `times_s` (see `PandapowerQuasiStaticStepper.run()`'s own
            docstring: recording an oscillator at the coarse `dt_s` cadence
            aliases it whenever `dt_s` doesn't satisfy Nyquist for
            `natural_freq_hz`, e.g. a 1.0s `dt_s` against a 0.63 Hz
            oscillator -- confirmed empirically in this sandbox: it silently
            recovers a false ~0.37 Hz alias instead of the real 0.63 Hz).
        oscillator_output: oscillator id -> `.output` series, aligned to
            `oscillator_times_s` (recorded BEFORE each substep, so
            `oscillator_output[id][0]` is genuinely the pre-excitation 0.0
            state at `oscillator_times_s[0]`, not a one-substep-ahead value).
        events: every `GeneratorEvent` fired during the run, in fire order.
    """

    times_s: list[float]
    vm_pu: list[float]
    va_degree: list[float]
    oscillator_times_s: list[float]
    oscillator_output: dict[str, list[float]]
    events: list[GeneratorEvent]


class PandapowerQuasiStaticStepper:
    """Steps a pandapower net's power flow repeatedly over simulated time,
    polling a list of (pandapower-targeted) `Generator`s each tick and
    advancing a set of `SecondOrderOscillator`s alongside -- the precursor
    phase's own analog of `scenario.py`'s `run_scenario()` DPsim EMT loop,
    at a coarse quasi-static cadence instead of a 200us EMT timestep.

    Generators here do not read `MeasurementState.values`/`.history` (the
    two reused kinds, `PlantBehaviourGenerator`/`OperatorActionGenerator`,
    are purely time-triggered -- confirmed in `generators.py`), so this
    stepper hands every `ready()` call an otherwise-empty `MeasurementState`
    rather than building a real measurement history the way
    `scenario.py`'s own `_build_measurement_state()` does for the EMT loop.
    If a future precursor generator needs real feedback, extend this method,
    not silently assume it already exists.

    Attributes:
        net: the pandapower net (already built by `chaosnet.to_pandapower()`
            plus any scenario-specific `sgen`/`load` additions).
        measurement_bus_id: the pandapower bus index (from `net.bus`, NOT a
            chaosnet tap-name-derived index -- callers resolve that
            translation themselves, e.g. by matching `net.bus["name"]`
            against `to_pandapower()`'s own `f"chaos-bus-{index}"`
            convention) to record `vm_pu`/`va_degree` from each tick.
    """

    def __init__(self, net: pp.pandapowerNet, measurement_bus_id: int) -> None:
        self.net = net
        self.measurement_bus_id = measurement_bus_id

    def run(
        self,
        duration_s: float,
        dt_s: float,
        generators: list[Generator],
        oscillators: dict[str, SecondOrderOscillator],
        oscillator_dt_s: float = 0.02,
        verbose: bool = False,
    ) -> PrecursorRunResult:
        """Run `round(duration_s / dt_s) + 1` ticks, from t=0 to t=duration_s
        inclusive.

        Args:
            duration_s: total precursor time to simulate (s).
            dt_s: quasi-static tick cadence (s) -- the `pandapower.runpp()`
                cadence. Coarse (e.g. 1.0s) is fine for the trend, but is far
                too coarse to RK4-integrate a ~0.63 Hz oscillator directly
                (confirmed empirically in this sandbox: `dt_s=1.0` diverges
                to ~1e156 within 200s -- `dt_s * wn ~= 4.0` is well past
                RK4's stability boundary for an oscillatory system, roughly
                `dt * wn < 2.8`). `oscillator_dt_s` decouples the two
                cadences: each outer tick substeps every oscillator
                `round(dt_s / oscillator_dt_s)` times at the finer interval,
                so the trend stays cheap while the oscillator stays stable.
            generators: pandapower-targeted `Generator`s (their own
                `apply_setpoint`/`apply_action` closures mutate `self.net`
                directly -- this method does not touch generator internals).
            oscillators: id -> `SecondOrderOscillator`, substepped every
                outer tick regardless of firing (excitation is a separate
                generator event; the oscillator's own dynamics run
                continuously once excited).
            oscillator_dt_s: inner RK4 step size (s) for every oscillator --
                default 0.02s is comfortably stable up to several Hz (the
                same order of magnitude `test_precursor.py` uses).
            verbose: print each generator firing as it happens.

        Returns:
            The full `PrecursorRunResult`.
        """
        n_ticks = int(round(duration_s / dt_s))
        n_substeps = max(1, int(round(dt_s / oscillator_dt_s)))
        inner_dt_s = dt_s / n_substeps
        state: MeasurementState = {"t_s": 0.0, "values": {}, "history": {}}

        times_s: list[float] = []
        vm_pu: list[float] = []
        va_degree: list[float] = []
        oscillator_times_s: list[float] = []
        oscillator_output: dict[str, list[float]] = {osc_id: [] for osc_id in oscillators}
        events: list[GeneratorEvent] = []

        for i in range(n_ticks + 1):
            t_s = i * dt_s
            state["t_s"] = t_s
            for gen in generators:
                if gen.ready(t_s, state):
                    ev = gen.fire(self.net, t_s)
                    events.append(ev)
                    if verbose:
                        print(
                            f"  fired: {ev['generator_id']} ({ev['kind']}) at t={t_s:.2f}s"
                        )

            pp.runpp(self.net)

            times_s.append(t_s)
            vm_pu.append(float(self.net.res_bus.at[self.measurement_bus_id, "vm_pu"]))
            va_degree.append(
                float(self.net.res_bus.at[self.measurement_bus_id, "va_degree"])
            )

            if i < n_ticks:
                for sub in range(n_substeps):
                    oscillator_times_s.append(t_s + sub * inner_dt_s)
                    for osc_id, osc in oscillators.items():
                        oscillator_output[osc_id].append(osc.output)
                    for osc in oscillators.values():
                        osc.step(inner_dt_s)
            else:
                oscillator_times_s.append(t_s)
                for osc_id, osc in oscillators.items():
                    oscillator_output[osc_id].append(osc.output)

        return PrecursorRunResult(
            times_s, vm_pu, va_degree, oscillator_times_s, oscillator_output, events
        )


def synthesize_precursor_waveform(
    result: PrecursorRunResult,
    base_kv: float,
    oscillator_gains_v: dict[str, float],
    sample_rate_hz: int = SAMPLE_RATE_HZ,
    fundamental_hz: float = FUNDAMENTAL_HZ,
    measurement_noise_v: float = 0.0,
    rng_seed: int | None = None,
) -> ThreePhaseWaveform:
    """Interpolate a coarse `PrecursorRunResult` up to `sample_rate_hz` and
    build a real instantaneous 3-phase `ThreePhaseWaveform` -- the same
    `mag(t)*cos(2*pi*f*t + phase(t) + 2*pi*k/3)` construction every other
    EMT-derived waveform in this repo already represents, just synthesized
    from a quasi-static trend instead of measured from a live DPsim solve.

    The oscillator perturbation is added as a magnitude-only offset (matches
    `OscillationDetector`'s own |V1|-magnitude-only definition -- no claim
    about real angle/rotor-swing dynamics is made).

    Args:
        result: the stepper's own coarse trend + oscillator output.
        base_kv: nominal line-to-line RMS voltage (kV) of the measurement
            bus -- `vm_pu` is scaled against
            `chaosnet.nominal_peak_line_neutral_v(base_kv)`, the same public
            helper `chaosnet.py`'s own EMT reference-phasor construction
            uses (reused, not re-derived).
        oscillator_gains_v: oscillator id -> peak-volts-per-unit-output gain
            (tuned so the perturbation is visible to
            `OscillationDetector.min_confidence` without dominating the
            underlying trend -- see calibration notes).
        sample_rate_hz: raw instantaneous sample rate (default
            `phase_model.SAMPLE_RATE_HZ`, matching every other waveform in
            this repo so `phasor_frames()` needs no special-casing).
        fundamental_hz: nominal grid frequency (default
            `phase_model.FUNDAMENTAL_HZ`).
        measurement_noise_v: standard deviation (V) of Gaussian noise added
            to the magnitude trend -- a small, explicit SCADA/PMU-class
            measurement-noise floor (default 0.0, i.e. off). Without it a
            decaying oscillator never truly "disappears": its exponential
            envelope approaches zero asymptotically but never crosses it, so
            in a perfectly clean synthetic signal `OscillationDetector`'s
            confidence (a spectral-purity RATIO, peak/total power) stays
            roughly constant even as the oscillation's absolute amplitude
            drops by orders of magnitude -- confirmed empirically in this
            sandbox's own calibration (a "quiet check" window showed
            virtually identical confidence to the active window). A modest
            noise floor is what makes "has this mode genuinely decayed
            below detectability" a real, checkable question instead of a
            numerical artifact -- and is also more physically honest, since
            real telemetry is never noiseless.
        rng_seed: seeds the noise generator so `--step run`/`--step check`
            stay reproducible (this module has no seed of its own -- callers
            pass their own scenario seed through).

    Returns:
        A `ThreePhaseWaveform` spanning `result.times_s[0]` to
        `result.times_s[-1]` at `sample_rate_hz`.
    """
    coarse_t = np.asarray(result.times_s, dtype=float)
    osc_t = np.asarray(result.oscillator_times_s, dtype=float)
    base_v = chaosnet.nominal_peak_line_neutral_v(base_kv)
    mag_v_coarse = np.asarray(result.vm_pu, dtype=float) * base_v
    phase_rad_coarse = np.deg2rad(np.asarray(result.va_degree, dtype=float))

    fine_t = np.arange(coarse_t[0], coarse_t[-1], 1.0 / sample_rate_hz)
    mag_v = np.interp(fine_t, coarse_t, mag_v_coarse)
    phase_rad = np.interp(fine_t, coarse_t, phase_rad_coarse)

    # Oscillators are interpolated against their OWN finer `osc_t` time base,
    # not `coarse_t` -- interpolating a ~0.63 Hz signal that was only ever
    # sampled at `coarse_t`'s 1.0s cadence would silently alias it (see
    # `PrecursorRunResult.oscillator_times_s`'s own docstring).
    for osc_id, gain_v in oscillator_gains_v.items():
        osc_series = np.asarray(result.oscillator_output[osc_id], dtype=float)
        osc_fine = np.interp(fine_t, osc_t, osc_series)
        mag_v = mag_v + gain_v * osc_fine

    if measurement_noise_v > 0.0:
        rng = np.random.default_rng(rng_seed)
        mag_v = mag_v + rng.normal(0.0, measurement_noise_v, size=mag_v.shape)

    omega = 2.0 * np.pi * fundamental_hz
    theta = omega * fine_t + phase_rad
    va = mag_v * np.cos(theta)
    vb = mag_v * np.cos(theta - 2.0 * np.pi / 3.0)
    vc = mag_v * np.cos(theta + 2.0 * np.pi / 3.0)
    return ThreePhaseWaveform(fine_t, va, vb, vc)
