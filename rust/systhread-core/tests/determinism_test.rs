mod common;
use common::fixture_path;
use systhread_core::instances::{load_digital_thread, load_grid, load_pipeline};
use systhread_core::iso_ir::{build_digital_thread_iso_ir, build_grid_iso_ir, build_pipeline_iso_ir};
use systhread_core::render::render_svg;
use systhread_core::sysml_gen::{render_digital_thread, render_grid_topology, render_pipeline_phases};

/// Relates to the spec's hard gate (docs/superpowers/specs/2026-08-25-systhread-design.md §2,
/// "Deterministic, CI-diffable output": every artifact MUST be byte-identical across repeated
/// runs on unchanged input), but this test only proves a narrower, in-process property: that
/// systhread-core's output doesn't drift against *itself* across repeated calls within the same
/// process. It cannot observe cross-process non-determinism, and that risk is not purely
/// theoretical bookkeeping -- the `kasuari` crate's simplex solver iterates a
/// `hashbrown::HashMap` with a per-process-random-seeded hasher when choosing pivots, so a
/// genuinely underdetermined constraint system (two valid solutions, no objective distinguishing
/// them) could in principle resolve differently across two separate process runs. The stronger
/// cross-process determinism guarantee currently rests on the byte-identical fixture tests
/// (Tasks 2/8/9) re-running successfully across independent CI process invocations, not on this
/// test.
#[test]
fn all_three_tracks_all_three_artifact_kinds_are_stable_across_repeated_runs() {
    let dt = load_digital_thread(&fixture_path("schema/digital_thread_instances.yaml")).unwrap();
    let grid = load_grid(&fixture_path("schema/grid_instances.yaml")).unwrap();
    let pipeline = load_pipeline(&fixture_path("schema/pipeline_phases_instances.yaml")).unwrap();

    for _ in 0..3 {
        assert_eq!(render_digital_thread(&dt), render_digital_thread(&dt));
        assert_eq!(render_grid_topology(&grid), render_grid_topology(&grid));
        assert_eq!(render_pipeline_phases(&pipeline), render_pipeline_phases(&pipeline));

        let dt_ir_a = build_digital_thread_iso_ir(&dt);
        let dt_ir_b = build_digital_thread_iso_ir(&dt);
        assert_eq!(dt_ir_a, dt_ir_b);
        let grid_ir_a = build_grid_iso_ir(&grid);
        let grid_ir_b = build_grid_iso_ir(&grid);
        assert_eq!(grid_ir_a, grid_ir_b);
        let pipeline_ir_a = build_pipeline_iso_ir(&pipeline);
        let pipeline_ir_b = build_pipeline_iso_ir(&pipeline);
        assert_eq!(pipeline_ir_a, pipeline_ir_b);

        assert_eq!(render_svg(&dt_ir_a), render_svg(&dt_ir_b));
        assert_eq!(render_svg(&grid_ir_a), render_svg(&grid_ir_b));
        assert_eq!(render_svg(&pipeline_ir_a), render_svg(&pipeline_ir_b));
    }
}
