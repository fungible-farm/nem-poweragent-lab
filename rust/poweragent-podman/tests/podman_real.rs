//! Real Podman lifecycle. Skips (loudly) when Podman or the test image is absent, unless
//! POWERAGENT_REQUIRE_PODMAN=1, which the just recipe sets so a missing runtime is a failure.
use poweragent_podman::{container_name, Podman, SidecarRuntime};
use poweragent_sidecar::{ContainerSpec, Runtime, SidecarSpec};
use std::process::Command;

fn bin() -> String {
    std::env::var("POWERAGENT_PODMAN").unwrap_or_else(|_| if cfg!(windows) { "podman.exe".into() } else { "podman".into() })
}
fn podman(args: &[&str]) -> Option<String> {
    let o = Command::new(bin()).args(args).output().ok()?;
    o.status.success().then(|| String::from_utf8_lossy(&o.stdout).trim().to_string())
}
fn require() -> bool { std::env::var("POWERAGENT_REQUIRE_PODMAN").as_deref() == Ok("1") }

/// alpine:3.20 pinned by the digest Podman recorded when it was pulled.
fn image() -> Option<String> {
    let d = podman(&["image", "inspect", "docker.io/library/alpine:3.20", "--format", "{{.Digest}}"])?;
    d.starts_with("sha256:").then(|| format!("docker.io/library/alpine@{d}"))
}

struct Cleanup(Podman, String, String);
impl Drop for Cleanup {
    fn drop(&mut self) { let _ = self.0.stop(&self.1, &self.2); }
}

#[test]
fn start_inspect_idempotent_start_and_stop() {
    let Some(image) = image() else {
        assert!(!require(), "POWERAGENT_REQUIRE_PODMAN=1 but podman or docker.io/library/alpine:3.20 is unavailable");
        eprintln!("SKIPPED: podman or the alpine:3.20 image is unavailable");
        return;
    };
    let task = format!("t{}", std::process::id());
    let spec = SidecarSpec {
        name: "probe".into(), runtime: Runtime::Podman, depends_on: vec![], requires: vec![],
        container: Some(ContainerSpec { image, command: vec!["sleep".into(), "120".into()], memory_mb: 64, cpu_millis: 500, pids: 32 }),
    };
    let rt = Podman::new(bin());
    let _guard = Cleanup(Podman::new(bin()), task.clone(), "probe".into());
    let name = container_name(&task, "probe").unwrap();

    rt.start(&task, &spec).expect("start");
    assert_eq!(podman(&["inspect", "--format", "{{.State.Running}}", &name]).as_deref(), Some("true"));

    let info = podman(&["inspect", "--format", "json", &name]).expect("inspect");
    let v: serde_json::Value = serde_json::from_str(&info).unwrap();
    let c = &v[0];
    eprintln!("NetworkMode={} ReadonlyRootfs={} CapDrop={} Memory={} PidsLimit={} User={}", c["HostConfig"]["NetworkMode"], c["HostConfig"]["ReadonlyRootfs"], c["HostConfig"]["CapDrop"], c["HostConfig"]["Memory"], c["HostConfig"]["PidsLimit"], c["Config"]["User"]);
    assert_eq!(c["HostConfig"]["NetworkMode"], "none");
    assert_eq!(c["HostConfig"]["ReadonlyRootfs"], true);
    assert_eq!(c["HostConfig"]["Memory"], 64 * 1024 * 1024);
    assert_eq!(c["HostConfig"]["PidsLimit"], 32);
    // Podman expands `--cap-drop ALL` into its 11 default capabilities, so check what the process really holds.
    let probe = podman(&["exec", &name, "sh", "-c",
        "grep -E '^Cap(Eff|Bnd|Prm)' /proc/1/status; id -u; (touch /etc/x 2>&1 || echo ro-root); touch /work/ok && echo work-writable"]).expect("exec probe");
    eprintln!("INSIDE:
{probe}");
    for set in ["CapEff:	0000000000000000", "CapBnd:	0000000000000000", "CapPrm:	0000000000000000"] {
        assert!(probe.contains(set), "capability set not empty: {probe}");
    }
    assert!(probe.lines().any(|l| l == "65534"), "not running as the unprivileged user: {probe}");
    assert!(probe.contains("ro-root") || probe.contains("Read-only file system"), "root filesystem is writable: {probe}");
    assert!(probe.contains("work-writable"), "private tmpfs not writable: {probe}");
    assert_eq!(c["Config"]["Labels"]["poweragent.sidecar"], "probe");
    assert_eq!(c["Config"]["Labels"]["poweragent.task"], task.as_str());

    rt.start(&task, &spec).expect("second start is a no-op while running");
    let n = podman(&["ps", "--filter", &format!("name={name}"), "--format", "{{.Names}}"]).unwrap();
    assert_eq!(n.lines().count(), 1, "no duplicate container");

    rt.stop(&task, "probe").expect("stop");
    assert!(podman(&["container", "exists", &name]).is_none(), "container removed");
    rt.stop(&task, "probe").expect("stopping an absent sidecar succeeds");
}

#[test]
fn an_unpinned_image_never_reaches_podman() {
    let spec = SidecarSpec {
        name: "bad".into(), runtime: Runtime::Podman, depends_on: vec![], requires: vec![],
        container: Some(ContainerSpec { image: "alpine:3.20".into(), command: vec![], memory_mb: 64, cpu_millis: 500, pids: 32 }),
    };
    // A nonexistent binary proves validation fails first: a spawn attempt would give a different error.
    let err = Podman::new("definitely-not-a-real-binary").start("t1", &spec).unwrap_err();
    assert!(err.contains("not pinned"), "{err}");
}
