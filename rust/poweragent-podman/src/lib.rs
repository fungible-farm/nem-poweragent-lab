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

/// Facts read back from an existing container.
struct Found {
    task: String,
    sidecar: String,
    images: [String; 2],
    network: String,
    read_only: bool,
    user: String,
    memory: u64,
    pids: u64,
    nano_cpus: u64,
    running: bool,
}

impl Found {
    /// Started by PowerAgent for this task and sidecar (by label)?
    fn owned_by(&self, task: &str, sidecar: &str) -> bool {
        self.task == task && self.sidecar == sidecar
    }
    /// Everything the hardened `run_args` asked for, read back. A container that merely has the right name or labels
    /// but a different image or weaker configuration does not match.
    fn matches(&self, c: &ContainerSpec) -> Result<(), String> {
        let mut bad = Vec::new();
        if !self.images.iter().any(|i| *i == c.image) {
            bad.push(format!("image {:?} is not the registered {:?}", self.images, c.image));
        }
        if self.network != "none" {
            bad.push(format!("network mode {:?}, wanted none", self.network));
        }
        if !self.read_only {
            bad.push("root filesystem is writable".into());
        }
        if self.user != "65534:65534" {
            bad.push(format!("user {:?}, wanted 65534:65534", self.user));
        }
        if self.memory != u64::from(c.memory_mb) * 1024 * 1024 {
            bad.push(format!("memory limit {} differs", self.memory));
        }
        if self.pids != u64::from(c.pids) {
            bad.push(format!("pids limit {} differs", self.pids));
        }
        if self.nano_cpus != u64::from(c.cpu_millis) * 1_000_000 {
            bad.push(format!("cpu limit {} differs", self.nano_cpus));
        }
        if bad.is_empty() { Ok(()) } else { Err(bad.join("; ")) }
    }
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
    /// What an existing container with this name actually is. `None` if there is none.
    fn inspect(&self, name: &str) -> Result<Option<Found>, String> {
        if !self.exists(name)? {
            return Ok(None);
        }
        let fmt = "{{index .Config.Labels \"poweragent.task\"}}|{{index .Config.Labels \"poweragent.sidecar\"}}|{{.ImageName}}|{{.Config.Image}}|{{.HostConfig.NetworkMode}}|{{.HostConfig.ReadonlyRootfs}}|{{.Config.User}}|{{.HostConfig.Memory}}|{{.HostConfig.PidsLimit}}|{{.HostConfig.NanoCpus}}|{{.State.Running}}";
        let o = self.run(&Self::s(&["inspect", "--format", fmt, name]))?;
        if !o.status.success() {
            return Err(format!("podman inspect {name} failed: {}", String::from_utf8_lossy(&o.stderr).trim()));
        }
        let text = String::from_utf8_lossy(&o.stdout).trim().to_string();
        let f: Vec<&str> = text.split('|').collect();
        if f.len() != 11 {
            return Err(format!("unexpected inspect output for {name}: {text:?}"));
        }
        let n = |x: &str| x.trim().parse::<u64>().unwrap_or(u64::MAX);
        Ok(Some(Found {
            task: f[0].trim().to_string(),
            sidecar: f[1].trim().to_string(),
            images: [f[2].trim().to_string(), f[3].trim().to_string()],
            network: f[4].trim().to_string(),
            read_only: f[5].trim() == "true",
            user: f[6].trim().to_string(),
            memory: n(f[7]),
            pids: n(f[8]),
            nano_cpus: n(f[9]),
            running: f[10].trim() == "true",
        }))
    }
    fn exists(&self, name: &str) -> Result<bool, String> {
        Ok(self.run(&Self::s(&["container", "exists", name]))?.status.success())
    }
}

impl SidecarRuntime for Podman {
    fn start(&self, task: &str, spec: &SidecarSpec) -> Result<(), String> {
        let args = run_args(task, spec)?; // validates everything before any process is spawned
        let name = container_name(task, &spec.name)?;
        let c = spec.container.as_ref().ok_or("no container spec")?;
        if let Some(found) = self.inspect(&name)? {
            // Never trust a container by its name. It must be ours (labels) AND be exactly what we would have started.
            if !found.owned_by(task, &spec.name) {
                return Err(format!("name collision: container {name:?} exists but was not started by PowerAgent for this task and sidecar; refusing to reuse or remove it"));
            }
            if let Err(why) = found.matches(c) {
                return Err(format!("container {name:?} carries PowerAgent labels but is not the registered configuration ({why}); refusing to reuse or remove it"));
            }
            if found.running {
                return Ok(());
            }
            self.run(&Self::s(&["rm", "-f", &name]))?; // ours, verified, and stopped
        }
        let o = self.run(&args)?;
        if !o.status.success() {
            return Err(format!("podman run failed for {:?}: {}", spec.name, String::from_utf8_lossy(&o.stderr).trim()));
        }
        // Read back what actually started and refuse it if it is not what was asked for.
        match self.inspect(&name)? {
            Some(f) if f.owned_by(task, &spec.name) && f.matches(c).is_ok() => Ok(()),
            Some(f) => {
                let why = f.matches(c).err().unwrap_or_else(|| "labels differ".into());
                let _ = self.run(&Self::s(&["rm", "-f", "-t", "0", &name]));
                Err(format!("container {name:?} started but does not match the registered configuration: {why}"))
            }
            None => Err(format!("container {name:?} is not present after podman run")),
        }
    }

    fn stop(&self, task: &str, name: &str) -> Result<(), String> {
        let cname = container_name(task, name)?;
        let Some(found) = self.inspect(&cname)? else { return Ok(()) };
        if !found.owned_by(task, name) {
            return Err(format!("refusing to stop container {cname:?}: it was not started by PowerAgent for this task and sidecar"));
        }
        let o = self.run(&Self::s(&["rm", "--force", "--time", "5", &cname]))?;
        if o.status.success() || !self.exists(&cname)? {
            Ok(())
        } else {
            Err(format!("podman rm failed for {name:?}: {}", String::from_utf8_lossy(&o.stderr).trim()))
        }
    }
}
