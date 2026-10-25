//! The Phase 2 happy path as one function (issue #54, section 9). Order matters and is fixed:
//! audit the decision before acting, deny on anything unestablished, never fall back off MXC for
//! this runner. The caller cannot supply a command: the only work is a typed [`Job`].

use mxc_sdk::v1::WaitResult;
use poweragent_audit::{decision_event, AuditLog, Bus, Event, EventKind};
use poweragent_exec::{build_request, run, Job};
use poweragent_policy::{decide, AdminPolicy, Decision, TaskProfile};
use poweragent_podman::SidecarRuntime;
use poweragent_sidecar::{resolve, Action, ContainerSpec, Drain, Reconciler, Registry, Runtime, SidecarSpec};
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
    /// Podman sidecars: digest-pinned image, fixed argv and limits (administrator-owned).
    pub image: Option<String>,
    #[serde(default)]
    pub command: Vec<String>,
    pub memory_mb: Option<u32>,
    pub cpu_millis: Option<u32>,
    pub pids: Option<u32>,
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
        let container = match (&runtime, e.image) {
            (Runtime::Podman, Some(image)) => {
                let c = ContainerSpec {
                    image,
                    command: e.command,
                    memory_mb: e.memory_mb.unwrap_or(256),
                    cpu_millis: e.cpu_millis.unwrap_or(500),
                    pids: e.pids.unwrap_or(64),
                };
                c.validate().map_err(|m| format!("sidecar {:?}: {m}", e.name))?;
                Some(c)
            }
            (Runtime::Podman, None) => None, // planned-only entry; the Podman runtime refuses to start it
            (Runtime::Windows, Some(_)) => return Err(format!("sidecar {:?}: a windows sidecar cannot have an image", e.name)),
            (Runtime::Windows, None) => None,
        };
        specs.push(SidecarSpec { name: e.name, runtime, depends_on: e.depends_on, requires: e.requires, container });
    }
    Ok(Registry::new(specs))
}

pub struct RunArgs<'a> {
    pub task: String,
    pub profile: TaskProfile,
    pub policy: AdminPolicy,
    pub registry: Registry,
    pub job: Job,
    pub worker: PathBuf,
    pub audit_path: PathBuf,
    /// Launches the planned sidecars. `PlannedOnly` launches nothing.
    pub sidecars: &'a dyn SidecarRuntime,
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

/// Stop every sidecar the task still holds, auditing each stop. Used on every exit path.
fn teardown(bus: &mut Bus, rt: &dyn SidecarRuntime, rec: &mut Reconciler, task: &str) -> Result<(), String> {
    let mut failures = Vec::new();
    for act in rec.release(task, Drain::Immediate) {
        if let Action::Stop(n) = act {
            if let Err(e) = rt.stop(task, &n) {
                failures.push(format!("{n}: {e}"));
            }
            if rt.launches() {
                bus.emit(Event { task: task.into(), kind: EventKind::SidecarStopped { name: n } })?;
            }
        }
    }
    if failures.is_empty() { Ok(()) } else { Err(format!("sidecar stop failed: {}", failures.join("; "))) }
}

/// Run one task end to end. Any failure to write audit is returned as an error and nothing runs.
pub fn run_task(a: RunArgs<'_>, bus: &mut Bus) -> Result<Outcome, String> {
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
            let spec = a.registry.get(n).ok_or_else(|| format!("planned sidecar {n:?} vanished from the registry"))?;
            if let Err(e) = a.sidecars.start(&a.task, spec) {
                let _ = teardown(bus, a.sidecars, &mut rec, &a.task);
                return denied(bus, &a.task, format!("sidecar_start_failed: {e}"));
            }
            if a.sidecars.launches() {
                bus.emit(Event { task: a.task.clone(), kind: EventKind::SidecarStarted { name: n.clone() } })?;
            }
        }
    }

    let request = match build_request(&decision, &a.profile, &a.worker, &a.job) {
        Ok(r) => r,
        Err(e) => {
            let _ = teardown(bus, a.sidecars, &mut rec, &a.task);
            return denied(bus, &a.task, format!("request: {e:?}"));
        }
    };
    let result = run(request); // MXC only; an SDK error is a failure, never a fallback
    let outcome = match result {
        Ok(o) => match o.outcome {
            WaitResult::Exited(c) => Outcome::Exited(c),
            _ => Outcome::TimedOut,
        },
        Err(e) => {
            let _ = teardown(bus, a.sidecars, &mut rec, &a.task);
            return denied(bus, &a.task, format!("mxc_error: {e:?}"));
        }
    };
    let stop = teardown(bus, a.sidecars, &mut rec, &a.task);
    let note = match &stop {
        Ok(()) => String::new(),
        Err(e) => format!("; {e}"),
    };
    bus.emit(Event { task: a.task.clone(), kind: EventKind::Finished { outcome: format!("{outcome:?}{note}") } })?;
    stop.map(|()| outcome)
}

pub fn open_bus(path: &Path) -> Result<Bus, String> {
    Ok(Bus::new(AuditLog::open(path)?))
}
