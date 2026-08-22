//! Optional PyO3 extension module (Cargo feature `python`, `maturin build
//! --features python`) -- a developer-convenience fast path only. The
//! primary, always-required interchange between the Python scenario
//! engine and this detector stays the file-based COMTRADE format (see
//! `comtrade.rs`'s module docs for why); this just lets calibration/test
//! code call the detector in-process instead of shelling out to the CLI
//! binary. Pattern confirmed against real local precedent in
//! `~/.b00t/vendor/tomllm/src/python.rs` and `~/.b00t/b00t-lib-chat`
//! (`pyo3 = { features = ["extension-module"] }`, `#[pyclass]`/
//! `#[pymethods]`/`#[pymodule]`).

use pyo3::prelude::*;

use crate::comtrade::{parse as parse_comtrade, to_waveform};
use crate::detector::OscillationDetector;

#[pyclass(name = "Finding")]
#[derive(Clone)]
pub struct PyFinding {
    #[pyo3(get)]
    pub detector_id: String,
    #[pyo3(get)]
    pub time_s: f64,
    #[pyo3(get)]
    pub kind: String,
    #[pyo3(get)]
    pub confidence: f64,
    #[pyo3(get)]
    pub mode_hz: f64,
    #[pyo3(get)]
    pub window_s: f64,
}

impl From<crate::detector::Finding> for PyFinding {
    fn from(f: crate::detector::Finding) -> Self {
        Self {
            detector_id: f.detector_id,
            time_s: f.time_s,
            kind: f.kind,
            confidence: f.confidence,
            mode_hz: f.mode_hz,
            window_s: f.window_s,
        }
    }
}

/// Parse a COMTRADE `.cfg`/`.dat` pair (as strings) and run the FFT
/// oscillation detector across the whole record.
#[pyfunction]
fn detect_oscillation(
    cfg_contents: &str,
    dat_contents: &str,
    analysis_window_s: f64,
    min_confidence: f64,
) -> PyResult<Vec<PyFinding>> {
    let record = parse_comtrade(cfg_contents, dat_contents)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
    let wave = to_waveform(&record).map_err(pyo3::exceptions::PyValueError::new_err)?;
    let up_to_s = wave.duration_s();
    let detector = OscillationDetector::new("oscillation-fft-detector", analysis_window_s, min_confidence);
    Ok(detector
        .consume(&wave, up_to_s)
        .into_iter()
        .map(PyFinding::from)
        .collect())
}

#[pymodule]
pub fn fft_detector(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyFinding>()?;
    m.add_function(wrap_pyfunction!(detect_oscillation, m)?)?;
    Ok(())
}
