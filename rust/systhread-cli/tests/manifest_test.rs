use std::path::PathBuf;
use std::process::Command;

fn systhread_bin() -> &'static str {
    env!("CARGO_BIN_EXE_systhread")
}

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures").join(name)
}

#[test]
fn render_writes_a_manifest_with_real_content_hashes() {
    let out_dir = std::env::temp_dir().join(format!("systhread_manifest_test_{}", std::process::id()));
    std::fs::create_dir_all(&out_dir).unwrap();

    let output = Command::new(systhread_bin())
        .args(["render", "--track", "pipeline"])
        .arg(fixture("pipeline_phases_instances.yaml"))
        .args(["--out"])
        .arg(&out_dir)
        .output()
        .unwrap();
    assert!(output.status.success(), "stderr: {}", String::from_utf8_lossy(&output.stderr));

    let manifest_text = std::fs::read_to_string(out_dir.join("manifest.json")).unwrap();
    let manifest: serde_json::Value = serde_json::from_str(&manifest_text).unwrap();
    let artifacts = manifest["artifacts"].as_array().unwrap();
    assert_eq!(artifacts.len(), 3, "manifest should describe exactly the 3 rendered files, not itself");

    use sha2::{Digest, Sha256};

    // Hash-verify all three artifact kinds against the real bytes on disk, not just `sysml` --
    // the manifest is FR6's ledgrrr contract and every entry in it needs to be trustworthy.
    for (kind, filename) in [
        ("sysml", "pipeline.sysml"),
        ("svg", "pipeline.svg"),
        ("iso_ir_json", "pipeline_iso_ir.json"),
    ] {
        let entry = artifacts
            .iter()
            .find(|a| a["kind"] == kind)
            .unwrap_or_else(|| panic!("manifest missing a '{kind}' entry: {artifacts:?}"));
        assert_eq!(entry["path"], filename);
        let hash = entry["content_hash"].as_str().unwrap();
        assert!(hash.starts_with("sha256:"));
        assert_eq!(hash.len(), "sha256:".len() + 64);

        // The hash must be over the real bytes on disk, not a placeholder.
        let real_bytes = std::fs::read(out_dir.join(filename)).unwrap();
        let expected = format!("sha256:{:x}", Sha256::digest(&real_bytes));
        assert_eq!(hash, expected, "content_hash mismatch for {filename}");
    }

    std::fs::remove_dir_all(&out_dir).ok();
}
