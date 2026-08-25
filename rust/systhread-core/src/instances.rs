use serde::Deserialize;
use std::path::Path;

#[derive(Debug, Deserialize)]
pub struct DigitalThreadInstances {
    #[serde(default)]
    pub agents: Vec<AgentInstance>,
    #[serde(default)]
    pub mcp_servers: Vec<ServerOrSourceInstance>,
    #[serde(default)]
    pub data_sources: Vec<ServerOrSourceInstance>,
}

#[derive(Debug, Deserialize)]
pub struct AgentInstance {
    pub name: String,
    pub source: String,
    #[serde(default)]
    pub uses: Option<String>,
    pub refresh_cadence: String,
    pub owner: String,
}

/// MCPServer and DataSource instances share this exact field set in Lab 6's schema
/// (name/source/refresh_cadence/owner, no `uses`) -- see generate_sysml.py's own
/// render_digital_thread, which reads both kinds through identical dict keys.
#[derive(Debug, Deserialize)]
pub struct ServerOrSourceInstance {
    pub name: String,
    pub source: String,
    pub refresh_cadence: String,
    pub owner: String,
}

#[derive(Debug, Deserialize)]
pub struct GridInstances {
    #[serde(default)]
    pub buses: Vec<BusInstance>,
    #[serde(default)]
    pub generators: Vec<GeneratorInstance>,
    #[serde(default)]
    pub lines: Vec<LineInstance>,
}

#[derive(Debug, Deserialize)]
pub struct BusInstance {
    pub name: String,
    pub source: String,
    pub voltage_kv: f64,
    pub cim_class_uri: String,
}

#[derive(Debug, Deserialize)]
pub struct GeneratorInstance {
    pub name: String,
    pub source: String,
    pub bus: String,
    pub rated_mw: f64,
    pub cim_class_uri: String,
}

#[derive(Debug, Deserialize)]
pub struct LineInstance {
    pub name: String,
    pub source: String,
    pub from_bus: String,
    pub to_bus: String,
    pub kind: String,
    #[serde(default)]
    pub length_km: Option<f64>,
    pub cim_class_uri: String,
}

#[derive(Debug, Deserialize)]
pub struct PipelinePhasesInstances {
    #[serde(default)]
    pub phases: Vec<PhaseInstance>,
}

#[derive(Debug, Deserialize)]
pub struct PhaseInstance {
    pub name: String,
    pub source: String,
    pub role: String,
    #[serde(default)]
    pub next: Option<String>,
}

pub fn load_digital_thread(path: &Path) -> DigitalThreadInstances {
    let text = std::fs::read_to_string(path)
        .unwrap_or_else(|e| panic!("read {}: {e}", path.display()));
    serde_norway::from_str(&text).unwrap_or_else(|e| panic!("parse {}: {e}", path.display()))
}

pub fn load_grid(path: &Path) -> GridInstances {
    let text = std::fs::read_to_string(path)
        .unwrap_or_else(|e| panic!("read {}: {e}", path.display()));
    serde_norway::from_str(&text).unwrap_or_else(|e| panic!("parse {}: {e}", path.display()))
}

pub fn load_pipeline(path: &Path) -> PipelinePhasesInstances {
    let text = std::fs::read_to_string(path)
        .unwrap_or_else(|e| panic!("read {}: {e}", path.display()));
    serde_norway::from_str(&text).unwrap_or_else(|e| panic!("parse {}: {e}", path.display()))
}
