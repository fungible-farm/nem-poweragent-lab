//! Rust FFT/COMTRADE anomaly-detector testbench (Lab 7).
//!
//! Reads a COMTRADE (.cfg/.dat) transient record -- the same file format
//! real relays/DFRs emit -- and runs a `realfft`-based oscillation
//! detector that mirrors
//! `labs/_shared/scenario_engine/detectors.py::OscillationDetector`
//! field-for-field, proving the generate (Python)/detect (Rust) round
//! trip works end-to-end before any real hardware is in the loop.

pub mod comtrade;
pub mod detector;

#[cfg(feature = "python")]
pub mod python;

pub use comtrade::{parse as parse_comtrade, to_waveform, Comtrade};
pub use detector::{Finding, OscillationDetector};
