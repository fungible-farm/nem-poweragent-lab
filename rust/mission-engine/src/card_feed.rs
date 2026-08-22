//! The interactive `bevy_ui` card feed -- Lab 8 0e's verdict ("build the card
//! feed natively in Bevy"; OperatorFabric's `Card` data model kept as a design
//! reference, not a runtime dependency) implemented for real.
//!
//! Feature-gated (`--features interactive`) because it pulls winit/wgpu/text
//! rendering into the build. `just check-lab9` never builds this: no other lab
//! in this repo needs a display, and keeping that true is deliberate.

use bevy::prelude::*;

use crate::grid2op_bridge::Grid2OpBridge;
use crate::mission_fsm::{MissionPhase, MissionPhaseHistory};
use crate::objectives::ObjectiveScore;

/// Marker for the scrolling column the cards are appended to.
#[derive(Component)]
pub struct CardFeedRoot;

/// OperatorFabric's card severity vocabulary, kept as a design reference.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CardSeverity {
    Information,
    Compliant,
    Action,
    Alarm,
}

impl CardSeverity {
    fn colour(self) -> Color {
        match self {
            CardSeverity::Information => Color::srgb(0.16, 0.35, 0.58),
            CardSeverity::Compliant => Color::srgb(0.16, 0.48, 0.28),
            CardSeverity::Action => Color::srgb(0.62, 0.45, 0.10),
            CardSeverity::Alarm => Color::srgb(0.62, 0.18, 0.18),
        }
    }
}

pub struct CardFeedPlugin;

impl Plugin for CardFeedPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, setup_card_feed)
            .add_systems(Update, push_card.after(crate::mission_fsm::advance_phase));
    }
}

fn setup_card_feed(mut commands: Commands) {
    commands.spawn(Camera2d);
    commands.spawn((
        Node {
            width: Val::Percent(100.0),
            height: Val::Percent(100.0),
            flex_direction: FlexDirection::Column,
            row_gap: Val::Px(8.0),
            padding: UiRect::all(Val::Px(16.0)),
            overflow: Overflow::scroll_y(),
            ..default()
        },
        BackgroundColor(Color::srgb(0.06, 0.07, 0.09)),
        CardFeedRoot,
    ));
}

/// One card per real observation -- appended, never rewritten, so the feed
/// reads as a mission log.
fn push_card(
    mut commands: Commands,
    bridge: Res<Grid2OpBridge>,
    score: Res<ObjectiveScore>,
    phase: Res<MissionPhase>,
    history: Res<MissionPhaseHistory>,
    root: Query<Entity, With<CardFeedRoot>>,
    mut rendered: Local<usize>,
) {
    let Some(obs) = bridge.latest.as_ref() else {
        return;
    };
    if *rendered >= history.0.len() {
        return;
    }
    *rendered = history.0.len();

    let Ok(root) = root.single() else {
        return;
    };

    let satisfied = score.result.as_ref().is_some_and(|r| r.is_satisfied());
    let severity = match (*phase, satisfied) {
        (MissionPhase::Resolved, _) => CardSeverity::Compliant,
        (_, true) => CardSeverity::Information,
        (MissionPhase::ContingencyDetected, false) => CardSeverity::Alarm,
        (_, false) => CardSeverity::Action,
    };

    let title = format!("step {} — {}", obs.step, *phase);
    let body = match score.result.as_ref() {
        Some(result) if result.is_satisfied() => format!(
            "GridSecurityObjective satisfied (confidence {:.3}); rho_max {:.6} over {} cluster branches",
            result.confidence,
            score.rho_max,
            obs.lines.len()
        ),
        Some(result) => format!("{} (confidence {:.3})", result.disposition, result.confidence),
        None => "no score yet".to_string(),
    };

    let card = commands
        .spawn((
            Node {
                flex_direction: FlexDirection::Column,
                padding: UiRect::all(Val::Px(12.0)),
                row_gap: Val::Px(4.0),
                // Bevy 0.19: BorderRadius is a field on `Node`, not a
                // standalone Component (it was one in earlier releases).
                border_radius: BorderRadius::all(Val::Px(6.0)),
                ..default()
            },
            BackgroundColor(severity.colour()),
        ))
        .id();

    let title_node = commands
        .spawn((
            Text::new(title),
            TextFont {
                font_size: FontSize::Px(18.0),
                ..default()
            },
            TextColor(Color::WHITE),
        ))
        .id();
    let body_node = commands
        .spawn((
            Text::new(body),
            TextFont {
                font_size: FontSize::Px(14.0),
                ..default()
            },
            TextColor(Color::srgb(0.88, 0.90, 0.94)),
        ))
        .id();

    commands.entity(card).add_children(&[title_node, body_node]);
    commands.entity(root).add_children(&[card]);
}
