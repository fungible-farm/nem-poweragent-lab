use crate::track::Track;
use std::path::Path;
use systhread_core::{instances, sysml_gen, validate};

/// Shared by check.rs and render.rs: both loaders deserialize a possibly-empty struct
/// (every instance collection field is `#[serde(default)]` in systhread-core) instead of
/// erroring on a wrong `--track` / typo'd path / truncated file, so both commands must guard
/// against "loaded cleanly but every collection is empty" themselves before generating/validating
/// a syntactically-valid-but-empty model.
pub(crate) fn empty_instances_error(path: &Path, track: Track) -> String {
    format!(
        "{} contains no {} instances -- wrong --track, or an empty file?",
        path.display(),
        track.slug()
    )
}

/// Generates the .sysml text for `track` from the instance YAML at `path`, then validates it.
/// Returns Ok/Err only -- no stdout output. In `--stdio` mode stdout IS the MCP JSON-RPC
/// transport (see mcp.rs), so this function must stay silent; the CLI's PASS/FAIL presentation
/// lives in main.rs's `Commands::Check` dispatch arm instead.
pub fn run(track: Track, path: &Path) -> Result<(), String> {
    let sysml_text = match track {
        Track::DigitalThread => {
            let inst = instances::load_digital_thread(path)?;
            if inst.agents.is_empty() && inst.mcp_servers.is_empty() && inst.data_sources.is_empty() {
                return Err(empty_instances_error(path, track));
            }
            sysml_gen::render_digital_thread(&inst)
        }
        Track::Grid => {
            let inst = instances::load_grid(path)?;
            if inst.buses.is_empty() && inst.generators.is_empty() && inst.lines.is_empty() {
                return Err(empty_instances_error(path, track));
            }
            sysml_gen::render_grid_topology(&inst)
        }
        Track::Pipeline => {
            let inst = instances::load_pipeline(path)?;
            if inst.phases.is_empty() {
                return Err(empty_instances_error(path, track));
            }
            sysml_gen::render_pipeline_phases(&inst)
        }
    };

    validate::is_valid_sysml(&sysml_text)
}
