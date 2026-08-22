//! FFT-based oscillation-mode detector -- a Rust port of
//! `labs/_shared/scenario_engine/detectors.py::OscillationDetector.consume()`.
//!
//! Reuses `phase_model::ThreePhaseWaveform::phasor_frames()` and
//! `positive_sequence()` unmodified (no phasor/DFT reimplementation, same
//! "thin transform" requirement PRD-0001 places on the Python detectors);
//! the FFT itself uses `realfft` (real-input wrapper over `rustfft`) rather
//! than the hand-rolled DFT already in `phase_model`, since a genuine FFT
//! library is the whole point of this testbench.

use phase_model::ThreePhaseWaveform;
use realfft::RealFftPlanner;
use serde::Serialize;

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Finding {
    pub detector_id: String,
    pub time_s: f64,
    pub kind: String,
    pub confidence: f64,
    pub mode_hz: f64,
    pub window_s: f64,
}

pub struct OscillationDetector {
    pub id: String,
    pub analysis_window_s: f64,
    pub min_confidence: f64,
}

impl OscillationDetector {
    pub fn new(id: impl Into<String>, analysis_window_s: f64, min_confidence: f64) -> Self {
        Self {
            id: id.into(),
            analysis_window_s,
            min_confidence,
        }
    }

    /// Mirrors `OscillationDetector.consume()` field-for-field: phasor
    /// extraction -> positive-sequence magnitude -> trailing-window
    /// detrend -> Hann window -> real FFT -> DC-bin-excluded peak/total
    /// power confidence ratio -> threshold gate.
    pub fn consume(&self, wave: &ThreePhaseWaveform, up_to_s: f64) -> Vec<Finding> {
        let (frame_times, phasors) = wave.phasor_frames(phase_model::PHASOR_RATE_HZ);

        let mask: Vec<usize> = frame_times
            .iter()
            .enumerate()
            .filter(|(_, &t)| t <= up_to_s)
            .map(|(i, _)| i)
            .collect();
        if mask.len() < 8 {
            return Vec::new();
        }

        let v1 = ThreePhaseWaveform::positive_sequence(&[
            mask.iter().map(|&i| phasors[0][i]).collect(),
            mask.iter().map(|&i| phasors[1][i]).collect(),
            mask.iter().map(|&i| phasors[2][i]).collect(),
        ]);
        let t_masked: Vec<f64> = mask.iter().map(|&i| frame_times[i]).collect();
        let mag: Vec<f64> = v1.iter().map(|c| c.abs()).collect();

        let window_start = up_to_s - self.analysis_window_s;
        let win_idx: Vec<usize> = t_masked
            .iter()
            .enumerate()
            .filter(|(_, &t)| t >= window_start)
            .map(|(i, _)| i)
            .collect();
        if win_idx.len() < 8 {
            return Vec::new();
        }
        let t_win: Vec<f64> = win_idx.iter().map(|&i| t_masked[i]).collect();
        let mag_win: Vec<f64> = win_idx.iter().map(|&i| mag[i]).collect();

        let mean = mag_win.iter().sum::<f64>() / mag_win.len() as f64;
        let detrended: Vec<f64> = mag_win.iter().map(|m| m - mean).collect();
        let all_zero = detrended.iter().all(|d| d.abs() < 1e-12);
        if all_zero {
            return Vec::new();
        }

        let n = detrended.len();
        let dt: f64 = {
            let diffs: Vec<f64> = t_win.windows(2).map(|w| w[1] - w[0]).collect();
            diffs.iter().sum::<f64>() / diffs.len() as f64
        };

        // Hann window, matching numpy.hanning(n) exactly (both endpoints 0).
        let hann: Vec<f64> = (0..n)
            .map(|i| {
                if n <= 1 {
                    1.0
                } else {
                    0.5 - 0.5 * (2.0 * std::f64::consts::PI * i as f64 / (n as f64 - 1.0)).cos()
                }
            })
            .collect();
        let mut windowed: Vec<f64> = detrended
            .iter()
            .zip(&hann)
            .map(|(d, w)| d * w)
            .collect();

        let mut planner = RealFftPlanner::<f64>::new();
        let fft = planner.plan_fft_forward(n);
        let mut spectrum = fft.make_output_vec();
        if fft.process(&mut windowed, &mut spectrum).is_err() {
            return Vec::new();
        }

        let power: Vec<f64> = spectrum.iter().map(|c| c.norm()).collect();
        if power.len() < 2 {
            return Vec::new();
        }

        // Skip the DC bin (index 0), same as the Python reference.
        let (peak_idx, peak_power) = power[1..]
            .iter()
            .enumerate()
            .fold((0usize, f64::MIN), |(bi, bp), (i, &p)| {
                if p > bp {
                    (i, p)
                } else {
                    (bi, bp)
                }
            });
        let peak_idx = peak_idx + 1;
        let total_power: f64 = {
            let s: f64 = power[1..].iter().sum();
            if s == 0.0 {
                1.0
            } else {
                s
            }
        };
        let confidence = (peak_power / total_power).min(1.0);
        if confidence < self.min_confidence {
            return Vec::new();
        }

        let mode_hz = peak_idx as f64 / (n as f64 * dt);

        vec![Finding {
            detector_id: self.id.clone(),
            time_s: *t_win.last().unwrap(),
            kind: "oscillation".to_string(),
            confidence,
            mode_hz,
            window_s: self.analysis_window_s,
        }]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A synthetic 3-phase waveform whose |V1| magnitude oscillates at a
    /// known frequency around a constant mean -- the detector must recover
    /// that frequency, independent of any real fixture.
    fn synth_wave(mode_hz: f64, duration_s: f64) -> ThreePhaseWaveform {
        let sr = phase_model::SAMPLE_RATE_HZ;
        let n = (duration_s * sr) as usize;
        let f0 = phase_model::FUNDAMENTAL_HZ;
        let mut times = Vec::with_capacity(n);
        let mut va = Vec::with_capacity(n);
        let mut vb = Vec::with_capacity(n);
        let mut vc = Vec::with_capacity(n);
        for i in 0..n {
            let t = i as f64 / sr;
            let mag = 100.0 + 5.0 * (2.0 * std::f64::consts::PI * mode_hz * t).sin();
            let base = 2.0 * std::f64::consts::PI * f0 * t;
            times.push(t);
            va.push(mag * base.cos());
            vb.push(mag * (base - 2.0 * std::f64::consts::PI / 3.0).cos());
            vc.push(mag * (base + 2.0 * std::f64::consts::PI / 3.0).cos());
        }
        ThreePhaseWaveform::new(times, va, vb, vc).unwrap()
    }

    #[test]
    fn recovers_known_oscillation_frequency() {
        let wave = synth_wave(0.6333, 20.0);
        let det = OscillationDetector::new("test-osc", 15.0, 0.1);
        let findings = det.consume(&wave, 20.0);
        assert_eq!(findings.len(), 1, "expected one finding");
        let f = &findings[0];
        assert!(
            (f.mode_hz - 0.6333).abs() < 0.05,
            "mode_hz {} not close to 0.6333",
            f.mode_hz
        );
        assert!(f.confidence > 0.1);
    }

    #[test]
    fn no_finding_below_min_history() {
        let wave = synth_wave(0.6333, 0.05);
        let det = OscillationDetector::new("test-osc", 15.0, 0.1);
        assert!(det.consume(&wave, 0.05).is_empty());
    }

    #[test]
    fn no_finding_for_flat_magnitude() {
        let sr = phase_model::SAMPLE_RATE_HZ;
        let n = (20.0 * sr) as usize;
        let f0 = phase_model::FUNDAMENTAL_HZ;
        let mut times = Vec::with_capacity(n);
        let mut va = Vec::with_capacity(n);
        let mut vb = Vec::with_capacity(n);
        let mut vc = Vec::with_capacity(n);
        for i in 0..n {
            let t = i as f64 / sr;
            let base = 2.0 * std::f64::consts::PI * f0 * t;
            times.push(t);
            va.push(100.0 * base.cos());
            vb.push(100.0 * (base - 2.0 * std::f64::consts::PI / 3.0).cos());
            vc.push(100.0 * (base + 2.0 * std::f64::consts::PI / 3.0).cos());
        }
        let wave = ThreePhaseWaveform::new(times, va, vb, vc).unwrap();
        let det = OscillationDetector::new("test-osc", 15.0, 0.1);
        assert!(det.consume(&wave, 20.0).is_empty());
    }
}
