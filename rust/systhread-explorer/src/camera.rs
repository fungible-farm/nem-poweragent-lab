//! Orbit camera state and its pure geometry — no Bevy dependency except the Component derive,
//! so this compiles and tests on the default (Bevy-free) feature set too.

use crate::scene::SceneSpec;

/// Camera state. Kept as data rather than as accumulated `Transform` mutations so that a future
/// XR rig (design §7) replaces only the system that writes it, not the scene-building code.
#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "explorer-3d", derive(bevy::prelude::Component))]
pub struct Orbit {
    pub target: [f32; 3],
    pub yaw: f32,
    pub pitch: f32,
    pub radius: f32,
    /// A flat (2D) layout has no depth axis worth orbiting around, so pitch stays at zero.
    pub lock_pitch: bool,
}

/// The camera offset implied by an `Orbit`, in the same convention `scene::camera` used.
pub fn orbit_offset(orbit: &Orbit) -> [f32; 3] {
    [
        orbit.radius * orbit.yaw.cos() * orbit.pitch.cos(),
        orbit.radius * orbit.pitch.sin(),
        orbit.radius * orbit.yaw.sin() * orbit.pitch.cos(),
    ]
}

/// Seeds the orbit from the scene's own camera placement, so frame zero looks exactly like what
/// `scene_spec` described and the first drag continues from there rather than jumping.
pub fn orbit_from_scene(spec: &SceneSpec) -> Orbit {
    let delta = [
        spec.camera_position[0] - spec.camera_target[0],
        spec.camera_position[1] - spec.camera_target[1],
        spec.camera_position[2] - spec.camera_target[2],
    ];
    let radius = (delta[0] * delta[0] + delta[1] * delta[1] + delta[2] * delta[2]).sqrt();
    let pitch = if spec.flat || radius == 0.0 {
        0.0
    } else {
        (delta[1] / radius).asin()
    };
    let yaw = if spec.flat { std::f32::consts::FRAC_PI_2 } else { delta[2].atan2(delta[0]) };
    Orbit { target: spec.camera_target, yaw, pitch, radius, lock_pitch: spec.flat }
}
