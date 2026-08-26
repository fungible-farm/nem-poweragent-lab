//! Phase 0 of the systhread MBSE capability. See
//! docs/superpowers/specs/2026-08-25-systhread-design.md.
//!
//! ## Error-handling convention
//!
//! A `pub fn` returns `Result<T, String>` if and only if it crosses this crate's boundary with
//! the outside world -- reading a file, parsing text that originated outside this crate's own
//! generators (`instances::load_*`, `validate::is_valid_sysml`). Everything downstream of that
//! boundary (`iso_ir::*`, `render::render_svg`, `sysml_gen::render_*`) is a pure in-memory
//! transform over already-loaded, already-typed Rust structs or `Value`s this crate's own
//! loaders produced, and is infallible by construction -- it returns a bare value, not a
//! `Result` wrapping an error variant that can never actually occur. Do not wrap an infallible
//! transform in `Result` "to be safe"; do not let a function that touches the filesystem or
//! parses untrusted text panic instead of returning `Result`. When adding a new `pub fn`, decide
//! which side of that boundary it's on and follow the matching convention -- this crate has no
//! functions that mix the two (partially fallible, partially not) today, and mixing them is a
//! sign the function should be split rather than exempted from this rule.

pub mod cytoscape;
pub mod instances;
pub mod iso_ir;
pub mod layout;
pub mod layout3d;
mod numfmt;
pub mod positioned;
pub mod render;
pub mod sysml_gen;
pub mod validate;
