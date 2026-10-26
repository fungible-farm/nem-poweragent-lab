//! Gate 3, native half: a real windows-rs call behind the same authorisation as the rule tests.
#![cfg(target_os = "windows")]
use poweragent_fallback::native::{execute, NativeError};
use poweragent_fallback::{Op, Refusal};
use poweragent_policy::*;

fn decision(backend: Backend, root: &str) -> Decision {
    Decision::Run { backend, granted: vec![Capability::FsRead { path: root.into() }] }
}
fn op(p: &str) -> Op { Op::NativeFileVersion { path: p.into() } }

#[test]
fn authorized_native_op_returns_a_real_version() {
    let d = decision(Backend::WindowsRs, "C:/Windows/System32");
    let v = execute(&d, &op("C:/Windows/System32/kernel32.dll")).unwrap();
    let parts: Vec<_> = v.split('.').collect();
    assert!(parts.len() == 4 && parts.iter().all(|x| x.parse::<u32>().is_ok()), "got {v}");
    assert!(parts[2].parse::<u32>().unwrap() >= 22000, "a Windows 11 system file: {v}");
}
#[test]
fn path_outside_the_grant_is_refused_without_touching_win32() {
    let d = decision(Backend::WindowsRs, "C:/Windows/System32");
    assert!(matches!(execute(&d, &op("C:/Windows/explorer.exe")), Err(NativeError::Refused(Refusal::PathNotGranted(_)))));
}
#[test]
fn decision_for_a_different_backend_is_refused() {
    let d = decision(Backend::Jea, "C:/Windows/System32");
    assert!(matches!(execute(&d, &op("C:/Windows/System32/kernel32.dll")), Err(NativeError::Refused(Refusal::DecisionDoesNotPermit { .. }))));
}
#[test]
fn a_deny_decision_runs_nothing() {
    let d = Decision::Deny { reason: DenyReason::NoPermittedBackend };
    assert!(execute(&d, &op("C:/Windows/System32/kernel32.dll")).is_err());
}
#[test]
fn missing_file_is_an_os_error_not_a_panic() {
    let d = decision(Backend::WindowsRs, "C:/Windows/System32");
    assert!(matches!(execute(&d, &op("C:/Windows/System32/nope-does-not-exist.dll")), Err(NativeError::Os(_))));
}
#[test]
fn jea_ops_are_not_served_by_the_native_adapter() {
    let d = decision(Backend::WindowsRs, "C:/Windows/System32");
    assert!(execute(&d, &Op::JeaListDirectory { path: "C:/Windows/System32".into() }).is_err());
}


// ---------------------------------------------------------------- reparse-point escapes
use std::{fs, path::PathBuf, process::Command};

fn tree(name: &str) -> PathBuf {
    let root = PathBuf::from(env!("CARGO_TARGET_TMPDIR")).join(format!("native-{name}"));
    let _ = Command::new("cmd").args(["/c", "rmdir", "/s", "/q", &root.to_string_lossy()]).output(); // never follows junctions
    fs::create_dir_all(&root).unwrap();
    root
}
fn junction(link: &PathBuf, target: &PathBuf) {
    let o = Command::new("cmd").args(["/c", "mklink", "/J", &link.to_string_lossy(), &target.to_string_lossy()]).output().unwrap();
    assert!(o.status.success(), "mklink /J failed: {}", String::from_utf8_lossy(&o.stdout));
}
fn copy_kernel32(to: &PathBuf) { fs::copy(r"C:\Windows\System32\kernel32.dll", to).unwrap(); }
fn granted(root: &PathBuf) -> Decision {
    decision(Backend::WindowsRs, &root.to_string_lossy().replace('\\', "/"))
}

#[test]
fn a_junction_inside_the_root_cannot_reach_a_directory_outside_it() {
    let base = tree("escape");
    let (root, outside) = (base.join("root"), base.join("outside"));
    fs::create_dir_all(&root).unwrap();
    fs::create_dir_all(&outside).unwrap();
    copy_kernel32(&outside.join("secret.dll"));
    junction(&root.join("link"), &outside);

    let path = root.join("link").join("secret.dll").to_string_lossy().replace('\\', "/");
    let d = granted(&root);
    // The old, purely lexical check approves this path: that is the vulnerability.
    assert_eq!(poweragent_fallback::authorize(&d, &op(&path)), Ok(()), "lexical check no longer shows the hole");
    // The adapter must resolve the real target and refuse.
    let r = execute(&d, &op(&path));
    assert!(matches!(r, Err(NativeError::Refused(Refusal::PathNotGranted(_)))), "junction escape not refused: {r:?}");
}

#[test]
fn a_junction_that_stays_inside_the_root_is_allowed() {
    let base = tree("inside");
    let root = base.join("root");
    fs::create_dir_all(root.join("real")).unwrap();
    copy_kernel32(&root.join("real").join("k.dll"));
    junction(&root.join("alias"), &root.join("real"));
    let path = root.join("alias").join("k.dll").to_string_lossy().replace('\\', "/");
    let v = execute(&granted(&root), &op(&path)).expect("in-root junction should work");
    assert!(v.split('.').count() == 4, "{v}");
}

#[test]
fn a_granted_root_that_is_itself_a_junction_is_resolved_before_comparing() {
    let base = tree("rootlink");
    let real = base.join("real");
    fs::create_dir_all(&real).unwrap();
    copy_kernel32(&real.join("k.dll"));
    let via = base.join("via");
    junction(&via, &real);
    let path = via.join("k.dll").to_string_lossy().replace('\\', "/");
    assert!(execute(&granted(&via), &op(&path)).is_ok(), "root given through a junction should still work");
}

#[test]
fn a_sibling_directory_sharing_the_root_prefix_is_not_inside_it() {
    let base = tree("prefix");
    let (root, sibling) = (base.join("data"), base.join("data-other"));
    fs::create_dir_all(&root).unwrap();
    fs::create_dir_all(&sibling).unwrap();
    copy_kernel32(&sibling.join("k.dll"));
    let path = sibling.join("k.dll").to_string_lossy().replace('\\', "/");
    assert!(execute(&granted(&root), &op(&path)).is_err());
}

#[test]
fn a_file_symlink_pointing_outside_is_refused_when_symlinks_can_be_created() {
    let base = tree("symlink");
    let (root, outside) = (base.join("root"), base.join("outside"));
    fs::create_dir_all(&root).unwrap();
    fs::create_dir_all(&outside).unwrap();
    copy_kernel32(&outside.join("secret.dll"));
    if std::os::windows::fs::symlink_file(outside.join("secret.dll"), root.join("s.dll")).is_err() {
        eprintln!("SKIPPED: this account may not create symbolic links (needs Developer Mode or elevation)");
        return;
    }
    let path = root.join("s.dll").to_string_lossy().replace('\\', "/");
    assert!(matches!(execute(&granted(&root), &op(&path)), Err(NativeError::Refused(_))));
}
