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

/// Every instance collection field is `#[serde(default)]` in systhread-core, so loading a
/// digital-thread file under `--track grid` deserializes cleanly into an all-empty
/// `GridInstances` (none of `buses`/`generators`/`lines` match its keys) and, without the
/// empty-instances guard, would generate a syntactically valid but empty model and print PASS.
/// That must not happen: wrong track, or an empty/truncated file, should fail loudly.
#[test]
fn check_fails_on_a_wrong_track_that_deserializes_to_all_empty_collections() {
    let output = Command::new(systhread_bin())
        .args(["check", "--track", "grid"])
        .arg(fixture("digital_thread_instances.yaml"))
        .output()
        .unwrap();
    assert!(
        !output.status.success(),
        "check --track grid against a digital-thread file should fail, not PASS"
    );
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(!stdout.contains("PASS"), "stdout should not report PASS: {stdout}");
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        stderr.contains("wrong --track"),
        "expected a clear wrong-track/empty-file error, got stderr: {stderr}"
    );
}
