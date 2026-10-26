//! Gate 0 of issue #54 (MXC-first Windows host integration).
//!
//! The agent *requests* capabilities in a [`TaskProfile`]; an independent [`AdminPolicy`]
//! decides what may be granted; [`decide`] picks an execution backend from what the host
//! [`Probe`] reports. Every unknown or unsupported situation resolves to [`Decision::Deny`]
//! (SEC-010). Nothing here executes anything, and nothing an LLM supplies is installed or run.

use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

pub const API_VERSION: &str = "poweragent.dev/v1alpha1";
pub const KIND: &str = "TaskProfile";

/// Execution substrates, in ADR-002 fallback order (MXC first).
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Backend {
    Mxc,
    Jea,
    WindowsRs,
    IsolatedVm,
}

/// ADR-002 order. Fallback beyond the first entry needs explicit administrator policy.
pub const FALLBACK_ORDER: [Backend; 4] =
    [Backend::Mxc, Backend::Jea, Backend::WindowsRs, Backend::IsolatedVm];

/// A capability the task asks for. Deliberately closed: there is no "run command" variant.
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Capability {
    FsRead { path: String },
    FsWrite { path: String },
    NetEgress { host: String },
    Sidecar { name: String },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Metadata {
    pub name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Spec {
    /// Task runs generated/untrusted code: requires OS-enforced containment (SEC-012).
    pub untrusted_code: bool,
    pub capabilities: Vec<Capability>,
    pub timeout_seconds: u32,
}

/// Declarative request manifest. A proposed schema, not an MXC or Podman API (FR-003).
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct TaskProfile {
    pub api_version: String,
    pub kind: String,
    pub metadata: Metadata,
    pub spec: Spec,
}

/// Central policy, owned by the policy authority. Never derived from agent-controlled content.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct AdminPolicy {
    pub allowed_capabilities: BTreeSet<Capability>,
    /// Backends other than MXC the administrator explicitly permits as fallback.
    pub allowed_fallbacks: BTreeSet<Backend>,
}

/// What the host backend probe reported (Gate 0 command output).
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Probe {
    /// MXC backend present and healthy on this host.
    pub mxc_available: bool,
    /// MXC can enforce every restriction in the compiled policy (e.g. network model).
    pub mxc_supports_policy: bool,
    pub available_fallbacks: BTreeSet<Backend>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "outcome", rename_all = "snake_case")]
pub enum Decision {
    Run { backend: Backend, granted: Vec<Capability> },
    Deny { reason: DenyReason },
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "why", rename_all = "snake_case")]
pub enum DenyReason {
    InvalidProfile { detail: String },
    /// Authorization failed; never triggers fallback (ADR-002).
    CapabilityNotAuthorized { denied: Vec<Capability> },
    /// Untrusted code and MXC cannot contain it: never run uncontained (SEC-012).
    ContainmentUnavailable,
    NoPermittedBackend,
}

/// Structural validation beyond what serde enforces.
pub fn validate(p: &TaskProfile) -> Result<(), String> {
    if p.api_version != API_VERSION {
        return Err(format!("unsupported apiVersion {:?}", p.api_version));
    }
    if p.kind != KIND {
        return Err(format!("unsupported kind {:?}", p.kind));
    }
    if p.metadata.name.is_empty() {
        return Err("metadata.name is empty".into());
    }
    if p.spec.timeout_seconds == 0 {
        return Err("spec.timeoutSeconds must be > 0".into());
    }
    for c in &p.spec.capabilities {
        let value = match c {
            Capability::FsRead { path } | Capability::FsWrite { path } => path,
            Capability::NetEgress { host } => host,
            Capability::Sidecar { name } => name,
        };
        if value.is_empty() {
            return Err("capability value is empty".into());
        }
        if let Capability::FsRead { path } | Capability::FsWrite { path } = c {
            if path.split(['/', '\\']).any(|s| s == "..") {
                return Err("path traversal ('..') is not allowed".into());
            }
        }
    }
    Ok(())
}

pub fn parse_profile(json: &str) -> Result<TaskProfile, String> {
    let p: TaskProfile = serde_json::from_str(json).map_err(|e| e.to_string())?;
    validate(&p)?;
    Ok(p)
}

/// Decide whether and where a task may run. Deterministic and side-effect free.
pub fn decide(profile: &TaskProfile, policy: &AdminPolicy, probe: &Probe) -> Decision {
    if let Err(detail) = validate(profile) {
        return Decision::Deny { reason: DenyReason::InvalidProfile { detail } };
    }

    // Intersect request with central policy. Any excess is a denial, not a fallback trigger.
    let denied: Vec<Capability> = profile
        .spec
        .capabilities
        .iter()
        .filter(|c| !policy.allowed_capabilities.contains(*c))
        .cloned()
        .collect();
    if !denied.is_empty() {
        return Decision::Deny { reason: DenyReason::CapabilityNotAuthorized { denied } };
    }
    let granted = profile.spec.capabilities.clone();

    if probe.mxc_available && probe.mxc_supports_policy {
        return Decision::Run { backend: Backend::Mxc, granted };
    }

    // MXC cannot serve this task. Untrusted code never falls back off an OS-enforced container.
    if profile.spec.untrusted_code {
        return Decision::Deny { reason: DenyReason::ContainmentUnavailable };
    }

    // Trusted tasks may fall back, but only to a backend the administrator listed.
    for b in FALLBACK_ORDER.iter().skip(1) {
        if policy.allowed_fallbacks.contains(b) && probe.available_fallbacks.contains(b) {
            return Decision::Run { backend: *b, granted };
        }
    }
    Decision::Deny { reason: DenyReason::NoPermittedBackend }
}
