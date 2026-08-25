use crate::track::Track;
use std::path::Path;
use systhread_core::{instances, sysml_gen, validate};

/// Generates the .sysml text for `track` from the instance YAML at `path`, then validates it.
/// Prints PASS/FAIL to stdout (the CLI's user-facing output) and returns Ok/Err (main.rs's exit-code signal) —
/// two different audiences for the same result, kept as two return channels rather than one.
pub fn run(track: Track, path: &Path) -> Result<(), String> {
    let sysml_text = match track {
        Track::DigitalThread => {
            let inst = instances::load_digital_thread(path)?;
            sysml_gen::render_digital_thread(&inst)
        }
        Track::Grid => {
            let inst = instances::load_grid(path)?;
            sysml_gen::render_grid_topology(&inst)
        }
        Track::Pipeline => {
            let inst = instances::load_pipeline(path)?;
            sysml_gen::render_pipeline_phases(&inst)
        }
    };

    match validate::is_valid_sysml(&sysml_text) {
        Ok(()) => {
            println!("PASS");
            Ok(())
        }
        Err(reason) => {
            println!("FAIL: {reason}");
            Err(reason)
        }
    }
}
