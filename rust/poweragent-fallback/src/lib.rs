//! Gate 3 rule logic (issue #54). Agent-facing requests are a *closed* set of typed operations
//! (FR-008, FR-009, SEC-004). There is no script, command line or executable-path field anywhere, so
//! "run this PowerShell" cannot even be expressed; unknown fields and unknown ops fail to parse.
//! An operation is authorised only if the ADR-002 decision selected the matching fallback backend
//! and the path it touches is inside a granted `FsRead` root.

use poweragent_policy::{Backend, Capability, Decision};
use serde::Deserialize;

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum Op {
    /// Served by the JEA endpoint (constrained language, allowlisted command, fixed parameters).
    JeaListDirectory { path: String },
    /// Served by the windows-rs adapter (typed Win32 call, no process spawn).
    NativeFileVersion { path: String },
}

impl Op {
    fn backend(&self) -> Backend {
        match self {
            Op::JeaListDirectory { .. } => Backend::Jea,
            Op::NativeFileVersion { .. } => Backend::WindowsRs,
        }
    }
    fn path(&self) -> &str {
        match self {
            Op::JeaListDirectory { path } | Op::NativeFileVersion { path } => path,
        }
    }
}

#[derive(Debug, PartialEq, Eq)]
pub enum Refusal {
    Unparseable(String),
    DecisionDoesNotPermit { wanted: Backend },
    PathNotGranted(String),
}

pub fn parse_op(json: &str) -> Result<Op, Refusal> {
    serde_json::from_str(json).map_err(|e| Refusal::Unparseable(e.to_string()))
}

fn norm(p: &str) -> String {
    p.replace('\\', "/").trim_end_matches('/').to_lowercase()
}

fn inside(root: &str, path: &str) -> bool {
    let (r, p) = (norm(root), norm(path));
    !p.split('/').any(|s| s == "..") && (p == r || p.starts_with(&format!("{r}/")))
}

/// Authorise one operation against the decision for its task.
pub fn authorize(decision: &Decision, op: &Op) -> Result<(), Refusal> {
    let (backend, granted) = match decision {
        Decision::Run { backend, granted } => (*backend, granted),
        Decision::Deny { .. } => return Err(Refusal::DecisionDoesNotPermit { wanted: op.backend() }),
    };
    if backend != op.backend() {
        return Err(Refusal::DecisionDoesNotPermit { wanted: op.backend() });
    }
    let ok = granted.iter().any(|c| matches!(c, Capability::FsRead { path } if inside(path, op.path())));
    if ok { Ok(()) } else { Err(Refusal::PathNotGranted(op.path().to_string())) }
}

#[cfg(windows)]
pub mod native;
