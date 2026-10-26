//! poweragent report --audit F --out FILE.html   (static, script-free view; exit 4 if the chain is broken)
//! poweragent reap --audit F   (stop every running helper PowerAgent started; for recovery after a crash)
//! poweragent revoke --policy F --registry F --audit F   (stop running helpers the policy no longer allows; audited)
//! poweragent run --profile F --policy F --audit F [--registry F] [--plan-only] --in FILE --out FILE
//! Runs the deterministic sum worker under the full policy chain. Exit: 0 worker ok, 1 worker
//! failed or timed out, 3 denied, 2 usage or I/O error. There is no way to pass a command.

use poweragent::{load_registry, open_bus, run_task, Outcome, RunArgs};
use poweragent_exec::Job;
use poweragent_podman::{PlannedOnly, Podman, SidecarRuntime};
use poweragent_policy::{parse_profile, AdminPolicy};
use poweragent_sidecar::Registry;
use std::{collections::HashMap, path::PathBuf, process::ExitCode};

fn flags() -> Result<HashMap<String, String>, String> {
    let mut it = std::env::args().skip(1);
    match it.next().as_deref() {
        Some("run") => {}
        _ => return Err("usage: poweragent run --profile F --policy F --audit F [--registry F] --in FILE --out FILE".into()),
    }
    let mut m = HashMap::new();
    while let Some(k) = it.next() {
        let k = k.strip_prefix("--").ok_or_else(|| format!("unexpected argument {k:?}"))?.to_string();
        if k == "plan-only" {
            m.insert(k, String::new());
            continue;
        }
        m.insert(k, it.next().ok_or("missing value")?);
    }
    Ok(m)
}

fn report() -> Result<ExitCode, String> {
    let a: Vec<String> = std::env::args().skip(2).collect();
    let (audit, out) = match a.as_slice() {
        [k1, audit, k2, out] if k1 == "--audit" && k2 == "--out" => (audit, out),
        _ => return Err("usage: poweragent report --audit F --out FILE.html".into()),
    };
    let html = poweragent_audit::render_html(std::path::Path::new(audit))?;
    std::fs::write(out, &html).map_err(|e| format!("{out}: {e}"))?;
    Ok(if html.contains("AUDIT CHAIN BROKEN") { ExitCode::from(4) } else { ExitCode::SUCCESS })
}

fn revoke() -> Result<ExitCode, String> {
    let a: Vec<String> = std::env::args().skip(2).collect();
    let (policy_path, registry_path, audit) = match a.as_slice() {
        [k1, p, k2, r, k3, au] if k1 == "--policy" && k2 == "--registry" && k3 == "--audit" => (p, r, au),
        _ => return Err("usage: poweragent revoke --policy F --registry F --audit F".into()),
    };
    let registry = load_registry(std::fs::read_to_string(registry_path).map_err(|e| format!("{registry_path}: {e}"))?.trim_start_matches('\u{feff}'))?;
    let text = std::fs::read_to_string(policy_path).map_err(|e| format!("{policy_path}: {e}"))?;
    let policy: AdminPolicy = serde_json::from_str(text.trim_start_matches('\u{feff}')).map_err(|e| e.to_string())?;
    let podman = Podman::new(if cfg!(windows) { "podman.exe" } else { "podman" });
    let mut bus = open_bus(&PathBuf::from(audit))?;
    let stopped = poweragent::revoke_unauthorised(&policy, &registry, &podman, &mut bus)?;
    for s in &stopped {
        println!("revoked {s}");
    }
    eprintln!("{} running helper(s) revoked", stopped.len());
    Ok(ExitCode::SUCCESS)
}

fn reap() -> Result<ExitCode, String> {
    let a: Vec<String> = std::env::args().skip(2).collect();
    let audit = match a.as_slice() {
        [k, au] if k == "--audit" => au,
        _ => return Err("usage: poweragent reap --audit F".into()),
    };
    let podman = Podman::new(if cfg!(windows) { "podman.exe" } else { "podman" });
    let mut bus = open_bus(&PathBuf::from(audit))?;
    let stopped = poweragent::reap(&podman, &mut bus)?;
    for s in &stopped {
        println!("reaped {s}");
    }
    eprintln!("{} orphaned helper(s) stopped", stopped.len());
    Ok(ExitCode::SUCCESS)
}

fn go() -> Result<ExitCode, String> {
    match std::env::args().nth(1).as_deref() {
        Some("report") => return report(),
        Some("revoke") => return revoke(),
        Some("reap") => return reap(),
        _ => {}
    }
    let f = flags()?;
    let get = |k: &str| f.get(k).cloned().ok_or(format!("missing --{k}"));
    let read = |p: String| std::fs::read_to_string(&p).map(|s| s.trim_start_matches('\u{feff}').to_string()).map_err(|e| format!("{p}: {e}"));
    let profile = parse_profile(&read(get("profile")?)?)?;
    let policy: AdminPolicy = serde_json::from_str(&read(get("policy")?)?).map_err(|e| e.to_string())?;
    let registry = match f.get("registry") {
        Some(p) => load_registry(&read(p.clone())?)?,
        None => Registry::default(),
    };
    let worker = std::env::current_exe().map_err(|e| e.to_string())?.with_file_name("poweragent-worker.exe");
    let mut bus = open_bus(&PathBuf::from(get("audit")?))?;
    // Helpers are launched with Podman by default. --plan-only is the explicit dry run: they are audited as planned
    // and nothing is launched. A task that needs helpers is never allowed to succeed with them silently skipped.
    let podman = Podman::new(if cfg!(windows) { "podman.exe" } else { "podman" });
    let plan_only = f.contains_key("plan-only");
    let runtime: &dyn SidecarRuntime = if plan_only { &PlannedOnly } else { &podman };
    let args = RunArgs {
        sidecars: runtime,
        plan_only,
        task: profile.metadata.name.clone(),
        profile,
        policy,
        registry,
        job: Job::Sum { input: get("in")?, output: get("out")? },
        worker,
        audit_path: PathBuf::from(get("audit")?),
    };
    let outcome = run_task(args, &mut bus)?;
    eprintln!("{outcome:?}");
    Ok(match outcome {
        Outcome::Exited(0) => ExitCode::SUCCESS,
        Outcome::Denied(_) => ExitCode::from(3),
        _ => ExitCode::from(1),
    })
}

fn main() -> ExitCode {
    go().unwrap_or_else(|e| {
        eprintln!("error: {e}");
        ExitCode::from(2)
    })
}
