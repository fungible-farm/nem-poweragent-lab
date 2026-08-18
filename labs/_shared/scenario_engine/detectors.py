"""Composable telemetry `Detector`s for the scenario engine
(docs/prd/0001-composable-generator-detector-platform.md).

A `Detector` consumes the telemetry stream and emits `Finding` records.
Every concrete detector here is a *thin transform* of
`phase_model.py`'s existing views (`ThreePhaseWaveform`, `phasor_frames()`,
`positive_sequence()`, `scada_rms()`) -- no waveform/phasor math is
reimplemented, per PRD-0001 Goal 2's explicit requirement. Five detectors,
the first four feeding the fifth:

- `OscillationDetector` -- mode/frequency estimate from the phasor stream
  (the one detector with genuinely new signal-processing logic: nothing in
  phase_model.py estimates a mode frequency today).
- `RoCoFDetector` -- rate-of-change-of-frequency from consecutive
  positive-sequence phase differences.
- `VoltageCascadeDetector` -- cumulative voltage-rise acceleration (a
  scoped-down version of PRD-0001's own description -- see that class's
  own docstring for the named limitation).
- `AngleSeparationDetector` -- inter-region phase-angle separation.
- `CascadingFailureClassifier` -- composites the other four detectors'
  own Finding output into one "heading toward a blackout" trajectory
  score -- the item Lab 5's Definition of Done named and explicitly
  deferred ("does not implement SPARTAN's anomaly-detection logic... a
  subsequent phase").

Cross-lab dependency note (deliberate, documented deviation from
`gridfit.py`'s own "labs import _shared, never the reverse" convention):
this module imports `labs/05-spartan-chaosnet-transient-stream/phase_model.py`
directly, via the `sys.path` bootstrap below, because PRD-0001 requires
detectors to be thin transforms of that module's views rather than a
reimplementation, and because -- per PRD-0001's own "Where this lives"
section -- this package conceptually lives alongside Lab 5's EMT/DPsim
plumbing, not a Labs-1-3-style generic utility.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, TypedDict

import numpy as np

_LAB5_DIR = Path(__file__).resolve().parent.parent.parent / "05-spartan-chaosnet-transient-stream"
if str(_LAB5_DIR) not in sys.path:
    sys.path.insert(0, str(_LAB5_DIR))

from phase_model import (  # noqa: E402  (see sys.path bootstrap above)
    ThreePhaseWaveform,
    phasor_frames,
    positive_sequence,
    scada_rms,
)


class Finding(TypedDict):
    """One detector finding -- PRD-0001's own sketch, typed.

    Attributes:
        detector_id: the emitting Detector's own `id`.
        time_s: simulated time (s) this finding applies to.
        kind: one of "oscillation" | "voltage_cascade" | "rocof" |
            "angle_separation" | "composite".
        confidence: 0.0-1.0 detector-defined confidence.
        detail: kind-specific extra fields.
    """

    detector_id: str
    time_s: float
    kind: str
    confidence: float
    detail: dict


class Detector(Protocol):
    """PRD-0001's Detector interface: consumes the telemetry stream and
    emits scored, timestamped Findings."""

    id: str

    def consume(self, wave: ThreePhaseWaveform, up_to_s: float) -> list[Finding]:
        """Return every Finding this detector identifies in `wave`, up to
        and including simulated time `up_to_s`."""
        ...


# --- Concrete detectors ------------------------------------------------------


@dataclass
class OscillationDetector:
    """Mode-frequency estimate from the phasor stream -- the one detector
    with genuinely new signal-processing logic (phase_model.py has no
    mode estimator today), per PRD-0001 "Composable capability:
    Detectors". Reuses `phasor_frames()`/`positive_sequence()` for the
    phasor view itself (no reimplementation of the phasor DFT); the
    mode-frequency estimate is a plain FFT of `|V1|`'s fluctuation around
    its own trailing-window mean.

    Iberian's report (cited in PRD-0001's own Detectors section) names two
    concrete real targets (a 0.63 Hz local mode, a 0.2 Hz inter-area mode)
    -- this synthetic platform round's own demo scenario has neither of
    those real precursors and instead detects the real switching-transient
    ringing chaosnet.py's own fault-resistance sweep already documents
    (see chaosnet.py's `FAULT_CLOSED_RESISTANCE_OHM` comment), which is a
    genuine, non-fabricated oscillatory mode in the same |V1| signal, just
    not a historical one -- exactly what PRD-0001's "platform smoke test,
    not a historical-accuracy attempt" framing calls for.

    Attributes:
        id: unique detector id.
        analysis_window_s: trailing window (s) of phasor-frame history the
            FFT is taken over.
        min_confidence: below this confidence, `consume()` reports no
            finding for that call (a flat/decayed magnitude series
            legitimately has no coherent mode to report).
    """

    id: str
    analysis_window_s: float = 1.0
    min_confidence: float = 0.15

    def consume(self, wave: ThreePhaseWaveform, up_to_s: float) -> list[Finding]:
        frame_times, pa, pb, pc = phasor_frames(wave)
        mask = frame_times <= up_to_s
        frame_times = frame_times[mask]
        if len(frame_times) < 8:
            return []
        v1 = positive_sequence(pa[mask], pb[mask], pc[mask])
        mag = np.abs(v1)
        window_mask = frame_times >= (up_to_s - self.analysis_window_s)
        t_win = frame_times[window_mask]
        mag_win = mag[window_mask]
        if len(mag_win) < 8:
            return []
        detrended = mag_win - np.mean(mag_win)
        if np.allclose(detrended, 0.0):
            return []
        dt = float(np.mean(np.diff(t_win)))
        fft = np.fft.rfft(detrended * np.hanning(len(detrended)))
        freqs = np.fft.rfftfreq(len(detrended), d=dt)
        power = np.abs(fft)
        if len(power) < 2:
            return []
        # Skip the DC bin (index 0): a "mode" means a nonzero oscillation
        # frequency, not the already-removed mean.
        peak_idx = 1 + int(np.argmax(power[1:]))
        peak_power = float(power[peak_idx])
        total_power = float(np.sum(power[1:])) or 1.0
        confidence = min(1.0, peak_power / total_power)
        if confidence < self.min_confidence:
            return []
        return [
            {
                "detector_id": self.id,
                "time_s": float(t_win[-1]),
                "kind": "oscillation",
                "confidence": confidence,
                "detail": {
                    "mode_hz": float(freqs[peak_idx]),
                    "window_s": self.analysis_window_s,
                },
            }
        ]


# Frame lag (in phasor_frames() output indices) used by RoCoFDetector's
# phase-difference estimator, in preference to consecutive-frame
# differencing. phase_model.py's own PHASOR_RATE_HZ (100 Hz) is exactly
# 2x FUNDAMENTAL_HZ (50 Hz) by that module's own documented design (its
# "50-sample stride" choice) -- which means a *consecutive*-frame phase
# difference sits exactly at the pi-radian ambiguity boundary of phase
# unwrapping at nominal frequency (each frame is precisely half a nominal
# cycle apart), numerically unusable (confirmed empirically in this
# sandbox: a naive consecutive-frame np.unwrap() produced spurious
# +-2500-5000 Hz/s "RoCoF" throughout an otherwise-steady pre-fault
# window). Comparing frames `ROCOF_FRAME_LAG` apart (2 frames = one full
# nominal cycle) makes the *expected* raw phase delta at nominal frequency
# ~0 rad instead of ~pi rad -- safely inside np.angle()'s own unambiguous
# (-pi, pi] range for any physically plausible frequency deviation, and a
# standard PMU frequency-estimation choice (compare phase over a full
# cycle rather than a half cycle).
ROCOF_FRAME_LAG: int = 2


@dataclass
class RoCoFDetector:
    """Rate-of-change-of-frequency threshold detector -- PRD-0001's own
    text: "good first one to get right and test." Frequency deviation from
    `phase_model.FUNDAMENTAL_HZ` is derived from the positive-sequence
    phasor's own phase progression between frames `ROCOF_FRAME_LAG` apart
    (see that constant's own comment for why not consecutive frames):
    `f_dev = angle(V1[i+lag] * conj(V1[i])) / (2*pi*dt_lag)`, the standard
    PMU phase-difference frequency identity; RoCoF is a further finite
    difference of that series.

    Attributes:
        id: unique detector id.
        threshold_hz_per_s: |RoCoF| above this triggers a finding. AEMO's
            2026 GPSRR report states RoCoF stayed within +-1 Hz/s until
            the Iberian blackout's final collapse instant (cited in
            PRD-0001's own Detectors section) -- used here only as this
            detector's *default*, not asserted as this synthetic demo's
            own ground truth (a scenario's own fixture states its own
            value).
    """

    id: str
    threshold_hz_per_s: float = 1.0

    def consume(self, wave: ThreePhaseWaveform, up_to_s: float) -> list[Finding]:
        frame_times, pa, pb, pc = phasor_frames(wave)
        mask = frame_times <= up_to_s
        frame_times = frame_times[mask]
        lag = ROCOF_FRAME_LAG
        if len(frame_times) < lag + 2:
            return []
        v1 = positive_sequence(pa[mask], pb[mask], pc[mask])
        dt_lag = frame_times[lag:] - frame_times[:-lag]
        raw_delta = np.angle(v1[lag:] * np.conj(v1[:-lag]))
        f_dev = raw_delta / (2.0 * np.pi * dt_lag)
        t_mid = (frame_times[lag:] + frame_times[:-lag]) / 2.0
        rocof = np.gradient(f_dev, t_mid)
        findings: list[Finding] = []
        for t, r in zip(t_mid, rocof):
            if abs(r) > self.threshold_hz_per_s:
                findings.append(
                    {
                        "detector_id": self.id,
                        "time_s": float(t),
                        "kind": "rocof",
                        "confidence": min(1.0, abs(r) / self.threshold_hz_per_s),
                        "detail": {"rocof_hz_s": float(r)},
                    }
                )
        return findings


@dataclass
class VoltageCascadeDetector:
    """Cumulative voltage-rise acceleration detector -- a scoped-down
    version of PRD-0001's own description (generation-loss-vs-voltage-rise
    correlation). This platform round has no generation-loss telemetry
    source (no plant/dispatch model feeds phase_model.py today), so this
    implementation tracks the one signal phase_model.py actually
    produces -- `scada_rms()`'s own RMS trend -- and flags an accelerating
    rise above a reference baseline. Named limitation, not hidden: a
    scenario with a real generation-loss series (e.g. 0002's SA 2016
    wind-farm MW figure) should extend `consume()`'s inputs, not silently
    claim the correlation this class doesn't yet compute.

    Attributes:
        id: unique detector id.
        rise_threshold_v: absolute RMS rise above the pre-run reference
            baseline (the first `scada_rms()` interval) that counts as
            "cascade in progress."
        acceleration_threshold_v_per_s2: minimum second derivative of the
            RMS trend (V/s^2) required alongside `rise_threshold_v`, so a
            slow, non-accelerating rise doesn't false-positive.
    """

    id: str
    rise_threshold_v: float
    acceleration_threshold_v_per_s2: float

    def consume(self, wave: ThreePhaseWaveform, up_to_s: float) -> list[Finding]:
        intervals = [iv for iv in scada_rms(wave) if iv[1] <= up_to_s + 1e-9]
        if len(intervals) < 3:
            return []
        baseline = intervals[0][2]
        mids = np.array([(a + b) / 2.0 for a, b, _ in intervals])
        rms = np.array([v for _, _, v in intervals])
        rise = rms - baseline
        accel = np.gradient(np.gradient(rms, mids), mids)
        findings: list[Finding] = []
        for t, r, a in zip(mids, rise, accel):
            if r > self.rise_threshold_v and a > self.acceleration_threshold_v_per_s2:
                findings.append(
                    {
                        "detector_id": self.id,
                        "time_s": float(t),
                        "kind": "voltage_cascade",
                        "confidence": min(1.0, float(r) / self.rise_threshold_v),
                        "detail": {"rise_v": float(r), "acceleration_v_s2": float(a)},
                    }
                )
        return findings


@dataclass
class AngleSeparationDetector:
    """Inter-region phase-angle separation detector -- the detector-side
    mirror of `IslandingProtectionGenerator` (PRD-0001's own framing):
    tracks the positive-sequence phase-angle difference between two named
    buses, flagging the precursor before a real islanding/out-of-step
    trip. Reuses `phasor_frames()`/`positive_sequence()` for both buses --
    no independent angle math.

    Attributes:
        id: unique detector id.
        region_b_wave: the second bus's waveform (region A is whatever
            `wave` `consume()` is called with) -- fixed at construction
            since a scenario run produces one waveform per monitored bus
            and this detector always compares the same named pair.
        threshold_deg: angle separation (degrees) above which a finding is
            emitted.
    """

    id: str
    region_b_wave: ThreePhaseWaveform
    threshold_deg: float

    def consume(self, wave: ThreePhaseWaveform, up_to_s: float) -> list[Finding]:
        ta, paa, pab, pac = phasor_frames(wave)
        tb, pba, pbb, pbc = phasor_frames(self.region_b_wave)
        n = min(len(ta), len(tb))
        ta = ta[:n]
        mask = ta <= up_to_s
        v1a = positive_sequence(paa[:n], pab[:n], pac[:n])[mask]
        v1b = positive_sequence(pba[:n], pbb[:n], pbc[:n])[mask]
        times = ta[mask]
        sep_deg = np.degrees(np.angle(v1a) - np.angle(v1b))
        sep_deg = (sep_deg + 180.0) % 360.0 - 180.0  # wrap to [-180, 180)
        findings: list[Finding] = []
        for t, s in zip(times, sep_deg):
            if abs(s) > self.threshold_deg:
                findings.append(
                    {
                        "detector_id": self.id,
                        "time_s": float(t),
                        "kind": "angle_separation",
                        "confidence": min(1.0, abs(float(s)) / self.threshold_deg),
                        "detail": {"angle_sep_deg": float(s)},
                    }
                )
        return findings


# Composite score weights per Finding kind for CascadingFailureClassifier's
# default -- oscillation and rocof are direct fast-dynamics precursors
# (weighted higher), voltage_cascade/angle_separation are slower structural
# precursors (weighted lower). An illustrative, documented default for this
# synthetic platform round, not a value tuned against a real incident --
# 0002/0003's own scenarios should override with values tuned against their
# own real fixture, not this default.
DEFAULT_KIND_WEIGHTS: dict[str, float] = {
    "oscillation": 0.4,
    "rocof": 0.4,
    "voltage_cascade": 0.15,
    "angle_separation": 0.15,
}


@dataclass
class CascadingFailureClassifier:
    """Composite "heading toward a blackout" classifier -- combines
    Findings already emitted by the other four detectors into one
    trajectory score over time, per PRD-0001's own framing (the item Lab
    5's Definition of Done named and explicitly deferred: "does not
    implement SPARTAN's anomaly-detection logic... a subsequent phase").

    Does not consume a waveform directly: its whole point is compositing
    already-computed signals, not recomputing them (no reimplementation of
    any of the four). `consume()` still accepts the same
    `(wave, up_to_s)` shape as every other Detector (so callers can treat
    all five uniformly) but ignores `wave`, operating instead on Findings
    registered via `set_source_findings()`.

    Attributes:
        id: unique detector id.
        weight_by_kind: per-Finding-kind weight in the composite score
            (missing kinds default to 0.0 -- see `DEFAULT_KIND_WEIGHTS`).
        min_score: composite score above which a "composite" Finding is
            emitted for a given time bucket.
    """

    id: str
    weight_by_kind: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_KIND_WEIGHTS)
    )
    min_score: float = 0.5
    _source_findings: list[Finding] = field(default_factory=list, repr=False)

    def set_source_findings(self, findings: list[Finding]) -> None:
        """Register the other four detectors' Finding output this
        classifier composites over (call once per run before `consume()`).
        """
        self._source_findings = list(findings)

    def consume(self, wave: ThreePhaseWaveform, up_to_s: float) -> list[Finding]:
        """Detector-protocol entry point: composites over the Findings
        already registered via `set_source_findings()`. `wave` is unused
        (see class docstring) -- accepted only so every detector's
        `consume()` call site stays uniform."""
        return self._classify(self._source_findings, up_to_s)

    def _classify(self, findings: list[Finding], up_to_s: float) -> list[Finding]:
        """Combine prior Findings into composite trajectory Findings.

        Args:
            findings: Finding records already produced by the other four
                detectors against the same run.
            up_to_s: only Findings with `time_s <= up_to_s` are considered.

        Returns:
            One composite Finding per distinct `time_s` bucket whose
            weighted score exceeds `min_score`, sorted by `time_s`.
        """
        by_time: dict[float, float] = {}
        contributors: dict[float, list[str]] = {}
        for f in findings:
            if f["time_s"] > up_to_s:
                continue
            w = self.weight_by_kind.get(f["kind"], 0.0)
            score = w * f["confidence"]
            by_time[f["time_s"]] = by_time.get(f["time_s"], 0.0) + score
            contributors.setdefault(f["time_s"], []).append(f["kind"])
        out: list[Finding] = []
        for t in sorted(by_time):
            if by_time[t] >= self.min_score:
                out.append(
                    {
                        "detector_id": self.id,
                        "time_s": t,
                        "kind": "composite",
                        "confidence": min(1.0, by_time[t]),
                        "detail": {"contributors": contributors[t], "score": by_time[t]},
                    }
                )
        return out
