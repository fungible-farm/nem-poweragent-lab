use crate::track::Track;
use std::path::{Path, PathBuf};
use systhread_core::{instances, iso_ir, render as core_render, sysml_gen, validate};

fn track_slug(track: Track) -> &'static str {
    match track {
        Track::DigitalThread => "digital-thread",
        Track::Grid => "grid",
        Track::Pipeline => "pipeline",
    }
}

/// Generates, validates, translates to iso-IR, and renders SVG for `track`, writing all three
/// artifacts into `out` (created if missing). Returns the paths written, in write order, so
/// Task 6's manifest step can hash exactly these files without re-deriving the naming scheme.
pub fn run(track: Track, path: &Path, out: &Path) -> Result<Vec<PathBuf>, String> {
    std::fs::create_dir_all(out).map_err(|e| format!("create {}: {e}", out.display()))?;
    let slug = track_slug(track);

    let (sysml_text, iso_ir_value) = match track {
        Track::DigitalThread => {
            let inst = instances::load_digital_thread(path)?;
            (sysml_gen::render_digital_thread(&inst), iso_ir::build_digital_thread_iso_ir(&inst))
        }
        Track::Grid => {
            let inst = instances::load_grid(path)?;
            (sysml_gen::render_grid_topology(&inst), iso_ir::build_grid_iso_ir(&inst))
        }
        Track::Pipeline => {
            let inst = instances::load_pipeline(path)?;
            (sysml_gen::render_pipeline_phases(&inst), iso_ir::build_pipeline_iso_ir(&inst))
        }
    };

    validate::is_valid_sysml(&sysml_text)?;

    let svg_text = core_render::render_svg(&iso_ir_value);
    let iso_ir_text = serde_json::to_string_pretty(&iso_ir_value).map_err(|e| e.to_string())? + "\n";

    let sysml_path = out.join(format!("{slug}.sysml"));
    let svg_path = out.join(format!("{slug}.svg"));
    let iso_ir_path = out.join(format!("{slug}_iso_ir.json"));

    std::fs::write(&sysml_path, &sysml_text).map_err(|e| format!("write {}: {e}", sysml_path.display()))?;
    std::fs::write(&svg_path, &svg_text).map_err(|e| format!("write {}: {e}", svg_path.display()))?;
    std::fs::write(&iso_ir_path, &iso_ir_text).map_err(|e| format!("write {}: {e}", iso_ir_path.display()))?;

    Ok(vec![sysml_path, svg_path, iso_ir_path])
}
