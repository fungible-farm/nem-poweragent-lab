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
}

fn to_mcp_error(reason: String) -> McpError {
    McpError { code: ErrorCode::INTERNAL_ERROR, message: reason.into(), data: None }
}

#[derive(Clone)]
pub struct SysthreadMcpServer {
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
    async fn systhread_check(
        &self,
        Parameters(params): Parameters<CheckParams>,
    ) -> Result<CallToolResult, McpError> {
        let path = std::path::PathBuf::from(&params.path);
        crate::commands::check::run(params.track, &path).map_err(to_mcp_error)?;
        Ok(CallToolResult::success(vec![ContentBlock::text("PASS")]))
    }

    #[tool(description = "Generate, validate, translate, and render one systhread track to a manifest-described output directory")]
    async fn systhread_render(
        &self,
        Parameters(params): Parameters<RenderParams>,
    ) -> Result<CallToolResult, McpError> {
        let path = std::path::PathBuf::from(&params.path);
        let out = std::path::PathBuf::from(&params.out);
        let written = crate::commands::render::run(params.track, &path, &out).map_err(to_mcp_error)?;
        let summary = written.iter().map(|p| p.display().to_string()).collect::<Vec<_>>().join("\n");
        Ok(CallToolResult::success(vec![ContentBlock::text(summary)]))
    }
}

#[tool_handler]
impl ServerHandler for SysthreadMcpServer {
    fn get_info(&self) -> ServerInfo {
        ServerInfo::new(ServerCapabilities::builder().enable_tools().build())
            .with_protocol_version(ProtocolVersion::V_2024_11_05)
            .with_server_info(Implementation::from_build_env())
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
