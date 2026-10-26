//! The Phase 2 happy path as one function (issue #54, section 9). Order matters and is fixed:
//! audit the decision before acting, deny on anything unestablished, never fall back off MXC for
//! this runner. The caller cannot supply a command: the only work is a typed [`Job`].

use mxc_sdk::v1::WaitResult;
use poweragent_audit::{decision_event, AuditLog, Bus, Event, EventKind};
use poweragent_exec::{build_request, run, Job};
use poweragent_policy::{decide, AdminPolicy, Decision, TaskProfile};
use poweragent_podman::{Podman, SidecarRuntime};
use poweragent_sidecar::{resolve, Action, ContainerSpec, Reconciler, Registry, Runtime, SidecarSpec};
use std::collections::BTreeSet;
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
    /// Starts and stops the helpers a task needs.
    pub sidecars: &'a dyn SidecarRuntime,
    /// Explicit dry-run mode: required helpers are audited as *planned* and nothing is launched. Without it,
    /// a task that needs helpers is refused unless `sidecars` really launches them, so an authorised, required
    /// helper can never silently become a no-op while the task reports success.
    pub plan_only: bool,
}

#[derive(Debug, PartialEq, Eq)]
pub enum Outcome {
    /// Contained worker finished with this exit code.
    Exited(i32),
    TimedOut,
    /// Not run; the reason is also in the audit log.
    Denied(String),
}

/// Holds the helpers a task may have started and guarantees an attempt to stop every one of them, on every exit
/// path: normal completion, a denial, an audit failure, or an unwinding panic (Drop). A name is held *before*
/// its start is attempted, so a start that fails half-way is still cleaned up.
struct Lease<'a> {
    rt: &'a dyn SidecarRuntime,
    task: String,
    held: Vec<String>,
}

impl<'a> Lease<'a> {
    fn new(rt: &'a dyn SidecarRuntime, task: &str) -> Self {
        Lease { rt, task: task.to_string(), held: vec![] }
    }
    fn hold(&mut self, name: &str) {
        self.held.push(name.to_string());
    }
    /// Stop every held helper (reverse start order), continuing past failures. Returns each name with its result.
    fn stop_all(&mut self) -> Vec<(String, Result<(), String>)> {
        let mut out = Vec::new();
        while let Some(n) = self.held.pop() {
            let r = self.rt.stop(&self.task, &n);
            out.push((n, r));
        }
        out
    }
}

impl Drop for Lease<'_> {
    fn drop(&mut self) {
        let _ = self.stop_all(); // best effort when unwinding; the normal path has already emptied `held`
    }
}

/// Stop everything the lease holds, audit each stop (when helpers were really launched), and never let an
/// audit failure prevent the remaining stops. Errors from stopping and from auditing are aggregated.
fn release(bus: &mut Bus, lease: &mut Lease<'_>, audit_stops: bool) -> Result<(), String> {
    let task = lease.task.clone();
    let mut problems = Vec::new();
    for (n, r) in lease.stop_all() {
        if let Err(e) = r {
            problems.push(format!("stop {n}: {e}"));
        }
        if audit_stops {
            if let Err(e) = bus.emit(Event { task: task.clone(), kind: EventKind::SidecarStopped { name: n.clone() } }) {
                problems.push(format!("audit stop {n}: {e}"));
            }
        }
    }
    if problems.is_empty() { Ok(()) } else { Err(format!("sidecar cleanup: {}", problems.join("; "))) }
}

enum Inner {
    /// The worker ran.
    Ran(Outcome),
    /// Denied after the decision was audited: the caller audits the reason once the helpers are stopped.
    Denied(String),
    /// Denied by the decision itself, which already wrote its own audit event.
    DeniedAudited(String),
}

fn run_inner(a: &RunArgs<'_>, bus: &mut Bus, lease: &mut Lease<'_>) -> Result<Inner, String> {
    let report = poweragent_probe::probe_host(Some(&a.profile));
    let decision = decide(&a.profile, &a.policy, &report.probe);
    bus.emit(decision_event(&a.task, &decision))?;
    if let Decision::Deny { reason } = &decision {
        return Ok(Inner::DeniedAudited(format!("{reason:?}")));
    }

    let plan = match resolve(&decision, &a.registry) {
        Ok(p) => p,
        Err(e) => return Ok(Inner::Denied(format!("sidecar_resolution: {e:?}"))),
    };
    if !plan.is_empty() && !a.plan_only && !a.sidecars.launches() {
        return Ok(Inner::Denied(format!(
            "sidecar_not_launchable: the task requires {plan:?} but this runtime launches nothing; use a launching runtime or plan-only mode"
        )));
    }
    let mut rec = Reconciler::default();
    let actions = match rec.activate(&a.task, &plan) {
        Ok(x) => x,
        Err(e) => return Ok(Inner::Denied(format!("sidecar_disabled: {e}"))),
    };
    for act in &actions {
        if let Action::Start(n) = act {
            bus.emit(Event { task: a.task.clone(), kind: EventKind::SidecarPlanned { name: n.clone() } })?;
            if a.plan_only {
                continue;
            }
            let spec = a.registry.get(n).ok_or_else(|| format!("planned sidecar {n:?} vanished from the registry"))?;
            lease.hold(n); // before the start: a half-finished start is still cleaned up
            if let Err(e) = a.sidecars.start(&a.task, spec) {
                return Ok(Inner::Denied(format!("sidecar_start_failed: {e}")));
            }
            bus.emit(Event { task: a.task.clone(), kind: EventKind::SidecarStarted { name: n.clone() } })?;
        }
    }

    let request = match build_request(&decision, &a.profile, &a.worker, &a.job) {
        Ok(r) => r,
        Err(e) => return Ok(Inner::Denied(format!("request: {e:?}"))),
    };
    match run(request) {
        // MXC only; an SDK error is a failure, never a fallback
        Ok(o) => Ok(Inner::Ran(match o.outcome {
            WaitResult::Exited(c) => Outcome::Exited(c),
            _ => Outcome::TimedOut,
        })),
        Err(e) => Ok(Inner::Denied(format!("mxc_error: {e:?}"))),
    }
}

/// Run one task end to end. An audit failure is returned as an error, and every helper that may have been started
/// is still stopped.
pub fn run_task(a: RunArgs<'_>, bus: &mut Bus) -> Result<Outcome, String> {
    let mut lease = Lease::new(a.sidecars, &a.task);
    let inner = run_inner(&a, bus, &mut lease);
    let cleanup = release(bus, &mut lease, a.sidecars.launches() && !a.plan_only);
    match inner {
        Err(e) => Err(match cleanup {
            Ok(()) => e,
            Err(c) => format!("{e}; {c}"),
        }),
        Ok(Inner::DeniedAudited(r)) => cleanup.map(|()| Outcome::Denied(r)),
        Ok(Inner::Denied(r)) => {
            let audited = bus.emit(Event { task: a.task.clone(), kind: EventKind::Denied { reason: r.clone() } });
            match (audited, cleanup) {
                (Ok(()), Ok(())) => Ok(Outcome::Denied(r)),
                (Err(e), Ok(())) => Err(e),
                (Ok(()), Err(c)) => Err(c),
                (Err(e), Err(c)) => Err(format!("{e}; {c}")),
            }
        }
        Ok(Inner::Ran(outcome)) => {
            let note = match &cleanup {
                Ok(()) => String::new(),
                Err(e) => format!("; {e}"),
            };
            bus.emit(Event { task: a.task.clone(), kind: EventKind::Finished { outcome: format!("{outcome:?}{note}") } })?;
            cleanup.map(|()| outcome)
        }
    }
}

/// Is `name` still authorised by `policy` in full: its own sidecar capability, every capability it requires, and
/// every helper it depends on (recursively)? An unknown helper is not authorised.
fn sidecar_authorised(policy: &AdminPolicy, registry: &Registry, name: &str, seen: &mut BTreeSet<String>) -> bool {
    if !seen.insert(name.to_string()) {
        return false; // dependency cycle
    }
    let Some(spec) = registry.get(name) else { return false };
    let own = poweragent_policy::Capability::Sidecar { name: name.to_string() };
    let ok = policy.allowed_capabilities.contains(&own)
        && spec.requires.iter().all(|c| policy.allowed_capabilities.contains(c))
        && spec.depends_on.iter().all(|d| sidecar_authorised(policy, registry, d, seen));
    seen.remove(name);
    ok
}

fn stop_matching(podman: &Podman, bus: &mut Bus, keep: &dyn Fn(&str) -> bool) -> Result<Vec<String>, String> {
    let mut revoked = Vec::new();
    let mut problems = Vec::new();
    for (task, name) in podman.list_running()? {
        if keep(&name) {
            continue;
        }
        match podman.stop(&task, &name) {
            Ok(()) => {
                revoked.push(format!("{task}/{name}"));
                if let Err(e) = bus.emit(Event { task: task.clone(), kind: EventKind::SidecarRevoked { name: name.clone() } }) {
                    problems.push(format!("audit {task}/{name}: {e}"));
                }
            }
            Err(e) => problems.push(format!("stop {task}/{name}: {e}")), // keep going: stop everything we can
        }
    }
    if problems.is_empty() { Ok(revoked) } else { Err(format!("revoked {revoked:?}; problems: {}", problems.join("; "))) }
}

/// Central disable of RUNNING helpers (FR-001, FR-006): stop every helper this runtime started that the current
/// policy no longer fully authorises (its own capability, everything it requires, everything it depends on), and
/// audit each stop. A helper missing from the registry is revoked. Containers the runtime did not start (no
/// `poweragent.*` labels) are never touched.
pub fn revoke_unauthorised(policy: &AdminPolicy, registry: &Registry, podman: &Podman, bus: &mut Bus) -> Result<Vec<String>, String> {
    stop_matching(podman, bus, &|name| sidecar_authorised(policy, registry, name, &mut BTreeSet::new()))
}

/// Orphan recovery: stop every running helper this runtime started, whatever the policy says. Use after a
/// crash or kill of `poweragent run`, when no destructor could clean up.
pub fn reap(podman: &Podman, bus: &mut Bus) -> Result<Vec<String>, String> {
    stop_matching(podman, bus, &|_| false)
}

pub fn open_bus(path: &Path) -> Result<Bus, String> {
    Ok(Bus::new(AuditLog::open(path)?))
}
