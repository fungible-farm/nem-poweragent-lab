"""Hand-written ASCII COMTRADE (IEEE C37.111, revision "1999") writer.

No PyPI package writes COMTRADE (`comtrade`/`python-comtrade` is read-only;
`comtradehandlers` is a real writer but unmaintained and not published).
The ASCII format is small enough to hand-write directly rather than depend
on an unpublished git package -- this matches this repo's own established
preference for small explicit code over unmaintained deps (see
`run_dpsim.py`'s `_write_villas_csv()`). The field-by-field spec below was
cross-validated against two independent open-source implementations
(`dparrini/python-comtrade` as reader, `relihanl/comtradehandlers` as
writer) during this feature's own research pass.

Declares revision "1999" (not "2013") deliberately -- it needs none of the
2013-only optional lines (`time_code,local_code` / `tmq_code,leap_second`)
and is universally supported by COMTRADE readers, including the Rust
reader this project's own `rust/fft-detector/src/comtrade.rs` implements.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # `phase_model` only resolves once a caller has bootstrapped
    # `labs/05-spartan-chaosnet-transient-stream` onto sys.path (see
    # `detectors.py`'s own bootstrap) -- this module only needs
    # `ThreePhaseWaveform`'s duck-typed `.times`/`.va`/`.vb`/`.vc`
    # attributes, not the class itself, so the import stays type-only.
    from phase_model import ThreePhaseWaveform

_CRLF = "\r\n"


def write_comtrade(wave: ThreePhaseWaveform, base_path: Path, station_name: str = "LAB7") -> None:
    """Write `base_path.cfg` and `base_path.dat` for `wave`'s VA/VB/VC.

    `base_path` should have no suffix, e.g. `Path("out/precursor")` writes
    `out/precursor.cfg` and `out/precursor.dat`.
    """
    cfg_path = base_path.with_suffix(".cfg")
    dat_path = base_path.with_suffix(".dat")

    n = len(wave.times)
    line_frequency = 50.0

    cfg_lines = [
        f"{station_name},,1999",
        "3,3A,0D",
        # An,ch_id,ph,ccbm,uu,a,b,skew,min,max,primary,secondary,PS
        "1,VA,A,,V,1.0,0.0,0.0,-1000000,1000000,1.0,1.0,P",
        "2,VB,B,,V,1.0,0.0,0.0,-1000000,1000000,1.0,1.0,P",
        "3,VC,C,,V,1.0,0.0,0.0,-1000000,1000000,1.0,1.0,P",
        f"{line_frequency:g}",
        "0",
        f"0,{n}",
        "01/01/2026,00:00:00.000000",
        "01/01/2026,00:00:00.000000",
        "ASCII",
        "1.0",
    ]
    cfg_path.write_text(_CRLF.join(cfg_lines) + _CRLF)

    t0 = float(wave.times[0])
    dat_lines = []
    for i in range(n):
        ts_us = round((wave.times[i] - t0) * 1_000_000.0)
        dat_lines.append(
            f"{i + 1},{ts_us},{wave.va[i]:.6g},{wave.vb[i]:.6g},{wave.vc[i]:.6g}"
        )
    dat_path.write_text(_CRLF.join(dat_lines) + _CRLF + "\x1a")
