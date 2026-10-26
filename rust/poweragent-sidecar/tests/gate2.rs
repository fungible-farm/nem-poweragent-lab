//! Gate 2 acceptance, table-style. Linux-provable per issue section 7 (no OS calls).
use poweragent_policy::{decide, AdminPolicy, Backend, Capability, Decision, Metadata, Probe, Spec, TaskProfile};
use poweragent_sidecar::*;

fn sc(name: &str) -> Capability {
    Capability::Sidecar { name: name.into() }
}
fn spec(name: &str, runtime: Runtime, deps: &[&str], requires: Vec<Capability>) -> SidecarSpec {
    SidecarSpec { name: name.into(), runtime, depends_on: deps.iter().map(|s| s.to_string()).collect(), requires, container: None }
}
fn registry() -> Registry {
    Registry::new(vec![
        spec("pandapower", Runtime::Podman, &[], vec![]),
        spec("powerio", Runtime::Podman, &["pandapower"], vec![]),
        spec("powerflow-solver-b", Runtime::Podman, &[], vec![]),
        spec("powerfactory-adapter", Runtime::Windows, &[], vec![Capability::FsRead { path: "C:/pf/projects".into() }]),
        spec("a", Runtime::Podman, &["b"], vec![]),
        spec("b", Runtime::Podman, &["a"], vec![]),
    ])
}
fn run_decision(caps: Vec<Capability>, policy_caps: Vec<Capability>) -> Decision {
    let profile = TaskProfile {
        api_version: "poweragent.dev/v1alpha1".into(),
        kind: "TaskProfile".into(),
        metadata: Metadata { name: "study".into() },
        spec: Spec { untrusted_code: false, capabilities: caps, timeout_seconds: 60 },
    };
    let policy = AdminPolicy { allowed_capabilities: policy_caps.into_iter().collect(), ..Default::default() };
    decide(&profile, &policy, &Probe { mxc_available: true, mxc_supports_policy: true, ..Default::default() })
}

#[test]
fn synthetic_nem_study_starts_only_the_two_solver_sidecars() {
    // powerio depends on pandapower, so the study asks for both; powerfactory is installed but stays off.
    let caps = vec![sc("pandapower"), sc("powerio")];
    let d = run_decision(caps.clone(), caps);
    let plan = resolve(&d, &registry()).unwrap();
    assert_eq!(plan, vec!["pandapower", "powerio"]); // dependency first
    let mut r = Reconciler::default();
    let actions = r.activate("study-1", &plan).unwrap();
    assert_eq!(actions, vec![Action::Start("pandapower".into()), Action::Start("powerio".into())]);
    assert!(!r.running().contains("powerfactory-adapter"));
}

#[test]
fn sidecar_cannot_increase_the_authorized_capability_set() {
    // The task is granted powerio but not its dependency: the resolver must not add pandapower.
    let d = run_decision(vec![sc("powerio")], vec![sc("powerio")]);
    match resolve(&d, &registry()) {
        Err(ResolveError::NotGranted { sidecar, missing }) => {
            assert_eq!(sidecar, "powerio");
            assert_eq!(missing, vec![sc("pandapower")]);
        }
        other => panic!("{other:?}"),
    }
}

#[test]
fn sidecar_requiring_an_ungranted_capability_is_rejected() {
    let d = run_decision(vec![sc("powerfactory-adapter")], vec![sc("powerfactory-adapter")]);
    assert!(matches!(resolve(&d, &registry()), Err(ResolveError::NotGranted { .. })));
}

#[test]
fn windows_capability_task_activates_the_approved_adapter() {
    let caps = vec![sc("powerfactory-adapter"), Capability::FsRead { path: "C:/pf/projects".into() }];
    let d = run_decision(caps.clone(), caps);
    let plan = resolve(&d, &registry()).unwrap();
    assert_eq!(plan, vec!["powerfactory-adapter"]);
}

#[test]
fn unapproved_sidecar_is_denied_before_resolution() {
    // Policy does not list the adapter: decide() denies, and resolve refuses a Deny.
    let d = run_decision(vec![sc("powerfactory-adapter")], vec![]);
    assert!(matches!(d, Decision::Deny { .. }));
    assert_eq!(resolve(&d, &registry()), Err(ResolveError::NotRunnable));
}

#[test]
fn disabling_the_adapter_blocks_activation_and_stops_it() {
    let caps = vec![sc("powerfactory-adapter"), Capability::FsRead { path: "C:/pf/projects".into() }];
    let plan = resolve(&run_decision(caps.clone(), caps), &registry()).unwrap();
    let mut r = Reconciler::default();
    r.activate("t1", &plan).unwrap();
    assert_eq!(r.revoke("powerfactory-adapter", Drain::Immediate), vec![Action::Stop("powerfactory-adapter".into())]);
    assert!(r.activate("t2", &plan).is_err(), "disabled sidecar must not activate");
    assert!(r.running().is_empty());
    r.restore("powerfactory-adapter");
    assert!(r.activate("t2", &plan).is_ok());
}

#[test]
fn reference_counting_stops_a_shared_sidecar_only_after_the_last_task() {
    let plan = vec!["pandapower".to_string()];
    let mut r = Reconciler::default();
    assert_eq!(r.activate("t1", &plan).unwrap(), vec![Action::Start("pandapower".into())]);
    assert_eq!(r.activate("t2", &plan).unwrap(), vec![], "already running: no second start");
    assert_eq!(r.release("t1", Drain::Immediate), vec![]);
    assert_eq!(r.release("t2", Drain::Immediate), vec![Action::Stop("pandapower".into())]);
    assert_eq!(r.release("t2", Drain::Immediate), vec![], "idempotent");
}

#[test]
fn stops_run_in_reverse_start_order() {
    let mut r = Reconciler::default();
    r.activate("t", &["pandapower".into(), "powerio".into()]).unwrap();
    assert_eq!(
        r.release("t", Drain::Immediate),
        vec![Action::Stop("powerio".into()), Action::Stop("pandapower".into())]
    );
}

#[test]
fn unknown_and_cyclic_sidecars_are_errors() {
    let d = run_decision(vec![sc("ghost")], vec![sc("ghost")]);
    assert_eq!(resolve(&d, &registry()), Err(ResolveError::Unknown("ghost".into())));
    let caps = vec![sc("a"), sc("b")];
    let d = run_decision(caps.clone(), caps);
    assert!(matches!(resolve(&d, &registry()), Err(ResolveError::Cycle(_))));
    let _ = Backend::Mxc;
}

#[test]
fn container_images_must_be_pinned_by_digest() {
    let ok = |image: &str| ContainerSpec { image: image.into(), command: vec![], memory_mb: 256, cpu_millis: 500, pids: 64 }.validate();
    let d = "a".repeat(64);
    assert!(ok(&format!("docker.io/library/alpine@sha256:{d}")).is_ok());
    for bad in ["alpine:3.20", "alpine:latest", "alpine", &format!("alpine@sha256:{}", "a".repeat(63)), &format!("-v@sha256:{d}"), &format!("a b@sha256:{d}")] {
        assert!(ok(bad).is_err(), "{bad}");
    }
    let no_limits = ContainerSpec { image: format!("x@sha256:{d}"), command: vec![], memory_mb: 0, cpu_millis: 500, pids: 64 };
    assert!(no_limits.validate().is_err());
}
