//! Gate 2 (issue #54): dynamic sidecars.
//!
//! A sidecar is *installed but inactive* until a task whose granted capabilities include
//! `Capability::Sidecar { name }` activates it. The administrator policy is the only switch that
//! enables a sidecar (FR-001); a sidecar can never add to the capability set (SEC-002), so its
//! dependencies and the capabilities it needs must already be granted. This module is pure: it
//! returns [`Action`]s for a host to carry out and does not start anything itself.

use poweragent_policy::{Capability, Decision};
use std::collections::{BTreeMap, BTreeSet};

/// Where a sidecar runs (FR-002).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Runtime {
    Podman,
    Windows,
}

#[derive(Debug, Clone)]
pub struct SidecarSpec {
    pub name: String,
    pub runtime: Runtime,
    /// Sidecars that must be running first. They must be granted too; they are not added implicitly.
    pub depends_on: Vec<String>,
    /// Capabilities the sidecar needs; all must be in the task's granted set.
    pub requires: Vec<Capability>,
}

/// Installed sidecars (immutable catalogue; installing is a deployment concern, FR-012).
#[derive(Debug, Default)]
pub struct Registry(BTreeMap<String, SidecarSpec>);

impl Registry {
    pub fn new(specs: Vec<SidecarSpec>) -> Self {
        Registry(specs.into_iter().map(|s| (s.name.clone(), s)).collect())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ResolveError {
    NotRunnable,
    Unknown(String),
    /// Dependency or required capability absent from the granted set.
    NotGranted { sidecar: String, missing: Vec<Capability> },
    Cycle(String),
}

fn sidecar_cap(name: &str) -> Capability {
    Capability::Sidecar { name: name.to_string() }
}

/// Sidecars to run for a task, dependencies first, from an authorized decision only.
pub fn resolve(decision: &Decision, registry: &Registry) -> Result<Vec<String>, ResolveError> {
    let granted: &Vec<Capability> = match decision {
        Decision::Run { granted, .. } => granted,
        Decision::Deny { .. } => return Err(ResolveError::NotRunnable),
    };
    let granted_set: BTreeSet<&Capability> = granted.iter().collect();
    let requested: Vec<&str> = granted
        .iter()
        .filter_map(|c| if let Capability::Sidecar { name } = c { Some(name.as_str()) } else { None })
        .collect();

    let mut order: Vec<String> = Vec::new();
    let mut visiting: BTreeSet<String> = BTreeSet::new();
    for name in requested {
        visit(name, registry, &granted_set, &mut order, &mut visiting)?;
    }
    Ok(order)
}

fn visit(
    name: &str,
    registry: &Registry,
    granted: &BTreeSet<&Capability>,
    order: &mut Vec<String>,
    visiting: &mut BTreeSet<String>,
) -> Result<(), ResolveError> {
    if order.iter().any(|n| n == name) {
        return Ok(());
    }
    if !visiting.insert(name.to_string()) {
        return Err(ResolveError::Cycle(name.to_string()));
    }
    let spec = registry.0.get(name).ok_or_else(|| ResolveError::Unknown(name.to_string()))?;
    let mut missing: Vec<Capability> = spec.requires.iter().filter(|c| !granted.contains(c)).cloned().collect();
    missing.extend(spec.depends_on.iter().map(|d| sidecar_cap(d)).filter(|c| !granted.contains(c)));
    if !missing.is_empty() {
        return Err(ResolveError::NotGranted { sidecar: name.to_string(), missing });
    }
    for dep in &spec.depends_on {
        visit(dep, registry, granted, order, visiting)?;
    }
    visiting.remove(name);
    order.push(name.to_string());
    Ok(())
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Action {
    Start(String),
    Stop(String),
}

/// How a revoked or released sidecar is stopped (FR-006).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Drain {
    /// Stop as soon as the last reference is gone / immediately on revocation.
    Immediate,
}

/// Desired-state reconciler with per-sidecar reference counts. Idempotent: repeating a call with the
/// same arguments yields no further actions.
#[derive(Debug, Default)]
pub struct Reconciler {
    tasks: BTreeMap<String, Vec<String>>, // task id -> sidecars it holds, start order
    revoked: BTreeSet<String>,
}

impl Reconciler {
    fn refs(&self, name: &str) -> usize {
        self.tasks.values().filter(|v| v.iter().any(|n| n == name)).count()
    }
    pub fn running(&self) -> BTreeSet<String> {
        self.tasks.values().flatten().cloned().collect()
    }

    /// Activate `plan` for `task`. Fails if any member has been disabled centrally; nothing starts then.
    pub fn activate(&mut self, task: &str, plan: &[String]) -> Result<Vec<Action>, String> {
        if let Some(r) = plan.iter().find(|n| self.revoked.contains(*n)) {
            return Err(format!("sidecar {r:?} is disabled by policy"));
        }
        let before = self.running();
        self.tasks.insert(task.to_string(), plan.to_vec());
        Ok(plan.iter().filter(|n| !before.contains(*n)).map(|n| Action::Start(n.clone())).collect())
    }

    /// Release a task; stop sidecars nobody else holds (reverse start order).
    pub fn release(&mut self, task: &str, _drain: Drain) -> Vec<Action> {
        let Some(plan) = self.tasks.remove(task) else { return vec![] };
        plan.iter().rev().filter(|n| self.refs(n) == 0).map(|n| Action::Stop(n.clone())).collect()
    }

    /// Central disable: block future activation and stop it now. Tasks that held it lose it.
    pub fn revoke(&mut self, name: &str, _drain: Drain) -> Vec<Action> {
        self.revoked.insert(name.to_string());
        let was_running = self.running().contains(name);
        for plan in self.tasks.values_mut() {
            plan.retain(|n| n != name);
        }
        if was_running { vec![Action::Stop(name.to_string())] } else { vec![] }
    }

    /// Re-enable after an administrator lifts the disable.
    pub fn restore(&mut self, name: &str) {
        self.revoked.remove(name);
    }
}
