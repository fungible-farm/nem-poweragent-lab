use std::path::PathBuf;
use std::process::Command;

fn systhread_bin() -> &'static str {
    env!("CARGO_BIN_EXE_systhread")
}

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures").join(name)
}

#[test]
fn check_passes_on_a_real_valid_track() {
    let output = Command::new(systhread_bin())
        .args(["check", "--track", "digital-thread"])
        .arg(fixture("digital_thread_instances.yaml"))
        .output()
        .unwrap();
    assert!(output.status.success(), "stderr: {}", String::from_utf8_lossy(&output.stderr));
    assert!(String::from_utf8_lossy(&output.stdout).contains("PASS"));
}

#[test]
fn check_fails_cleanly_on_a_missing_file() {
    let output = Command::new(systhread_bin())
        .args(["check", "--track", "digital-thread", "does/not/exist.yaml"])
        .output()
        .unwrap();
    assert!(!output.status.success());
}
