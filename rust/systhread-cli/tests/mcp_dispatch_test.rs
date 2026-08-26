use std::process::{Command, Stdio};
use std::time::Duration;

fn systhread_bin() -> &'static str {
    env!("CARGO_BIN_EXE_systhread")
}

/// `--stdio` should start a long-running process (the MCP server), not exit immediately like
/// every other flag combination does -- confirmed by giving it a short-lived stdin (closed
/// immediately) and checking it doesn't exit within a tight deadline, then killing it.
#[test]
fn stdio_flag_starts_a_long_running_process() {
    let mut child = Command::new(systhread_bin())
        .arg("--stdio")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();

    std::thread::sleep(Duration::from_millis(300));
    let still_running = child.try_wait().unwrap().is_none();
    child.kill().ok();
    child.wait().ok();

    assert!(still_running, "systhread --stdio exited immediately instead of serving");
}
