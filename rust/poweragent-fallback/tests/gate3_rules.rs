//! Gate 3 rule-level proof (Linux-provable). The JEA endpoint and windows-rs adapter themselves, and the
//! interactive-session COM case, still need the real Windows machine; nothing here claims them.
use poweragent_fallback::*;
use poweragent_policy::*;
use std::collections::BTreeSet;

fn fs_read(p: &str) -> Capability { Capability::FsRead { path: p.into() } }
fn profile(untrusted: bool) -> TaskProfile {
    TaskProfile {
        api_version: "poweragent.dev/v1alpha1".into(), kind: "TaskProfile".into(),
        metadata: Metadata { name: "t".into() },
        spec: Spec { untrusted_code: untrusted, capabilities: vec![fs_read("C:/pf")], timeout_seconds: 30 },
    }
}
fn policy(fallbacks: &[Backend]) -> AdminPolicy {
    AdminPolicy { allowed_capabilities: [fs_read("C:/pf")].into_iter().collect(), allowed_fallbacks: fallbacks.iter().copied().collect() }
}
fn no_mxc(avail: &[Backend]) -> Probe {
    Probe { mxc_available: false, mxc_supports_policy: false, available_fallbacks: avail.iter().copied().collect::<BTreeSet<_>>() }
}

#[test]
fn one_authorized_jea_op_and_one_authorized_native_op_succeed() {
    let jea = decide(&profile(false), &policy(&[Backend::Jea]), &no_mxc(&[Backend::Jea]));
    let op = parse_op(r#"{"op":"jea_list_directory","path":"C:\\pf\\projects"}"#).unwrap();
    assert_eq!(authorize(&jea, &op), Ok(()));
    let native = decide(&profile(false), &policy(&[Backend::WindowsRs]), &no_mxc(&[Backend::WindowsRs]));
    let op = parse_op(r#"{"op":"native_file_version","path":"C:/pf/app.exe"}"#).unwrap();
    assert_eq!(authorize(&native, &op), Ok(()));
}

#[test]
fn arbitrary_powershell_and_process_invocation_cannot_be_expressed() {
    for bad in [
        r#"{"op":"run_powershell","script":"Get-Process"}"#,
        r#"{"op":"jea_list_directory","path":"C:/pf","script":"calc"}"#,
        r#"{"op":"native_file_version","path":"C:/pf/a.exe","exe":"C:/Windows/System32/cmd.exe"}"#,
        r#"{"op":"exec","command":"cmd /c whoami"}"#,
        r#"{"command":"powershell -enc AAAA"}"#,
    ] {
        assert!(matches!(parse_op(bad), Err(Refusal::Unparseable(_))), "{bad}");
    }
}

#[test]
fn path_outside_the_granted_root_or_with_traversal_is_refused() {
    let d = decide(&profile(false), &policy(&[Backend::Jea]), &no_mxc(&[Backend::Jea]));
    for path in ["C:/Windows/System32", "C:/pf/../Windows", "C:/pfx/other", "D:/pf"] {
        let op = Op::JeaListDirectory { path: path.into() };
        assert!(matches!(authorize(&d, &op), Err(Refusal::PathNotGranted(_))), "{path}");
    }
}

#[test]
fn mxc_unavailable_never_silently_expands_privilege() {
    // Untrusted code: no fallback at all, even though JEA is listed and available.
    let d = decide(&profile(true), &policy(&[Backend::Jea]), &no_mxc(&[Backend::Jea]));
    assert!(matches!(d, Decision::Deny { reason: DenyReason::ContainmentUnavailable }));
    assert!(authorize(&d, &Op::JeaListDirectory { path: "C:/pf".into() }).is_err());
    // Trusted task, but the administrator did not list a fallback: deny.
    let d = decide(&profile(false), &policy(&[]), &no_mxc(&[Backend::Jea, Backend::WindowsRs]));
    assert!(matches!(d, Decision::Deny { reason: DenyReason::NoPermittedBackend }));
}

#[test]
fn an_op_cannot_borrow_a_different_backend_than_the_decision_selected() {
    let jea = decide(&profile(false), &policy(&[Backend::Jea]), &no_mxc(&[Backend::Jea]));
    let native_op = Op::NativeFileVersion { path: "C:/pf/a.exe".into() };
    assert_eq!(authorize(&jea, &native_op), Err(Refusal::DecisionDoesNotPermit { wanted: Backend::WindowsRs }));
}

#[test]
fn failed_authorization_does_not_fall_back() {
    // Capability not in policy: denied as unauthorized, not routed to JEA even though JEA is allowed.
    let mut p = profile(false);
    p.spec.capabilities.push(fs_read("C:/secret"));
    let d = decide(&p, &policy(&[Backend::Jea]), &no_mxc(&[Backend::Jea]));
    assert!(matches!(d, Decision::Deny { reason: DenyReason::CapabilityNotAuthorized { .. } }));
}
