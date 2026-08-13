#!/usr/bin/env python3
"""Lab 5, PRD-0005 Phase 1 -- grid-forming transient stabilizer.

This is the "take corrective or assistive action when feasible" half of
SPARTAN's own stated design (docs/prd/0005-grid-forming-stabilizer-and-
renewable-models.md's Problem statement): Lab 5's other views only
classify/log/alert a fault transient; this module actively injects a
compensating voltage at the fault bus and measures whether it reduces the
transient for real.

**Honest scope note (PRD-0005's own instruction, followed literally): this
is the conventional VSM/PID fallback, not the Negative-Imaginary (NI)
systems-theoretic controller the PRD proposes as its first choice.** Fitting
DPsim's actual `ControlledVoltageSource` plant to NI's required sign/phase
conditions is a real, open feasibility question (see the PRD's Open
questions) that this phase did not attempt to resolve rigorously -- doing so
honestly would need deriving the plant's frequency-domain transfer function
from DPsim's discretized MNA formulation and checking the NI lemma's phase
conditions against it, disproportionate effort for what Phase 1 needs to
measure. What *is* kept from the PRD's framing: the controller's angle/
frequency state obeys the same second-order swing-equation structure
DPsim's own `SynchronGenerator{3,4,5,6a,6b}OrderVBR` models use (inertia +
damping opposing a measured power imbalance), and its voltage-magnitude
loop is a simple droop, decoupled from the swing loop -- structurally the
same "swing equation + exciter" shape a real synchronous generator model
has, driving `ControlledVoltageSource` instead of a literal rotating
machine (per the PRD's "What was checked this session" finding: DPsim has
the right math, just attached to the wrong device).

**Circuit placement**: the stabilizer is a shunt-connected voltage-behind-
impedance source -- like a real STATCOM/DVR -- coupled to the fault bus
itself (`chaosnet.py`'s `dsys["fault_buses"][target]`, the same bus
`fault_adjacent_line_name()`/`fault_adjacent_lines` already identify as the
docs/backlog/0006 tier-2 monitoring point) through a small series R+jX
filter impedance, not connected directly to the bus with zero impedance.
Placing sensor and actuator at the *same* bus is deliberate: it is the
"collocated sensor/actuator" shape NI theory itself is designed for (PRD
Goal 1), and it is also just the standard real-world STATCOM/DVR placement
-- support the bus that is actually sagging, not a stiff upstream bus. (The
fault-adjacent *line*'s other endpoint, for this lab's seed-42 topology, is
literally the ext-grid bus -- an ideal, infinitely stiff source -- so
placing the device there instead would be physically pointless; confirmed
directly against `sample_topology.json`: `fault_adjacent_line=line0_12`,
`ext_grid_bus=0`, `tap_buses=[0, 11, 12]`, i.e. SUB-3's fault-adjacent line
*is* the ext-grid injection line.)

**A real DPsim API finding worth recording**: `dpsimpy.SystemTopology` has
no supported way to add a brand-new `SimNode` to an already-built topology
-- `SystemTopology.add(node)` silently no-ops (the node never appears in
`system.nodes` afterward) and a `Simulation` built on top of that
half-registered node hangs forever in `sim.start()` rather than raising.
Confirmed directly in this sandbox with a minimal 3-node test circuit.
Every node must be present in the `SystemTopology(...)` constructor's node
list up front, so `add_stabilizer_to_system()` below rebuilds a *new*
`SystemTopology` from `chaosnet.to_dpsim_emt_system()`'s exposed
`components` list plus this module's own new node/coupling/source, rather
than mutating the existing one in place.

**Actuator/model honesty, per PRD-0005's Non-goals**: this controller has
finite control bandwidth (it only updates its droop/swing targets at
`phase_model.PHASOR_RATE_HZ`, the same PMU reporting rate Lab 5's own
detectors use -- a real digital controller's inherent update-rate limit,
not continuous/ideal), a finite coupling impedance (so it cannot force the
bus to an arbitrary voltage instantaneously), and a clipped voltage-droop
output (`ACTUATOR_HEADROOM_FRAC` -- a real converter's finite voltage
rating). None of that is tuned to hit a target mitigation percentage; the
parameters below are one-shot, literature-typical engineering choices
(cited in each constant's own comment), not swept/tuned against the real
run's outcome.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

import numpy as np

import chaosnet
import phase_model

LAB_DIR = Path(__file__).resolve().parent

SYSTEM_OMEGA_RAD_S: float = 2.0 * math.pi * chaosnet.SYSTEM_FREQUENCY_HZ

# Matches phase_model.SAMPLE_RATE_HZ / FUNDAMENTAL_HZ exactly (100 samples
# at 5 kHz = run_dpsim.TIME_STEP_S's 200us step) -- same one-cycle DFT
# window length Lab 5's own phasor detector uses, so the controller's
# measurement really is "the same real-time measurement" the PRD asks for,
# not a differently-sized approximation of it.
N_CYCLE: int = int(round(phase_model.SAMPLE_RATE_HZ / phase_model.FUNDAMENTAL_HZ))

# --- Device sizing (one-shot engineering choices, not tuned to a result) ---

# Assumed stabilizer device rating (MVA). Chosen to be comparable to a
# single local SimBench load's real p_mw magnitude (this lab's loads are
# real SimBench MV-rural records, typically sub-MW to a few MW) -- a
# plausible single-feeder-scale STATCOM/DVR, not a device sized to
# guarantee a particular mitigation outcome.
STABILIZER_RATING_MVA: float = 1.0

# Coupling filter: 10% reactance on the device's own base impedance is a
# commonly cited typical VSC coupling-filter value in grid-forming-inverter
# literature (e.g. IEEE/CIGRE grid-forming control guideline ranges of
# 5-15%); X/R = 10 is a typical filter-reactor quality factor. Neither
# swept nor adjusted after seeing a result.
COUPLING_X_PU: float = 0.10
COUPLING_XR_RATIO: float = 10.0

# Full_Serial_RLC needs a real C parameter even though this coupling branch
# is only meant to be R+jX; set enormous (1 F) so its 50 Hz reactance
# (~3.2 mOhm) is negligible against the R+X above (~ohms) -- a documented
# modelling shortcut to reuse Full_Serial_RLC's single 2-terminal component
# without adding a second intermediate node, not a claim that a real
# coupling filter has a 1 F capacitor.
_COUPLING_C_FARAD: float = 1.0

# --- Swing-equation (angle/frequency) loop parameters -----------------------

# Inertia constant H (s) and per-unit damping D -- both inside the ranges
# commonly cited for emulated/virtual inertia in grid-forming-inverter VSM
# literature (H ~ 2-10 s, D ~ 10-50 pu). One-shot choice, not tuned.
INERTIA_H_S: float = 2.0
DAMPING_D_PU: float = 20.0
# No real steady-state power export/import target for a pure support
# device (this stabilizer has no generation asset behind it -- Phase 3's
# renewable-source work is explicitly out of scope here).
P_REF_PU: float = 0.0

# --- Voltage-magnitude droop loop -------------------------------------------

# Droop gain (V of EMF boost per V of measured sag) -- a modest, one-shot
# value giving partial correction, not full cancellation (PRD non-goal:
# never claim elimination). Not tuned against the measured outcome below.
VOLTAGE_DROOP_KV: float = 2.0

# Converter voltage headroom, as a fraction of nominal peak -- the honest
# "actuator/converter rating limit" the PRD's Non-goals section names as
# one of the real reasons a stabilizer can't reach 100% mitigation.
ACTUATOR_HEADROOM_FRAC: float = 0.15


# --- Phase 2: cable-length propagation-delay compensation -------------------
#
# docs/prd/0005-grid-forming-stabilizer-and-renewable-models.md Goal 3 (its
# Phasing section's "Phase 2"): a deadtime/Smith-predictor-style compensation
# term added on top of the swing/droop control law above, gated by each
# GridFormingStabilizer instance's own `delay_compensation_enabled` field so
# Phase 1's exact no-compensation behavior stays reproducible (see that
# field's own docstring -- when False, the code path below is a structural
# no-op, not just an empirically-small effect).
#
# **Real propagation-delay figure, computed, not assumed.** The fault-
# adjacent line (`chaosnet._fault_adjacent_line()`'s own deterministic
# selection -- "line0_12" for seed 42, reused directly here rather than
# re-parsed from sample_topology.json, since this module already has the
# live `topology` object in hand; docs/backlog/0006's R-X trajectory work
# reads the identical numbers from the committed JSON fixture instead,
# because it runs standalone after the fact) carries real per-km SimBench
# parameters: for seed 42, length_km=0.6, r_ohm_per_km=0.443,
# x_ohm_per_km=0.132, c_nf_per_km~=190. Those per-km figures are textbook
# *underground-cable* signatures, not overhead-line ones -- x_ohm_per_km
# ~=0.132 is roughly a third of a typical overhead line's ~0.3-0.4 ohm/km,
# and c_nf_per_km ~=190 is roughly twenty times a typical overhead line's
# ~10 nF/km (a cable's tightly-spaced concentric conductors give low series
# reactance; its solid dielectric gives high shunt capacitance -- both
# consistent with a cable, neither with a bare conductor in air). This
# matches `chaosnet.SIMBENCH_CODE`'s real source, "1-MV-rural--0-sw": German
# MV distribution is predominantly underground cable even in "rural"
# SimBench classifications, unlike the US overhead-line convention the name
# might otherwise suggest.
#
# **Propagation-velocity assumption, stated honestly.** v = c / sqrt(er) is
# the standard telegrapher's-equation TEM-mode propagation velocity for a
# cable whose insulation has relative permittivity er. XLPE (cross-linked
# polyethylene, the standard MV cable insulation) is commonly cited at
# er ~= 2.3 by cable manufacturers and consistent with IEC 60502 -- giving
# v ~= 299792.458 / sqrt(2.3) ~= 1.977e5 km/s. This is deliberately NOT the
# ~2.75e5-3.0e5 km/s figure commonly cited for overhead lines (a bare
# conductor in air, er~1) -- that would be the wrong physical regime for
# this topology's real per-km parameters, per the cable-signature finding
# above.
CABLE_RELATIVE_PERMITTIVITY: float = 2.3
SPEED_OF_LIGHT_KM_S: float = 299_792.458
CABLE_PROPAGATION_VELOCITY_KM_S: float = (
    SPEED_OF_LIGHT_KM_S / math.sqrt(CABLE_RELATIVE_PERMITTIVITY)
)


def propagation_delay_s(topology: "chaosnet.ChaosTopology", fault_bus: int) -> float:
    """Real one-way propagation delay (s) along the fault-adjacent line
    (`chaosnet._fault_adjacent_line()`'s own selection, reused directly --
    the same line docs/backlog/0006's R-X trajectory work already reports
    the real impedance of), at `CABLE_PROPAGATION_VELOCITY_KM_S`.

    **Honesty note on what this delay physically represents here.** Phase
    1's stabilizer is deliberately coupled at the *same* bus as the fault
    switch (this module's own docstring, "Circuit placement" section --
    collocated sensor/actuator, the shape NI theory itself targets and also
    the standard real-world STATCOM/DVR placement). In that literal
    circuit, the physical separation between the fault point and the
    stabilizer's own coupling point is zero, not this line's length. This
    delay is used here as PRD-0005 Phase 2's own named prototype-scale
    deadtime parameter -- "prototype it small and measure whether it
    actually improves mitigation" -- i.e. the real, computed propagation-
    delay figure this line's own real length/impedance would produce,
    applied as the Smith-predictor's assumed measurement-to-actuation
    deadtime, not a claim that this exact shunt-collocated circuit has a
    physical disturbance-to-controller travel distance of `length_km`. A
    genuinely remote/series-coupled stabilizer (this module's README
    already names that as a future variant, not attempted in Phase 1 or
    here) is where this delay would apply literally, without this caveat.

    Args:
        topology: output of `chaosnet.build_chaos_topology()` -- the same
            topology object the live DPsim solve is built from.
        fault_bus: local bus index of the fault target.

    Returns:
        `length_km / CABLE_PROPAGATION_VELOCITY_KM_S`, seconds.
    """
    line = chaosnet._fault_adjacent_line(topology, fault_bus)
    return line["length_km"] / CABLE_PROPAGATION_VELOCITY_KM_S


def coupling_impedance_ohm(vn_kv: float) -> tuple[float, float]:
    """Coupling filter R, X (ohm) for a `STABILIZER_RATING_MVA`-sized
    device at a bus with nominal line-line RMS voltage `vn_kv`.

    Z_base = vn_kv_v^2 / rating_va (ohm), the standard base-impedance
    formula; X = COUPLING_X_PU * Z_base, R = X / COUPLING_XR_RATIO.

    Args:
        vn_kv: nominal line-line RMS voltage of the coupling bus, kV.

    Returns:
        (r_ohm, x_ohm).
    """
    z_base = (vn_kv * 1000.0) ** 2 / (STABILIZER_RATING_MVA * 1e6)
    x_ohm = COUPLING_X_PU * z_base
    r_ohm = x_ohm / COUPLING_XR_RATIO
    return r_ohm, x_ohm


def _instant_abc(peak_v: float, theta_rad: float) -> np.ndarray:
    """Balanced 3-phase instantaneous voltage sample at angle `theta_rad`,
    peak `peak_v` -- the real-valued (3, 1) shape
    `dpsimpy.emt.ph3.ControlledVoltageSource`'s `V_ref` attribute expects
    (confirmed interactively in this sandbox: `V_ref` is a real, per-step
    instantaneous-value matrix, unlike `NetworkInjection`'s complex phasor
    `V_ref` -- different component, different convention).

    Args:
        peak_v: commanded EMF peak line-neutral magnitude (V).
        theta_rad: commanded phase-A angle (rad).

    Returns:
        (3, 1) float array [va, vb, vc].
    """
    return np.array(
        [
            [peak_v * math.cos(theta_rad)],
            [peak_v * math.cos(theta_rad - 2.0 * math.pi / 3.0)],
            [peak_v * math.cos(theta_rad + 2.0 * math.pi / 3.0)],
        ]
    )


class StabilizerHandles(TypedDict):
    """dpsimpy component handles `add_stabilizer_to_system()` builds, for
    `run_dpsim.py`'s per-step control loop to read/drive."""

    node: object  # dpsimpy.emt.SimNode -- the stabilizer's internal EMF node
    coupling: object  # dpsimpy.emt.ph3.Full_Serial_RLC
    source: object  # dpsimpy.emt.ph3.ControlledVoltageSource
    peak_v: float  # nominal peak line-neutral voltage at the coupling bus
    vn_kv: float
    r_ohm: float
    x_ohm: float


def add_stabilizer_to_system(
    dsys: "chaosnet.DpsimChaosSystem", topology: "chaosnet.ChaosTopology", target: str,
) -> StabilizerHandles:
    """Splice a grid-forming stabilizer into `dsys` at the fault bus for
    `target`, and replace `dsys["system"]` with the rebuilt
    `dpsimpy.SystemTopology` that includes it.

    Mutates `dsys["system"]` in place (see module docstring for why a
    fresh `SystemTopology` is required rather than an incremental add).

    Args:
        dsys: output of `chaosnet.to_dpsim_emt_system()` -- must carry the
            `components` key (PRD-0005 Phase 1 addition to `chaosnet.py`).
        topology: the `ChaosTopology` `dsys` was built from.
        target: a tap name already present in `dsys["fault_buses"]`.

    Returns:
        Handles to the new node/coupling/source components.
    """
    import dpsimpy  # local import: matches chaosnet.py's own convention

    fault_bus_idx = dsys["fault_buses"][target]
    bus_node = dsys["nodes"][fault_bus_idx]
    vn_kv = topology["buses"][fault_bus_idx]["vn_kv"]
    r_ohm, x_ohm = coupling_impedance_ohm(vn_kv)
    l_henry = x_ohm / SYSTEM_OMEGA_RAD_S
    peak_v = chaosnet.nominal_peak_line_neutral_v(vn_kv)

    stab_node = dpsimpy.emt.SimNode(f"stab_node_{target}", dpsimpy.PhaseType.ABC)
    coupling = dpsimpy.emt.ph3.Full_Serial_RLC(f"stab_coupling_{target}", dpsimpy.LogLevel.warn)
    coupling.set_parameters(
        np.eye(3) * r_ohm, np.eye(3) * l_henry, np.eye(3) * _COUPLING_C_FARAD
    )
    coupling.connect([bus_node, stab_node])

    source = dpsimpy.emt.ph3.ControlledVoltageSource(f"stab_source_{target}", dpsimpy.LogLevel.warn)
    source.set_parameters(_instant_abc(peak_v, 0.0))
    # Two-terminal connect, matching chaosnet.py's own Switch convention
    # ([bus, gnd]) -- confirmed necessary in this sandbox: a one-terminal
    # connect() call does not raise, but the resulting SystemTopology
    # segfaults inside its own constructor (a real, reproducible finding,
    # not a guess -- see the PRD's own "What was checked this session").
    source.connect([stab_node, dpsimpy.emt.SimNode.gnd])

    all_nodes = list(dsys["nodes"].values()) + [stab_node]
    all_components = list(dsys["components"]) + [coupling, source]
    dsys["system"] = dpsimpy.SystemTopology(
        topology["system_frequency_hz"], all_nodes, all_components
    )

    return {
        "node": stab_node,
        "coupling": coupling,
        "source": source,
        "peak_v": peak_v,
        "vn_kv": vn_kv,
        "r_ohm": r_ohm,
        "x_ohm": x_ohm,
    }


@dataclass
class GridFormingStabilizer:
    """The real-time VSM/PID-style control law (see module docstring for
    why this is the honest fallback, not the NI-theoretic controller).

    `step()` is called once per EMT timestep from `run_dpsim.py`'s solve
    loop, with the fault bus's own instantaneous voltage (the same
    quantity `run_dpsim.py` already taps for `dpsim_transient_log.json`)
    and the stabilizer's own coupling-branch instantaneous current. It
    returns the next `V_ref` instantaneous-voltage matrix to write onto the
    `ControlledVoltageSource`.

    Internally: the angle/frequency state (`delta_rad`/`domega_pu`) obeys a
    discretized 2nd-order swing equation, driven by a real measured active
    power at the coupling branch, averaged over a one-cycle window (the
    same `N_CYCLE`-sample window `phase_model.phasor_frames()` uses,
    computed *causally* here -- backward-looking, not centered, since a
    real-time controller cannot see future samples; `phase_model`'s own
    `phasor_frames()` deliberately centers its window for offline accuracy,
    which is fine for post-run analysis but not for this live loop). The
    voltage-magnitude state (`e_boost_v`) is a simple droop against the
    same window's positive-sequence magnitude estimate. Both states update
    only at `phase_model.PHASOR_RATE_HZ` (a real PMU/controller's update
    rate); the angle is integrated every EMT step in between (zero-order
    hold on the swing-equation's driving inputs), which is standard
    discrete-control practice, not a shortcut.

    **Phase 2 addition (`delay_compensation_enabled`/`delay_s`):** an
    additive, opt-in deadtime/Smith-predictor term on the two control-tick
    measurements (`v1_mag`, `p_meas_pu`) feeding the swing/droop laws above
    -- see `step()`'s own control-tick block. When
    `delay_compensation_enabled` is False (the default, Phase 1's exact
    configuration), the measurements used are bit-identical to Phase 1's
    (`v1_mag = v1_mag_meas`, `p_meas_pu = p_meas_pu_meas`, no arithmetic
    difference at all) -- structurally, not just empirically, reproducible.
    See `propagation_delay_s()` for how `delay_s` is computed and what it
    honestly represents in this collocated circuit.
    """

    nominal_peak_v: float
    time_step_s: float
    rating_va: float = field(default=STABILIZER_RATING_MVA * 1e6)
    inertia_h_s: float = INERTIA_H_S
    damping_pu: float = DAMPING_D_PU
    p_ref_pu: float = P_REF_PU
    voltage_droop_kv: float = VOLTAGE_DROOP_KV
    actuator_headroom_frac: float = ACTUATOR_HEADROOM_FRAC
    # Phase 2 (PRD-0005 Goal 3): opt-in deadtime/Smith-predictor
    # compensation -- False/0.0 defaults reproduce Phase 1 exactly.
    delay_compensation_enabled: bool = False
    delay_s: float = 0.0

    delta_rad: float = field(default=0.0, init=False)
    domega_pu: float = field(default=0.0, init=False)
    e_boost_v: float = field(default=0.0, init=False)
    _step_count: int = field(default=0, init=False)
    _control_stride: int = field(init=False)
    _weights: np.ndarray = field(init=False, repr=False)
    _va_hist: deque = field(init=False, repr=False)
    _vb_hist: deque = field(init=False, repr=False)
    _vc_hist: deque = field(init=False, repr=False)
    _ia_hist: deque = field(init=False, repr=False)
    _ib_hist: deque = field(init=False, repr=False)
    _ic_hist: deque = field(init=False, repr=False)
    # Phase 2 predictor state: previous control-tick's raw (uncompensated)
    # measurements, needed for the finite-difference rate estimate below.
    _prev_v1_mag: float = field(default=0.0, init=False, repr=False)
    _prev_p_meas_pu: float = field(default=0.0, init=False, repr=False)
    _has_prev_measurement: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._control_stride = max(
            1, int(round(1.0 / phase_model.PHASOR_RATE_HZ / self.time_step_s))
        )
        k = np.arange(N_CYCLE)
        # Identical DFT weights to phase_model.phasor_frames()'s own
        # `weights` -- same estimator, causal (backward-looking) window.
        self._weights = np.exp(-2j * np.pi * k / N_CYCLE) * (2.0 / N_CYCLE)
        self._va_hist = deque(maxlen=N_CYCLE)
        self._vb_hist = deque(maxlen=N_CYCLE)
        self._vc_hist = deque(maxlen=N_CYCLE)
        self._ia_hist = deque(maxlen=N_CYCLE)
        self._ib_hist = deque(maxlen=N_CYCLE)
        self._ic_hist = deque(maxlen=N_CYCLE)
        self.actuator_headroom_v: float = self.actuator_headroom_frac * self.nominal_peak_v

    def _positive_sequence_mag(self) -> float:
        a = np.exp(2j * np.pi / 3)
        va = complex(np.sum(np.asarray(self._va_hist) * self._weights))
        vb = complex(np.sum(np.asarray(self._vb_hist) * self._weights))
        vc = complex(np.sum(np.asarray(self._vc_hist) * self._weights))
        v1 = (va + a * vb + a**2 * vc) / 3.0
        return abs(v1)

    def _active_power_w(self) -> float:
        va = np.asarray(self._va_hist)
        vb = np.asarray(self._vb_hist)
        vc = np.asarray(self._vc_hist)
        ia = np.asarray(self._ia_hist)
        ib = np.asarray(self._ib_hist)
        ic = np.asarray(self._ic_hist)
        instant_p = va * ia + vb * ib + vc * ic
        return float(np.mean(instant_p))

    def step(
        self, t_s: float, va: float, vb: float, vc: float, ia: float, ib: float, ic: float,
    ) -> np.ndarray:
        """Advance the controller by one EMT timestep and return the next
        `V_ref` instantaneous-voltage matrix.

        Args:
            t_s: current simulated time (s).
            va/vb/vc: fault bus instantaneous voltage (V), this step.
            ia/ib/ic: stabilizer coupling-branch instantaneous current (A),
                this step.

        Returns:
            (3, 1) float array for `ControlledVoltageSource.attr("V_ref").set(...)`.
        """
        self._va_hist.append(va)
        self._vb_hist.append(vb)
        self._vc_hist.append(vc)
        self._ia_hist.append(ia)
        self._ib_hist.append(ib)
        self._ic_hist.append(ic)
        self._step_count += 1

        if self._step_count % self._control_stride == 0 and len(self._va_hist) == N_CYCLE:
            v1_mag_meas = self._positive_sequence_mag()
            p_meas_pu_meas = self._active_power_w() / self.rating_va
            dt_control = self._control_stride * self.time_step_s

            if self.delay_compensation_enabled and self._has_prev_measurement:
                # Phase 2 deadtime/Smith-predictor term: a first-order
                # forward extrapolation of each raw measurement by the real
                # computed line propagation delay (delay_s), using the
                # measured rate of change between this control tick and the
                # last one -- the simplest honest predictor that "time-
                # aligns the controller's correction with when the
                # disturbance actually needs cancelling" (PRD-0005 Goal 3)
                # rather than reacting to the raw, already-lagged
                # measurement naively. See propagation_delay_s()'s own
                # honesty note on what delay_s represents in this
                # collocated circuit.
                v1_rate = (v1_mag_meas - self._prev_v1_mag) / dt_control
                p_rate = (p_meas_pu_meas - self._prev_p_meas_pu) / dt_control
                v1_mag = v1_mag_meas + self.delay_s * v1_rate
                p_meas_pu = p_meas_pu_meas + self.delay_s * p_rate
            else:
                # Phase 1's exact path -- no arithmetic difference at all,
                # not merely a numerically-small one, when compensation is
                # disabled (the default) or on the very first control tick
                # (no rate estimate yet available).
                v1_mag = v1_mag_meas
                p_meas_pu = p_meas_pu_meas

            self._prev_v1_mag = v1_mag_meas
            self._prev_p_meas_pu = p_meas_pu_meas
            self._has_prev_measurement = True

            domega_dot_pu = (
                self.p_ref_pu - p_meas_pu - self.damping_pu * self.domega_pu
            ) / (2.0 * self.inertia_h_s)
            self.domega_pu += domega_dot_pu * dt_control

            raw_boost = self.voltage_droop_kv * (self.nominal_peak_v - v1_mag)
            self.e_boost_v = float(
                np.clip(raw_boost, -self.actuator_headroom_v, self.actuator_headroom_v)
            )

        # Continuous integration every EMT step (zero-order hold on the
        # swing-equation inputs computed above between control ticks).
        self.delta_rad += self.domega_pu * SYSTEM_OMEGA_RAD_S * self.time_step_s
        theta = SYSTEM_OMEGA_RAD_S * t_s + self.delta_rad
        e_peak = self.nominal_peak_v + self.e_boost_v
        return _instant_abc(e_peak, theta)


# --- Post-run metrics (offline, non-causal -- reuses phase_model directly) --


def _fault_bus_waveform(log: dict) -> phase_model.ThreePhaseWaveform:
    return phase_model.ThreePhaseWaveform.from_log(log)


def peak_sag_percent(log: dict) -> float:
    """Peak |V1| sag depth (%) during the fault window, relative to the
    pre-fault |V1| level -- offline analysis via `phase_model.phasor_frames()`
    (the acausal, centered-window estimator; appropriate here since this
    runs after the solve, not inside its control loop).

    Args:
        log: a `dpsim_transient_log.json`-shaped dict (fault bus va/vb/vc,
            trigger_time_s, clear_time_s).

    Returns:
        100 * (1 - min(|V1|_in_fault) / mean(|V1|_pre_fault)).
    """
    wave = _fault_bus_waveform(log)
    ft, ph_a, ph_b, ph_c = phase_model.phasor_frames(wave)
    v1 = np.abs(phase_model.positive_sequence(ph_a, ph_b, ph_c))
    trigger_s, clear_s = float(log["trigger_time_s"]), float(log["clear_time_s"])
    pre = ft < trigger_s
    in_fault = (ft >= trigger_s) & (ft <= clear_s)
    pre_ref = float(np.mean(v1[pre]))
    fault_min = float(np.min(v1[in_fault]))
    return 100.0 * (1.0 - fault_min / pre_ref)


def recovery_time_s(log: dict, tolerance_frac: float = 0.02) -> float | None:
    """Time (s) from fault clearance until |V1(t)| first settles within
    `tolerance_frac` of its pre-fault level and stays there for the rest of
    the recording.

    Args:
        log: a `dpsim_transient_log.json`-shaped dict.
        tolerance_frac: fractional band around the pre-fault |V1| level
            counted as "recovered" (default 2%).

    Returns:
        Seconds after `clear_time_s`, or None if the recording never
        settles within tolerance before it ends (an honest "didn't
        recover in the window" result, not a fabricated number).
    """
    wave = _fault_bus_waveform(log)
    ft, ph_a, ph_b, ph_c = phase_model.phasor_frames(wave)
    v1 = np.abs(phase_model.positive_sequence(ph_a, ph_b, ph_c))
    trigger_s, clear_s = float(log["trigger_time_s"]), float(log["clear_time_s"])
    pre = ft < trigger_s
    pre_ref = float(np.mean(v1[pre]))
    post = ft >= clear_s
    post_ft = ft[post]
    within = np.abs(v1[post] - pre_ref) <= tolerance_frac * pre_ref
    # First index after which every remaining sample is within tolerance.
    for i in range(len(within)):
        if within[i:].all():
            return float(post_ft[i] - clear_s)
    return None


def peak_rocof_hz_s(log: dict) -> float:
    """Peak |RoCoF| (Hz/s) derived from the unwrapped phase angle of the
    fault bus's own positive-sequence phasor -- d(angle)/dt / (2*pi).

    Honesty note (this is what the PRD asks be checked before building new
    machinery, and what the result actually shows): this network has a
    single ideal, fixed-frequency `NetworkInjection` source and otherwise
    only passive RLC branches -- there is no rotating-mass/generator
    dynamics anywhere for a genuine system-frequency excursion to occur
    against. Any nonzero value this returns is therefore an *apparent*
    RoCoF from the DFT-estimated fundamental's phase jitter around the
    fault switching transient, not evidence of a real frequency-stability
    event -- reported as such, not oversold.

    Args:
        log: a `dpsim_transient_log.json`-shaped dict.

    Returns:
        Peak absolute RoCoF (Hz/s) over the whole recording.
    """
    wave = _fault_bus_waveform(log)
    ft, ph_a, ph_b, ph_c = phase_model.phasor_frames(wave)
    v1 = phase_model.positive_sequence(ph_a, ph_b, ph_c)
    angle = np.unwrap(np.angle(v1))
    dt = np.diff(ft)
    freq_hz = np.diff(angle) / (2.0 * np.pi * dt) + phase_model.FUNDAMENTAL_HZ
    rocof = np.diff(freq_hz) / dt[1:]
    if rocof.size == 0:
        return 0.0
    return float(np.max(np.abs(rocof)))


class ComparisonSummary(TypedDict):
    baseline: dict
    stabilized: dict
    peak_sag_reduction_pp: float  # percentage-point reduction, baseline - stabilized
    peak_sag_reduction_percent_of_baseline: float


BASELINE_LOG_JSON = LAB_DIR / "dpsim_transient_log.json"
STABILIZED_LOG_JSON = LAB_DIR / "dpsim_transient_log_stabilized.json"
COMPARISON_JSON = LAB_DIR / "stabilizer_comparison.json"


def run_comparison(
    schedule_path: Path | None = None, seed: int | None = None, countdown_seconds: int = 0,
    verbose: bool = True,
) -> ComparisonSummary:
    """Run `chaos_schedule.yaml`'s real fault twice against the identical
    topology -- once with the stabilizer off (the existing baseline path,
    writing `dpsim_transient_log.json` exactly as before), once with it
    on (writing `dpsim_transient_log_stabilized.json`) -- and compute the
    real before/after mitigation numbers via `phase_model`.

    Writes `stabilizer_comparison.json` (PRD-0005's own instruction: report
    numbers in a form a later phase, e.g. Phase 1.5's EMT->OPF headroom
    translation, can consume without re-running the simulation).

    Args:
        schedule_path: defaults to `run_dpsim.DEFAULT_SCHEDULE_FILE`.
        seed: defaults to `chaosnet.DEFAULT_SEED`.
        countdown_seconds: wall-clock countdown for each run (default 0,
            i.e. the fast/non-interactive path -- pass
            `run_dpsim.FAULT_COUNTDOWN_SECONDS` for the interactive demo).
        verbose: forwarded to `run_dpsim.run_step()`.

    Returns:
        The real, computed ComparisonSummary.
    """
    import run_dpsim  # local import: keeps chaosnet-only callers dpsim-free

    schedule_path = schedule_path or run_dpsim.DEFAULT_SCHEDULE_FILE
    seed = chaosnet.DEFAULT_SEED if seed is None else seed

    if verbose:
        print("[grid_forming] running baseline (stabilizer off)...")
    baseline_summary = run_dpsim.run_step(
        schedule_path, seed=seed, countdown_seconds=countdown_seconds, verbose=verbose,
        stabilizer=False, output_log_path=BASELINE_LOG_JSON,
    )
    if verbose:
        print("[grid_forming] running stabilized (stabilizer on)...")
    stabilized_summary = run_dpsim.run_step(
        schedule_path, seed=seed, countdown_seconds=countdown_seconds, verbose=verbose,
        stabilizer=True, output_log_path=STABILIZED_LOG_JSON,
    )

    baseline_log = json_load(BASELINE_LOG_JSON)
    stabilized_log = json_load(STABILIZED_LOG_JSON)

    baseline_sag = peak_sag_percent(baseline_log)
    stabilized_sag = peak_sag_percent(stabilized_log)
    baseline_recovery = recovery_time_s(baseline_log)
    stabilized_recovery = recovery_time_s(stabilized_log)
    baseline_rocof = peak_rocof_hz_s(baseline_log)
    stabilized_rocof = peak_rocof_hz_s(stabilized_log)

    reduction_pp = baseline_sag - stabilized_sag
    reduction_pct_of_baseline = (
        100.0 * reduction_pp / baseline_sag if baseline_sag > 0 else 0.0
    )

    summary: ComparisonSummary = {
        "baseline": {
            "run_summary": baseline_summary,
            "peak_sag_percent": round(baseline_sag, 3),
            "recovery_time_s": baseline_recovery,
            "peak_rocof_hz_s": round(baseline_rocof, 4),
        },
        "stabilized": {
            "run_summary": stabilized_summary,
            "peak_sag_percent": round(stabilized_sag, 3),
            "recovery_time_s": stabilized_recovery,
            "peak_rocof_hz_s": round(stabilized_rocof, 4),
            "stabilizer_params": {
                "rating_mva": STABILIZER_RATING_MVA,
                "coupling_x_pu": COUPLING_X_PU,
                "coupling_xr_ratio": COUPLING_XR_RATIO,
                "inertia_h_s": INERTIA_H_S,
                "damping_pu": DAMPING_D_PU,
                "voltage_droop_kv": VOLTAGE_DROOP_KV,
                "actuator_headroom_frac": ACTUATOR_HEADROOM_FRAC,
            },
        },
        "peak_sag_reduction_pp": round(reduction_pp, 3),
        "peak_sag_reduction_percent_of_baseline": round(reduction_pct_of_baseline, 2),
    }

    COMPARISON_JSON.write_text(_dumps(summary))
    if verbose:
        print(
            f"[grid_forming] peak sag: baseline {baseline_sag:.2f}% -> "
            f"stabilized {stabilized_sag:.2f}% "
            f"({reduction_pp:+.2f} pp, {reduction_pct_of_baseline:+.1f}% of baseline); "
            f"recovery: baseline={_fmt_recovery(baseline_recovery)} "
            f"stabilized={_fmt_recovery(stabilized_recovery)}; "
            f"peak RoCoF: baseline={baseline_rocof:.4f} Hz/s "
            f"stabilized={stabilized_rocof:.4f} Hz/s"
        )
        print(f"[grid_forming] wrote {COMPARISON_JSON.name}")
    return summary


def _fmt_recovery(v: float | None) -> str:
    return f"{v:.4f}s" if v is not None else "did not settle in window"


def json_load(path: Path) -> dict:
    import json

    return json.loads(path.read_text())


def _dumps(obj) -> str:
    import json

    return json.dumps(obj, indent=2)


def check_step() -> bool:
    """`--step check`: re-run the real comparison fast (0s countdowns) and
    assert the stabilized run's peak sag is measurably smaller than the
    baseline's -- a numeric-outcome check against real computed numbers,
    per PRD-0005's own discipline (no hardcoded expected percentage; the
    assertion is purely "stabilized < baseline", derived fresh every run).

    Returns:
        True if the stabilized run's peak sag is smaller than the
        baseline's; False otherwise (printed either way).
    """
    summary = run_comparison(countdown_seconds=0, verbose=False)
    baseline_sag = summary["baseline"]["peak_sag_percent"]
    stabilized_sag = summary["stabilized"]["peak_sag_percent"]
    ok = stabilized_sag < baseline_sag
    if ok:
        print(
            f"MATCH: stabilizer reduces peak sag "
            f"({baseline_sag:.2f}% -> {stabilized_sag:.2f}%, "
            f"{summary['peak_sag_reduction_pp']:+.2f} pp)"
        )
    else:
        print(
            f"FAIL: stabilizer did not reduce peak sag "
            f"(baseline={baseline_sag:.2f}% stabilized={stabilized_sag:.2f}%)"
        )
    return ok


def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", choices=["run", "check"], default="run")
    args = parser.parse_args()

    if args.step == "run":
        run_comparison(countdown_seconds=0, verbose=True)
    elif args.step == "check":
        ok = check_step()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
