//! Table-driven fail-closed truth table for ADR-002 / SEC-002, 004, 010, 012.
use poweragent_policy::*;
use std::collections::BTreeSet;

fn cap(path: &str) -> Capability {
    Capability::FsRead { path: path.into() }
}

fn profile(untrusted: bool, caps: Vec<Capability>) -> TaskProfile {
    TaskProfile {
        api_version: API_VERSION.into(),
        kind: KIND.into(),
        metadata: Metadata { name: "t".into() },
        spec: Spec { untrusted_code: untrusted, capabilities: caps, timeout_seconds: 30 },
    }
}

fn policy(caps: &[Capability], fallbacks: &[Backend]) -> AdminPolicy {
    AdminPolicy {
        allowed_capabilities: caps.iter().cloned().collect(),
        allowed_fallbacks: fallbacks.iter().copied().collect(),
    }
}

fn probe(mxc: bool, supports: bool, fb: &[Backend]) -> Probe {
    Probe {
        mxc_available: mxc,
        mxc_supports_policy: supports,
        available_fallbacks: fb.iter().copied().collect::<BTreeSet<_>>(),
    }
}

#[test]
fn truth_table() {
    use Backend::*;
    let a = cap("C:/in");
    struct Row {
        name: &'static str,
        untrusted: bool,
        policy: AdminPolicy,
        probe: Probe,
        want: Option<Backend>, // None => must deny
    }
    let rows = vec![
        Row { name: "mxc healthy", untrusted: true, policy: policy(&[a.clone()], &[]), probe: probe(true, true, &[]), want: Some(Mxc) },
        Row { name: "untrusted, mxc absent, fallback allowed+available -> deny", untrusted: true, policy: policy(&[a.clone()], &[Jea]), probe: probe(false, false, &[Jea]), want: None },
        Row { name: "untrusted, mxc cannot enforce policy -> deny", untrusted: true, policy: policy(&[a.clone()], &[Jea]), probe: probe(true, false, &[Jea]), want: None },
        Row { name: "trusted, mxc absent, jea allowed+available", untrusted: false, policy: policy(&[a.clone()], &[Jea]), probe: probe(false, false, &[Jea]), want: Some(Jea) },
        Row { name: "trusted, mxc absent, jea available but NOT allowed -> deny", untrusted: false, policy: policy(&[a.clone()], &[]), probe: probe(false, false, &[Jea]), want: None },
        Row { name: "trusted, mxc absent, jea allowed but unavailable -> deny", untrusted: false, policy: policy(&[a.clone()], &[Jea]), probe: probe(false, false, &[]), want: None },
        Row { name: "fallback order: jea before windows_rs", untrusted: false, policy: policy(&[a.clone()], &[WindowsRs, Jea]), probe: probe(false, false, &[WindowsRs, Jea]), want: Some(Jea) },
        Row { name: "falls through to windows_rs when jea unavailable", untrusted: false, policy: policy(&[a.clone()], &[WindowsRs, Jea]), probe: probe(false, false, &[WindowsRs]), want: Some(WindowsRs) },
        Row { name: "nothing available -> deny", untrusted: false, policy: policy(&[a.clone()], &[Jea, WindowsRs, IsolatedVm]), probe: probe(false, false, &[]), want: None },
        Row { name: "default (empty) probe -> deny", untrusted: true, policy: policy(&[a.clone()], &[]), probe: Probe::default(), want: None },
    ];
    for r in rows {
        let d = decide(&profile(r.untrusted, vec![a.clone()]), &r.policy, &r.probe);
        match (r.want, &d) {
            (Some(b), Decision::Run { backend, .. }) => assert_eq!(b, *backend, "{}", r.name),
            (None, Decision::Deny { .. }) => {}
            _ => panic!("{}: got {:?}", r.name, d),
        }
    }
}

#[test]
fn unauthorized_capability_denied_even_with_healthy_mxc_and_fallbacks() {
    let d = decide(
        &profile(false, vec![cap("C:/secret")]),
        &policy(&[cap("C:/in")], &[Backend::Jea]),
        &probe(true, true, &[Backend::Jea]),
    );
    assert!(matches!(d, Decision::Deny { reason: DenyReason::CapabilityNotAuthorized { .. } }));
}

#[test]
fn authorization_failure_never_triggers_fallback() {
    let d = decide(
        &profile(false, vec![cap("C:/secret")]),
        &policy(&[], &[Backend::Jea]),
        &probe(false, false, &[Backend::Jea]),
    );
    assert!(matches!(d, Decision::Deny { reason: DenyReason::CapabilityNotAuthorized { .. } }));
}

#[test]
fn untrusted_without_mxc_reports_containment_unavailable() {
    let d = decide(&profile(true, vec![]), &policy(&[], &[Backend::Jea]), &Probe::default());
    assert_eq!(d, Decision::Deny { reason: DenyReason::ContainmentUnavailable });
}

#[test]
fn schema_rejects_bad_profiles() {
    let ok = r#"{"apiVersion":"poweragent.dev/v1alpha1","kind":"TaskProfile","metadata":{"name":"x"},
      "spec":{"untrustedCode":true,"capabilities":[{"kind":"fs_read","path":"C:/in"}],"timeoutSeconds":10}}"#;
    assert!(parse_profile(ok).is_ok());
    for (name, bad) in [
        ("wrong version", ok.replace("v1alpha1", "v2")),
        ("wrong kind", ok.replace("TaskProfile", "Other")),
        ("zero timeout", ok.replace("\"timeoutSeconds\":10", "\"timeoutSeconds\":0")),
        ("traversal", ok.replace("C:/in", "C:/in/../Windows")),
        ("unknown field", ok.replace("\"timeoutSeconds\":10", "\"timeoutSeconds\":10,\"exec\":\"cmd\"")),
        ("exec capability", ok.replace("fs_read", "run_command")),
    ] {
        assert!(parse_profile(&bad).is_err(), "{name} should be rejected");
    }
}
