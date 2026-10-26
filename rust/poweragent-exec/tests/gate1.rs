//! Gate 1 adversarial tests. They run the real Windows processcontainer, so they are
//! Windows-only; elsewhere the file compiles to nothing and the gate is *not* claimed.
#![cfg(target_os = "windows")]

use mxc_sdk::v1::WaitResult;
use poweragent_exec::{build_request, run, BuildError, Job};
use poweragent_policy::{decide, AdminPolicy, Backend, Capability, Decision, Metadata, Probe, Spec, TaskProfile};
use std::{fs, net::TcpListener, path::PathBuf};

fn worker() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_poweragent-worker"))
}

struct Dirs {
    input: PathBuf,
    output: PathBuf,
    secret: PathBuf,
}

/// Fresh per-test directories under the cargo target dir (not %TEMP%).
fn dirs(name: &str) -> Dirs {
    let root = PathBuf::from(env!("CARGO_TARGET_TMPDIR")).join(name);
    let _ = fs::remove_dir_all(&root);
    let d = Dirs { input: root.join("in"), output: root.join("out"), secret: root.join("secret") };
    for p in [&d.input, &d.output, &d.secret] {
        fs::create_dir_all(p).unwrap();
    }
    fs::write(d.input.join("data.bin"), [1u8, 2, 3, 4, 250]).unwrap();
    fs::write(d.secret.join("secret.txt"), "top secret").unwrap();
    d
}

fn setup(d: &Dirs, timeout: u32, write: bool) -> (TaskProfile, Decision) {
    let mut caps = vec![Capability::FsRead { path: d.input.to_string_lossy().into() }];
    if write {
        caps.push(Capability::FsWrite { path: d.output.to_string_lossy().into() });
    }
    let profile = TaskProfile {
        api_version: "poweragent.dev/v1alpha1".into(),
        kind: "TaskProfile".into(),
        metadata: Metadata { name: "gate1".into() },
        spec: Spec { untrusted_code: true, capabilities: caps.clone(), timeout_seconds: timeout },
    };
    let policy = AdminPolicy { allowed_capabilities: caps.into_iter().collect(), ..Default::default() };
    let probe = Probe { mxc_available: true, mxc_supports_policy: true, ..Default::default() };
    let decision = decide(&profile, &policy, &probe);
    (profile, decision)
}

fn exec(d: &Dirs, timeout: u32, write: bool, job: Job) -> (WaitResult, String) {
    let (profile, decision) = setup(d, timeout, write);
    let req = build_request(&decision, &profile, &worker(), &job).expect("build");
    let out = run(req).expect("mxc run");
    (out.outcome, String::from_utf8_lossy(&out.stdout).into_owned())
}

fn p(dir: &PathBuf, f: &str) -> String {
    dir.join(f).to_string_lossy().into_owned()
}

#[test]
fn deterministic_worker_reads_ro_input_and_writes_only_to_output() {
    let d = dirs("det");
    let job = Job::Sum { input: p(&d.input, "data.bin"), output: p(&d.output, "sum.txt") };
    let (o1, s1) = exec(&d, 20, true, job.clone());
    assert_eq!(o1, WaitResult::Exited(0), "{s1}");
    assert_eq!(fs::read_to_string(d.output.join("sum.txt")).unwrap(), "260");
    let (o2, _) = exec(&d, 20, true, job);
    assert_eq!(o2, WaitResult::Exited(0));
    assert_eq!(fs::read_to_string(d.output.join("sum.txt")).unwrap(), "260", "deterministic");
}

#[test]
fn cannot_write_into_read_only_input() {
    let d = dirs("rowrite");
    let (o, s) = exec(&d, 20, true, Job::TryWrite { path: p(&d.input, "evil.txt") });
    assert_eq!(o, WaitResult::Exited(1), "{s}"); println!("CONTAINED: {s}");
    assert!(!d.input.join("evil.txt").exists());
}

#[test]
fn cannot_read_ungranted_directory() {
    let d = dirs("secret");
    let (o, s) = exec(&d, 20, true, Job::TryRead { path: p(&d.secret, "secret.txt") });
    assert_eq!(o, WaitResult::Exited(1), "{s}"); println!("CONTAINED: {s}");
    assert!(!s.contains("top secret"));
}

#[test]
fn cannot_write_ungranted_directory() {
    let d = dirs("secretw");
    let (o, s) = exec(&d, 20, true, Job::TryWrite { path: p(&d.secret, "evil.txt") });
    assert_eq!(o, WaitResult::Exited(1), "{s}"); println!("CONTAINED: {s}");
    assert!(!d.secret.join("evil.txt").exists());
}

#[test]
fn cannot_connect_to_host_loopback() {
    let d = dirs("net");
    let l = TcpListener::bind("127.0.0.1:0").unwrap();
    let addr = l.local_addr().unwrap().to_string();
    let (o, s) = exec(&d, 20, true, Job::TryConnect { addr });
    assert_eq!(o, WaitResult::Exited(1), "{s}"); println!("CONTAINED: {s}");
}

#[test]
fn cannot_connect_to_external_address() {
    let d = dirs("netext");
    let (o, s) = exec(&d, 20, true, Job::TryConnect { addr: "1.1.1.1:443".into() });
    assert_eq!(o, WaitResult::Exited(1), "{s}"); println!("CONTAINED: {s}");
}

#[test]
fn timeout_is_enforced() {
    let d = dirs("timeout");
    let start = std::time::Instant::now();
    let (o, _) = exec(&d, 3, true, Job::Sleep { seconds: 60 });
    assert_eq!(o, WaitResult::TimedOut);
    assert!(start.elapsed().as_secs() < 30);
}

#[test]
fn network_grant_is_never_translated() {
    let d = dirs("netgrant");
    let (mut profile, _) = setup(&d, 5, false);
    profile.spec.capabilities.push(Capability::NetEgress { host: "example.com".into() });
    let decision = Decision::Run { backend: Backend::Mxc, granted: profile.spec.capabilities.clone() };
    assert_eq!(
        build_request(&decision, &profile, &worker(), &Job::Sleep { seconds: 0 }).unwrap_err(),
        BuildError::NetworkGrantUnsupported("example.com".into())
    );
}

#[test]
fn deny_decision_never_builds_a_request() {
    let d = dirs("deny");
    let (profile, _) = setup(&d, 5, false);
    let deny = decide(&profile, &AdminPolicy::default(), &Probe::default());
    assert_eq!(
        build_request(&deny, &profile, &worker(), &Job::Sleep { seconds: 0 }).unwrap_err(),
        BuildError::NotRunOnMxc
    );
}
