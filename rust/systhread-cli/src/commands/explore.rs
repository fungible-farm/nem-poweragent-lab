/// FR7 (the interactive explorer) is explicitly Phase 3 in the spec -- this command exists in
/// Phase 1 only so the b00t/just packaging surface (Task 7/8) has something real to wire to and
/// test, not to pretend the explorer is built. See docs/superpowers/specs/2026-08-25-systhread-design.md §6.
pub fn run() -> Result<(), String> {
    Err("systhread explore: not yet implemented -- ships in Phase 3 (FR7, the interactive model explorer)".to_string())
}
