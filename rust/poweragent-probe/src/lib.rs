//! Gate 0 backend probe (issue #54). Read-only: it asks the pinned `mxc-sdk` which backends the
//! host can run and maps that to the policy crate's [`Probe`]. Anything not positively
//! established is reported as unsupported (SEC-010, fail closed).

use mxc_sdk::v1::AvailableBackend;
use poweragent_policy::{Capability, Probe, TaskProfile};
use serde::Serialize;

/// The MXC backend the issue prefers for native Windows execution (ADR-001).
pub const WINDOWS_BACKEND: &str = "processcontainer";

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Report {
    pub os: &'static str,
    pub backends: Vec<AvailableBackend>,
    /// Requirements of the supplied profile that the host cannot be shown to enforce.
    pub unsupported: Vec<String>,
    pub probe: Probe,
}

fn backend_name_for_os() -> &'static str {
    if cfg!(target_os = "windows") {
        WINDOWS_BACKEND
    } else {
        "bubblewrap"
    }
}

/// Map SDK facts and a profile to the policy probe. Pure; unit-tested with synthetic backends.
pub fn assess(os: &'static str, backends: Vec<AvailableBackend>, profile: Option<&TaskProfile>) -> Report {
    let wanted = backend_name_for_os();
    let mxc_available = backends.iter().any(|b| b.backend == wanted);

    let mut unsupported = Vec::new();
    if let Some(p) = profile {
        for c in &p.spec.capabilities {
            // Network enforcement is only proven by the Gate 1 adversarial tests, so it is not
            // claimed here. Filesystem and sidecar requests need no extra host capability.
            if let Capability::NetEgress { host } = c {
                unsupported.push(format!(
                    "net_egress {host}: egress enforcement is not verified until Gate 1"
                ));
            }
        }
    }
    let probe = Probe {
        mxc_available,
        mxc_supports_policy: mxc_available && unsupported.is_empty(),
        available_fallbacks: Default::default(),
    };
    Report { os, backends, unsupported, probe }
}

/// Probe the real host.
pub fn probe_host(profile: Option<&TaskProfile>) -> Report {
    assess(std::env::consts::OS, mxc_sdk::v1::available_backends(), profile)
}
