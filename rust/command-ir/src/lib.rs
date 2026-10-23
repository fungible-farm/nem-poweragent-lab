//! PowerCoder's typed command IR, first step of PRD-0010 G1 (backlog 0015).
//!
//! Two commands, `SOLVE` and `SIMULATE`, both lowered to today's `run_study_trial` tool
//! (`powercoder/inference/studies.py`):
//!
//! - [`Solve`]: an AC power flow of the intact network or one N-1 outage, observing one element
//!   (`operation = "none"`, `scale = 1`, `element_id = 0`, as the trained procedure sends it);
//! - [`Simulate`]: one perturbation trial: scale all loads, one line's rating or one
//!   generator's dispatch, and observe the quantity that modification moves.
//!
//! [`study_trial_schema`] emits the tool's JSON Schema, and [`to_python_json`] writes it with
//! Python `json.dumps` separators. Their output must be byte-identical to the schema the
//! evaluation serves (`tests/served_run_study_trial.json`, written from `studies.tool_schema()`),
//! so an IR-generated schema can never skew training against serving (AGENTS.md FM-23).
//! A minimal textual DSL ([`parse`]) compiles to the IR.

use serde_json::{json, Map, Value};
use std::fmt;

/// IR version; bump on any change to command shape or lowering.
pub const IR_VERSION: &str = "0.1.0";
/// The study tool's scale interval (`studies.SCALE_MIN`/`SCALE_MAX`).
pub const SCALE_MIN: f64 = 0.9;
pub const SCALE_MAX: f64 = 1.1;
/// The study tool's solver-iteration cap (`studies.MAX_ITERATIONS`).
pub const MAX_ITERATIONS: u32 = 100;
/// Iterations the trained procedure asks for (`trajectories.TRIAL_MAX_ITER`).
pub const DEFAULT_MAX_ITER: u32 = 50;

/// The served tool description, verbatim (`studies.tool_schema`); the fixture test guards it.
pub const STUDY_TRIAL_DESCRIPTION: &str = "Run one fresh Newton-Raphson AC trial. load_scale multiplies ALL loads' P/Q and observes bus_voltage; line_rating scales one line max_i_ka and observes line_loading; gen_dispatch scales one generator P and observes trafo_loading. Use operation=none for base/N-1 reports. Returns actual measurements, not a fitted answer. element_id selects the modified line/generator (unused for all-load scaling). observation_id selects the observed bus/line/transformer. Omit contingency_line (or pass null) for the intact network; an integer takes that line out of service, and 0 is a real line. status=constraint_violation with metric_valid=true is still a usable measurement: compare voltage_violations with base_case_voltage_violations, which the unmodified case already has.";

/// Networks the study tool serves, in its enum order (`powermcp.CASE_FILES` then fixtures).
pub const NETWORKS: [&str; 4] = ["snem-sa-2000", "snem-1803", "fixture-2bus-ok", "fixture-2bus-nonconverged"];

/// What a trial observes.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Observation {
    BusVoltage,
    LineLoading,
    TrafoLoading,
}

impl Observation {
    pub const ALL: [Observation; 3] = [Observation::BusVoltage, Observation::LineLoading, Observation::TrafoLoading];

    pub fn as_str(self) -> &'static str {
        match self {
            Observation::BusVoltage => "bus_voltage",
            Observation::LineLoading => "line_loading",
            Observation::TrafoLoading => "trafo_loading",
        }
    }
}

/// What a SIMULATE trial changes. Each modification observes one quantity (`studies.py`'s rule).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Modification {
    LoadScale,
    LineRating,
    GenDispatch,
}

impl Modification {
    pub fn as_str(self) -> &'static str {
        match self {
            Modification::LoadScale => "load_scale",
            Modification::LineRating => "line_rating",
            Modification::GenDispatch => "gen_dispatch",
        }
    }

    /// The only observation the study tool accepts with this modification.
    pub fn observation(self) -> Observation {
        match self {
            Modification::LoadScale => Observation::BusVoltage,
            Modification::LineRating => Observation::LineLoading,
            Modification::GenDispatch => Observation::TrafoLoading,
        }
    }
}

/// An AC power flow, intact or with one line out, observing one element.
#[derive(Clone, Debug, PartialEq)]
pub struct Solve {
    pub network: String,
    pub contingency_line: Option<u32>,
    pub observation: Observation,
    pub observation_id: u32,
    pub max_iter: u32,
}

/// One perturbation trial.
#[derive(Clone, Debug, PartialEq)]
pub struct Simulate {
    pub network: String,
    pub modification: Modification,
    pub scale: f64,
    /// The modified line or generator; ignored by load scaling, which scales every load.
    pub element_id: u32,
    pub observation_id: u32,
    pub contingency_line: Option<u32>,
    pub max_iter: u32,
}

/// A typed command.
#[derive(Clone, Debug, PartialEq)]
pub enum Command {
    Solve(Solve),
    Simulate(Simulate),
}

/// Why a command was refused before reaching the tool.
#[derive(Debug, PartialEq)]
pub enum IrError {
    UnknownNetwork(String),
    ScaleOutOfRange(f64),
    MaxIterOutOfRange(u32),
    Syntax(String),
}

impl fmt::Display for IrError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            IrError::UnknownNetwork(n) => write!(f, "unknown network {n:?}; served: {NETWORKS:?}"),
            IrError::ScaleOutOfRange(s) => write!(f, "scale {s} outside [{SCALE_MIN}, {SCALE_MAX}]"),
            IrError::MaxIterOutOfRange(m) => write!(f, "max_iter {m} outside [1, {MAX_ITERATIONS}]"),
            IrError::Syntax(msg) => write!(f, "syntax: {msg}"),
        }
    }
}

fn check_common(network: &str, max_iter: u32) -> Result<(), IrError> {
    if !NETWORKS.contains(&network) {
        return Err(IrError::UnknownNetwork(network.to_string()));
    }
    if !(1..=MAX_ITERATIONS).contains(&max_iter) {
        return Err(IrError::MaxIterOutOfRange(max_iter));
    }
    Ok(())
}

impl Command {
    /// Check what the schema (and `studies.run_study_trial`) would refuse, before any call.
    pub fn validate(&self) -> Result<(), IrError> {
        match self {
            Command::Solve(s) => check_common(&s.network, s.max_iter),
            Command::Simulate(s) => {
                check_common(&s.network, s.max_iter)?;
                if !(s.scale.is_finite() && (SCALE_MIN..=SCALE_MAX).contains(&s.scale)) {
                    return Err(IrError::ScaleOutOfRange(s.scale));
                }
                Ok(())
            }
        }
    }

    /// The `run_study_trial` arguments, in schema property order. `contingency_line` is
    /// omitted for the intact network, as the trained procedure omits it (FM-18).
    pub fn lower(&self) -> Result<Value, IrError> {
        self.validate()?;
        let mut args = Map::new();
        let (network, operation, scale, element_id, observation, observation_id, contingency, max_iter) = match self {
            Command::Solve(s) => (&s.network, "none", json!(1.0), 0, s.observation, s.observation_id, s.contingency_line, s.max_iter),
            Command::Simulate(s) => (&s.network, s.modification.as_str(), json!(s.scale), s.element_id, s.modification.observation(),
                                     s.observation_id, s.contingency_line, s.max_iter),
        };
        args.insert("network_id".into(), json!(network));
        args.insert("operation".into(), json!(operation));
        args.insert("scale".into(), scale);
        args.insert("element_id".into(), json!(element_id));
        args.insert("observation".into(), json!(observation.as_str()));
        args.insert("observation_id".into(), json!(observation_id));
        if let Some(line) = contingency {
            args.insert("contingency_line".into(), json!(line));
        }
        args.insert("max_iter".into(), json!(max_iter));
        Ok(Value::Object(args))
    }
}

/// The served `run_study_trial` tool definition, generated from the IR's own constants.
pub fn study_trial_schema() -> Value {
    let operations: Vec<&str> = std::iter::once("none")
        .chain([Modification::LoadScale, Modification::LineRating, Modification::GenDispatch].map(Modification::as_str))
        .collect();
    let observations: Vec<&str> = Observation::ALL.iter().map(|o| o.as_str()).collect();
    json!({
        "type": "function",
        "function": {
            "name": "run_study_trial",
            "description": STUDY_TRIAL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "additionalProperties": false,
                "properties": {
                    "network_id": {"type": "string", "enum": NETWORKS},
                    "operation": {"type": "string", "enum": operations},
                    "scale": {"type": "number", "minimum": SCALE_MIN, "maximum": SCALE_MAX},
                    "element_id": {"type": "integer"},
                    "observation": {"type": "string", "enum": observations},
                    "observation_id": {"type": "integer"},
                    "contingency_line": {"type": ["integer", "null"]},
                    "max_iter": {"type": "integer", "minimum": 1, "maximum": MAX_ITERATIONS}
                },
                "required": ["network_id", "operation", "scale", "element_id", "observation", "observation_id", "max_iter"]
            }
        }
    })
}

/// Python `json.dumps` default formatting: `", "` between items, `": "` after keys.
struct PythonFormatter;

impl serde_json::ser::Formatter for PythonFormatter {
    fn begin_array_value<W: ?Sized + std::io::Write>(&mut self, writer: &mut W, first: bool) -> std::io::Result<()> {
        if first { Ok(()) } else { writer.write_all(b", ") }
    }
    fn begin_object_key<W: ?Sized + std::io::Write>(&mut self, writer: &mut W, first: bool) -> std::io::Result<()> {
        if first { Ok(()) } else { writer.write_all(b", ") }
    }
    fn begin_object_value<W: ?Sized + std::io::Write>(&mut self, writer: &mut W) -> std::io::Result<()> {
        writer.write_all(b": ")
    }
}

/// Serialize as Python's `json.dumps(value)` does, so bytes compare with the served schema.
pub fn to_python_json(value: &Value) -> String {
    let mut out = Vec::new();
    let mut ser = serde_json::Serializer::with_formatter(&mut out, PythonFormatter);
    serde::Serialize::serialize(value, &mut ser).expect("serializing a Value cannot fail");
    String::from_utf8(out).expect("serde_json writes UTF-8")
}

/// Parse the textual DSL into a command.
///
/// ```text
/// SOLVE <network> [OUTAGE <line>] OBSERVE <bus_voltage|line_loading|trafo_loading> <id> [MAXITER <n>]
/// SIMULATE <network> <load_scale|line_rating|gen_dispatch> <scale> [ELEMENT <id>] OBSERVE <id>
///          [OUTAGE <line>] [MAXITER <n>]
/// ```
pub fn parse(text: &str) -> Result<Command, IrError> {
    let words: Vec<&str> = text.split_whitespace().collect();
    let syntax = |m: &str| IrError::Syntax(m.to_string());
    let number = |w: Option<&&str>, what: &str| -> Result<u32, IrError> {
        w.ok_or_else(|| syntax(&format!("{what} needs a value")))?
            .parse::<u32>()
            .map_err(|_| syntax(&format!("{what} must be a non-negative integer")))
    };
    let keyword = |key: &str| words.iter().position(|w| w.eq_ignore_ascii_case(key));
    let value_after = |key: &str| keyword(key).map(|i| words.get(i + 1));
    let network = words.get(1).ok_or_else(|| syntax("missing network"))?.to_string();
    let outage = match value_after("OUTAGE") { Some(w) => Some(number(w, "OUTAGE")?), None => None };
    let max_iter = match value_after("MAXITER") { Some(w) => number(w, "MAXITER")?, None => DEFAULT_MAX_ITER };
    let command = match words.first().map(|w| w.to_ascii_uppercase()) {
        Some(ref verb) if verb == "SOLVE" => {
            let i = keyword("OBSERVE").ok_or_else(|| syntax("SOLVE needs OBSERVE <kind> <id>"))?;
            let kind = words.get(i + 1).ok_or_else(|| syntax("OBSERVE needs a kind"))?;
            let observation = Observation::ALL.into_iter().find(|o| o.as_str() == *kind)
                .ok_or_else(|| syntax(&format!("unknown observation {kind}")))?;
            Command::Solve(Solve { network, contingency_line: outage, observation,
                                   observation_id: number(words.get(i + 2), "OBSERVE")?, max_iter })
        }
        Some(ref verb) if verb == "SIMULATE" => {
            let kind = words.get(2).ok_or_else(|| syntax("SIMULATE needs a modification"))?;
            let modification = [Modification::LoadScale, Modification::LineRating, Modification::GenDispatch]
                .into_iter().find(|m| m.as_str() == *kind)
                .ok_or_else(|| syntax(&format!("unknown modification {kind}")))?;
            let scale = words.get(3).ok_or_else(|| syntax("SIMULATE needs a scale"))?
                .parse::<f64>().map_err(|_| syntax("scale must be a number"))?;
            let element_id = match value_after("ELEMENT") { Some(w) => number(w, "ELEMENT")?, None => 0 };
            let observation_id = number(value_after("OBSERVE").flatten(), "OBSERVE")?;
            Command::Simulate(Simulate { network, modification, scale, element_id, observation_id,
                                         contingency_line: outage, max_iter })
        }
        _ => return Err(syntax("a command starts with SOLVE or SIMULATE")),
    };
    command.validate()?;
    Ok(command)
}
