"""`labs/_shared/scenario_engine` -- the composable Generator/Detector
platform, docs/prd/0001-composable-generator-detector-platform.md.

Generalizes Lab 5's (`labs/05-spartan-chaosnet-transient-stream/`) single
fixed-time fault into a causally-linked event system: a `Generator`
injects a discrete event into a running DPsim solve (time- or
condition-triggered), a `Detector` consumes the resulting telemetry stream
and emits scored findings, and `score_run()` checks both against a
committed ground-truth fixture in two independent sections (generator
realism, detector performance).

Modules:
    generators -- `Generator` protocol + 5 concrete generators.
    detectors -- `Detector` protocol + 5 concrete detectors.
    scenario -- schedule schema extension + `run_scenario()` driver.
    scoring -- `score_run()` + report printing.
    demo_scenario -- this round's own synthetic proof scenario (PRD-0001's
        acceptance bar: at least one condition-triggered generator and one
        detector, demonstrated end-to-end, before 0002/0003 attempt the
        real historical cases).

Cross-lab dependency note (deliberate, documented deviation from
`labs/_shared/gridfit.py`'s own "labs import _shared, never the reverse"
convention): `detectors.py` and `scenario.py` import Lab 5's
`phase_model.py` directly, because PRD-0001 requires detectors to be thin
transforms of that module's views rather than a reimplementation, and
because -- per PRD-0001's own "Where this lives" section -- this package
conceptually lives alongside Lab 5's EMT/DPsim plumbing (imported by Lab
5's own chaos-net and by the future 0002/0003 scenario modules), not a
Labs-1-3-style generic utility like `gridfit.py`.
"""
from .detectors import (
    AngleSeparationDetector,
    CascadingFailureClassifier,
    Detector,
    Finding,
    OscillationDetector,
    RoCoFDetector,
    VoltageCascadeDetector,
)
from .generators import (
    CountTriggerCondition,
    Generator,
    GeneratorEvent,
    IslandingProtectionGenerator,
    MeasurementState,
    NetworkFaultGenerator,
    OperatorActionGenerator,
    PlantBehaviourGenerator,
    ProtectionTripGenerator,
    SustainTriggerCondition,
    TripAction,
    TriggerCondition,
)
from .scenario import (
    ScenarioRunResult,
    eval_stride_steps,
    is_condition_triggered,
    load_scenario_schedule,
    run_scenario,
    step_generators,
)
from .scoring import ScoreEntry, ScoreReport, print_score_report, score_run

__all__ = [
    "AngleSeparationDetector",
    "CascadingFailureClassifier",
    "CountTriggerCondition",
    "Detector",
    "Finding",
    "Generator",
    "GeneratorEvent",
    "IslandingProtectionGenerator",
    "MeasurementState",
    "NetworkFaultGenerator",
    "OperatorActionGenerator",
    "OscillationDetector",
    "PlantBehaviourGenerator",
    "ProtectionTripGenerator",
    "RoCoFDetector",
    "ScenarioRunResult",
    "ScoreEntry",
    "ScoreReport",
    "SustainTriggerCondition",
    "TriggerCondition",
    "TripAction",
    "VoltageCascadeDetector",
    "eval_stride_steps",
    "is_condition_triggered",
    "load_scenario_schedule",
    "print_score_report",
    "run_scenario",
    "score_run",
    "step_generators",
]
