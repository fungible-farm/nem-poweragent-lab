use rmcp::handler::server::ServerHandler;
use rmcp::handler::server::wrapper::Parameters;
use rmcp::model::ContentBlock;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::time::Duration;
use systhread_cli::mcp::{CheckParams, RenderParams, SysthreadMcpServer};
use systhread_cli::track::Track;

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures").join(name)
}

fn systhread_bin() -> &'static str {
    env!("CARGO_BIN_EXE_systhread")
}

fn text_of(result: &rmcp::model::CallToolResult) -> String {
    result
        .content
        .iter()
        .find_map(|c| match c {
            ContentBlock::Text(t) => Some(t.text.clone()),
            _ => None,
        })
        .unwrap_or_else(|| panic!("expected a text content block in {result:?}"))
}

#[test]
fn get_info_reports_real_server_identity() {
    let server = SysthreadMcpServer::new();
    let info = server.get_info();
    assert!(info.instructions.unwrap().contains("systhread"));

    // Regression pin for the identity bug: `Implementation::from_build_env()` expands
    // CARGO_PKG_NAME/CARGO_PKG_VERSION inside the rmcp crate at rmcp's own compile time,
    // so a naive call reports the server as {"name":"rmcp","version":"3.1.4"} instead of
    // systhread-cli's own identity. Assert on the actual wire identity, not just instructions.
    assert_eq!(info.server_info.name, "systhread-cli");
    assert_eq!(info.server_info.version, env!("CARGO_PKG_VERSION"));
}

/// Calls the `systhread_check` tool method directly (as the MCP router would dispatch it),
/// against a real, valid fixture -- this is the tool-call surface no prior test exercised,
/// which is exactly what let the stdout-corruption bug (bare `println!("PASS")` from
/// `check::run`) hide through 12 prior reviews.
#[tokio::test]
async fn systhread_check_tool_reports_pass_for_a_valid_track() {
    let server = SysthreadMcpServer::new();
    let params = CheckParams {
        track: Track::DigitalThread,
        path: fixture("digital_thread_instances.yaml").display().to_string(),
    };

    let result = server
        .systhread_check(Parameters(params))
        .await
        .expect("check tool call on a valid fixture should succeed");

    assert_eq!(result.is_error, Some(false));
    assert_eq!(text_of(&result), "PASS");
}

/// The empty-instances guard (a wrong `--track` deserializes cleanly into an all-empty,
/// `#[serde(default)]` struct) must also fire through the MCP tool-call path, not just the CLI.
#[tokio::test]
async fn systhread_check_tool_errors_on_wrong_track() {
    let server = SysthreadMcpServer::new();
    let params = CheckParams {
        track: Track::Grid,
        path: fixture("digital_thread_instances.yaml").display().to_string(),
    };

    let err = server
        .systhread_check(Parameters(params))
        .await
        .expect_err("a digital-thread file loaded as --track grid should not silently PASS");

    assert!(
        err.message.contains("wrong --track"),
        "unexpected error message: {}",
        err.message
    );
}

/// Calls `systhread_render` directly and checks the real artifacts land on disk, matching
/// what `commands::render::run` itself promises.
#[tokio::test]
async fn systhread_render_tool_writes_all_three_artifacts() {
    let server = SysthreadMcpServer::new();
    let out_dir = std::env::temp_dir().join(format!("systhread_mcp_render_test_{}", std::process::id()));
    let params = RenderParams {
        track: Track::Pipeline,
        path: fixture("pipeline_phases_instances.yaml").display().to_string(),
        out: out_dir.display().to_string(),
    };

    let result = server
        .systhread_render(Parameters(params))
        .await
        .expect("render tool call on a valid fixture should succeed");

    assert_eq!(result.is_error, Some(false));
    let summary = text_of(&result);
    assert!(summary.contains("pipeline.sysml"), "unexpected summary: {summary}");

    assert!(out_dir.join("pipeline.sysml").exists());
    assert!(out_dir.join("pipeline.svg").exists());
    assert!(out_dir.join("pipeline_iso_ir.json").exists());
    assert!(out_dir.join("manifest.json").exists());

    std::fs::remove_dir_all(&out_dir).ok();
}

/// Reads response lines from the child's stdout on a background thread (so writing our
/// requests can't deadlock against a full pipe buffer), forwarding each raw line to `tx`.
fn spawn_stdout_reader(stdout: std::process::ChildStdout, tx: mpsc::Sender<String>) {
    std::thread::spawn(move || {
        let reader = BufReader::new(stdout);
        for line in reader.lines() {
            match line {
                Ok(l) => {
                    if tx.send(l).is_err() {
                        break;
                    }
                }
                Err(_) => break,
            }
        }
    });
}

/// Drains `rx` into `collected`, returning true once a line parses as JSON with `"id": target_id`
/// (a response to one of our requests), or false if `deadline` elapses first. Every line seen
/// along the way -- matching or not, valid JSON or not -- is pushed to `collected`, because the
/// whole point of this test is to catch a non-JSON line anywhere in the stream.
fn recv_response(rx: &mpsc::Receiver<String>, target_id: i64, collected: &mut Vec<String>, deadline: Duration) -> bool {
    let start = std::time::Instant::now();
    while start.elapsed() < deadline {
        let remaining = deadline - start.elapsed();
        match rx.recv_timeout(remaining) {
            Ok(line) => {
                let matched = serde_json::from_str::<serde_json::Value>(&line)
                    .ok()
                    .and_then(|v| v.get("id").cloned())
                    .map(|id| id == serde_json::json!(target_id))
                    .unwrap_or(false);
                collected.push(line);
                if matched {
                    return true;
                }
            }
            Err(_) => return false,
        }
    }
    false
}

/// Regression pin for the stdout-corruption bug: spawns the real compiled `systhread --stdio`
/// binary, performs a real MCP handshake (initialize -> notifications/initialized -> a
/// `systhread_check` tools/call), and asserts EVERY line written to stdout during the session
/// parses as JSON. Before the fix, `check::run`'s bare `println!("PASS")` injected a
/// non-JSON line into the JSON-RPC transport on the very first tool call -- this test must fail
/// if that regresses.
#[test]
fn stdio_session_never_writes_non_json_to_stdout() {
    let mut child = Command::new(systhread_bin())
        .arg("--stdio")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("failed to spawn systhread --stdio");

    let mut stdin = child.stdin.take().expect("child stdin");
    let stdout = child.stdout.take().expect("child stdout");

    let (tx, rx) = mpsc::channel::<String>();
    spawn_stdout_reader(stdout, tx);

    let mut lines: Vec<String> = Vec::new();
    let deadline = Duration::from_secs(10);

    let initialize = serde_json::json!({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "systhread-regression-test", "version": "0.0.0"}
        }
    });
    writeln!(stdin, "{}", serde_json::to_string(&initialize).unwrap()).unwrap();
    stdin.flush().unwrap();

    let got_initialize_response = recv_response(&rx, 1, &mut lines, deadline);

    let initialized = serde_json::json!({
        "jsonrpc": "2.0",
        "method": "notifications/initialized"
    });
    let call = serde_json::json!({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "systhread_check",
            "arguments": {
                "track": "digital-thread",
                "path": fixture("digital_thread_instances.yaml").display().to_string()
            }
        }
    });
    writeln!(stdin, "{}", serde_json::to_string(&initialized).unwrap()).unwrap();
    writeln!(stdin, "{}", serde_json::to_string(&call).unwrap()).unwrap();
    stdin.flush().unwrap();

    let got_tool_response = recv_response(&rx, 2, &mut lines, deadline);

    child.kill().ok();
    child.wait().ok();

    assert!(
        got_initialize_response,
        "never received a response to the initialize request; lines seen: {lines:?}"
    );
    assert!(
        got_tool_response,
        "never received a response to the systhread_check tools/call request; lines seen: {lines:?}"
    );
    assert!(!lines.is_empty(), "expected at least one line on stdout during the session");

    for line in &lines {
        serde_json::from_str::<serde_json::Value>(line)
            .unwrap_or_else(|e| panic!("stdout line was not valid JSON ({e}): {line:?}\nfull session: {lines:?}"));
    }

    // Confirm the tool call actually succeeded end to end, not just that the transport stayed clean.
    let tool_response = lines
        .iter()
        .find_map(|l| {
            serde_json::from_str::<serde_json::Value>(l)
                .ok()
                .filter(|v| v.get("id") == Some(&serde_json::json!(2)))
        })
        .expect("a response line with id 2");
    assert!(
        tool_response.get("error").is_none(),
        "tools/call for systhread_check returned a JSON-RPC error: {tool_response}"
    );
}
