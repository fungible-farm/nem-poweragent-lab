use std::process::Command;

fn systhread_bin() -> &'static str {
    env!("CARGO_BIN_EXE_systhread")
}

#[test]
fn explore_fails_with_a_clear_not_yet_implemented_message() {
    let output = Command::new(systhread_bin()).arg("explore").output().unwrap();
    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("Phase 3"), "stderr should name the phase that ships this: {stderr}");
}

#[test]
fn drift_fails_with_a_clear_not_yet_implemented_message() {
    let output = Command::new(systhread_bin()).arg("drift").output().unwrap();
    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("Phase 4"), "stderr should name the phase that ships this: {stderr}");
}
