//! Phase model — the oxidized Python `phase_model.py` (PSCADOSSE).
//!
//! One canonical 3-phase waveform state machine generates every view:
//! the raw samples ARE the machine, and the C37.118 phasors, positive
//! sequence, SCADA RMS, and anomaly (peak-deviation) signal are transforms of
//! the same states — so no view can disagree about what the waveform was.
//!
//! This crate is the "simulation computation compiled into WASM and shipped
//! to the browser" piece of the demo architecture: the Dioxus UI (future)
//! loads this crate as WASM, replays the real DPsim log client-side, and
//! renders the feeds on canvas with the computation running in the browser.
//! `rust/phase-model/src/ring.rs` provides the lock-per-consumer ring buffer
//! distribution primitive.
//!
//! License MIT OR Apache-2.0 (golden-path policy, see docs/PSCADOSSE.md).

pub mod ring;

use std::f64::consts::PI;

#[cfg(target_arch = "wasm32")]
use wasm_bindgen::prelude::*;

/// NEM fundamental (50 Hz); the phasor DFT is evaluated at this bin.
pub const FUNDAMENTAL_HZ: f64 = 50.0;
/// Default recording sample rate (DPsim log step 200 us -> 5000 Hz).
pub const SAMPLE_RATE_HZ: f64 = 5000.0;
/// C37.118 synchrophasor reporting rate (frames per second), PDU output.
pub const PHASOR_RATE_HZ: u32 = 100;
/// SCADA/EMS update cadence (s), the classic control-center telemetry rate.
pub const SCADA_UPDATE_S: f64 = 4.0;

/// Minimal complex number (avoids a num-complex dependency for the DFT).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Complex {
    pub re: f64,
    pub im: f64,
}

impl Complex {
    pub const fn new(re: f64, im: f64) -> Self {
        Self { re, im }
    }
    pub fn abs(self) -> f64 {
        (self.re * self.re + self.im * self.im).sqrt()
    }
    pub fn scale(self, f: f64) -> Self {
        Self::new(self.re * f, self.im * f)
    }
}

impl std::ops::Add for Complex {
    type Output = Self;
    fn add(self, o: Self) -> Self {
        Self::new(self.re + o.re, self.im + o.im)
    }
}

impl std::ops::Mul for Complex {
    type Output = Self;
    fn mul(self, o: Self) -> Self {
        Self::new(self.re * o.re - self.im * o.im, self.re * o.im + self.im * o.re)
    }
}

/// The waveform state machine: the ordered 3-phase instantaneous-voltage
/// states, and the source every derived view is generated from.
#[derive(Debug, Clone)]
pub struct ThreePhaseWaveform {
    pub times: Vec<f64>,
    pub va: Vec<f64>,
    pub vb: Vec<f64>,
    pub vc: Vec<f64>,
}

impl ThreePhaseWaveform {
    /// Build from aligned sample arrays (validated lengths).
    pub fn new(
        times: Vec<f64>,
        va: Vec<f64>,
        vb: Vec<f64>,
        vc: Vec<f64>,
    ) -> Result<Self, String> {
        let n = times.len();
        if n != va.len() || n != vb.len() || n != vc.len() {
            return Err("times/va/vb/vc must all have the same length".into());
        }
        if n < 2 {
            return Err("need at least two samples".into());
        }
        Ok(Self { times, va, vb, vc })
    }

    /// Parse a dpsim_transient_log.json dict (real DPsim output).
    pub fn from_log_json(json: &str) -> Result<Self, String> {
        #[derive(serde::Deserialize)]
        struct Log {
            times: Vec<f64>,
            va: Vec<f64>,
            vb: Vec<f64>,
            vc: Vec<f64>,
        }
        let log: Log = serde_json::from_str(json).map_err(|e| e.to_string())?;
        Self::new(log.times, log.va, log.vb, log.vc)
    }

    /// Recording duration (s) = last sample time.
    pub fn duration_s(&self) -> f64 {
        *self.times.last().unwrap_or(&0.0)
    }

    /// C37.118-style synchrophasors for all three phases, at `rate_hz`.
    ///
    /// One-cycle DFT at FUNDAMENTAL_HZ, frame centered every 1/rate_hz s
    /// (overlapping windows — a PMU's standard estimate). Every phase goes
    /// through the identical estimator, generated from the same states.
    /// Returns (frame_times_s, [complex phasors; 3]).
    pub fn phasor_frames(&self, rate_hz: u32) -> (Vec<f64>, [Vec<Complex>; 3]) {
        let n_cycle = (SAMPLE_RATE_HZ / FUNDAMENTAL_HZ).round() as usize; // 100 @ 5 kHz
        let stride = ((SAMPLE_RATE_HZ / rate_hz as f64).round() as usize).max(1); // 50 @ 100 Hz
        let n0 = n_cycle / 2;
        let weights: Vec<Complex> = (0..n_cycle)
            .map(|k| {
                let a = -2.0 * PI * k as f64 / n_cycle as f64;
                Complex::new(a.cos(), a.sin())
            })
            .collect();

        let series = [&self.va, &self.vb, &self.vc];
        let n = self.times.len();
        let mut frame_times: Vec<f64> = Vec::new();
        let mut acc: [Vec<Complex>; 3] = [Vec::new(), Vec::new(), Vec::new()];
        let mut center = n0;
        while center < n - n0 {
            frame_times.push(self.times[center]);
            for (acc_phase, series_phase) in acc.iter_mut().zip(series.iter()) {
                let mut x = Complex::new(0.0, 0.0);
                for (k, w) in weights.iter().enumerate() {
                    let v = series_phase[center - n0 + k];
                    x = x + Complex::new(v, 0.0) * *w;
                }
                acc_phase.push(x.scale(2.0 / n_cycle as f64));
            }
            center += stride;
        }
        (frame_times, acc)
    }

    /// Positive-sequence phasor (symmetrical components), complex per frame.
    ///
    /// V1 = (Va + a*Vb + a^2*Vc) / 3 with a = e^(j 120 deg). A balanced system
    /// keeps |V1| at the phase amplitude; a line-to-ground fault drops it.
    pub fn positive_sequence(phasors: &[Vec<Complex>; 3]) -> Vec<Complex> {
        let a = Complex::new((2.0 * PI / 3.0).cos(), (2.0 * PI / 3.0).sin());
        phasors[0]
            .iter()
            .zip(&phasors[1])
            .zip(&phasors[2])
            .map(|((va, vb), vc)| (*va + a * *vb + (a * a) * *vc).scale(1.0 / 3.0))
            .collect()
    }

    /// Peak deviation magnitude per window — the anomaly-rate signal.
    ///
    /// Deviation(t) = max over phases of max(0, |v(t)| - reference_peak),
    /// reference_peak = that phase's pre-fault peak (states before
    /// `trigger_s`). Returns [(window_start_s, window_end_s, peak_dev_V)].
    pub fn peak_deviation_bins(
        &self,
        trigger_s: f64,
        window_s: f64,
    ) -> Vec<(f64, f64, f64)> {
        let mut refs = [0.0f64; 3];
        for (p, series) in refs.iter_mut().zip([&self.va, &self.vb, &self.vc]) {
            for (t, v) in self.times.iter().zip(series.iter()) {
                if *t < trigger_s {
                    *p = p.max(v.abs());
                }
            }
        }
        let mut devs = Vec::with_capacity(self.times.len());
        for i in 0..self.times.len() {
            let d = [self.va[i], self.vb[i], self.vc[i]]
                .iter()
                .enumerate()
                .map(|(p, v)| (v.abs() - refs[p]).max(0.0))
                .fold(0.0f64, f64::max);
            devs.push(d);
        }

        let end = self.duration_s();
        let mut start = 0.0;
        let mut bins = Vec::new();
        while start < end {
            let win_end = (start + window_s).min(end);
            let mut peak = 0.0f64;
            for i in 0..self.times.len() {
                if self.times[i] >= start && self.times[i] < win_end {
                    peak = peak.max(devs[i]);
                }
            }
            bins.push((start, win_end, peak));
            start = win_end;
        }
        bins
    }
}

/// WASM exports — the "simulation computation compiled into WASM, shipped to
/// the browser" layer. Free functions (wasm-bindgen can't export Vec<f64>
/// struct fields); each takes the real log JSON and returns the computed
/// arrays, so the Dioxus UI drives the whole computation client-side.
#[cfg(target_arch = "wasm32")]
#[wasm_bindgen]
pub fn wasm_raw_times(log_json: &str) -> Result<Vec<f64>, JsValue> {
    ThreePhaseWaveform::from_log_json(log_json)
        .map(|w| w.times)
        .map_err(|e| JsValue::from_str(&e))
}

#[cfg(target_arch = "wasm32")]
#[wasm_bindgen]
pub fn wasm_raw_va(log_json: &str) -> Result<Vec<f64>, JsValue> {
    ThreePhaseWaveform::from_log_json(log_json)
        .map(|w| w.va)
        .map_err(|e| JsValue::from_str(&e))
}

#[cfg(target_arch = "wasm32")]
#[wasm_bindgen]
pub fn wasm_raw_vb(log_json: &str) -> Result<Vec<f64>, JsValue> {
    ThreePhaseWaveform::from_log_json(log_json)
        .map(|w| w.vb)
        .map_err(|e| JsValue::from_str(&e))
}

#[cfg(target_arch = "wasm32")]
#[wasm_bindgen]
pub fn wasm_raw_vc(log_json: &str) -> Result<Vec<f64>, JsValue> {
    ThreePhaseWaveform::from_log_json(log_json)
        .map(|w| w.vc)
        .map_err(|e| JsValue::from_str(&e))
}

#[cfg(target_arch = "wasm32")]
#[wasm_bindgen]
pub fn wasm_frame_times(log_json: &str, rate_hz: u32) -> Result<Vec<f64>, JsValue> {
    ThreePhaseWaveform::from_log_json(log_json)
        .map(|w| w.phasor_frames(rate_hz).0)
        .map_err(|e| JsValue::from_str(&e))
}

fn phasor_mags(log_json: &str, rate_hz: u32, phase: usize) -> Result<Vec<f64>, String> {
    let wave = ThreePhaseWaveform::from_log_json(log_json)?;
    Ok(wave
        .phasor_frames(rate_hz)
        .1[phase]
        .iter()
        .map(|c| c.abs())
        .collect())
}

#[cfg(target_arch = "wasm32")]
#[wasm_bindgen]
pub fn wasm_va_phasor_mag(log_json: &str, rate_hz: u32) -> Result<Vec<f64>, JsValue> {
    phasor_mags(log_json, rate_hz, 0).map_err(|e| JsValue::from_str(&e))
}

#[cfg(target_arch = "wasm32")]
#[wasm_bindgen]
pub fn wasm_vb_phasor_mag(log_json: &str, rate_hz: u32) -> Result<Vec<f64>, JsValue> {
    phasor_mags(log_json, rate_hz, 1).map_err(|e| JsValue::from_str(&e))
}

#[cfg(target_arch = "wasm32")]
#[wasm_bindgen]
pub fn wasm_vc_phasor_mag(log_json: &str, rate_hz: u32) -> Result<Vec<f64>, JsValue> {
    phasor_mags(log_json, rate_hz, 2).map_err(|e| JsValue::from_str(&e))
}

#[cfg(target_arch = "wasm32")]
#[wasm_bindgen]
pub fn wasm_pos_sequence_mag(log_json: &str, rate_hz: u32) -> Result<Vec<f64>, JsValue> {
    let wave = ThreePhaseWaveform::from_log_json(log_json).map_err(|e| JsValue::from_str(&e))?;
    let (_, ph) = wave.phasor_frames(rate_hz);
    Ok(ThreePhaseWaveform::positive_sequence(&ph)
        .iter()
        .map(|c| c.abs())
        .collect())
}

#[cfg(target_arch = "wasm32")]
#[wasm_bindgen]
pub fn wasm_peak_deviation_bins(
    log_json: &str,
    trigger_s: f64,
    window_s: f64,
) -> Result<Vec<f64>, JsValue> {
    let wave = ThreePhaseWaveform::from_log_json(log_json).map_err(|e| JsValue::from_str(&e))?;
    let mut out = Vec::new();
    for (s, e, p) in wave.peak_deviation_bins(trigger_s, window_s) {
        out.extend([s, e, p]);
    }
    Ok(out)
}
