//! The systhread model explorer. See
//! `docs/superpowers/specs/2026-08-26-systhread-3d-explorer-design.md`.
//!
//! The crate is split so that everything except the ECS layer is Bevy-free and target-agnostic:
//! `loader` and `scene` compile (and are tested) on native and `wasm32-unknown-unknown` with no
//! Bevy and no GPU, and the `explorer-3d` modules only turn already-computed data into entities.
//! That split is what makes the geometry unit-testable at all -- see design §6 on not settling for
//! a visual smoke check.

pub mod camera;
pub mod loader;
pub mod scene;

#[cfg(feature = "explorer-3d")]
pub mod asset;
#[cfg(feature = "explorer-3d")]
pub mod app;
