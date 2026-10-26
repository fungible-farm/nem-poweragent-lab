use mxc_sdk::v1::AvailableBackend;
use poweragent_policy::parse_profile;
use poweragent_probe::{assess, WINDOWS_BACKEND};

fn backend(name: &str) -> AvailableBackend {
    AvailableBackend { backend: name.into(), tier: None, capabilities: vec![], warnings: vec![] }
}
fn host_backend() -> &'static str {
    if cfg!(target_os = "windows") { WINDOWS_BACKEND } else { "bubblewrap" }
}
const FS_ONLY: &str = r#"{"apiVersion":"poweragent.dev/v1alpha1","kind":"TaskProfile","metadata":{"name":"t"},
 "spec":{"untrustedCode":true,"timeoutSeconds":5,"capabilities":[{"kind":"fs_read","path":"C:/in"}]}}"#;
const NET: &str = r#"{"apiVersion":"poweragent.dev/v1alpha1","kind":"TaskProfile","metadata":{"name":"t"},
 "spec":{"untrustedCode":true,"timeoutSeconds":5,"capabilities":[{"kind":"net_egress","host":"example.com"}]}}"#;

#[test]
fn no_backends_means_mxc_unavailable() {
    let r = assess("test", vec![], None);
    assert!(!r.probe.mxc_available && !r.probe.mxc_supports_policy);
}
#[test]
fn unrelated_backend_is_not_mxc() {
    let r = assess("test", vec![backend("lxc")], None);
    assert!(!r.probe.mxc_available);
}
#[test]
fn host_backend_present_supports_fs_only_profile() {
    let p = parse_profile(FS_ONLY).unwrap();
    let r = assess("test", vec![backend(host_backend())], Some(&p));
    assert!(r.probe.mxc_available && r.probe.mxc_supports_policy && r.unsupported.is_empty());
}
#[test]
fn network_request_is_reported_unsupported_and_fails_closed() {
    let p = parse_profile(NET).unwrap();
    let r = assess("test", vec![backend(host_backend())], Some(&p));
    assert!(r.probe.mxc_available && !r.probe.mxc_supports_policy);
    assert_eq!(r.unsupported.len(), 1);
}
