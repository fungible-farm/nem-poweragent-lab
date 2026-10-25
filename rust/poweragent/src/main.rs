//! poweragent report --audit F --out FILE.html   (static, script-free view; exit 4 if the chain is broken)
//! poweragent run --profile F --policy F --audit F [--registry F] [--podman] --in FILE --out FILE
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
        if k == "podman" {
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

fn go() -> Result<ExitCode, String> {
    if std::env::args().nth(1).as_deref() == Some("report") {
        return report();
    }
    let f = flags()?;
    let get = |k: &str| f.get(k).cloned().ok_or(format!("missing --{k}"));
    let read = |p: String| std::fs::read_to_string(&p).map_err(|e| format!("{p}: {e}"));
    let profile = parse_profile(&read(get("profile")?)?)?;
    let policy: AdminPolicy = serde_json::from_str(&read(get("policy")?)?).map_err(|e| e.to_string())?;
    let registry = match f.get("registry") {
        Some(p) => load_registry(&read(p.clone())?)?,
        None => Registry::default(),
    };
    let worker = std::env::current_exe().map_err(|e| e.to_string())?.with_file_name("poweragent-worker.exe");
    let mut bus = open_bus(&PathBuf::from(get("audit")?))?;
    // Sidecars are launched only with --podman; otherwise they are planned and audited, not started.
    let podman = Podman::new(if cfg!(windows) { "podman.exe" } else { "podman" });
    let runtime: &dyn SidecarRuntime = if f.contains_key("podman") { &podman } else { &PlannedOnly };
    let args = RunArgs {
        sidecars: runtime,
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
