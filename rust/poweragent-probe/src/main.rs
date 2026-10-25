//! `poweragent-probe [--profile FILE --policy FILE]`
//! Prints a JSON report. With a profile and policy it also prints the ADR-002 decision and exits
//! 0 (run) or 3 (deny). Exit 2 is a usage or input error. It never executes the task.

use poweragent_policy::{decide, parse_profile, AdminPolicy, Decision};
use std::process::ExitCode;

fn read(path: &str) -> Result<String, String> {
    std::fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))
}

fn run() -> Result<ExitCode, String> {
    let mut args = std::env::args().skip(1);
    let (mut profile_path, mut policy_path) = (None, None);
    while let Some(a) = args.next() {
        match a.as_str() {
            "--profile" => profile_path = args.next(),
            "--policy" => policy_path = args.next(),
            _ => return Err(format!("unknown argument {a:?}; usage: poweragent-probe [--profile FILE --policy FILE]")),
        }
    }
    let profile = profile_path.as_deref().map(|p| read(p).and_then(|s| parse_profile(&s))).transpose()?;
    let report = poweragent_probe::probe_host(profile.as_ref());
    let mut out = serde_json::to_value(&report).map_err(|e| e.to_string())?;
    let mut code = ExitCode::SUCCESS;
    if let Some(profile) = &profile {
        let policy: AdminPolicy = match policy_path.as_deref() {
            Some(p) => serde_json::from_str(&read(p)?).map_err(|e| e.to_string())?,
            None => AdminPolicy::default(), // no policy file means nothing is allowed
        };
        let decision = decide(profile, &policy, &report.probe);
        if matches!(decision, Decision::Deny { .. }) {
            code = ExitCode::from(3);
        }
        out["decision"] = serde_json::to_value(&decision).map_err(|e| e.to_string())?;
    }
    println!("{}", serde_json::to_string_pretty(&out).map_err(|e| e.to_string())?);
    Ok(code)
}

fn main() -> ExitCode {
    run().unwrap_or_else(|e| {
        eprintln!("error: {e}");
        ExitCode::from(2)
    })
}
