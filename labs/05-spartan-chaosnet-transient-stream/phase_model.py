#!/usr/bin/env python3
"""Lab 5 -- the canonical 3-phase waveform state-machine (PSCADOSSE).

PSCADOSSE = "PS/CAD and Open Systems Simulation Engineering": the EMT/phasor
domain and capability set that commercial PS/CAD exemplifies, implemented here
with the open variants this repo recommends (DPsim for EMT, pandapower for
load flow). Using actual commercial PSCAD is a modeller's own choice -- it is
never required in this repo (AGENTS.md non-goal: no commercial engines on the
golden path).

The principle this module realizes: every telemetry view of a fault event is
GENERATED from the same waveform phase state-machine -- there is one source of
truth (the ordered sequence of 3-phase instantaneous-voltage states) and every
derived quantity is a transform of it:

- `ThreePhaseWaveform` -- the state machine itself: ordered `PhaseState`
  records (time_s, va_v, vb_v, vc_v) from a real recording. The raw 5 kHz view
  is literally this object.
- `phasor_frames()` -- C37.118-style synchrophasors (complex, per phase) via a
  one-cycle DFT at the 50 Hz fundamental, generated from the same states.
- `positive_sequence()` / `negative_sequence()` / `zero_sequence()` -- the full
  V1/V2/V0 symmetrical-component triplet, from the same phasors. In general, a
  balanced system has all its voltage in V1 and a genuine unbalanced fault
  (single line-to-ground, line-to-line) puts real magnitude into V0 and/or V2
  -- the standard protection-relay signature for *classifying* a fault, not
  just detecting one (docs/backlog/0006, option 1). **Confirmed against Lab
  5's real run**: `chaos_schedule.yaml`'s `type: line-to-ground` event is
  implemented by `chaosnet.py` as a *symmetric* 3-phase-to-ground switch (a
  diagonal `np.eye(3) * FAULT_CLOSED_RESISTANCE_OHM` matrix -- see README's
  sandbox note 1), which is electrically a three-phase fault, not a true
  single-phase-to-ground fault -- measured directly against a real
  `dpsim_transient_log.json`, |V0| stays at numerical zero (~1e-12 V)
  throughout, and |V2| only shows a small switching-transient blip (tens of V
  against a ~13 kV |V1|), not a sustained fault-window rise. The sequence view
  is honest about this: it shows V1 dipping uniformly and V0/V2 staying flat,
  which is the correct symmetric-fault signature for what this model actually
  simulates, not the asymmetric single-LG signature its schedule's label
  might suggest.
- `scada_rms()` -- SCADA/EMS 4 s RMS aggregation, generated from the same
  states (no separate data path).

Nothing here fabricates physics: the states come from a real DPsim solve
(`dpsim_transient_log.json`); this module only turns them into the standard
power-system views.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

import numpy as np

# Power-system fundamental (NEM is 50 Hz); the phasor DFT is evaluated at this
# bin over one full cycle (100 samples at the 5 kHz recording rate).
FUNDAMENTAL_HZ: float = 50.0
# Default recording sample rate (DPsim log step 200 us -> 5000 Hz).
SAMPLE_RATE_HZ: int = 5000
# C37.118 synchrophasor reporting rate (frames per second) -- the PDU output
# rate. 100 Hz > the 50 Hz fundamental, so one-cycle frames overlap (50-sample
# stride at 5 kHz).
PHASOR_RATE_HZ: int = 100
# SCADA/EMS update cadence (s) -- the classic control-center telemetry rate.
SCADA_UPDATE_S: float = 4.0


@dataclass(frozen=True)
class PhaseState:
    """One instantaneous 3-phase state of the waveform (the state-machine node).

    Attributes:
        time_s: simulated time (s).
        va_v / vb_v / vc_v: the three phase instantaneous voltages (V).
    """

    time_s: float
    va_v: float
    vb_v: float
    vc_v: float


class ThreePhaseWaveform:
    """The ordered phase-state sequence -- the single source of truth.

    Holds the real recorded states and generates every derived view
    (raw/phasor/SCADA) from them, so the views can never disagree about what
    the waveform was.

    Attributes:
        times: recorded sample times (s).
        va / vb / vc: per-phase instantaneous voltages (V), aligned to `times`.
    """

    def __init__(self, times: np.ndarray, va: np.ndarray, vb: np.ndarray, vc: np.ndarray) -> None:
        if not (len(times) == len(va) == len(vb) == len(vc)):
            raise ValueError("times/va/vb/vc must all have the same length")
        if len(times) < 2:
            raise ValueError("need at least two samples")
        self.times = np.asarray(times, dtype=float)
        self.va = np.asarray(va, dtype=float)
        self.vb = np.asarray(vb, dtype=float)
        self.vc = np.asarray(vc, dtype=float)

    @classmethod
    def from_log(cls, log: dict) -> "ThreePhaseWaveform":
        """Build the state machine from a dpsim_transient_log.json dict."""
        return cls(
            np.asarray(log["times"], dtype=float),
            np.asarray(log["va"], dtype=float),
            np.asarray(log["vb"], dtype=float),
            np.asarray(log["vc"], dtype=float),
        )

    def states(self) -> list[PhaseState]:
        """The ordered state sequence (list of PhaseState records)."""
        return [
            PhaseState(float(t), float(a), float(b), float(c))
            for t, a, b, c in zip(self.times, self.va, self.vb, self.vc)
        ]

    @property
    def duration_s(self) -> float:
        """Recording duration (s) = last sample time."""
        return float(self.times[-1])


# --- Generated views (all transforms of the same state machine) --------------


def phasor_frames(
    wave: ThreePhaseWaveform, rate_hz: int = PHASOR_RATE_HZ,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """C37.118-style synchrophasors for all three phases, at `rate_hz`.

    One-cycle DFT at FUNDAMENTAL_HZ, frame centered every 1/rate_hz s
    (overlapping windows -- a PMU's standard estimate, not naive decimation):
    X = (2/N) * sum(x[n] * exp(-j*2*pi*(n - n0)/N)) over one cycle. Every
    phase goes through the identical estimator, generated from the same
    states, so the phasor view is literally the same data as the raw view.

    Args:
        wave: the waveform state machine.
        rate_hz: phasor reporting rate (default PHASOR_RATE_HZ = 100).

    Returns:
        (frame_times_s, ph_a, ph_b, ph_c) -- complex phasor arrays per phase.
    """
    fs = SAMPLE_RATE_HZ
    n_cycle = int(round(fs / FUNDAMENTAL_HZ))  # 100 samples/cycle @ 5 kHz
    stride = max(1, int(round(fs / rate_hz)))
    n0 = n_cycle // 2
    k_cycle = np.arange(n_cycle)
    weights = np.exp(-2j * np.pi * k_cycle / n_cycle)

    frame_times: list[float] = []
    acc: dict[str, list[complex]] = {"va": [], "vb": [], "vc": []}
    for center in range(n0, len(wave.times) - n0, stride):
        frame_times.append(float(wave.times[center]))
        for key, series in (("va", wave.va), ("vb", wave.vb), ("vc", wave.vc)):
            win = series[center - n0: center - n0 + n_cycle]
            acc[key].append(complex(np.sum(win * weights)) * (2.0 / n_cycle))
    return (
        np.asarray(frame_times),
        np.asarray(acc["va"]),
        np.asarray(acc["vb"]),
        np.asarray(acc["vc"]),
    )


def positive_sequence(
    ph_a: np.ndarray, ph_b: np.ndarray, ph_c: np.ndarray,
) -> np.ndarray:
    """Positive-sequence phasor (symmetrical components), complex per frame.

    V1 = (Va + a*Vb + a^2*Vc) / 3 with a = e^(j 120 deg) -- the standard
    C37.118 sequence quantity. A balanced system keeps |V1| at the phase
    amplitude; a line-to-ground fault drops it (the faulted phase collapses
    while the others swell), so |V1| is the cleanest single anomaly signal.

    Args:
        ph_a/ph_b/ph_c: complex phasor arrays (same frame times).

    Returns:
        Complex V1 array per frame (|.| gives the magnitude).
    """
    a = np.exp(2j * np.pi / 3)
    return (ph_a + a * ph_b + a**2 * ph_c) / 3.0


def negative_sequence(
    ph_a: np.ndarray, ph_b: np.ndarray, ph_c: np.ndarray,
) -> np.ndarray:
    """Negative-sequence phasor (symmetrical components), complex per frame.

    V2 = (Va + a^2*Vb + a*Vc) / 3 -- the same rotation-factor construction as
    `positive_sequence()` with the a/a^2 terms swapped. A balanced 3-phase
    system has |V2| ~ 0; an unbalanced fault puts real magnitude into it
    (line-to-line and line-to-ground faults both do; a symmetric 3-phase
    fault does not), which is what makes V2 a *classification* signal rather
    than only a magnitude-of-dip signal like |V1| alone.

    Args:
        ph_a/ph_b/ph_c: complex phasor arrays (same frame times).

    Returns:
        Complex V2 array per frame (|.| gives the magnitude).
    """
    a = np.exp(2j * np.pi / 3)
    return (ph_a + a**2 * ph_b + a * ph_c) / 3.0


def zero_sequence(
    ph_a: np.ndarray, ph_b: np.ndarray, ph_c: np.ndarray,
) -> np.ndarray:
    """Zero-sequence phasor (symmetrical components), complex per frame.

    V0 = (Va + Vb + Vc) / 3 -- no rotation factors, since the zero-sequence
    component is in-phase across all three conductors by definition. A
    balanced system, and any *symmetric* event (all three phases faulted
    identically -- see this module's docstring re: Lab 5's actual fault
    model), keeps |V0| ~ 0. A genuine single-phase (or two-phase)-to-ground
    fault would break the Va+Vb+Vc=0 identity a healthy 3-wire system holds,
    and |V0| present alongside a |V1| dip would be that fault's signature --
    but that is a claim about the general theory, not about what Lab 5's
    committed `chaos_schedule.yaml` scenario actually produces (it stays
    symmetric, so |V0| stays at numerical zero there; see the module
    docstring for the measured confirmation).

    Args:
        ph_a/ph_b/ph_c: complex phasor arrays (same frame times).

    Returns:
        Complex V0 array per frame (|.| gives the magnitude).
    """
    return (ph_a + ph_b + ph_c) / 3.0


def scada_rms(
    wave: ThreePhaseWaveform, update_s: float = SCADA_UPDATE_S,
) -> list[tuple[float, float, float]]:
    """SCADA/EMS telemetry at `update_s`: phase-A RMS per interval.

    One (start, end, rms_V) per update interval overlapping the recording --
    generated from the same states as the raw/phasor views. With a short
    recording the whole event fits inside a single interval (that is the
    SCADA-can't-see-the-transient lesson, not a bug).

    Args:
        wave: the waveform state machine.
        update_s: SCADA update cadence (s).

    Returns:
        Sorted [(interval_start_s, interval_end_s, rms_V)].
    """
    end_t = wave.duration_s
    out: list[tuple[float, float, float]] = []
    start = 0.0
    while start < end_t:
        stop = start + update_s
        m = (wave.times >= start) & (wave.times < stop)
        rms = float(np.sqrt(np.mean(wave.va[m] ** 2))) if m.any() else 0.0
        out.append((start, min(stop, end_t), rms))
        start = stop
    return out


def peak_deviation_bins(
    wave: ThreePhaseWaveform, trigger_s: float, window_s: float,
) -> list[tuple[float, float, float]]:
    """Peak deviation magnitude per window -- the anomaly-rate signal.

    Deviation(t) = max over phases of max(0, |v_phase(t)| - reference_peak),
    where reference_peak is that phase's pre-fault peak (the KISS "beyond
    nominal" measure, reference window = states before `trigger_s`). A bin's
    value is the peak of deviation(t) within the window. Generated from the
    same states as every other view, so the classifier's input can never
    disagree with what the waveform was.

    Args:
        wave: the waveform state machine.
        trigger_s: fault trigger time (s); states before it define the
            pre-fault reference peaks.
        window_s: aggregation window length (s).

    Returns:
        Sorted [(window_start_s, window_end_s, peak_deviation_V)].
    """
    t = wave.times
    phases = np.stack([wave.va, wave.vb, wave.vc], axis=1)
    pre = t < trigger_s
    ref_peaks = np.abs(phases[pre]).max(axis=0)
    deviation = np.max(np.maximum(0.0, np.abs(phases) - ref_peaks), axis=1)

    bins: list[tuple[float, float, float]] = []
    start = 0.0
    end = float(t[-1])
    while start < end:
        win_end = min(start + window_s, end)
        m = (t >= start) & (t < win_end)
        bins.append((start, win_end, float(deviation[m].max()) if m.any() else 0.0))
        start = win_end
    return bins
