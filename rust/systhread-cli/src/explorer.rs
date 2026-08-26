use rmcp::schemars::{self, JsonSchema};
use serde::Deserialize;
use systhread_core::layout3d::LayoutMode;

/// Which explorer geometry `--explorer` should compute. Its clap value names are `2d`/`3d`
/// because that is what a user types; the Rust variant names match `LayoutMode`'s. Also
/// deserializable with the same `2d`/`3d` spelling, so the MCP `systhread_render` tool's
/// `explorer_layout` parameter accepts exactly what a CLI user would type.
#[derive(Clone, Copy, Debug, clap::ValueEnum, Deserialize, JsonSchema)]
pub enum ExplorerLayout {
    #[value(name = "2d")]
    #[serde(rename = "2d")]
    TwoD,
    #[value(name = "3d")]
    #[serde(rename = "3d")]
    ThreeD,
}

impl ExplorerLayout {
    pub fn mode(self) -> LayoutMode {
        match self {
            ExplorerLayout::TwoD => LayoutMode::TwoD,
            ExplorerLayout::ThreeD => LayoutMode::ThreeD,
        }
    }
}
