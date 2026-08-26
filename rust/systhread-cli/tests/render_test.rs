use std::path::PathBuf;
use std::process::Command;

fn systhread_bin() -> &'static str {
    env!("CARGO_BIN_EXE_systhread")
}

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures").join(name)
}

#[test]
fn render_writes_sysml_svg_and_iso_ir_json() {
    let out_dir = std::env::temp_dir().join(format!("systhread_render_test_{}", std::process::id()));
    std::fs::create_dir_all(&out_dir).unwrap();

    let output = Command::new(systhread_bin())
        .args(["render", "--track", "pipeline"])
        .arg(fixture("pipeline_phases_instances.yaml"))
        .args(["--out"])
        .arg(&out_dir)
        .output()
        .unwrap();
    assert!(output.status.success(), "stderr: {}", String::from_utf8_lossy(&output.stderr));

    assert!(out_dir.join("pipeline.sysml").exists());
    assert!(out_dir.join("pipeline.svg").exists());
    assert!(out_dir.join("pipeline_iso_ir.json").exists());

    let sysml = std::fs::read_to_string(out_dir.join("pipeline.sysml")).unwrap();
    assert!(sysml.contains("part def"), "rendered .sysml doesn't look like real output: {sysml}");

    std::fs::remove_dir_all(&out_dir).ok();
}

#[test]
fn render_fails_cleanly_on_invalid_track_data() {
    let out_dir = std::env::temp_dir().join(format!("systhread_render_fail_test_{}", std::process::id()));
    let output = Command::new(systhread_bin())
        .args(["render", "--track", "digital-thread", "does/not/exist.yaml", "--out"])
        .arg(&out_dir)
        .output()
        .unwrap();
    assert!(!output.status.success());
}
