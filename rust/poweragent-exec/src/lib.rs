//! Gate 1 (issue #54): MXC-first execution. The only way to obtain a [`ContainerRequest`] here is
//! from a [`Decision::Run`] on the MXC backend, built from *granted* capabilities. Callers choose a
//! worker [`Job`] from a closed set; there is no arbitrary-command entry point (FR-007, SEC-004).

use mxc_sdk::v1::configs::ProcessContainerConfig;
use mxc_sdk::v1::policy::{NetworkAction, NetworkEgressPolicy, NetworkIngressPolicy, NetworkPolicy};
use mxc_sdk::v1::{self, Containment, ContainerRequest, ExecutionResult, FilesystemPolicy};
use poweragent_policy::{Backend, Capability, Decision, TaskProfile};
use std::path::Path;

/// Closed set of worker operations. The worker binary is fixed by the host, not by the caller.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Job {
    /// Deterministic: sum the bytes of `input`, write the decimal result to `output`.
    Sum { input: String, output: String },
    /// Adversarial probes; the worker reports whether the OS let it through.
    TryRead { path: String },
    TryWrite { path: String },
    TryConnect { addr: String },
    Sleep { seconds: u32 },
}

#[derive(Debug, PartialEq, Eq)]
pub enum BuildError {
    NotRunOnMxc,
    /// Egress rules are not enforceable-and-proven yet, so they are never translated (fail closed).
    NetworkGrantUnsupported(String),
    BadArg(String),
}

fn quote(s: &str) -> Result<String, BuildError> {
    if s.contains('"') || s.contains('\n') || s.contains('\r') {
        return Err(BuildError::BadArg(s.to_string()));
    }
    Ok(format!("\"{s}\""))
}

fn win(p: &str) -> String {
    p.replace('/', "\\")
}

/// Build the MXC request for an authorized run. `worker` is the host-installed worker binary; its
/// directory is the only extra read grant.
pub fn build_request(
    decision: &Decision,
    profile: &TaskProfile,
    worker: &Path,
    job: &Job,
) -> Result<ContainerRequest, BuildError> {
    let granted = match decision {
        Decision::Run { backend: Backend::Mxc, granted } => granted,
        _ => return Err(BuildError::NotRunOnMxc),
    };
    let mut readonly: Vec<String> = Vec::new();
    let mut readwrite: Vec<String> = Vec::new();
    for c in granted {
        match c {
            Capability::FsRead { path } => readonly.push(win(path)),
            Capability::FsWrite { path } => readwrite.push(win(path)),
            Capability::NetEgress { host } => return Err(BuildError::NetworkGrantUnsupported(host.clone())),
            Capability::Sidecar { .. } => {} // Gate 2; no effect on the worker request
        }
    }
    if let Some(dir) = worker.parent() {
        readonly.push(dir.to_string_lossy().into_owned());
    }
    let exe = quote(&worker.to_string_lossy())?;
    let command = match job {
        Job::Sum { input, output } => format!("{exe} sum {} {}", quote(input)?, quote(output)?),
        Job::TryRead { path } => format!("{exe} try-read {}", quote(path)?),
        Job::TryWrite { path } => format!("{exe} try-write {}", quote(path)?),
        Job::TryConnect { addr } => format!("{exe} try-connect {}", quote(addr)?),
        Job::Sleep { seconds } => format!("{exe} sleep {seconds}"),
    };
    Ok(ContainerRequest {
        timeout_ms: Some(profile.spec.timeout_seconds.saturating_mul(1000)),
        filesystem: Some(FilesystemPolicy {
            readonly_paths: readonly,
            readwrite_paths: readwrite,
            ..Default::default()
        }),
        network: Some(NetworkPolicy {
            egress: Some(NetworkEgressPolicy { default: Some(NetworkAction::Deny), ..Default::default() }),
            ingress: Some(NetworkIngressPolicy {
                default: Some(NetworkAction::Deny),
                host_loopback: Some(NetworkAction::Deny),
            }),
            runtime_config: None,
        }),
        containment: Containment::ProcessContainer(ProcessContainerConfig::default()),
        ..ContainerRequest::new(command)
    })
}

/// Run inside the container. Any SDK error is returned as-is: there is no fallback to another backend.
pub fn run(request: ContainerRequest) -> Result<ExecutionResult, v1::Error> {
    v1::run(request, Default::default())
}
