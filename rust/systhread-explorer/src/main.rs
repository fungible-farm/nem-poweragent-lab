//! systhread-explorer -- Bevy-native 2D/3D SysML model graph explorer.
//! See docs/superpowers/specs/2026-08-26-systhread-3d-explorer-design.md.
//!
//! Crate scaffold only: this proves the verified `explorer-3d` Bevy feature
//! list (Cargo.toml) actually resolves and compiles inside this repo's real
//! workspace, on both the native and wasm32-unknown-unknown targets -- not
//! just in the throwaway scratch package the spike used. No
//! `PositionedGraph`/`Layout` types and no real rendering logic exist yet;
//! those land task-by-task per the implementation plan.
//!
//! Deliberately does not call `App::run()` -- constructing the App with
//! `DefaultPlugins` (which Bevy compiles down to only the plugins whose
//! crates are actually present under this feature set, the same reason
//! mission-engine's own `interactive` feature can use `DefaultPlugins`
//! safely despite excluding bevy_animation/bevy_gltf/bevy_scene) is enough
//! to prove the types resolve. Running the app loop would try to open a
//! real window, which this scaffold task is not claiming to have verified.

fn main() {
    #[cfg(feature = "explorer-3d")]
    {
        use bevy::prelude::*;
        // Constructing (not running) proves DefaultPlugins' types resolve
        // against this crate's explorer-3d feature list.
        let mut app = App::new();
        app.add_plugins(DefaultPlugins);
        println!(
            "systhread-explorer scaffold: explorer-3d feature enabled, Bevy App type resolves. \
             No rendering logic yet -- see the implementation plan."
        );
    }
    #[cfg(not(feature = "explorer-3d"))]
    {
        println!(
            "systhread-explorer scaffold: default build (no explorer-3d feature). \
             Run with --features explorer-3d to exercise the verified Bevy 3D feature list."
        );
    }
}
