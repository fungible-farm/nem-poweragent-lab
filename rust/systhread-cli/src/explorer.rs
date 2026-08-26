use systhread_core::layout3d::LayoutMode;

/// Which explorer geometry `--explorer` should compute. Its clap value names are `2d`/`3d`
/// because that is what a user types; the Rust variant names match `LayoutMode`'s.
#[derive(Clone, Copy, Debug, clap::ValueEnum)]
pub enum ExplorerLayout {
    #[value(name = "2d")]
    TwoD,
    #[value(name = "3d")]
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
