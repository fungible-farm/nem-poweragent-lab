//! The Phase 2 happy path as one function (issue #54, section 9). Order matters and is fixed:
//! audit the decision before acting, deny on anything unestablished, never fall back off MXC for
//! this runner. The caller cannot supply a command: the only work is a typed [`Job`].

use mxc_sdk::v1::WaitResult;
use poweragent_audit::{decision_event, AuditLog, Bus, Event, EventKind};
use poweragent_exec::{build_request, run, Job};
use poweragent_policy::{decide, AdminPolicy, Decision, TaskProfile};
use poweragent_sidecar::{resolve, Action, Drain, Reconciler, Registry, Runtime, SidecarSpec};
use serde::Deserialize;
use std::path::{Path, PathBuf};

/// JSON form of an installed sidecar (the catalogue an administrator deploys).
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct SidecarEntry {
    pub name: String,
    pub runtime: String,
    #[serde(default)]
    pub depends_on: Vec<String>,
    #[serde(default)]
    pub requires: Vec<poweragent_policy::Capability>,
}

pub fn load_registry(json: &str) -> Result<Registry, String> {
    let entries: Vec<SidecarEntry> = serde_json::from_str(json).map_err(|e| e.to_string())?;
    let mut specs = Vec::new();
    for e in entries {
        let runtime = match e.runtime.as_str() {
            "podman" => Runtime::Podman,
            "windows" => Runtime::Windows,
            other => return Err(format!("sidecar {:?}: unknown runtime {other:?}", e.name)),
        };
        specs.push(SidecarSpec { name: e.name, runtime, depends_on: e.depends_on, requires: e.requires });
    }
    Ok(Registry::new(specs))
}

pub struct RunArgs {
    pub task: String,
    pub profile: TaskProfile,
    pub policy: AdminPolicy,
    pub registry: Registry,
    pub job: Job,
    pub worker: PathBuf,
    pub audit_path: PathBuf,
}

#[derive(Debug, PartialEq, Eq)]
pub enum Outcome {
    /// Contained worker finished with this exit code.
    Exited(i32),
    TimedOut,
    /// Not run; the reason is also in the audit log.
    Denied(String),
}

fn denied(bus: &mut Bus, task: &str, reason: String) -> Result<Outcome, String> {
    bus.emit(Event { task: task.into(), kind: EventKind::Denied { reason: reason.clone() } })?;
    Ok(Outcome::Denied(reason))
}

/// Run one task end to end. Any failure to write audit is returned as an error and nothing runs.
pub fn run_task(a: RunArgs, bus: &mut Bus) -> Result<Outcome, String> {
    let report = poweragent_probe::probe_host(Some(&a.profile));
    let decision = decide(&a.profile, &a.policy, &report.probe);
    bus.emit(decision_event(&a.task, &decision))?;
    if let Decision::Deny { reason } = &decision {
        return Ok(Outcome::Denied(format!("{reason:?}")));
    }

    let plan = match resolve(&decision, &a.registry) {
        Ok(p) => p,
        Err(e) => return denied(bus, &a.task, format!("sidecar_resolution: {e:?}")),
    };
    let mut rec = Reconciler::default();
    let actions = match rec.activate(&a.task, &plan) {
        Ok(x) => x,
        Err(e) => return denied(bus, &a.task, format!("sidecar_disabled: {e}")),
    };
    for act in &actions {
        if let Action::Start(n) = act {
            bus.emit(Event { task: a.task.clone(), kind: EventKind::SidecarPlanned { name: n.clone() } })?;
        }
    }

    let request = match build_request(&decision, &a.profile, &a.worker, &a.job) {
        Ok(r) => r,
        Err(e) => return denied(bus, &a.task, format!("request: {e:?}")),
    };
    let result = run(request); // MXC only; an SDK error is a failure, never a fallback
    let outcome = match result {
        Ok(o) => match o.outcome {
            WaitResult::Exited(c) => Outcome::Exited(c),
            _ => Outcome::TimedOut,
        },
        Err(e) => return denied(bus, &a.task, format!("mxc_error: {e:?}")),
    };
    for act in rec.release(&a.task, Drain::Immediate) {
        if let Action::Stop(n) = act {
            bus.emit(Event { task: a.task.clone(), kind: EventKind::SidecarStopped { name: n } })?;
        }
    }
    bus.emit(Event { task: a.task.clone(), kind: EventKind::Finished { outcome: format!("{outcome:?}") } })?;
    Ok(outcome)
}

pub fn open_bus(path: &Path) -> Result<Bus, String> {
    Ok(Bus::new(AuditLog::open(path)?))
}
