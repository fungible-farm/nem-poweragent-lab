//! The ECS layer: turns a `SceneSpec` into entities and drives an orbit camera. All geometry
//! arrives already computed (see `scene`), so nothing here does math a test can't reach.

use crate::asset::{ExplorerAssetPlugin, PositionedGraphAsset};
use crate::camera::{orbit_from_scene, orbit_offset, Orbit};
use crate::scene::{scene_spec, EdgeVisual, NodeVisual, EDGE_RADIUS};
use bevy::core_pipeline::tonemapping::Tonemapping;
use bevy::prelude::*;

#[derive(Resource)]
struct GraphHandle(Handle<PositionedGraphAsset>);

#[derive(Resource, Default)]
struct SceneSpawned(bool);

/// Drop-in plugin: loads `asset_path` through Bevy's asset system and renders it.
pub struct ExplorerPlugin {
    pub asset_path: String,
}

impl Plugin for ExplorerPlugin {
    fn build(&self, app: &mut App) {
        let path = self.asset_path.clone();
        app.add_plugins(ExplorerAssetPlugin)
            .init_resource::<SceneSpawned>()
            .insert_resource(AssetPathToLoad(path))
            .add_systems(Startup, request_graph)
            .add_systems(Update, (spawn_scene_when_loaded, orbit_camera));
    }
}

#[derive(Resource)]
struct AssetPathToLoad(String);

fn request_graph(
    mut commands: Commands,
    asset_server: Res<AssetServer>,
    path: Res<AssetPathToLoad>,
) {
    let handle: Handle<PositionedGraphAsset> = asset_server.load(path.0.clone());
    commands.insert_resource(GraphHandle(handle));
}

fn spawn_scene_when_loaded(
    mut commands: Commands,
    handle: Option<Res<GraphHandle>>,
    graphs: Res<Assets<PositionedGraphAsset>>,
    mut spawned: ResMut<SceneSpawned>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    if spawned.0 {
        return;
    }
    let Some(handle) = handle else { return };
    let Some(asset) = graphs.get(&handle.0) else { return };

    let spec = scene_spec(&asset.graph);
    info!(
        "systhread-explorer: {} nodes, {} edges, flat={}",
        spec.nodes.len(),
        spec.edges.len(),
        spec.flat
    );

    // One shared unit mesh per kind: a unit-radius sphere and a unit-height, Y-aligned cylinder,
    // both scaled per entity. Reusing two meshes keeps the draw-call count independent of graph
    // size and matches how `EdgeVisual` was defined in `scene`.
    let sphere = meshes.add(Sphere::new(1.0));
    let cylinder = meshes.add(Cylinder::new(EDGE_RADIUS, 1.0));
    let node_material = materials.add(StandardMaterial::from_color(Color::srgb(0.35, 0.67, 0.94)));
    let edge_material = materials.add(StandardMaterial::from_color(Color::srgb(0.55, 0.58, 0.62)));

    for NodeVisual { position, radius, .. } in &spec.nodes {
        commands.spawn((
            Mesh3d(sphere.clone()),
            MeshMaterial3d(node_material.clone()),
            Transform::from_translation(Vec3::from_array(*position)).with_scale(Vec3::splat(*radius)),
        ));
    }

    for EdgeVisual { midpoint, direction, length, .. } in &spec.edges {
        commands.spawn((
            Mesh3d(cylinder.clone()),
            MeshMaterial3d(edge_material.clone()),
            Transform::from_translation(Vec3::from_array(*midpoint))
                .with_rotation(Quat::from_rotation_arc(Vec3::Y, Vec3::from_array(*direction)))
                .with_scale(Vec3::new(1.0, *length, 1.0)),
        ));
    }

    let orbit = orbit_from_scene(&spec);
    commands.spawn((
        Camera3d::default(),
        // `TonyMcMapFace` (the default) requires the `tonemapping_luts` feature's baked LUT
        // assets, which this crate doesn't enable -- without them it errors at draw time and
        // nothing renders lit. `None` needs no LUT asset and matches the flat, unlit-shading
        // style this viewer already uses (StandardMaterial with no PBR lighting setup beyond one
        // DirectionalLight).
        Tonemapping::None,
        Transform::from_translation(Vec3::from_array(spec.camera_position))
            .looking_at(Vec3::from_array(spec.camera_target), Vec3::Y),
        orbit,
    ));
    commands.spawn((
        DirectionalLight::default(),
        Transform::from_translation(
            Vec3::from_array(spec.camera_position) + Vec3::new(0.0, 4.0, 0.0),
        )
        .looking_at(Vec3::from_array(spec.camera_target), Vec3::Y),
    ));

    spawned.0 = true;
}

fn orbit_camera(
    mut motion: MessageReader<bevy::input::mouse::MouseMotion>,
    mut wheel: MessageReader<bevy::input::mouse::MouseWheel>,
    buttons: Res<ButtonInput<MouseButton>>,
    mut cameras: Query<(&mut Orbit, &mut Transform)>,
) {
    let mut drag = Vec2::ZERO;
    for event in motion.read() {
        drag += event.delta;
    }
    let mut zoom = 0.0;
    for event in wheel.read() {
        zoom += event.y;
    }
    if drag == Vec2::ZERO && zoom == 0.0 {
        return;
    }
    for (mut orbit, mut transform) in cameras.iter_mut() {
        if buttons.pressed(MouseButton::Left) {
            orbit.yaw -= drag.x * 0.005;
            if !orbit.lock_pitch {
                orbit.pitch = (orbit.pitch - drag.y * 0.005).clamp(-1.5, 1.5);
            }
        }
        orbit.radius = (orbit.radius - zoom * 0.5).max(1.0);
        let target = Vec3::from_array(orbit.target);
        transform.translation = target + Vec3::from_array(orbit_offset(&orbit));
        transform.look_at(target, Vec3::Y);
    }
}

/// Runs the explorer against an asset path relative to Bevy's asset root (`assets/` next to the
/// executable natively; the served directory on the web).
pub fn run(asset_path: &str) {
    App::new()
        .add_plugins(DefaultPlugins)
        .add_plugins(ExplorerPlugin { asset_path: asset_path.to_string() })
        .run();
}
