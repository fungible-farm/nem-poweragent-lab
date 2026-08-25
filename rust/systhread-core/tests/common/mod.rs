use std::path::{Path, PathBuf};

/// Resolves a path under `tests/fixtures/lab6/`, e.g. `fixture_path("schema/grid_instances.yaml")`.
pub fn fixture_path(rel: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures/lab6")
        .join(rel)
}
