"""Unit tests for `comtrade_writer.write_comtrade` -- fast, no pandapower/
Rust toolchain dependency. Confirms the writer's own output shape (field
counts, ASCII/1999 structure) and that a plain reimplementation of the
ASCII `.dat` grammar recovers the exact sample values written -- the
Python-side half of the cross-language contract
`rust/fft-detector/tests/comtrade_fixture.rs` checks the Rust-side half of.
"""
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SHARED_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SHARED_DIR))
from scenario_engine.comtrade_writer import write_comtrade  # noqa: E402


@dataclass
class _FakeWave:
    """Duck-types `phase_model.ThreePhaseWaveform`'s public attributes
    without needing Lab 5's own sys.path bootstrap."""

    times: np.ndarray
    va: np.ndarray
    vb: np.ndarray
    vc: np.ndarray


def _sample_wave(n: int = 20) -> _FakeWave:
    t = np.arange(n, dtype=float) / 5000.0
    return _FakeWave(
        times=t,
        va=100.0 * np.sin(2 * np.pi * 50.0 * t),
        vb=100.0 * np.sin(2 * np.pi * 50.0 * t - 2 * np.pi / 3),
        vc=100.0 * np.sin(2 * np.pi * 50.0 * t + 2 * np.pi / 3),
    )


def test_cfg_has_3_analog_0_digital_ascii_1999_structure(tmp_path: Path) -> None:
    wave = _sample_wave()
    base = tmp_path / "sample"
    write_comtrade(wave, base)

    lines = base.with_suffix(".cfg").read_text().splitlines()
    assert lines[0].endswith(",1999")
    assert lines[1] == "3,3A,0D"
    for i in range(2, 5):
        assert len(lines[i].split(",")) == 13
    assert lines[-2] == "ASCII"
    assert lines[-1] == "1.0"


def test_dat_row_count_and_field_count_match_wave(tmp_path: Path) -> None:
    wave = _sample_wave(n=37)
    base = tmp_path / "sample"
    write_comtrade(wave, base)

    dat_text = base.with_suffix(".dat").read_text()
    rows = [r for r in dat_text.replace("\x1a", "").splitlines() if r]
    assert len(rows) == 37
    for row in rows:
        assert len(row.split(",")) == 5  # n, timestamp, VA, VB, VC


def test_dat_values_round_trip_exactly(tmp_path: Path) -> None:
    wave = _sample_wave(n=10)
    base = tmp_path / "sample"
    write_comtrade(wave, base)

    rows = [r for r in base.with_suffix(".dat").read_text().replace("\x1a", "").splitlines() if r]
    parsed_va = [float(r.split(",")[2]) for r in rows]
    parsed_vb = [float(r.split(",")[3]) for r in rows]
    parsed_vc = [float(r.split(",")[4]) for r in rows]

    # a=1.0, b=0.0 in the .cfg -> raw .dat values ARE the engineering values.
    np.testing.assert_allclose(parsed_va, wave.va, rtol=1e-5)
    np.testing.assert_allclose(parsed_vb, wave.vb, rtol=1e-5)
    np.testing.assert_allclose(parsed_vc, wave.vc, rtol=1e-5)

    parsed_ts_us = [float(r.split(",")[1]) for r in rows]
    expected_ts_us = (wave.times - wave.times[0]) * 1_000_000.0
    np.testing.assert_allclose(parsed_ts_us, expected_ts_us, atol=1.0)
