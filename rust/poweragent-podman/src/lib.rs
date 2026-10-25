//! Sidecar runtime for Podman (FR-001, FR-002, FR-005; SEC-005, SEC-009). It acts on a
//! [`SidecarSpec`] from the administrator-installed registry and nothing else: there is no field
//! through which a task or an agent can supply an image, a flag or a command. Every container is
//! started detached with no network, a read-only root, a small private tmpfs for state, all
//! capabilities dropped, no privilege escalation, an unprivileged user, and memory/CPU/PID limits.
//! Images must already be present and are never pulled implicitly (`--pull never`).

use poweragent_sidecar::{ContainerSpec, Runtime, SidecarSpec};
use std::process::Command;

/// Starts and stops the sidecars a reconciler planned.
pub trait SidecarRuntime {
    fn start(&self, task: &str, spec: &SidecarSpec) -> Result<(), String>;
    /// Idempotent: stopping something that is not running succeeds.
    fn stop(&self, task: &str, name: &str) -> Result<(), String>;
    /// False when `start` launches nothing, so callers must not audit a start or stop as having happened.
    fn launches(&self) -> bool {
        true
    }
}

/// Launches nothing. Used when no container runtime is wanted or available.
pub struct PlannedOnly;
impl SidecarRuntime for PlannedOnly {
    fn start(&self, _: &str, _: &SidecarSpec) -> Result<(), String> {
        Ok(())
    }
    fn stop(&self, _: &str, _: &str) -> Result<(), String> {
        Ok(())
    }
    fn launches(&self) -> bool {
        false
    }
}

/// `[a-z0-9-]` only, so a name can never be an option or a path. Anything else is an error, not
/// silently rewritten.
fn part(kind: &str, s: &str) -> Result<(), String> {
    if s.is_empty() || s.len() > 40 || s.starts_with('-') || !s.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-') {
        return Err(format!("{kind} {s:?} must be 1-40 chars of [a-z0-9-] and not start with '-'"));
    }
    Ok(())
}

pub fn container_name(task: &str, sidecar: &str) -> Result<String, String> {
    part("task", task)?;
    part("sidecar", sidecar)?;
    Ok(format!("pa-{task}-{sidecar}"))
}

/// The complete `podman run` argument vector (without the binary). Pure, so it is unit-tested.
pub fn run_args(task: &str, spec: &SidecarSpec) -> Result<Vec<String>, String> {
    if spec.runtime != Runtime::Podman {
        return Err(format!("sidecar {:?} is not a Podman sidecar", spec.name));
    }
    let c: &ContainerSpec = spec.container.as_ref().ok_or_else(|| format!("sidecar {:?} has no container spec", spec.name))?;
    c.validate()?;
    let name = container_name(task, &spec.name)?;
    let mut a: Vec<String> = [
        "run", "--detach", "--rm", "--pull", "never",
        "--name", &name,
        "--label", &format!("poweragent.task={task}"),
        "--label", &format!("poweragent.sidecar={}", spec.name),
        "--network", "none",
        "--read-only",
        "--tmpfs", "/work:rw,noexec,nosuid,nodev,size=64m",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--user", "65534:65534",
        "--memory", &format!("{}m", c.memory_mb),
        "--cpus", &format!("{}.{:03}", c.cpu_millis / 1000, c.cpu_millis % 1000),
        "--pids-limit", &c.pids.to_string(),
    ]
    .iter()
    .map(|s| s.to_string())
    .collect();
    a.push(c.image.clone());
    a.extend(c.command.iter().cloned());
    Ok(a)
}

/// Real Podman. `bin` is chosen by the host installer (e.g. `podman` or `podman.exe`).
pub struct Podman {
    pub bin: String,
}

impl Podman {
    pub fn new(bin: impl Into<String>) -> Self {
        Podman { bin: bin.into() }
    }
    fn run(&self, args: &[String]) -> Result<std::process::Output, String> {
        Command::new(&self.bin).args(args).output().map_err(|e| format!("{}: {e}", self.bin))
    }
    fn s(v: &[&str]) -> Vec<String> {
        v.iter().map(|x| x.to_string()).collect()
    }
    /// (task, sidecar) of every running container this runtime started, found by its labels.
    pub fn list_running(&self) -> Result<Vec<(String, String)>, String> {
        let o = self.run(&Self::s(&[
            "ps", "--filter", "label=poweragent.sidecar", "--filter", "status=running",
            "--format", "{{.Label \"poweragent.task\"}}\t{{.Label \"poweragent.sidecar\"}}",
        ]))?;
        if !o.status.success() {
            return Err(format!("podman ps failed: {}", String::from_utf8_lossy(&o.stderr).trim()));
        }
        Ok(String::from_utf8_lossy(&o.stdout)
            .lines()
            .filter_map(|l| l.split_once('\t'))
            .filter(|(t, n)| container_name(t.trim(), n.trim()).is_ok())
            .map(|(t, n)| (t.trim().to_string(), n.trim().to_string()))
            .collect())
    }
    fn exists(&self, name: &str) -> Result<bool, String> {
        Ok(self.run(&Self::s(&["container", "exists", name]))?.status.success())
    }
    fn running(&self, name: &str) -> Result<bool, String> {
        let o = self.run(&Self::s(&["inspect", "--format", "{{.State.Running}}", name]))?;
        Ok(o.status.success() && String::from_utf8_lossy(&o.stdout).trim() == "true")
    }
}

impl SidecarRuntime for Podman {
    fn start(&self, task: &str, spec: &SidecarSpec) -> Result<(), String> {
        let args = run_args(task, spec)?; // validates everything before any process is spawned
        let name = container_name(task, &spec.name)?;
        if self.exists(&name)? {
            if self.running(&name)? {
                return Ok(());
            }
            self.run(&Self::s(&["rm", "-f", &name]))?;
        }
        let o = self.run(&args)?;
        if o.status.success() {
            Ok(())
        } else {
            Err(format!("podman run failed for {:?}: {}", spec.name, String::from_utf8_lossy(&o.stderr).trim()))
        }
    }

    fn stop(&self, task: &str, name: &str) -> Result<(), String> {
        let cname = container_name(task, name)?;
        if !self.exists(&cname)? {
            return Ok(());
        }
        let o = self.run(&Self::s(&["rm", "--force", "--time", "5", &cname]))?;
        if o.status.success() || !self.exists(&cname)? {
            Ok(())
        } else {
            Err(format!("podman rm failed for {name:?}: {}", String::from_utf8_lossy(&o.stderr).trim()))
        }
    }
}
