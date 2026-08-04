"""Composable event `Generator`s for the scenario engine
(docs/prd/0001-composable-generator-detector-platform.md).

A `Generator` is anything that can inject a discrete event into a running
DPsim solve, conditioned on simulated time and/or the current measurement
state -- PRD-0001's own framing, typed here for real. Five concrete kinds
cover every mechanism PRD-0001/0002/0003 name:

- `NetworkFaultGenerator` -- Lab 5's original time-triggered fault,
  generalized from "one fault" to "an ordered sequence."
- `ProtectionTripGenerator` -- the central new primitive: a named local
  measurement crossing a threshold trips a named asset. Its
  `trigger_condition` is a tagged union (`SustainTriggerCondition` |
  `CountTriggerCondition`) rather than a single flat shape, backporting
  the counting-window variant `docs/prd/0002-sa-2016-black-system-cascade-scenario.md`
  ("Composable capability mapping") names as a gap in PRD-0001's own
  sketch -- implemented now, per that PRD's explicit instruction, not
  deferred.
- `PlantBehaviourGenerator` -- a continuous setpoint change (not a binary
  trip).
- `OperatorActionGenerator` -- a scripted, latency-bound stand-in for a
  human control-room decision.
- `IslandingProtectionGenerator` -- a `ProtectionTripGenerator` specialised
  for inter-region/tie trips, kept distinct only so scoring can name the
  "point of no return" event separately (PRD-0001's own stated reasoning).

No `dpsimpy` import at module scope: these classes operate on whatever
dpsimpy component object they are handed (a `dpsimpy.emt.ph3.Switch`'s own
`.open()`/`.close()` methods, confirmed present in this sandbox's dpsim
1.2.1) or a plain Python callback, so this module has no direct DPsim
dependency of its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, Protocol, TypedDict

# --- Data contracts (PRD-0001 "Data contracts" section, typed for real) ----


class GeneratorEvent(TypedDict):
    """One committed generator firing -- PRD-0001's own sketch, typed.

    Attributes:
        generator_id: the firing Generator's own `id`.
        time_s: the real simulated time this firing happened (not the
            schedule's requested time -- for a condition-triggered
            generator these can differ; for a time-triggered one they
            should match within one measurement-cadence tick).
        kind: one of "fault" | "trip" | "setpoint_change" |
            "operator_action" | "island".
        target: the asset/substation this firing acted on.
        detail: kind-specific extra fields (e.g. the trigger_condition that
            fired, for a "trip").
    """

    generator_id: str
    time_s: float
    kind: str
    target: str
    detail: dict


class MeasurementState(TypedDict):
    """Snapshot of named measurements handed to `Generator.ready()` at each
    evaluated cadence tick (see `scenario.py`'s `eval_stride_steps()` for
    why this is not every raw EMT sample).

    Attributes:
        t_s: current simulated time (s).
        values: named scalar measurement -> current value, e.g.
            `{"SUB-1_voltage_v": 8123.4}` -- the vocabulary a
            `trigger_condition`'s `measurement` field indexes into. See
            `scenario.py`'s module docstring for the exact key convention
            this platform round populates.
        history: same names -> ordered `(t_s, value)` pairs from scenario
            start to now, oldest first -- needed to check a
            sustained-duration or rolling-window-count condition, since a
            single instantaneous value can't express either.
    """

    t_s: float
    values: dict[str, float]
    history: dict[str, list[tuple[float, float]]]


Comparator = Literal[">", ">=", "<", "<="]


class SustainTriggerCondition(TypedDict):
    """Threshold-sustained-for-a-duration trigger -- PRD-0001's original
    `ProtectionTripGenerator` sketch (`{measurement, comparator, limit,
    sustain_s}`), typed as one arm of the tagged union. True once
    `measurement` has satisfied `comparator limit` continuously for at
    least `sustain_s` of the generator's own recorded history.
    """

    kind: Literal["sustain"]
    measurement: str
    comparator: Comparator
    limit: float
    sustain_s: float


class CountTriggerCondition(TypedDict):
    """Counting-window trigger -- the variant
    docs/prd/0002-sa-2016-black-system-cascade-scenario.md's "Composable
    capability mapping" names as missing from PRD-0001's original sketch
    and instructs be backported here. True once at least `count`
    qualifying dips (`measurement < dip_threshold` at a sampled instant)
    have occurred within the trailing `window_s` -- models SA 2016's
    wind-farm fault-ride-through disconnection rule (N voltage dips within
    a rolling window).
    """

    kind: Literal["count"]
    measurement: str
    dip_threshold: float
    count: int
    window_s: float


TriggerCondition = SustainTriggerCondition | CountTriggerCondition


class TripAction(TypedDict):
    """What a `ProtectionTripGenerator` does once its `trigger_condition`
    is met.

    Attributes:
        asset: the name of the asset being acted on (for the log; the
            actual dpsimpy component is passed separately as the
            generator's own `switch`).
        effect: "open" or "close" the switch. Note: this platform round's
            concrete demo (`demo_scenario.py`) reuses chaosnet.py's
            to-ground fault-switch primitive as the trip actuator (no
            independent line/asset breaker component exists in chaosnet.py
            yet -- a named gap for 0002/0003's own real scenarios, not
            fixed here), so "close" is the action that makes the trip
            *happen* there, not "open" -- the effect string is taken
            literally against whichever component `switch` actually is.
    """

    asset: str
    effect: Literal["open", "close"]


def _comparator_holds(comparator: Comparator, value: float, limit: float) -> bool:
    """Evaluate one of the four supported comparators.

    Args:
        comparator: one of ">", ">=", "<", "<=".
        value: the measured value.
        limit: the threshold to compare against.

    Returns:
        True if `value comparator limit` holds.

    Raises:
        ValueError: for an unrecognized comparator string.
    """
    if comparator == ">":
        return value > limit
    if comparator == ">=":
        return value >= limit
    if comparator == "<":
        return value < limit
    if comparator == "<=":
        return value <= limit
    raise ValueError(f"unknown comparator {comparator!r}")


class Generator(Protocol):
    """PRD-0001's Generator interface: anything that can inject a discrete
    event into a running solve, conditioned on simulated time and/or the
    current measurement state."""

    id: str

    def ready(self, t_s: float, state: MeasurementState) -> bool:
        """True the first simulated instant this generator's condition is
        met (for a time-triggered generator: once `t_s` has reached the
        scheduled time)."""
        ...

    def fire(self, sim: object, t_s: float) -> GeneratorEvent:
        """Perform this generator's action against the live solve (`sim`,
        a dpsimpy.Simulation-shaped object -- typed as `object` since
        dpsimpy ships no type stubs, matching chaosnet.py's own
        `system: object` convention) and return the committed
        GeneratorEvent record."""
        ...


# --- Concrete generators ----------------------------------------------------


@dataclass
class NetworkFaultGenerator:
    """Time-triggered network fault -- Lab 5's original mechanism,
    generalized from "one fault" to "an ordered sequence," per PRD-0001
    Goal 1's `NetworkFaultGenerator` capability.

    `ready()` is time-only (no measurement dependency); `fire()` performs
    the open/close transition directly on `switch` (a
    `dpsimpy.emt.ph3.Switch`'s own `.open()`/`.close()` methods, confirmed
    present in this sandbox's dpsim 1.2.1), so this class also works
    inside `scenario.py`'s per-step polling loop (used by scenarios that
    mix time- and condition-triggered generators, e.g. `demo_scenario.py`).
    Lab 5's own `run_dpsim.py`, by contrast, keeps pre-registering its
    time-triggered events directly as `dpsimpy.event.SwitchEvent3Ph` pairs
    (see that script's own docstring) for its zero-behaviour-change
    regression path -- this class is not on that script's hot path for
    today's schedule.

    Attributes:
        id: unique generator id.
        target: substation tap name (a `chaosnet.ChaosTopology` tap_names
            entry) this fault is applied at.
        fault_type: label only (e.g. "line-to-ground") -- carried through
            to the `GeneratorEvent` detail, not itself simulated
            differently (matches Lab 5's own current behaviour: one fault
            mechanism, labelled).
        trigger_time_s: simulated time to close (fault in) the switch.
        clearing_duration_s: seconds after `trigger_time_s` to re-open
            (clear) the switch.
        switch: the `dpsimpy.emt.ph3.Switch` to actuate.
    """

    id: str
    target: str
    fault_type: str
    trigger_time_s: float
    clearing_duration_s: float
    switch: object
    _closed: bool = field(default=False, repr=False)
    _cleared: bool = field(default=False, repr=False)

    def ready(self, t_s: float, state: MeasurementState) -> bool:
        if not self._closed:
            return t_s >= self.trigger_time_s
        if not self._cleared:
            return t_s >= self.trigger_time_s + self.clearing_duration_s
        return False

    def fire(self, sim: object, t_s: float) -> GeneratorEvent:
        if not self._closed:
            self.switch.close()
            self._closed = True
            return {
                "generator_id": self.id,
                "time_s": t_s,
                "kind": "fault",
                "target": self.target,
                "detail": {"fault_type": self.fault_type, "action": "close"},
            }
        self.switch.open()
        self._cleared = True
        return {
            "generator_id": self.id,
            "time_s": t_s,
            "kind": "fault",
            "target": self.target,
            "detail": {"fault_type": self.fault_type, "action": "open"},
        }


@dataclass
class ProtectionTripGenerator:
    """Named local-measurement protection trip -- PRD-0001's central new
    primitive. `trigger_condition` is a tagged union
    (`SustainTriggerCondition` | `CountTriggerCondition`) so `ready()`
    dispatches on the `kind` discriminant instead of assuming one flat
    shape -- the fix for PRD-0002's own named gap in PRD-0001's original
    sketch.

    Attributes:
        id: unique generator id.
        target: asset name this trip acts on (a chaosnet tap name,
            matching `action["asset"]` and the switch actually wired to
            it).
        action: what happens once `trigger_condition` fires.
        trigger_condition: the tagged-union condition.
        switch: the `dpsimpy.emt.ph3.Switch` this trip actuates.
    """

    id: str
    target: str
    action: TripAction
    trigger_condition: TriggerCondition
    switch: object
    _fired: bool = field(default=False, repr=False)

    def ready(self, t_s: float, state: MeasurementState) -> bool:
        if self._fired:
            return False
        cond = self.trigger_condition
        if cond["kind"] == "sustain":
            return self._sustain_ready(t_s, state, cond)
        if cond["kind"] == "count":
            return self._count_ready(t_s, state, cond)
        raise ValueError(f"unknown trigger_condition kind {cond['kind']!r}")

    def _sustain_ready(
        self, t_s: float, state: MeasurementState, cond: SustainTriggerCondition
    ) -> bool:
        """True once every recorded sample within the trailing
        `sustain_s` window satisfies `comparator limit`, AND that trailing
        window is actually full (enough history has accumulated) -- a
        single sample that happens to qualify is not "sustained."."""
        history = state["history"].get(cond["measurement"], [])
        if not history:
            return False
        window_start = t_s - cond["sustain_s"]
        recent = [(t, v) for t, v in history if t >= window_start]
        if not recent:
            return False
        if recent[0][0] > window_start + 1e-9 and history[0][0] > window_start + 1e-9:
            # Not enough history has accumulated yet to span a full
            # sustain_s window (distinguished from "the window is full but
            # every sample in it happens to start exactly at window_start").
            return False
        return all(
            _comparator_holds(cond["comparator"], v, cond["limit"]) for _, v in recent
        )

    def _count_ready(
        self, t_s: float, state: MeasurementState, cond: CountTriggerCondition
    ) -> bool:
        """True once at least `count` recorded samples within the
        trailing `window_s` are below `dip_threshold`."""
        history = state["history"].get(cond["measurement"], [])
        window_start = t_s - cond["window_s"]
        dips = sum(
            1 for t, v in history if t >= window_start and v < cond["dip_threshold"]
        )
        return dips >= cond["count"]

    def fire(self, sim: object, t_s: float) -> GeneratorEvent:
        if self.action["effect"] == "open":
            self.switch.open()
        else:
            self.switch.close()
        self._fired = True
        return {
            "generator_id": self.id,
            "time_s": t_s,
            "kind": "trip",
            "target": self.target,
            "detail": {
                "action": dict(self.action),
                "trigger_condition": dict(self.trigger_condition),
            },
        }


@dataclass
class PlantBehaviourGenerator:
    """Continuous-setpoint plant response to a disturbance -- distinguished
    from `ProtectionTripGenerator` in that it changes a continuous control
    setpoint (e.g. reactive power following active power at a fixed power
    factor), not a binary connect/disconnect state (PRD-0001
    "Composable capability: Generators").

    Modelled generically via an `apply_setpoint` callback rather than a
    hard-coded dpsimpy component type: chaosnet.py's current
    RXLoad/NetworkInjection components are the only live components this
    platform round's demo touches, and neither exposes a natural "PV/wind
    inverter Q follows P" control today. The callback is the seam a future
    scenario (e.g. 0003's Iberian fixed-power-factor RES factor) wires to a
    real component attribute directly -- named here per AGENTS.md's
    sandbox-stand-in convention, not hidden.

    Attributes:
        id: unique generator id.
        target: asset name this setpoint change applies to.
        ready_at_s: simulated time this generator becomes ready to fire (a
            plant behaviour reacting to "the disturbance has started",
            modelled here as a fixed post-trigger time -- a real scenario
            would condition this on the same disturbance measurement a
            ProtectionTripGenerator watches).
        power_factor: fixed reactive/active power ratio applied at fire
            time (Q = P * power_factor, i.e. tan(phi) not cos(phi)).
        active_power_w: the plant's active power output (W) at fire time.
        apply_setpoint: callback invoked as `apply_setpoint(q_var)` to push
            the computed reactive-power setpoint into the live solve.
    """

    id: str
    target: str
    ready_at_s: float
    power_factor: float
    active_power_w: float
    apply_setpoint: Callable[[float], None]
    _fired: bool = field(default=False, repr=False)

    def ready(self, t_s: float, state: MeasurementState) -> bool:
        return not self._fired and t_s >= self.ready_at_s

    def fire(self, sim: object, t_s: float) -> GeneratorEvent:
        q_var = self.active_power_w * self.power_factor
        self.apply_setpoint(q_var)
        self._fired = True
        return {
            "generator_id": self.id,
            "time_s": t_s,
            "kind": "setpoint_change",
            "target": self.target,
            "detail": {"q_var": q_var, "power_factor": self.power_factor},
        }


@dataclass
class OperatorActionGenerator:
    """Scripted, latency-bound operator action -- stands in for a human
    control-room decision (PRD-0001 "Composable capability: Generators").
    `ready_at_s` is the moment the precursor condition that *should* prompt
    the action occurs; `latency_s` models the real time an operator takes
    to execute it (Iberian's own report: "less than 5 minutes" -- PRD-0001's
    own text), so `fire()` only actually happens at
    `ready_at_s + latency_s` -- reproducible as either a successful-but-late
    action or (if a later generator's own deadline passes first) a
    documented near-miss/failure mode, per PRD-0001's explicit intent, not
    an assumption of instantaneous perfect operator response.

    PRD-0001 flags this as "the natural place to let an agent stand in for
    the operator decision" instead of a fixed script -- that agent-driven
    variant is explicitly out of scope for 0001/0002/0003's core
    Definition of Done; this class is the deterministic scripted version
    only.

    Attributes:
        id: unique generator id.
        target: asset/control this action changes.
        action_label: human-readable description (e.g. "switch shunt
            reactor", "raise interconnector flow limit").
        ready_at_s: simulated time the precursor condition occurs.
        latency_s: simulated delay before the action executes.
        apply_action: callback invoked with no arguments at fire time to
            perform the action against the live solve.
    """

    id: str
    target: str
    action_label: str
    ready_at_s: float
    latency_s: float
    apply_action: Callable[[], None]
    _fired: bool = field(default=False, repr=False)

    def ready(self, t_s: float, state: MeasurementState) -> bool:
        return not self._fired and t_s >= self.ready_at_s + self.latency_s

    def fire(self, sim: object, t_s: float) -> GeneratorEvent:
        self.apply_action()
        self._fired = True
        return {
            "generator_id": self.id,
            "time_s": t_s,
            "kind": "operator_action",
            "target": self.target,
            "detail": {"action_label": self.action_label, "latency_s": self.latency_s},
        }


class IslandingProtectionGenerator(ProtectionTripGenerator):
    """Interconnector/tie trip once an angle-separation, loss-of-
    synchronism, or SPS/RAS-style condition is met -- architecturally
    identical to `ProtectionTripGenerator` (same `TriggerCondition` tagged
    union: an inter-region measurement is just another named measurement),
    kept as its own class only so scoring can name the "point of no
    return" event distinctly, per PRD-0001's own stated reasoning (Heywood's
    SPS in SA 2016; the Iberian DRS out-of-step protection / AC
    interconnector trips). Overrides only `fire()`'s emitted `kind`
    ("island" instead of "trip"); inherits `ready()` and `__init__`
    unchanged from `ProtectionTripGenerator`.
    """

    def fire(self, sim: object, t_s: float) -> GeneratorEvent:
        event = super().fire(sim, t_s)
        event["kind"] = "island"
        return event
