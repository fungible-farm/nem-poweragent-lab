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

/// NEM regions with cached demand (``powercoder.forecasting.hindcast``).
pub const REGIONS: [&str; 5] = ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"];
/// Forecasting baselines the harness serves (``hindcast.MODELS``).
pub const FORECAST_MODELS: [&str; 3] = ["persistence", "seasonal-naive", "seasonal-naive-empirical-quantiles"];
/// Networks with real limits and costs for OPTIMIZE (``engineering.cases``), besides the served ones.
pub const OPTIMIZE_CASES: [&str; 3] = ["ieee39-pab-stressed", "ieee118-restorebench", "pegase89-restorebench"];
/// The longest forecast horizon, in 5-minute intervals: one day.
pub const MAX_HORIZON: u32 = 288;
/// The most candidates one COMPARE may re-solve.
pub const MAX_CANDIDATES: usize = 10;

/// OPTIMIZE formulations (``dc_opf.run_dc_opf``, ``ac_opf.run_ac_opf``).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Formulation {
    Dc,
    Ac,
}

/// What COMPARE ranks candidate outages by.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CompareMetric {
    MaxLineLoading,
    MinBusVoltage,
}

/// A typed command: PRD-0010 PC-REQ-001's ten.
#[derive(Clone, Debug, PartialEq)]
pub enum Command {
    Solve(Solve),
    Simulate(Simulate),
    /// Observations as known at ``as_of`` (cached AEMO regional demand).
    Recall { region: String, from: String, to: String, as_of: String },
    /// A namespace path's value or children (``namespace.get``/``ls``).
    Resolve { path: String },
    /// WLS state estimation from synthetic measurements seeded by ``seed`` (G5 is blocked).
    Estimate { network: String, seed: u64 },
    Optimize { case: String, formulation: Formulation },
    Forecast { region: String, model: String, issue_time: String, horizons: Vec<u32> },
    /// Rolling-origin hindcast from ``start_day`` of the cached month, every ``every`` intervals.
    Hindcast { region: String, horizons: Vec<u32>, start_day: u32, every: u32 },
    Compare { network: String, candidate_lines: Vec<u32>, metric: CompareMetric },
    /// Resolve every cited number in a claim against the path it cites.
    Explain { claim: String },
}

/// Why a command was refused before reaching the tool.
#[derive(Debug, PartialEq)]
pub enum IrError {
    UnknownNetwork(String),
    Invalid(String),
    ScaleOutOfRange(f64),
    MaxIterOutOfRange(u32),
    Syntax(String),
}

impl fmt::Display for IrError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            IrError::UnknownNetwork(n) => write!(f, "unknown network {n:?}; served: {NETWORKS:?}"),
            IrError::Invalid(msg) => write!(f, "invalid: {msg}"),
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
    /// Check what the executors would refuse, before any call.
    pub fn validate(&self) -> Result<(), IrError> {
        let invalid = |m: String| Err(IrError::Invalid(m));
        let iso = |t: &str| t.len() >= 16 && t.as_bytes()[4] == b'-' && t.as_bytes()[10] == b'T';
        let horizons_ok = |h: &Vec<u32>| !h.is_empty() && h.iter().all(|x| (1..=MAX_HORIZON).contains(x));
        match self {
            Command::Recall { region, from, to, as_of } => {
                if !REGIONS.contains(&region.as_str()) { return invalid(format!("region {region} not in {REGIONS:?}")); }
                if ![from, to, as_of].iter().all(|t| iso(t)) { return invalid("times must be ISO 8601 (YYYY-MM-DDTHH:MM)".into()); }
                if from > to { return invalid("from is after to".into()); }
                Ok(())
            }
            Command::Resolve { path } => if path.starts_with('/') { Ok(()) } else { invalid("a path starts with /".into()) },
            Command::Estimate { network, .. } => check_common(network, DEFAULT_MAX_ITER),
            Command::Optimize { case, .. } => {
                if NETWORKS.contains(&case.as_str()) || OPTIMIZE_CASES.contains(&case.as_str()) { Ok(()) }
                else { invalid(format!("case {case} is neither served nor in {OPTIMIZE_CASES:?}")) }
            }
            Command::Forecast { region, model, issue_time, horizons } => {
                if !REGIONS.contains(&region.as_str()) { return invalid(format!("region {region} not in {REGIONS:?}")); }
                if !FORECAST_MODELS.contains(&model.as_str()) { return invalid(format!("model {model} not in {FORECAST_MODELS:?}")); }
                if !iso(issue_time) { return invalid("issue_time must be ISO 8601".into()); }
                if !horizons_ok(horizons) { return invalid(format!("horizons must be 1..={MAX_HORIZON}")); }
                Ok(())
            }
            Command::Hindcast { region, horizons, every, .. } => {
                if !REGIONS.contains(&region.as_str()) { return invalid(format!("region {region} not in {REGIONS:?}")); }
                if !horizons_ok(horizons) || *every == 0 { return invalid("horizons 1..=288 and every >= 1".into()); }
                Ok(())
            }
            Command::Compare { network, candidate_lines, .. } => {
                check_common(network, DEFAULT_MAX_ITER)?;
                if !(2..=MAX_CANDIDATES).contains(&candidate_lines.len()) {
                    return invalid(format!("2..={MAX_CANDIDATES} candidates"));
                }
                Ok(())
            }
            Command::Explain { claim } => if claim.trim().is_empty() { invalid("empty claim".into()) } else { Ok(()) },
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

    /// The command's name in the DSL.
    pub fn name(&self) -> &'static str {
        match self {
            Command::Solve(_) => "SOLVE", Command::Simulate(_) => "SIMULATE", Command::Recall { .. } => "RECALL",
            Command::Resolve { .. } => "RESOLVE", Command::Estimate { .. } => "ESTIMATE", Command::Optimize { .. } => "OPTIMIZE",
            Command::Forecast { .. } => "FORECAST", Command::Hindcast { .. } => "HINDCAST", Command::Compare { .. } => "COMPARE",
            Command::Explain { .. } => "EXPLAIN",
        }
    }

    /// The executor request: ``{"command": NAME, "args": {...}}``. SOLVE and SIMULATE carry the
    /// `run_study_trial` arguments of [`Command::lower`]; the Python executor
    /// (`powercoder/commands.py`) runs every command.
    pub fn request(&self) -> Result<Value, IrError> {
        self.validate()?;
        let args = match self {
            Command::Solve(_) | Command::Simulate(_) => self.lower()?,
            Command::Recall { region, from, to, as_of } => json!({"region": region, "from": from, "to": to, "as_of": as_of}),
            Command::Resolve { path } => json!({"path": path}),
            Command::Estimate { network, seed } => json!({"network_id": network, "seed": seed}),
            Command::Optimize { case, formulation } =>
                json!({"case": case, "formulation": if *formulation == Formulation::Ac { "ac" } else { "dc" }}),
            Command::Forecast { region, model, issue_time, horizons } =>
                json!({"region": region, "model": model, "issue_time": issue_time, "horizons": horizons}),
            Command::Hindcast { region, horizons, start_day, every } =>
                json!({"region": region, "horizons": horizons, "start_day": start_day, "every": every}),
            Command::Compare { network, candidate_lines, metric } => json!({"network_id": network, "candidate_lines": candidate_lines,
                "metric": if *metric == CompareMetric::MinBusVoltage { "min_bus_voltage" } else { "max_line_loading" }}),
            Command::Explain { claim } => json!({"claim": claim}),
        };
        Ok(json!({"ir_version": IR_VERSION, "command": self.name(), "args": args}))
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
            other => return Err(IrError::Invalid(format!("{} does not lower to run_study_trial", other.name()))),
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
        Some(ref verb) if verb == "RECALL" => {
            // RECALL <region> FROM <t> TO <t> [ASOF <t>]   (ASOF defaults to TO)
            let get = |k: &str| value_after(k).flatten().map(|w| w.to_string()).ok_or_else(|| syntax(&format!("RECALL needs {k} <time>")));
            let to = get("TO")?;
            Command::Recall { region: network, from: get("FROM")?, as_of: value_after("ASOF").flatten().map(|w| w.to_string()).unwrap_or(to.clone()), to }
        }
        Some(ref verb) if verb == "RESOLVE" => Command::Resolve { path: network },
        Some(ref verb) if verb == "ESTIMATE" => {
            let seed = match value_after("SEED") { Some(w) => number(w, "SEED")? as u64, None => 1 };
            Command::Estimate { network, seed }
        }
        Some(ref verb) if verb == "OPTIMIZE" => {
            let formulation = match words.get(2).map(|w| w.to_ascii_uppercase()) {
                Some(ref f) if f == "AC" => Formulation::Ac, Some(ref f) if f == "DC" => Formulation::Dc,
                _ => return Err(syntax("OPTIMIZE <case> <DC|AC>")),
            };
            Command::Optimize { case: network, formulation }
        }
        Some(ref verb) if verb == "FORECAST" || verb == "HINDCAST" => {
            let horizons: Vec<u32> = value_after("HORIZONS").flatten().ok_or_else(|| syntax("needs HORIZONS h1,h2,..."))?
                .split(',').map(|h| h.parse::<u32>().map_err(|_| syntax("horizons are integers"))).collect::<Result<_, _>>()?;
            if verb == "FORECAST" {
                let model = value_after("MODEL").flatten().ok_or_else(|| syntax("FORECAST needs MODEL <name>"))?.to_string();
                let issue_time = value_after("AT").flatten().ok_or_else(|| syntax("FORECAST needs AT <issue time>"))?.to_string();
                Command::Forecast { region: network, model, issue_time, horizons }
            } else {
                let start_day = match value_after("FROMDAY") { Some(w) => number(w, "FROMDAY")?, None => 9 };
                let every = match value_after("EVERY") { Some(w) => number(w, "EVERY")?, None => 12 };
                Command::Hindcast { region: network, horizons, start_day, every }
            }
        }
        Some(ref verb) if verb == "COMPARE" => {
            let lines: Vec<u32> = value_after("OUTAGES").flatten().ok_or_else(|| syntax("COMPARE needs OUTAGES l1,l2,..."))?
                .split(',').map(|h| h.parse::<u32>().map_err(|_| syntax("lines are integers"))).collect::<Result<_, _>>()?;
            let metric = match value_after("BY").flatten().map(|w| w.to_ascii_lowercase()) {
                Some(ref m) if m == "min_bus_voltage" => CompareMetric::MinBusVoltage,
                Some(ref m) if m == "max_line_loading" => CompareMetric::MaxLineLoading,
                _ => return Err(syntax("COMPARE needs BY <max_line_loading|min_bus_voltage>")),
            };
            Command::Compare { network, candidate_lines: lines, metric }
        }
        Some(ref verb) if verb == "EXPLAIN" => {
            let claim = text.trim_start()[7..].trim().to_string();
            Command::Explain { claim }
        }
        _ => return Err(syntax("a command starts with one of SOLVE SIMULATE RECALL RESOLVE ESTIMATE OPTIMIZE FORECAST HINDCAST COMPARE EXPLAIN")),
    };
    command.validate()?;
    Ok(command)
}
