//! Physics-verification tests: the Rust port must reproduce the exact
//! numbers the Python phase_model.py computes on the real DPsim log (the
//! "oxidation preserves the physics" proof).

use std::f64::consts::PI;
use std::path::Path;

use phase_model::{Complex, ThreePhaseWaveform};

#[test]
fn sine_amplitude_phasor() {
    // Balanced 50 Hz 3-phase, amplitude A: each phase phasor magnitude ~ A,
    // positive sequence ~ A (balanced => V1 = phase amplitude).
    let a = 10_000.0f64;
    let fs = 5000.0;
    let n = 1000;
    let dt = 1.0 / fs;
    let mut times = Vec::with_capacity(n);
    let mut va = Vec::with_capacity(n);
    let mut vb = Vec::with_capacity(n);
    let mut vc = Vec::with_capacity(n);
    for i in 0..n {
        let t = i as f64 * dt;
        times.push(t);
        va.push(a * (2.0 * PI * 50.0 * t).sin());
        vb.push(a * (2.0 * PI * 50.0 * t - 2.0 * PI / 3.0).sin());
        vc.push(a * (2.0 * PI * 50.0 * t + 2.0 * PI / 3.0).sin());
    }
    let wave = ThreePhaseWaveform::new(times, va, vb, vc).unwrap();
    let (ft, ph) = wave.phasor_frames(phase_model::PHASOR_RATE_HZ);
    assert!(!ft.is_empty());
    for phase in ph.iter() {
        for c in phase.iter() {
            assert!((c.abs() - a).abs() < a * 1e-2, "|phasor| {} ~= A {a}", c.abs());
        }
    }
    let v1 = ThreePhaseWaveform::positive_sequence(&ph);
    for c in v1.iter() {
        assert!((c.abs() - a).abs() < a * 1e-2, "|V1| {} ~= A {a}", c.abs());
    }
}

#[test]
fn real_log_matches_python() {
    // Real DPsim log lives at repo root (gitignored); skip cleanly if absent.
    let log_path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../labs/05-spartan-chaosnet-transient-stream/dpsim_transient_log.json");
    if !log_path.exists() {
        eprintln!("skipping real-log test: {} not present", log_path.display());
        return;
    }
    let json = std::fs::read_to_string(&log_path).unwrap();
    let wave = ThreePhaseWaveform::from_log_json(&json).unwrap();

    // Python reference (measured 2026-08-02 on the same log):
    //   frames=53, |V1| first frame=13329.085, |V1| in-fault min=11110.106,
    //   peak deviation (5 s) = 22431.16.
    let (ft, ph) = wave.phasor_frames(phase_model::PHASOR_RATE_HZ);
    assert_eq!(ft.len(), 53, "phasor frame count must match Python");
    assert!((ft[0] - 0.0104).abs() < 1e-6, "first frame time {} ~= 0.0104", ft[0]);

    let v1: Vec<f64> = ThreePhaseWaveform::positive_sequence(&ph)
        .iter()
        .map(|c| c.abs())
        .collect();
    assert!((v1[0] - 13_329.085).abs() < 0.5, "|V1|[0] {} ~= 13329.085", v1[0]);

    let trigger = 0.2f64;
    let clear = 0.35f64;
    let in_fault: Vec<&f64> = ft
        .iter()
        .zip(v1.iter())
        .filter(|(t, _)| **t >= trigger && **t <= clear)
        .map(|(_, m)| m)
        .collect();
    let v1_min = in_fault.iter().fold(f64::INFINITY, |m, x| m.min(**x));
    assert!((v1_min - 11_110.106).abs() < 0.5, "|V1| in-fault min {v1_min} ~= 11110.106");

    let bins = wave.peak_deviation_bins(trigger, 5.0);
    assert_eq!(bins.len(), 1);
    let (s, e, peak) = bins[0];
    assert!((s - 0.0).abs() < 1e-9);
    assert!((peak - 22_431.16).abs() < 1.0, "peak deviation {peak} ~= 22431.16 (e={e})");
}

#[test]
fn from_log_rejects_bad_lengths() {
    assert!(ThreePhaseWaveform::new(vec![0.0], vec![1.0], vec![], vec![]).is_err());
}

#[test]
fn complex_arithmetic_sanity() {
    let a = Complex::new(3.0, 4.0);
    assert!((a.abs() - 5.0).abs() < 1e-12);
    let b = Complex::new(1.0, 0.0);
    let c = a * b;
    assert!((c.re - 3.0).abs() < 1e-12 && (c.im - 4.0).abs() < 1e-12);
}
