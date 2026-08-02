#!/usr/bin/env python3
"""Lab 5 -- the same fault event at three telemetry rates, stacked concurrently
(KISS: one picture shows why telemetry rate decides what you can see).

Renders run_dpsim.py's real `dpsim_transient_log.json` into
`sample_telemetry_rates.png`, three panels sharing one time axis with the
fault window shaded across all of them. Every view is GENERATED from the same
waveform phase state-machine (`phase_model.py`, PSCADOSSE -- see its docstring
for what that means):

1. Raw 5 kHz recording (va/vb/vc) -- the state machine itself.
2. C37.118-style synchrophasor (PDU output) at 100 Hz -- the SAME three phases
   estimated by the identical one-cycle DFT (|Va|,|Vb|,|Vc|) plus the
   positive-sequence |V1| (dashed): phase A collapses, B/C swell, |V1| dips.
3. SCADA/EMS telemetry at a 4 s update -- phase-A RMS per interval. With this
   ~0.55 s log the entire event lands inside a single 4 s interval, so SCADA
   sees one point: the transient is invisible at this rate. That is the point
   of the view (fast transients hidden from slow telemetry).

Everything is computed from the real recording via `phase_model`; nothing
fabricated.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TypedDict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np

from phase_model import (  # noqa: E402
    PHASOR_RATE_HZ,
    SCADA_UPDATE_S,
    ThreePhaseWaveform,
    phasor_frames,
    positive_sequence,
    scada_rms,
)

LAB_DIR = Path(__file__).resolve().parent
TRANSIENT_LOG_JSON = LAB_DIR / "dpsim_transient_log.json"
OUTPUT_PNG = LAB_DIR / "sample_telemetry_rates.png"

REQUIRED_LOG_KEYS: tuple[str, ...] = (
    "times", "va", "vb", "vc", "trigger_time_s", "clear_time_s", "target",
)

# Color roles match the rest of the lab: blue = phase A/main, red = fault,
# muted gray = axis ink. Phase B/C are green/amber (same as animate_transient).
COLOR_PHASE_A = "#2a78d6"
COLOR_PHASE_B = "#4e9a63"
COLOR_PHASE_C = "#c07a2b"
COLOR_FAULT = "#e34948"
COLOR_INK = "#898781"


class TransientLog(TypedDict):
    """The JSON shape written by run_dpsim.py -- same keys, same semantics."""

    times: list[float]
    va: list[float]
    vb: list[float]
    vc: list[float]
    trigger_time_s: float
    clear_time_s: float
    target: str


def _load_log() -> TransientLog:
    """Read and structurally validate dpsim_transient_log.json."""
    if not TRANSIENT_LOG_JSON.exists():
        print(
            f"[missing] {TRANSIENT_LOG_JSON} not found. Produce it via the Lab 5 "
            "walkthrough (see labs/05-spartan-chaosnet-transient-stream/README.md).",
            file=sys.stderr,
        )
        sys.exit(1)
    log = json.loads(TRANSIENT_LOG_JSON.read_text())
    missing = [key for key in REQUIRED_LOG_KEYS if key not in log]
    if missing:
        print(f"[invalid] {TRANSIENT_LOG_JSON} missing keys: {missing}", file=sys.stderr)
        sys.exit(1)
    return log


def render(log: TransientLog, path: Path) -> None:
    """Stack the raw / 100 Hz phasor / 4 s SCADA views (shared time axis)."""
    wave = ThreePhaseWaveform.from_log(log)
    t = wave.times
    trigger_s = float(log["trigger_time_s"])
    clear_s = float(log["clear_time_s"])
    final_s = wave.duration_s

    ft, ph_a, ph_b, ph_c = phasor_frames(wave)
    v1 = np.abs(positive_sequence(ph_a, ph_b, ph_c))
    scada = scada_rms(wave)

    fig, (ax_raw, ax_phase, ax_scada) = plt.subplots(
        3, 1, figsize=(11.0, 10.0), dpi=130, sharex=True
    )

    # --- Panel 1: raw 5 kHz (the state machine itself) ----------------------
    ax_raw.plot(t, wave.va / 1000.0, color=COLOR_PHASE_A, lw=0.8, label="va")
    ax_raw.plot(t, wave.vb / 1000.0, color=COLOR_PHASE_B, lw=0.8, label="vb")
    ax_raw.plot(t, wave.vc / 1000.0, color=COLOR_PHASE_C, lw=0.8, label="vc")
    ax_raw.set_ylabel("raw 5 kHz (kV)")
    ax_raw.set_title(
        f"Lab 5 -- same {log['target']} fault at three telemetry rates"
    )
    ax_raw.legend(loc="upper right", fontsize=8)

    # --- Panel 2: C37.118 synchrophasor at 100 Hz, all three phases ---------
    ax_phase.plot(ft, np.abs(ph_a) / 1000.0, color=COLOR_PHASE_A, lw=1.2, marker=".", ms=3, label="|Va|")
    ax_phase.plot(ft, np.abs(ph_b) / 1000.0, color=COLOR_PHASE_B, lw=1.2, marker=".", ms=3, label="|Vb|")
    ax_phase.plot(ft, np.abs(ph_c) / 1000.0, color=COLOR_PHASE_C, lw=1.2, marker=".", ms=3, label="|Vc|")
    ax_phase.plot(ft, v1 / 1000.0, color=COLOR_INK, lw=1.6, ls="--", label="|V1| pos-seq")
    ax_phase.set_ylabel("phasor magnitude (kV)")
    ax_phase.legend(loc="lower left", fontsize=8)
    ax_phase.set_title(
        f"C37.118 PDU output @ {PHASOR_RATE_HZ} Hz -- three phases + "
        f"positive sequence (generated from phase_model)"
    )

    # --- Panel 3: SCADA/EMS at 4 s ------------------------------------------
    for start, stop, rms in scada:
        ax_scada.step([start, stop], [rms / 1000.0] * 2,
                      where="post", color=COLOR_FAULT, lw=2.0)
        ax_scada.plot((start + stop) / 2.0, rms / 1000.0,
                      color=COLOR_FAULT, marker="o", ms=5)
    ax_scada.set_ylabel(f"SCADA RMS {SCADA_UPDATE_S:.0f} s (kV)")
    ax_scada.set_xlabel("simulated time (s)")
    ax_scada.set_title(
        f"SCADA/EMS @ {SCADA_UPDATE_S:.0f} s update -- one interval covers "
        f"the whole {final_s:.2f} s event (invisible at this rate)"
    )

    # Fault window shaded concurrently on all three panels.
    for ax in (ax_raw, ax_phase, ax_scada):
        ax.axvspan(trigger_s, clear_s, color=COLOR_FAULT, alpha=0.12)
    ax_scada.set_xlim(0.0, final_s)

    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main() -> None:
    """Render sample_telemetry_rates.png and print the per-rate summary."""
    log = _load_log()
    render(log, OUTPUT_PNG)
    wave = ThreePhaseWaveform.from_log(log)
    ft, _, _, _ = phasor_frames(wave)
    print(f"[rates] wrote {OUTPUT_PNG}")
    print(f"  raw 5 kHz:        {len(wave.times)} samples over {wave.duration_s:.2f} s")
    print(f"  C37.118 @100 Hz:  {len(ft)} phasor frames x 3 phases "
          f"(+ pos-seq |V1|), generated from phase_model")
    print(f"  SCADA @{SCADA_UPDATE_S:.0f} s:   {len(scada_rms(wave))} "
          f"update interval(s) -- the whole event fits inside one")


if __name__ == "__main__":
    main()
