//! Phase 1 -- the Grid2Op observation source, wired into Bevy the way
//! `bevy_rapier` wraps Rapier (the precedent PRD-0009 names): a `Plugin`
//! registers a `Resource`, a `Startup` system opens the source, and an
//! `Update` system pumps external state into ECS each tick.
//!
//! Two sources, one Resource:
//!
//! * [`ObservationSource::Fixture`] reads the committed
//!   `fixtures/episode_observations.jsonl` line by line. **This is the only
//!   source `just check-lab9` uses** -- the same exclusion Lab 8 applies to
//!   spike 0a, for the same reason: the live path needs a local grid2op + uv
//!   install and a built `dataset_snemSA/`, none of which belong in a
//!   repeatable offline gate.
//! * [`ObservationSource::LiveSubprocess`] spawns
//!   `labs/09-.../grid2op_bridge.py` under `uv run --with grid2op
//!   --no-binary-package grid2op`, reads its stdout on a `std::thread` into an
//!   `mpsc::Receiver`, and writes one JSON action per observation back to its
//!   stdin. Exercised by `just lab9-live`, never by the test suite.

use std::collections::VecDeque;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{self, Receiver};
use std::sync::Mutex;

use bevy::prelude::*;
use serde::{Deserialize, Serialize};

/// One branch of Lab 6's cluster as grid2op reports it.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct LineObservation {
    pub grid2op_line_id: usize,
    pub name: String,
    /// grid2op's own line-loading ratio (flow / thermal limit).
    pub rho: f64,
}

/// One bus of Lab 6's cluster as grid2op reports it.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BusObservation {
    pub grid2op_sub_id: u32,
    pub name: String,
    pub v_kv: Option<f64>,
}

/// One line of the bridge's wire protocol.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct GridObservation {
    pub step: u32,
    pub done: bool,
    pub reward: f64,
    pub lines: Vec<LineObservation>,
    pub buses: Vec<BusObservation>,
}

impl GridObservation {
    /// Highest branch loading in the cluster this step.
    pub fn rho_max(&self) -> f64 {
        self.lines.iter().map(|l| l.rho).fold(f64::NEG_INFINITY, f64::max)
    }

    /// `(name, rho)` pairs in wire order -- the shape [`crate::objectives::MissionGridState`] takes.
    pub fn line_loadings(&self) -> Vec<(String, f64)> {
        self.lines.iter().map(|l| (l.name.clone(), l.rho)).collect()
    }
}

/// Where observations come from.
#[derive(Debug, Clone)]
pub enum ObservationSource {
    /// The committed JSONL fixture. Deterministic, offline, no grid2op needed.
    Fixture(PathBuf),
    /// The real `grid2op_bridge.py` subprocess.
    LiveSubprocess {
        script: PathBuf,
        /// One JSON action line sent per observation received.
        action: String,
    },
}

impl ObservationSource {
    pub fn fixture() -> Self {
        ObservationSource::Fixture(crate::paths::episode_fixture())
    }

    pub fn live() -> Self {
        ObservationSource::LiveSubprocess {
            script: crate::paths::grid2op_bridge_py(),
            action: r#"{"action": "do_nothing"}"#.to_string(),
        }
    }
}

/// The Bevy-side handle on the grid physics, mirroring `bevy_rapier`'s
/// `RapierContext` resource role.
#[derive(Resource)]
pub struct Grid2OpBridge {
    /// The most recent observation drained into ECS, if any.
    pub latest: Option<GridObservation>,
    /// Every observation seen this run, in order -- the mission's own history.
    pub history: Vec<GridObservation>,
    /// True once the source has produced its last observation.
    pub exhausted: bool,
    queue: VecDeque<GridObservation>,
    // `mpsc::Receiver` is `Send` but not `Sync`, and a Bevy `Resource` must be
    // both -- a real constraint that only shows up once the receiver is stored
    // in ECS rather than in a plain struct. A `Mutex` is the minimal fix, and
    // costs nothing here: only the single `drain_observations` system ever
    // touches it, through `ResMut` (exclusive access) at that.
    rx: Option<Mutex<Receiver<GridObservation>>>,
    child: Option<Child>,
    action: String,
}

impl Grid2OpBridge {
    fn from_fixture(path: &PathBuf) -> std::io::Result<Self> {
        let file = std::fs::File::open(path)?;
        let mut queue = VecDeque::new();
        for line in BufReader::new(file).lines() {
            let line = line?;
            if line.trim().is_empty() {
                continue;
            }
            let obs: GridObservation = serde_json::from_str(&line).map_err(|e| {
                std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    format!("{}: {e}", path.display()),
                )
            })?;
            queue.push_back(obs);
        }
        Ok(Self {
            latest: None,
            history: Vec::new(),
            exhausted: false,
            queue,
            rx: None,
            child: None,
            action: String::new(),
        })
    }

    fn from_subprocess(script: &PathBuf, action: &str) -> std::io::Result<Self> {
        // `--no-binary-package grid2op` is REQUIRED, not cosmetic: grid2op
        // 1.12.5's published PyPI wheel is missing grid2op/typing_variables.py
        // (Lab 8 0a diagnosed this by diffing a wheel install against an sdist
        // install). `--with pyyaml` covers the bridge's own Lab 6 schema read.
        let mut child = Command::new("uv")
            .arg("run")
            .arg("--with")
            .arg("grid2op")
            .arg("--with")
            .arg("pyyaml")
            .arg("--no-binary-package")
            .arg("grid2op")
            .arg("python")
            .arg(script)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()?;

        let stdout = child.stdout.take().expect("stdout was piped");
        let (tx, rx) = mpsc::channel();
        std::thread::spawn(move || {
            for line in BufReader::new(stdout).lines() {
                let Ok(line) = line else { break };
                if line.trim().is_empty() {
                    continue;
                }
                match serde_json::from_str::<GridObservation>(&line) {
                    Ok(obs) => {
                        if tx.send(obs).is_err() {
                            break;
                        }
                    }
                    Err(e) => eprintln!("[bridge] unparseable observation {line:?}: {e}"),
                }
            }
        });

        Ok(Self {
            latest: None,
            history: Vec::new(),
            exhausted: false,
            queue: VecDeque::new(),
            rx: Some(Mutex::new(rx)),
            child: Some(child),
            action: action.to_string(),
        })
    }

    /// Non-blocking: take at most one observation and make it current.
    fn pump(&mut self) {
        let next = match &self.rx {
            None => self.queue.pop_front(),
            Some(rx) => rx.lock().expect("bridge receiver mutex").try_recv().ok(),
        };
        match next {
            Some(obs) => {
                let done = obs.done;
                self.history.push(obs.clone());
                self.latest = Some(obs);
                if done {
                    self.exhausted = true;
                } else if self.rx.is_some() {
                    self.request_next();
                }
            }
            None => {
                if self.rx.is_none() && self.queue.is_empty() {
                    self.exhausted = true;
                }
            }
        }
    }

    fn request_next(&mut self) {
        if let Some(child) = self.child.as_mut()
            && let Some(stdin) = child.stdin.as_mut()
        {
            let _ = writeln!(stdin, "{}", self.action);
            let _ = stdin.flush();
        }
    }
}

impl Drop for Grid2OpBridge {
    fn drop(&mut self) {
        if let Some(child) = self.child.as_mut() {
            if let Some(stdin) = child.stdin.as_mut() {
                let _ = writeln!(stdin, r#"{{"action": "quit"}}"#);
            }
            let _ = child.wait();
        }
    }
}

/// Adds the bridge Resource and the per-tick drain System.
pub struct Grid2OpBridgePlugin(pub ObservationSource);

impl Plugin for Grid2OpBridgePlugin {
    fn build(&self, app: &mut App) {
        let bridge = match &self.0 {
            ObservationSource::Fixture(path) => Grid2OpBridge::from_fixture(path)
                .unwrap_or_else(|e| panic!("reading {}: {e}", path.display())),
            ObservationSource::LiveSubprocess { script, action } => {
                Grid2OpBridge::from_subprocess(script, action)
                    .unwrap_or_else(|e| panic!("spawning {}: {e}", script.display()))
            }
        };
        app.insert_resource(bridge)
            .add_systems(Update, drain_observations);
    }
}

/// The `Update` system that moves external simulator state into ECS.
pub fn drain_observations(mut bridge: ResMut<Grid2OpBridge>) {
    bridge.pump();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fixture_parses_and_has_the_cluster_shape() {
        let bridge = Grid2OpBridge::from_fixture(&crate::paths::episode_fixture()).unwrap();
        assert_eq!(bridge.queue.len(), 5, "fixture is a 5-step episode");
        for obs in &bridge.queue {
            assert_eq!(obs.lines.len(), 19, "Lab 6's cluster has 19 branches");
            assert_eq!(obs.buses.len(), 15, "Lab 6's cluster has 15 buses");
        }
    }
}
