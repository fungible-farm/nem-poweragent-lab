//! Bevy asset plumbing for the `PositionedGraph` artifact -- a thin adapter over `loader`, which
//! holds all the real parsing. Design §5: the viewer is one generic build that *loads* a
//! per-project artifact at runtime, never one compiled per project.

use bevy::asset::io::Reader;
use bevy::asset::{Asset, AssetLoader, LoadContext};
use bevy::prelude::*;
use bevy::reflect::TypePath;
use systhread_core::positioned::PositionedGraph;

#[derive(Asset, TypePath, Debug)]
pub struct PositionedGraphAsset {
    pub graph: PositionedGraph,
}

/// `TypePath` is required on the loader itself, not only on the asset:
/// `pub trait AssetLoader: TypePath + Send + Sync + 'static` (bevy_asset 0.19.1, src/loader.rs:32).
#[derive(Default, TypePath)]
pub struct PositionedGraphAssetLoader;

impl AssetLoader for PositionedGraphAssetLoader {
    type Asset = PositionedGraphAsset;
    type Settings = ();
    type Error = std::io::Error;

    async fn load(
        &self,
        reader: &mut dyn Reader,
        _settings: &(),
        _load_context: &mut LoadContext<'_>,
    ) -> Result<Self::Asset, Self::Error> {
        let mut bytes = Vec::new();
        reader.read_to_end(&mut bytes).await?;
        let graph = crate::loader::positioned_graph_from_bytes(&bytes)
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidData, e))?;
        Ok(PositionedGraphAsset { graph })
    }

    fn extensions(&self) -> &[&str] {
        &["json"]
    }
}

pub struct ExplorerAssetPlugin;

impl Plugin for ExplorerAssetPlugin {
    fn build(&self, app: &mut App) {
        app.init_asset::<PositionedGraphAsset>()
            .init_asset_loader::<PositionedGraphAssetLoader>();
    }
}
