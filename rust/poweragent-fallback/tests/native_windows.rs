//! Gate 3, native half: a real windows-rs call behind the same authorisation as the rule tests.
#![cfg(target_os = "windows")]
use poweragent_fallback::native::{execute, NativeError};
use poweragent_fallback::{Op, Refusal};
use poweragent_policy::*;

fn decision(backend: Backend, root: &str) -> Decision {
    Decision::Run { backend, granted: vec![Capability::FsRead { path: root.into() }] }
}
fn op(p: &str) -> Op { Op::NativeFileVersion { path: p.into() } }

#[test]
fn authorized_native_op_returns_a_real_version() {
    let d = decision(Backend::WindowsRs, "C:/Windows/System32");
    let v = execute(&d, &op("C:/Windows/System32/kernel32.dll")).unwrap();
    let parts: Vec<_> = v.split('.').collect();
    assert!(parts.len() == 4 && parts.iter().all(|x| x.parse::<u32>().is_ok()), "got {v}");
    assert!(parts[2].parse::<u32>().unwrap() >= 22000, "a Windows 11 system file: {v}");
}
#[test]
fn path_outside_the_grant_is_refused_without_touching_win32() {
    let d = decision(Backend::WindowsRs, "C:/Windows/System32");
    assert!(matches!(execute(&d, &op("C:/Windows/explorer.exe")), Err(NativeError::Refused(Refusal::PathNotGranted(_)))));
}
#[test]
fn decision_for_a_different_backend_is_refused() {
    let d = decision(Backend::Jea, "C:/Windows/System32");
    assert!(matches!(execute(&d, &op("C:/Windows/System32/kernel32.dll")), Err(NativeError::Refused(Refusal::DecisionDoesNotPermit { .. }))));
}
#[test]
fn a_deny_decision_runs_nothing() {
    let d = Decision::Deny { reason: DenyReason::NoPermittedBackend };
    assert!(execute(&d, &op("C:/Windows/System32/kernel32.dll")).is_err());
}
#[test]
fn missing_file_is_an_os_error_not_a_panic() {
    let d = decision(Backend::WindowsRs, "C:/Windows/System32");
    assert!(matches!(execute(&d, &op("C:/Windows/System32/nope-does-not-exist.dll")), Err(NativeError::Os(_))));
}
#[test]
fn jea_ops_are_not_served_by_the_native_adapter() {
    let d = decision(Backend::WindowsRs, "C:/Windows/System32");
    assert!(execute(&d, &Op::JeaListDirectory { path: "C:/Windows/System32".into() }).is_err());
}
