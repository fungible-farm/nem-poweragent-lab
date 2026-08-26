//! Shared float-formatting helpers, matching Python's own numeric formatting where this crate's
//! byte-identical-output requirement (`docs/superpowers/specs/2026-08-25-systhread-design.md`
//! §2) depends on it. Previously three independent implementations (`sysml_gen::fmt_real`,
//! `render::poly`'s bare `{:?}` Debug format, `render::fmt_g`) solved two distinct problems the
//! same way in two places; consolidated here so there is one definition per behavior.

/// Formats an f64 the way Python's `f"{value}"` formats a YAML-sourced float: always includes a
/// decimal point, even for whole numbers (`275.0`, not `275`) -- Rust's default `f64` `Display`
/// omits it. Used for `.sysml` attribute values (every numeric value in Lab 6's grid schema is
/// written with an explicit decimal point in YAML, so this path is always exercised) and for SVG
/// `fill-opacity` (previously produced via Rust's `{:?}` Debug format, which happens to have the
/// same "always show a decimal point" behavior as this function for every opacity value this
/// crate actually passes -- 1.0, 0.7, 0.55 -- but was two mechanisms achieving one behavior).
pub(crate) fn fmt_real(value: f64) -> String {
    let s = format!("{value}");
    if s.contains('.') || s.contains('e') || s.contains('E') {
        s
    } else {
        format!("{s}.0")
    }
}

/// Rust's `Display` for `f64` (drops trailing `.0` for whole numbers, e.g. `1.0` -> `"1"`), which
/// happens to match Python's `{:g}` format only for this crate's actual stroke-width call sites
/// (fixed literals `1.0`/`1.5`/`3.0`) -- it is NOT a general port of Python's `%g`/`{:g}`
/// semantics (which switches to exponential notation for large magnitudes; this does not).
pub(crate) fn fmt_g(v: f64) -> String {
    let s = format!("{v}");
    s
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fmt_real_always_shows_a_decimal_point() {
        assert_eq!(fmt_real(275.0), "275.0");
        assert_eq!(fmt_real(0.7), "0.7");
        assert_eq!(fmt_real(1.0), "1.0");
    }

    #[test]
    fn fmt_g_drops_trailing_zero() {
        assert_eq!(fmt_g(1.0), "1");
        assert_eq!(fmt_g(1.5), "1.5");
        assert_eq!(fmt_g(3.0), "3");
    }
}
