//! Pure argument-vector tests; run in the Linux sandbox. They prove what we *ask* Podman to do.
use poweragent_podman::{container_name, run_args};
use poweragent_sidecar::{ContainerSpec, Runtime, SidecarSpec};

fn digest() -> String { "b".repeat(64) }
fn spec(cmd: &[&str]) -> SidecarSpec {
    SidecarSpec {
        name: "pandapower".into(), runtime: Runtime::Podman, depends_on: vec![], requires: vec![],
        container: Some(ContainerSpec {
            image: format!("registry.example/pp@sha256:{}", digest()),
            command: cmd.iter().map(|s| s.to_string()).collect(),
            memory_mb: 256, cpu_millis: 500, pids: 64,
        }),
    }
}
fn has_pair(a: &[String], k: &str, v: &str) -> bool { a.windows(2).any(|w| w[0] == k && w[1] == v) }

#[test]
fn every_hardening_flag_is_present() {
    let a = run_args("study-1", &spec(&["serve"])).unwrap();
    assert_eq!(a[0], "run");
    for flag in ["--detach", "--rm", "--read-only"] { assert!(a.contains(&flag.to_string()), "{flag}"); }
    assert!(has_pair(&a, "--network", "none"));
    assert!(has_pair(&a, "--cap-drop", "ALL"));
    assert!(has_pair(&a, "--security-opt", "no-new-privileges"));
    assert!(has_pair(&a, "--user", "65534:65534"));
    assert!(has_pair(&a, "--pull", "never"));
    assert!(has_pair(&a, "--memory", "256m"));
    assert!(has_pair(&a, "--cpus", "0.500"));
    assert!(has_pair(&a, "--pids-limit", "64"));
    assert!(has_pair(&a, "--name", "pa-study-1-pandapower"));
    assert!(has_pair(&a, "--label", "poweragent.sidecar=pandapower"));
    assert!(a.iter().any(|x| x.starts_with("/work:rw,noexec,nosuid,nodev")));
}

#[test]
fn nothing_that_widens_access_can_appear() {
    let a = run_args("t", &spec(&[])).unwrap().join(" ");
    for bad in ["--privileged", "--net host", "--network host", "--volume", " -v ", "--mount", "--device", "--pid host", "--userns", "--cap-add", "--security-opt seccomp=unconfined"] {
        assert!(!a.contains(bad), "{bad} in {a}");
    }
}

#[test]
fn image_then_fixed_command_come_last_in_that_order() {
    let a = run_args("t", &spec(&["serve", "--port", "8080"])).unwrap();
    let n = a.len();
    assert!(a[n - 4].ends_with(&format!("@sha256:{}", digest())));
    assert_eq!(&a[n - 3..], ["serve", "--port", "8080"]);
}

#[test]
fn unpinned_or_unregistered_sidecars_never_produce_args() {
    let mut s = spec(&[]);
    s.container.as_mut().unwrap().image = "alpine:3.20".into();
    assert!(run_args("t", &s).is_err());
    let mut w = spec(&[]);
    w.runtime = Runtime::Windows;
    assert!(run_args("t", &w).is_err());
    let mut n = spec(&[]);
    n.container = None;
    assert!(run_args("t", &n).is_err());
}

#[test]
fn names_that_could_act_as_options_or_paths_are_rejected() {
    for bad in ["", "-rf", "a b", "../x", "UPPER", "a/b", "a;b", "x\n", &"a".repeat(41)] {
        assert!(container_name(bad, "ok").is_err(), "task {bad:?}");
        assert!(container_name("ok", bad).is_err(), "sidecar {bad:?}");
    }
    assert_eq!(container_name("study-1", "powerio").unwrap(), "pa-study-1-powerio");
}
