#!/usr/bin/env python3
"""Generate the committed COMTRADE fixtures + expected-finding JSON this
lab's Rust cross-language test (`rust/fft-detector/tests/comtrade_fixture.rs`)
checks against.

Reuses the real, already-calibrated Iberian 2025 precursor scenario
(`labs/05-spartan-chaosnet-transient-stream/scenarios/iberian_2025_blackout.py`)
up through its own `synthesize_precursor_waveform()` call -- same topology,
same `SecondOrderOscillator`s, same trend generators -- rather than
reinventing a synthetic signal. From that one real waveform, slices out a
window around each named oscillation mode (0.63 Hz local, 0.2 Hz
inter-area), runs Python's own `OscillationDetector.consume()` on each
slice to get real reference numbers, and writes both the COMTRADE fixture
and the expected-finding JSON the Rust test asserts against -- the same
"Python computes it in-memory, Rust reads it back from the file format"
proof this lab exists to demonstrate.

Not run by the fast test suite (real pandapower solve, ~40s) -- run by
hand (`just lab7-fixture`) whenever the precursor scenario's own physics
changes and the fixtures need regenerating.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_LAB5_SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "05-spartan-chaosnet-transient-stream" / "scenarios"
_LAB5_DIR = _LAB5_SCENARIOS_DIR.parent
for _p in (str(_LAB5_SCENARIOS_DIR), str(_LAB5_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import chaosnet  # noqa: E402
import pandapower as pp  # noqa: E402
import iberian_2025_blackout as ib  # noqa: E402

from _shared.scenario_engine.comtrade_writer import write_comtrade  # noqa: E402
from _shared.scenario_engine.detectors import OscillationDetector  # noqa: E402
from _shared.scenario_engine.precursor import PandapowerQuasiStaticStepper, SecondOrderOscillator, synthesize_precursor_waveform  # noqa: E402
from phase_model import ThreePhaseWaveform  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# Real slices of the full [0, 1740]s precursor window (production analysis
# windows are 90s/80s; these are shorter real slices of the SAME waveform,
# long enough for a clean FFT read (>=12 cycles local, >=5 cycles inter-
# area) while keeping the committed .dat file small.
LOCAL_SLICE_START_S = 80.0
LOCAL_SLICE_END_S = 100.0
INTER_AREA_SLICE_START_S = 1035.0
INTER_AREA_SLICE_END_S = 1060.0


def _build_wave(seed: int) -> ThreePhaseWaveform:
    topology = chaosnet.build_chaos_topology(seed)
    net = chaosnet.to_pandapower(topology)

    local_bus_idx = topology["tap_buses"][topology["tap_names"].index(ib.RES_TAP)]
    bus_name = f"chaos-bus-{local_bus_idx}"
    res_bus_id = int(net.bus.index[net.bus["name"] == bus_name][0])
    res_bus_vn_kv = float(net.bus.at[res_bus_id, "vn_kv"])

    sgen_idx = pp.create_sgen(net, bus=res_bus_id, p_mw=0.0, q_mvar=0.0, name="precursor_res_injection")
    accumulator = ib._QAccumulator(net, sgen_idx)

    local_osc = SecondOrderOscillator(
        id="local", natural_freq_hz=ib.LOCAL_MODE_NATURAL_FREQ_HZ, damping_ratio=ib.LOCAL_MODE_DAMPING_RATIO
    )
    inter_area_osc = SecondOrderOscillator(
        id="inter-area", natural_freq_hz=ib.INTER_AREA_MODE_NATURAL_FREQ_HZ, damping_ratio=ib.INTER_AREA_MODE_DAMPING_RATIO
    )
    generators = ib._build_precursor_generators(net, accumulator, local_osc, inter_area_osc)

    print(f"[generate_fixture] solving {ib.PRECURSOR_DURATION_S:.0f}s quasi-static precursor (seed={seed})...")
    stepper = PandapowerQuasiStaticStepper(net, res_bus_id)
    result = stepper.run(
        duration_s=ib.PRECURSOR_DURATION_S,
        dt_s=ib.PRECURSOR_DT_S,
        generators=generators,
        oscillators={"local": local_osc, "inter-area": inter_area_osc},
        oscillator_dt_s=ib.PRECURSOR_OSCILLATOR_DT_S,
        verbose=False,
    )

    return synthesize_precursor_waveform(
        result,
        base_kv=res_bus_vn_kv,
        oscillator_gains_v={"local": ib.LOCAL_MODE_GAIN_V, "inter-area": ib.INTER_AREA_MODE_GAIN_V},
        measurement_noise_v=ib.PRECURSOR_MEASUREMENT_NOISE_V,
        rng_seed=seed,
    )


def _slice_wave(wave: ThreePhaseWaveform, start_s: float, end_s: float) -> ThreePhaseWaveform:
    mask = (wave.times >= start_s) & (wave.times <= end_s)
    return ThreePhaseWaveform(wave.times[mask], wave.va[mask], wave.vb[mask], wave.vc[mask])


def _generate_one(wave: ThreePhaseWaveform, name: str, detector_id: str, analysis_window_s: float, min_confidence: float) -> None:
    up_to_s = float(wave.times[-1])
    detector = OscillationDetector(id=detector_id, analysis_window_s=analysis_window_s, min_confidence=min_confidence)
    findings = detector.consume(wave, up_to_s)
    if not findings:
        raise RuntimeError(f"{name}: no finding recovered from the real slice -- check window bounds/gains")
    finding = findings[0]
    print(f"[generate_fixture] {name}: mode_hz={finding['detail']['mode_hz']:.5f} confidence={finding['confidence']:.4f}")

    base_path = FIXTURES_DIR / name
    write_comtrade(wave, base_path, station_name=name.upper())

    expected = {
        "mode_hz": finding["detail"]["mode_hz"],
        "confidence": finding["confidence"],
        "window_s": analysis_window_s,
        "min_confidence": min_confidence,
    }
    (FIXTURES_DIR / f"{name}.expected.json").write_text(json.dumps([expected], indent=2) + "\n")


def main() -> None:
    FIXTURES_DIR.mkdir(exist_ok=True)
    wave = _build_wave(chaosnet.DEFAULT_SEED)

    local_slice = _slice_wave(wave, LOCAL_SLICE_START_S, LOCAL_SLICE_END_S)
    _generate_one(
        local_slice, "local_mode", "oscillation-local-mode",
        analysis_window_s=LOCAL_SLICE_END_S - LOCAL_SLICE_START_S, min_confidence=0.1,
    )

    inter_area_slice = _slice_wave(wave, INTER_AREA_SLICE_START_S, INTER_AREA_SLICE_END_S)
    _generate_one(
        inter_area_slice, "inter_area_mode", "oscillation-inter-area-mode",
        analysis_window_s=INTER_AREA_SLICE_END_S - INTER_AREA_SLICE_START_S, min_confidence=0.1,
    )

    print("[generate_fixture] done.")


if __name__ == "__main__":
    main()
