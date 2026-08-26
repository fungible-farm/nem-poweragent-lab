use std::path::PathBuf;
use std::process::Command;

fn systhread_bin() -> &'static str {
    env!("CARGO_BIN_EXE_systhread")
}

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures").join(name)
}

fn render_explorer(out_dir: &PathBuf, layout: &str) {
    std::fs::create_dir_all(out_dir).unwrap();
    let output = Command::new(systhread_bin())
        .args(["render", "--track", "pipeline"])
        .arg(fixture("pipeline_phases_instances.yaml"))
        .arg("--out")
        .arg(out_dir)
        .args(["--explorer", "--explorer-layout", layout])
        .output()
        .unwrap();
    assert!(output.status.success(), "stderr: {}", String::from_utf8_lossy(&output.stderr));
}

#[test]
fn explorer_flag_writes_a_positioned_graph_and_lists_it_in_the_manifest() {
    let out_dir = std::env::temp_dir().join(format!("systhread_explorer_{}", std::process::id()));
    render_explorer(&out_dir, "3d");

    let artifact = out_dir.join("pipeline_explorer.json");
    assert!(artifact.exists(), "expected {}", artifact.display());

    let text = std::fs::read_to_string(&artifact).unwrap();
    assert!(text.contains("\"three_d\""), "layout variant should be self-describing: {text}");
    assert!(text.ends_with("}\n"));

    let manifest: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(out_dir.join("manifest.json")).unwrap())
            .unwrap();
    let entry = manifest["artifacts"]
        .as_array()
        .unwrap()
        .iter()
        .find(|a| a["path"] == "pipeline_explorer.json")
        .expect("the explorer artifact must appear in the manifest");
    assert_eq!(entry["kind"], "positioned_graph_json");
    assert!(entry["content_hash"].as_str().unwrap().starts_with("sha256:"));

    std::fs::remove_dir_all(&out_dir).ok();
}

#[test]
fn explorer_layout_2d_selects_the_flat_variant() {
    let out_dir = std::env::temp_dir().join(format!("systhread_explorer_2d_{}", std::process::id()));
    render_explorer(&out_dir, "2d");
    let text = std::fs::read_to_string(out_dir.join("pipeline_explorer.json")).unwrap();
    assert!(text.contains("\"two_d\""));
    std::fs::remove_dir_all(&out_dir).ok();
}

#[test]
fn repeated_renders_are_byte_identical() {
    let a = std::env::temp_dir().join(format!("systhread_explorer_a_{}", std::process::id()));
    let b = std::env::temp_dir().join(format!("systhread_explorer_b_{}", std::process::id()));
    render_explorer(&a, "3d");
    render_explorer(&b, "3d");
    assert_eq!(
        std::fs::read(a.join("pipeline_explorer.json")).unwrap(),
        std::fs::read(b.join("pipeline_explorer.json")).unwrap()
    );
    std::fs::remove_dir_all(&a).ok();
    std::fs::remove_dir_all(&b).ok();
}

#[test]
fn without_the_flag_no_explorer_artifact_is_written() {
    let out_dir = std::env::temp_dir().join(format!("systhread_no_explorer_{}", std::process::id()));
    std::fs::create_dir_all(&out_dir).unwrap();
    let output = Command::new(systhread_bin())
        .args(["render", "--track", "pipeline"])
        .arg(fixture("pipeline_phases_instances.yaml"))
        .arg("--out")
        .arg(&out_dir)
        .output()
        .unwrap();
    assert!(output.status.success());
    assert!(!out_dir.join("pipeline_explorer.json").exists());

    let manifest: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(out_dir.join("manifest.json")).unwrap())
            .unwrap();
    assert_eq!(manifest["artifacts"].as_array().unwrap().len(), 3);

    std::fs::remove_dir_all(&out_dir).ok();
}
