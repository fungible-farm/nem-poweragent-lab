//! cim-gridy mission engine CLI.
//!
//! Default: headless (`MinimalPlugins`, no window, no GPU) against the
//! committed JSONL fixture -- the only mode `just check-lab9` exercises, since
//! no other lab in this repo needs a display.
//!
//! `--grid2op-live` swaps the fixture for the real `grid2op_bridge.py`
//! subprocess (needs `uv` + a built `dataset_snemSA/`).
//!
//! `--interactive` builds the real window + `bevy_ui` card feed (Lab 8 0e's
//! verdict), and is only available when the crate is built with
//! `--features interactive`. Without that feature the flag reports what to run
//! instead of silently opening nothing.

use bevy::app::ScheduleRunnerPlugin;
use bevy::prelude::*;
use clap::Parser;

use mission_engine::grid2op_bridge::{Grid2OpBridge, Grid2OpBridgePlugin, ObservationSource};
use mission_engine::mission_fsm::{MissionFsm, MissionPhase, MissionPhaseHistory};
use mission_engine::objectives::ObjectiveScore;
use mission_engine::optimizer::{self, ContingencyScenario};
use mission_engine::MissionEnginePlugin;

#[derive(Parser, Debug)]
#[command(
    name = "mission-engine",
    about = "cim-gridy PRD-0009 Phases 1-3: one minimal end-to-end grid-operator mission"
)]
struct Args {
    /// Drive the mission from the real grid2op subprocess instead of the
    /// committed fixture.
    #[arg(long)]
    grid2op_live: bool,

    /// Open a real window with the bevy_ui card feed (requires
    /// `--features interactive`).
    #[arg(long)]
    interactive: bool,

    /// How many grid2op steps to run.
    #[arg(long, default_value_t = 5)]
    steps: u32,

    /// Live mode only: how long to wait for the grid2op subprocess to produce
    /// each observation before giving up.
    #[arg(long, default_value_t = 300)]
    live_timeout_secs: u64,

    /// Write the Mermaid rendering of mission_fsm.toml to this path and exit.
    #[arg(long)]
    emit_mermaid: Option<std::path::PathBuf>,
}

fn main() {
    let args = Args::parse();

    if let Some(path) = args.emit_mermaid {
        let fsm = MissionFsm::load(&mission_engine::paths::mission_fsm_toml())
            .unwrap_or_else(|e| panic!("loading mission_fsm.toml: {e}"));
        std::fs::write(&path, fsm.render_mermaid())
            .unwrap_or_else(|e| panic!("writing {}: {e}", path.display()));
        println!("Wrote {}", path.display());
        return;
    }

    if args.interactive && cfg!(not(feature = "interactive")) {
        eprintln!(
            "--interactive needs the `interactive` cargo feature (real window + bevy_ui):\n  \
             cargo run --manifest-path rust/Cargo.toml -p mission-engine --release \\\n    \
             --features interactive -- --interactive"
        );
        std::process::exit(2);
    }

    let source = if args.grid2op_live {
        ObservationSource::live()
    } else {
        ObservationSource::fixture()
    };

    // Interactive: real window, real DefaultPlugins, real bevy_ui card feed,
    // and Bevy's own event loop -- a separate path from the turn-based
    // headless runner below on purpose.
    #[cfg(feature = "interactive")]
    if args.interactive {
        App::new()
            .add_plugins(DefaultPlugins)
            .add_plugins(Grid2OpBridgePlugin(source.clone()))
            .add_plugins(MissionEnginePlugin)
            .add_plugins(mission_engine::card_feed::CardFeedPlugin)
            .run();
        return;
    }

    let mut app = App::new();
    app.add_plugins(MinimalPlugins.set(ScheduleRunnerPlugin::run_once()))
        .add_plugins(Grid2OpBridgePlugin(source))
        .add_plugins(MissionEnginePlugin);

    // One card per real grid2op step: the mission is turn-based, not
    // frame-rate-driven.
    //
    // Live mode needs the wait loop, and that is a real finding, not
    // defensive padding: the first `--grid2op-live` run of this binary printed
    // no cards at all, because 5 instant `app.update()` calls all raced past
    // `try_recv()` while the subprocess was still spending ~60 s importing
    // grid2op and building the 503-bus environment. The Bevy side is
    // non-blocking by design (that is the whole point of the bevy_rapier
    // pattern), so the *runner* is what has to wait.
    let deadline = std::time::Duration::from_secs(args.live_timeout_secs);
    for step in 0..args.steps {
        let started = std::time::Instant::now();
        loop {
            app.update();
            let seen = app.world().resource::<Grid2OpBridge>().history.len() as u32;
            if seen > step {
                break;
            }
            if !args.grid2op_live || started.elapsed() > deadline {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(50));
        }
        if app.world().resource::<Grid2OpBridge>().history.len() as u32 <= step {
            eprintln!("no observation for step {step} within {deadline:?}; stopping");
            break;
        }
        print_card(&mut app);
    }

    println!("\n== Phase 3: strategic-objective optimizer ==");
    let scenario = ContingencyScenario::load().expect("contingency fixture loads");
    let ranked = optimizer::rank(&scenario);
    for (i, r) in ranked.iter().enumerate() {
        println!(
            "  {}. {:<26} {:<10} confidence={:.6} rho_max={:.6}",
            i + 1,
            r.candidate.name,
            if r.result.is_satisfied() {
                "SATISFIED"
            } else {
                "VIOLATED"
            },
            r.result.confidence,
            r.candidate.rho_max()
        );
    }
    let proposal = optimizer::to_dare_proposal(&scenario, &ranked);
    let (phase, accepted) = optimizer::dispatch_to_act(proposal);
    println!("  DARE proposal dispatched Decide -> {phase} (accepted={accepted})");
}

fn print_card(app: &mut App) {
    let world = app.world();
    let Some(bridge) = world.get_resource::<Grid2OpBridge>() else {
        return;
    };
    let Some(obs) = bridge.latest.as_ref() else {
        return;
    };
    let score = world.resource::<ObjectiveScore>();
    let phase = world.resource::<MissionPhase>();
    let history = world.resource::<MissionPhaseHistory>();
    let disposition = score
        .result
        .as_ref()
        .map(|r| r.disposition.to_string())
        .unwrap_or_else(|| "-".into());
    println!(
        "step {:>2} | phase {:<19} | rho_max {:.6} | overloaded {:>2}/{:<2} | {}",
        obs.step,
        phase.to_string(),
        score.rho_max,
        score.overloaded.len(),
        obs.lines.len(),
        disposition
    );
    let _ = history;
}
