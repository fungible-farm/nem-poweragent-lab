//! Cross-language proof: Python generates the waveform (real Iberian 2025
//! precursor scenario, `labs/07-rust-comtrade-fft-detector/generate_fixture.py`),
//! writes it to a real COMTRADE `.cfg`/`.dat` pair, and Python's own
//! `OscillationDetector.consume()` computes a real reference finding on
//! that same in-memory waveform. This test reads the committed COMTRADE
//! fixture back through the Rust reader and asserts the Rust FFT detector
//! recovers a matching finding -- the actual "generate (Python) / detect
//! (Rust) round trip via the real file format" proof this lab exists to
//! demonstrate. Mirrors `rust/phase-model/tests/physics.rs`'s own
//! hardcoded-reference-number pattern.

use std::fs;
use std::path::PathBuf;

use fft_detector::{parse_comtrade, to_waveform, OscillationDetector};

struct Case {
    name: &'static str,
    analysis_window_s: f64,
    /// Reference numbers from `fixtures/<name>.expected.json`, produced by
    /// Python's `OscillationDetector.consume()` on the same waveform this
    /// fixture's `.dat` was written from.
    expected_mode_hz: f64,
    expected_confidence: f64,
}

fn fixtures_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../labs/07-rust-comtrade-fft-detector/fixtures")
}

fn run_case(case: &Case) {
    let dir = fixtures_dir();
    let cfg = fs::read_to_string(dir.join(format!("{}.cfg", case.name)))
        .unwrap_or_else(|e| panic!("failed to read {}.cfg: {e}", case.name));
    let dat = fs::read_to_string(dir.join(format!("{}.dat", case.name)))
        .unwrap_or_else(|e| panic!("failed to read {}.dat: {e}", case.name));

    let record = parse_comtrade(&cfg, &dat).expect("COMTRADE parse should succeed");
    let wave = to_waveform(&record).expect("waveform conversion should succeed");

    let up_to_s = wave.duration_s();
    let detector = OscillationDetector::new(
        format!("oscillation-{}", case.name),
        case.analysis_window_s,
        0.1,
    );
    let findings = detector.consume(&wave, up_to_s);
    assert_eq!(findings.len(), 1, "{}: expected exactly one finding", case.name);
    let f = &findings[0];

    assert!(
        (f.mode_hz - case.expected_mode_hz).abs() < 0.02,
        "{}: mode_hz {} not within tolerance of Python reference {}",
        case.name,
        f.mode_hz,
        case.expected_mode_hz
    );
    assert!(
        (f.confidence - case.expected_confidence).abs() < 0.05,
        "{}: confidence {} not within tolerance of Python reference {}",
        case.name,
        f.confidence,
        case.expected_confidence
    );
}

#[test]
fn local_mode_matches_python_reference() {
    run_case(&Case {
        name: "local_mode",
        analysis_window_s: 20.0,
        expected_mode_hz: 0.6503251625812905,
        expected_confidence: 0.33610467881878775,
    });
}

#[test]
fn inter_area_mode_matches_python_reference() {
    run_case(&Case {
        name: "inter_area_mode",
        analysis_window_s: 25.0,
        expected_mode_hz: 0.200080032012805,
        expected_confidence: 0.3829456690100191,
    });
}
