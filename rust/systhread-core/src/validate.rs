/// Syntax gate for generated `.sysml` text, using the real native-Rust SysML v2 parser
/// (`sysml-v2-parser`, MIT) rather than a hand-rolled structural stand-in -- Lab 6's own
/// `validate_sysml.py` only used a line-pattern checker because no working Rust parser existed
/// at the time; this repo already spiked `sysml-v2-parser` against Lab 6's own generated output
/// with a confirmed 3/3 pass (labs/08-cim-gridy-phase0-spikes/0b-sysml-v2-parser/).
pub fn is_valid_sysml(text: &str) -> Result<(), String> {
    sysml_v2_parser::parse(text)
        .map(|_root_namespace| ())
        .map_err(|e| e.to_string())
}
