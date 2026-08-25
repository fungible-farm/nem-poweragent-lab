use systhread_cli::mcp::SysthreadMcpServer;
use rmcp::handler::server::ServerHandler;

#[test]
fn get_info_reports_real_server_identity() {
    let server = SysthreadMcpServer::new();
    let info = server.get_info();
    assert!(info.instructions.unwrap().contains("systhread"));
}
