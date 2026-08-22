//! CLI: read a COMTRADE `.cfg`/`.dat` pair, run the FFT oscillation
//! detector across the whole record, print findings as JSON.
//!
//! Usage: `fft-detector <base.cfg> <base.dat> [--check <expected.json>]`

use std::env;
use std::fs;
use std::process::ExitCode;

use fft_detector::{parse_comtrade, to_waveform, OscillationDetector};

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        eprintln!("usage: fft-detector <base.cfg> <base.dat> [--check <expected.json>]");
        return ExitCode::FAILURE;
    }
    let cfg_path = &args[1];
    let dat_path = &args[2];

    let cfg_contents = match fs::read_to_string(cfg_path) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("failed to read {cfg_path}: {e}");
            return ExitCode::FAILURE;
        }
    };
    let dat_contents = match fs::read_to_string(dat_path) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("failed to read {dat_path}: {e}");
            return ExitCode::FAILURE;
        }
    };

    let record = match parse_comtrade(&cfg_contents, &dat_contents) {
        Ok(r) => r,
        Err(e) => {
            eprintln!("COMTRADE parse error: {e}");
            return ExitCode::FAILURE;
        }
    };
    let wave = match to_waveform(&record) {
        Ok(w) => w,
        Err(e) => {
            eprintln!("failed to build waveform: {e}");
            return ExitCode::FAILURE;
        }
    };

    let up_to_s = wave.duration_s();

    // Default detector config, used when no --check fixture drives it.
    let mut analysis_window_s = 15.0;
    let mut min_confidence = 0.15;

    let check_idx = args.iter().position(|a| a == "--check");
    let expected_findings: Vec<serde_json::Value> = if let Some(check_idx) = check_idx {
        let expected_path = match args.get(check_idx + 1) {
            Some(p) => p,
            None => {
                eprintln!("--check requires a path argument");
                return ExitCode::FAILURE;
            }
        };
        let expected_contents = match fs::read_to_string(expected_path) {
            Ok(s) => s,
            Err(e) => {
                eprintln!("failed to read {expected_path}: {e}");
                return ExitCode::FAILURE;
            }
        };
        let expected: serde_json::Value = serde_json::from_str(&expected_contents).unwrap();
        let findings = expected.as_array().cloned().unwrap_or_default();
        // The check fixture's own declared window/confidence drive the
        // detector -- comparing an FFT peak computed over a different
        // window length than the reference was computed with is meaningless.
        if let Some(first) = findings.first() {
            if let Some(w) = first["window_s"].as_f64() {
                analysis_window_s = w;
            }
            if let Some(m) = first["min_confidence"].as_f64() {
                min_confidence = m;
            }
        }
        findings
    } else {
        Vec::new()
    };

    let detector = OscillationDetector::new("oscillation-fft-detector", analysis_window_s, min_confidence);
    let findings = detector.consume(&wave, up_to_s);

    let json = serde_json::to_string_pretty(&findings).unwrap();
    println!("{json}");

    if check_idx.is_some() {
        let actual: serde_json::Value = serde_json::from_str(&json).unwrap();
        let actual_findings = actual.as_array().cloned().unwrap_or_default();
        if expected_findings.len() != actual_findings.len() {
            eprintln!(
                "MISMATCH: expected {} findings, got {}",
                expected_findings.len(),
                actual_findings.len()
            );
            return ExitCode::FAILURE;
        }
        for (e, a) in expected_findings.iter().zip(actual_findings.iter()) {
            let e_hz = e["mode_hz"].as_f64().unwrap_or(f64::NAN);
            let a_hz = a["mode_hz"].as_f64().unwrap_or(f64::NAN);
            let e_conf = e["confidence"].as_f64().unwrap_or(f64::NAN);
            let a_conf = a["confidence"].as_f64().unwrap_or(f64::NAN);
            if (e_hz - a_hz).abs() > 0.02 || (e_conf - a_conf).abs() > 0.05 {
                eprintln!(
                    "MISMATCH: expected mode_hz={e_hz} confidence={e_conf}, got mode_hz={a_hz} confidence={a_conf}"
                );
                return ExitCode::FAILURE;
            }
        }
        println!("MATCH");
    }

    ExitCode::SUCCESS
}
