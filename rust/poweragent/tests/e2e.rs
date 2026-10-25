//! End-to-end acceptance on the real Windows backend (issue #54 section 9). Needs the worker
//! built first: `cargo build -p poweragent-exec` (the just recipe does this).
#![cfg(target_os = "windows")]

use poweragent::{load_registry, open_bus, run_task, Outcome, RunArgs};
use poweragent_audit::verify;
use poweragent_exec::Job;
use poweragent_policy::{AdminPolicy, Capability, Metadata, Spec, TaskProfile};
use std::{fs, path::PathBuf};

const REGISTRY: &str = r#"[
 {"name":"pandapower","runtime":"podman"},
 {"name":"powerio","runtime":"podman","dependsOn":["pandapower"]},
 {"name":"powerfactory-adapter","runtime":"windows"}]"#;

fn worker() -> PathBuf {
    let exe = std::env::current_exe().unwrap();
    let w = exe.parent().unwrap().parent().unwrap().join("poweragent-worker.exe");
    assert!(w.exists(), "build the worker first: cargo build -p poweragent-exec ({})", w.display());
    w
}
fn sc(n: &str) -> Capability { Capability::Sidecar { name: n.into() } }

struct Case { root: PathBuf, input: PathBuf, output: PathBuf, audit: PathBuf }
fn case(name: &str) -> Case {
    let root = PathBuf::from(env!("CARGO_TARGET_TMPDIR")).join(format!("e2e-{name}"));
    let _ = fs::remove_dir_all(&root);
    for d in ["in", "out"] { fs::create_dir_all(root.join(d)).unwrap(); }
    fs::write(root.join("in").join("data.bin"), [1u8, 2, 3, 4, 250]).unwrap();
    Case { input: root.join("in"), output: root.join("out"), audit: root.join("audit.jsonl"), root }
}
fn args(c: &Case, caps: Vec<Capability>, allowed: Vec<Capability>) -> RunArgs<'_> {
    RunArgs {
        task: "study".into(),
        profile: TaskProfile {
            api_version: "poweragent.dev/v1alpha1".into(), kind: "TaskProfile".into(),
            metadata: Metadata { name: "study".into() },
            spec: Spec { untrusted_code: true, capabilities: caps, timeout_seconds: 20 },
        },
        policy: AdminPolicy { allowed_capabilities: allowed.into_iter().collect(), ..Default::default() },
        registry: load_registry(REGISTRY).unwrap(),
        job: Job::Sum {
            input: c.input.join("data.bin").to_string_lossy().into(),
            output: c.output.join("sum.txt").to_string_lossy().into(),
        },
        worker: worker(),
        audit_path: c.audit.clone(),
        sidecars: &poweragent_podman::PlannedOnly,
    }
}
fn granted(c: &Case) -> Vec<Capability> {
    vec![
        Capability::FsRead { path: c.input.to_string_lossy().into() },
        Capability::FsWrite { path: c.output.to_string_lossy().into() },
        sc("pandapower"), sc("powerio"),
    ]
}
fn kinds(c: &Case) -> Vec<String> {
    fs::read_to_string(&c.audit).unwrap().lines()
        .map(|l| { let v: serde_json::Value = serde_json::from_str(l).unwrap(); v["event"]["kind"].as_str().unwrap().to_string() })
        .collect()
}

#[test]
fn authorised_task_runs_contained_with_only_required_sidecars_and_full_audit() {
    let c = case("happy");
    let g = granted(&c);
    let mut bus = open_bus(&c.audit).unwrap();
    let out = run_task(args(&c, g.clone(), g), &mut bus).unwrap();
    assert_eq!(out, Outcome::Exited(0));
    assert_eq!(fs::read_to_string(c.output.join("sum.txt")).unwrap(), "260");
    assert_eq!(kinds(&c), ["authorized", "sidecar_planned", "sidecar_planned", "finished"]);
    assert!(!fs::read_to_string(&c.audit).unwrap().contains("powerfactory"), "unrequested sidecar stays off");
    assert_eq!(verify(&c.audit).unwrap().0, 4);
    let _ = &c.root;
}

#[test]
fn unauthorised_capability_is_denied_before_anything_runs() {
    let c = case("deny");
    let mut bus = open_bus(&c.audit).unwrap();
    let out = run_task(args(&c, granted(&c), vec![]), &mut bus).unwrap();
    assert!(matches!(out, Outcome::Denied(_)));
    assert!(!c.output.join("sum.txt").exists());
    assert_eq!(kinds(&c), ["denied"]);
}

#[test]
fn network_request_is_denied_not_run_uncontained() {
    let c = case("net");
    let mut g = granted(&c);
    g.push(Capability::NetEgress { host: "example.com".into() });
    let mut bus = open_bus(&c.audit).unwrap();
    let out = run_task(args(&c, g.clone(), g), &mut bus).unwrap();
    assert!(matches!(out, Outcome::Denied(_)));
    assert!(!c.output.join("sum.txt").exists());
}

#[test]
fn sidecar_missing_its_dependency_grant_is_denied() {
    let c = case("dep");
    let g = vec![
        Capability::FsRead { path: c.input.to_string_lossy().into() },
        Capability::FsWrite { path: c.output.to_string_lossy().into() },
        sc("powerio"), // depends on pandapower, which is not granted
    ];
    let mut bus = open_bus(&c.audit).unwrap();
    let out = run_task(args(&c, g.clone(), g), &mut bus).unwrap();
    assert!(matches!(out, Outcome::Denied(r) if r.contains("sidecar_resolution")));
    assert!(!c.output.join("sum.txt").exists());
}

#[test]
fn dashboard_on_or_killed_gives_the_same_result_and_audit() {
    let (a, b) = (case("dash-on"), case("dash-off"));
    let ga = granted(&a);
    let mut bus_a = open_bus(&a.audit).unwrap();
    let rx = bus_a.subscribe(16);
    assert_eq!(run_task(args(&a, ga.clone(), ga), &mut bus_a).unwrap(), Outcome::Exited(0));
    assert_eq!(rx.try_iter().count(), 4);

    let gb = granted(&b);
    let mut bus_b = open_bus(&b.audit).unwrap();
    drop(bus_b.subscribe(1)); // dashboard dead before the run starts
    assert_eq!(run_task(args(&b, gb.clone(), gb), &mut bus_b).unwrap(), Outcome::Exited(0));

    assert_eq!(fs::read_to_string(a.output.join("sum.txt")).unwrap(), fs::read_to_string(b.output.join("sum.txt")).unwrap());
    // Paths differ per case, so compare the event kinds and the chain length, not the hashes.
    assert_eq!(kinds(&a), kinds(&b));
    assert_eq!(verify(&a.audit).unwrap().0, verify(&b.audit).unwrap().0);
}
