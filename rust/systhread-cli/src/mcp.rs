use crate::explorer::ExplorerLayout;
use crate::track::Track;
use rmcp::handler::server::{ServerHandler, router::tool::ToolRouter, wrapper::Parameters};
use rmcp::model::{CallToolResult, ContentBlock, ErrorCode, ErrorData as McpError, Implementation, ProtocolVersion, ServerCapabilities, ServerInfo};
use rmcp::schemars::{self, JsonSchema};
use rmcp::{ServiceExt, tool, tool_handler, tool_router, transport::stdio};
use serde::Deserialize;

#[derive(Debug, Deserialize, JsonSchema)]
pub struct CheckParams {
    pub track: Track,
    pub path: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct RenderParams {
    pub track: Track,
    pub path: String,
    pub out: String,
    /// Also emit the explorer's PositionedGraph JSON (FR7), in this geometry. Omit for the
    /// Phase 1 behaviour (no explorer artifact) -- matches the CLI's `--explorer-layout`, ignored
    /// unless present.
    #[serde(default)]
    pub explorer_layout: Option<ExplorerLayout>,
}

fn to_mcp_error(reason: String) -> McpError {
    McpError { code: ErrorCode::INTERNAL_ERROR, message: reason.into(), data: None }
}

#[derive(Clone)]
pub struct SysthreadMcpServer {
    // Read by the `#[tool_router]`/`#[tool_handler]` macro-generated dispatch code, not by any
    // code rustc's dead-code pass can see -- a known false positive for this idiom, not a real
    // unused field.
    #[allow(dead_code)]
    tool_router: ToolRouter<Self>,
}

impl SysthreadMcpServer {
    pub fn new() -> Self {
        Self { tool_router: Self::tool_router() }
    }
}

#[tool_router]
impl SysthreadMcpServer {
    #[tool(description = "Generate the .sysml text for one systhread track and validate it")]
    pub async fn systhread_check(
        &self,
        Parameters(params): Parameters<CheckParams>,
    ) -> Result<CallToolResult, McpError> {
        let path = std::path::PathBuf::from(&params.path);
        crate::commands::check::run(params.track, &path).map_err(to_mcp_error)?;
        Ok(CallToolResult::success(vec![ContentBlock::text("PASS")]))
    }

    #[tool(description = "Generate, validate, translate, and render one systhread track to a manifest-described output directory")]
    pub async fn systhread_render(
        &self,
        Parameters(params): Parameters<RenderParams>,
    ) -> Result<CallToolResult, McpError> {
        let path = std::path::PathBuf::from(&params.path);
        let out = std::path::PathBuf::from(&params.out);
        let written = crate::commands::render::run_with_explorer(params.track, &path, &out, params.explorer_layout)
            .map_err(to_mcp_error)?;
        let summary = written.iter().map(|p| p.display().to_string()).collect::<Vec<_>>().join("\n");
        Ok(CallToolResult::success(vec![ContentBlock::text(summary)]))
    }
}

#[tool_handler]
impl ServerHandler for SysthreadMcpServer {
    fn get_info(&self) -> ServerInfo {
        ServerInfo::new(ServerCapabilities::builder().enable_tools().build())
            .with_protocol_version(ProtocolVersion::V_2024_11_05)
            // `Implementation::from_build_env()` expands CARGO_PKG_NAME/CARGO_PKG_VERSION inside
            // the rmcp crate at rmcp's own compile time, so it reports rmcp's own identity
            // instead of systhread-cli's. Use this crate's own env! expansion instead.
            .with_server_info(Implementation::new(env!("CARGO_PKG_NAME"), env!("CARGO_PKG_VERSION")))
            .with_instructions(
                "systhread MCP server: generate/validate/render SysML v2 digital-thread models. \
                 Tools: systhread_check, systhread_render.",
            )
    }
}

pub async fn run_stdio() -> Result<(), String> {
    let server = SysthreadMcpServer::new();
    let running = server.serve(stdio()).await.map_err(|e| e.to_string())?;
    running.waiting().await.map_err(|e| e.to_string())?;
    Ok(())
}
