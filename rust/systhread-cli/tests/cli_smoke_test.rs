use std::process::Command;

fn systhread_bin() -> &'static str {
    env!("CARGO_BIN_EXE_systhread")
}

#[test]
fn help_flag_exits_zero_and_prints_usage() {
    let output = Command::new(systhread_bin()).arg("--help").output().unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("systhread"));
}

#[test]
fn no_args_exits_nonzero() {
    let output = Command::new(systhread_bin()).output().unwrap();
    assert!(!output.status.success());
}
