//! Phase 2 acceptance with REAL sidecars: MXC-contained worker plus Podman sidecars, on Windows.
//! Needs `cargo build -p poweragent-exec` and Podman with docker.io/library/alpine:3.20 present.
//! POWERAGENT_REQUIRE_PODMAN=1 turns a missing prerequisite into a failure instead of a skip.
#![cfg(target_os = "windows")]

use poweragent::{load_registry, open_bus, run_task, Outcome, RunArgs};
use poweragent_audit::verify;
use poweragent_exec::Job;
use poweragent_podman::{Podman, SidecarRuntime};
use poweragent_policy::{AdminPolicy, Capability, Metadata, Spec, TaskProfile};
use poweragent_sidecar::SidecarSpec;
use std::{cell::RefCell, fs, path::PathBuf, process::Command};

fn podman(args: &[&str]) -> Option<String> {
    let o = Command::new("podman.exe").args(args).output().ok()?;
    o.status.success().then(|| String::from_utf8_lossy(&o.stdout).trim().to_string())
}
fn image() -> Option<String> {
    let d = podman(&["image", "inspect", "docker.io/library/alpine:3.20", "--format", "{{.Digest}}"])?;
    d.starts_with("sha256:").then(|| format!("docker.io/library/alpine@{d}"))
}
fn worker() -> PathBuf {
    let w = std::env::current_exe().unwrap().parent().unwrap().parent().unwrap().join("poweragent-worker.exe");
    assert!(w.exists(), "build the worker first: cargo build -p poweragent-exec");
    w
}
fn sc(n: &str) -> Capability { Capability::Sidecar { name: n.into() } }

/// Wraps real Podman; records each start and checks the container is really running right after it.
struct Spy { inner: Podman, log: RefCell<Vec<String>> }
impl SidecarRuntime for Spy {
    fn start(&self, task: &str, spec: &SidecarSpec) -> Result<(), String> {
        self.inner.start(task, spec)?;
        let name = poweragent_podman::container_name(task, &spec.name)?;
        let running = podman(&["inspect", "--format", "{{.State.Running}}", &name]).as_deref() == Some("true");
        self.log.borrow_mut().push(format!("started:{}:running={running}", spec.name));
        Ok(())
    }
    fn stop(&self, task: &str, name: &str) -> Result<(), String> {
        self.log.borrow_mut().push(format!("stopped:{name}"));
        self.inner.stop(task, name)
    }
}
fn spy() -> Spy { Spy { inner: Podman::new("podman.exe"), log: RefCell::new(vec![]) } }

struct Case { task: String, input: PathBuf, output: PathBuf, audit: PathBuf }
fn case(task: &str) -> Case {
    let root = PathBuf::from(env!("CARGO_TARGET_TMPDIR")).join(format!("e2e-pod-{task}"));
    let _ = fs::remove_dir_all(&root);
    for d in ["in", "out"] { fs::create_dir_all(root.join(d)).unwrap(); }
    fs::write(root.join("in").join("data.bin"), [1u8, 2, 3, 4, 250]).unwrap();
    Case { task: task.into(), input: root.join("in"), output: root.join("out"), audit: root.join("audit.jsonl") }
}
fn registry(good: &str, powerio_image: &str) -> poweragent_sidecar::Registry {
    load_registry(&format!(r#"[
      {{"name":"pandapower","runtime":"podman","image":"{good}","command":["sleep","120"],"memoryMb":64,"pidsX":0}},
      {{"name":"powerio","runtime":"podman","dependsOn":["pandapower"],"image":"{powerio_image}","command":["sleep","120"],"memoryMb":64}}]"#)
        .replace(r#","pidsX":0"#, "")).unwrap()
}
fn args<'a>(c: &Case, reg: poweragent_sidecar::Registry, caps: Vec<Capability>, allowed: Vec<Capability>, rt: &'a dyn SidecarRuntime) -> RunArgs<'a> {
    RunArgs {
        task: c.task.clone(),
        profile: TaskProfile {
            api_version: "poweragent.dev/v1alpha1".into(), kind: "TaskProfile".into(),
            metadata: Metadata { name: c.task.clone() },
            spec: Spec { untrusted_code: true, capabilities: caps, timeout_seconds: 20 },
        },
        policy: AdminPolicy { allowed_capabilities: allowed.into_iter().collect(), ..Default::default() },
        registry: reg,
        job: Job::Sum { input: c.input.join("data.bin").to_string_lossy().into(), output: c.output.join("sum.txt").to_string_lossy().into() },
        worker: worker(),
        audit_path: c.audit.clone(),
        sidecars: rt,
    }
}
fn caps(c: &Case) -> Vec<Capability> {
    vec![Capability::FsRead { path: c.input.to_string_lossy().into() }, Capability::FsWrite { path: c.output.to_string_lossy().into() }, sc("pandapower"), sc("powerio")]
}
fn kinds(c: &Case) -> Vec<String> {
    fs::read_to_string(&c.audit).unwrap().lines()
        .map(|l| serde_json::from_str::<serde_json::Value>(l).unwrap()["event"]["kind"].as_str().unwrap().to_string()).collect()
}
fn leftovers(task: &str) -> String { podman(&["ps", "-a", "--filter", &format!("name=pa-{task}-"), "--format", "{{.Names}}"]).unwrap_or_default() }
fn prerequisites() -> Option<String> {
    let img = image();
    if img.is_none() {
        assert!(std::env::var("POWERAGENT_REQUIRE_PODMAN").as_deref() != Ok("1"), "podman or alpine:3.20 missing but POWERAGENT_REQUIRE_PODMAN=1");
        eprintln!("SKIPPED: podman or alpine:3.20 unavailable");
    }
    img
}

#[test]
fn only_the_required_sidecars_run_while_the_contained_worker_runs_then_stop() {
    let Some(img) = prerequisites() else { return };
    let c = case("podok");
    let rt = spy();
    let mut bus = open_bus(&c.audit).unwrap();
    let out = run_task(args(&c, registry(&img, &img), caps(&c), caps(&c), &rt), &mut bus).unwrap();
    assert_eq!(out, Outcome::Exited(0));
    assert_eq!(fs::read_to_string(c.output.join("sum.txt")).unwrap(), "260");
    assert_eq!(*rt.log.borrow(), ["started:pandapower:running=true", "started:powerio:running=true", "stopped:powerio", "stopped:pandapower"]);
    assert_eq!(kinds(&c), ["authorized", "sidecar_planned", "sidecar_started", "sidecar_planned", "sidecar_started", "sidecar_stopped", "sidecar_stopped", "finished"]);
    assert_eq!(leftovers(&c.task), "", "no sidecar container left behind");
    assert_eq!(verify(&c.audit).unwrap().0, 8);
}

#[test]
fn a_sidecar_that_fails_to_start_stops_the_ones_already_up_and_runs_nothing() {
    let Some(img) = prerequisites() else { return };
    let c = case("podfail");
    let missing = format!("docker.io/library/alpine@sha256:{}", "a".repeat(64)); // valid pin, not present locally; --pull never
    let rt = spy();
    let mut bus = open_bus(&c.audit).unwrap();
    let out = run_task(args(&c, registry(&img, &missing), caps(&c), caps(&c), &rt), &mut bus).unwrap();
    assert!(matches!(&out, Outcome::Denied(r) if r.contains("sidecar_start_failed")), "{out:?}");
    assert!(!c.output.join("sum.txt").exists(), "the worker must not run");
    assert_eq!(leftovers(&c.task), "", "pandapower was torn down");
    assert!(rt.log.borrow().contains(&"stopped:pandapower".to_string()));
}

#[test]
fn a_denied_task_starts_no_container_at_all() {
    let Some(img) = prerequisites() else { return };
    let c = case("poddeny");
    let rt = spy();
    let mut bus = open_bus(&c.audit).unwrap();
    let out = run_task(args(&c, registry(&img, &img), caps(&c), vec![], &rt), &mut bus).unwrap();
    assert!(matches!(out, Outcome::Denied(_)));
    assert!(rt.log.borrow().is_empty(), "{:?}", rt.log.borrow());
    assert_eq!(leftovers(&c.task), "");
}
