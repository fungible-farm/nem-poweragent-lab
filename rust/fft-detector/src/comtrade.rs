//! COMTRADE (IEEE C37.111) reader -- ASCII/1999-revision path only.
//!
//! `drewsilcock/comtrade` (MIT, crates.io `comtrade` v0.2.2) is the only
//! Rust COMTRADE crate that exists, but is unmaintained since 2022 and
//! self-described "WIP, not production ready" -- and pulls in
//! `derive_builder`/`regex`/`lazy_static`/`byteorder` for binary16/32/
//! float32/2013-timezone paths this project never emits (its own Python
//! writer only ever produces ASCII, revision "1999"). This module keeps
//! that crate's field semantics (multiplier/offset scaling, primary/
//! secondary factors, skew) -- the "harden the existing crate" intent --
//! but is a from-spec reimplementation scoped to the ASCII/1999 path,
//! which is the one path this project can actually round-trip-test
//! against real committed fixtures. Binary formats are rejected with a
//! clear error rather than silently mishandled.

use std::fmt;

#[derive(Debug)]
pub struct ParseError(pub String);

impl fmt::Display for ParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "COMTRADE parse error: {}", self.0)
    }
}
impl std::error::Error for ParseError {}

fn err(msg: impl Into<String>) -> ParseError {
    ParseError(msg.into())
}

#[derive(Debug, Clone, PartialEq)]
pub struct AnalogChannel {
    pub index: u32,
    pub name: String,
    pub phase: String,
    pub circuit_component_being_monitored: String,
    pub units: String,
    pub multiplier: f64,
    pub offset_adder: f64,
    pub skew: f64,
    pub min_value: f64,
    pub max_value: f64,
    pub primary_factor: f64,
    pub secondary_factor: f64,
    pub scaling_mode: char, // 'P' or 'S'
    /// Scaled engineering-unit values: raw * multiplier + offset_adder.
    pub data: Vec<f64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct StatusChannel {
    pub index: u32,
    pub name: String,
    pub data: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Comtrade {
    pub station_name: String,
    pub recording_device_id: String,
    pub line_frequency: f64,
    pub timestamps_us: Vec<f64>,
    pub analog_channels: Vec<AnalogChannel>,
    pub status_channels: Vec<StatusChannel>,
}

const SEP: char = ',';

fn split_line(line: &str) -> Vec<&str> {
    line.trim_end_matches(['\r', '\n']).split(SEP).collect()
}

fn parse_f64(s: &str, what: &str) -> Result<f64, ParseError> {
    s.trim()
        .parse::<f64>()
        .map_err(|_| err(format!("invalid float for {what}: '{s}'")))
}

fn parse_u32(s: &str, what: &str) -> Result<u32, ParseError> {
    s.trim()
        .parse::<u32>()
        .map_err(|_| err(format!("invalid integer for {what}: '{s}'")))
}

/// Parse a `.cfg` + `.dat` pair (ASCII data format, 1991/1999 revision).
pub fn parse(cfg_contents: &str, dat_contents: &str) -> Result<Comtrade, ParseError> {
    let mut lines = cfg_contents.lines();

    // Line 1: station_name,rec_dev_id[,rev_year]
    let header = lines.next().ok_or_else(|| err("empty .cfg file"))?;
    let header_fields = split_line(header);
    if header_fields.len() < 2 {
        return Err(err("station header line must have at least 2 fields"));
    }
    let station_name = header_fields[0].to_string();
    let recording_device_id = header_fields[1].to_string();

    // Line 2: TT,AAAa,DDDd
    let counts_line = lines.next().ok_or_else(|| err("missing channel-count line"))?;
    let counts = split_line(counts_line);
    if counts.len() != 3 {
        return Err(err("channel-count line must have 3 fields"));
    }
    let num_analog = {
        let tok = counts[1].trim();
        let digits = tok.trim_end_matches(|c: char| c.eq_ignore_ascii_case(&'a'));
        parse_u32(digits, "analog channel count")?
    };
    let num_status = {
        let tok = counts[2].trim();
        let digits = tok.trim_end_matches(|c: char| c.eq_ignore_ascii_case(&'d'));
        parse_u32(digits, "status channel count")?
    };

    // Analog channel lines: An,ch_id,ph,ccbm,uu,a,b,skew,min,max,primary,secondary,PS
    let mut analog_channels = Vec::with_capacity(num_analog as usize);
    for i in 0..num_analog {
        let line = lines
            .next()
            .ok_or_else(|| err(format!("missing analog channel line {i}")))?;
        let f = split_line(line);
        if f.len() != 13 {
            return Err(err(format!(
                "analog channel line {i} must have 13 fields, got {}",
                f.len()
            )));
        }
        analog_channels.push(AnalogChannel {
            index: parse_u32(f[0], "analog channel index")?,
            name: f[1].to_string(),
            phase: f[2].to_string(),
            circuit_component_being_monitored: f[3].to_string(),
            units: f[4].to_string(),
            multiplier: parse_f64(f[5], "analog multiplier")?,
            offset_adder: parse_f64(f[6], "analog offset")?,
            skew: parse_f64(f[7], "analog skew")?,
            min_value: parse_f64(f[8], "analog min")?,
            max_value: parse_f64(f[9], "analog max")?,
            primary_factor: parse_f64(f[10], "analog primary factor")?,
            secondary_factor: parse_f64(f[11], "analog secondary factor")?,
            scaling_mode: f[12].trim().chars().next().unwrap_or('P'),
            data: Vec::new(),
        });
    }

    // Status channel lines: Dn,ch_id,ph,ccbm,y
    let mut status_channels = Vec::with_capacity(num_status as usize);
    for i in 0..num_status {
        let line = lines
            .next()
            .ok_or_else(|| err(format!("missing status channel line {i}")))?;
        let f = split_line(line);
        if f.len() != 5 {
            return Err(err(format!("status channel line {i} must have 5 fields")));
        }
        status_channels.push(StatusChannel {
            index: parse_u32(f[0], "status channel index")?,
            name: f[1].to_string(),
            data: Vec::new(),
        });
    }

    // Line frequency.
    let freq_line = lines.next().ok_or_else(|| err("missing line-frequency line"))?;
    let line_frequency = parse_f64(freq_line.trim_end_matches(['\r', '\n']), "line frequency")?;

    // nrates line, then that many sample-rate lines (or one `0,<n>` line).
    let nrates_line = lines.next().ok_or_else(|| err("missing nrates line"))?;
    let nrates = parse_u32(nrates_line.trim_end_matches(['\r', '\n']), "nrates")?;
    let rate_lines = if nrates == 0 { 1 } else { nrates as usize };
    for _ in 0..rate_lines {
        lines.next().ok_or_else(|| err("missing sample-rate line"))?;
    }

    // Start timestamp, trigger timestamp (not needed for FFT detection --
    // the .dat file's own per-sample offsets are authoritative here).
    lines.next().ok_or_else(|| err("missing start timestamp line"))?;
    lines.next().ok_or_else(|| err("missing trigger timestamp line"))?;

    // File type.
    let file_type_line = lines.next().ok_or_else(|| err("missing file-type line"))?;
    let file_type = file_type_line.trim().to_ascii_uppercase();
    if file_type != "ASCII" {
        return Err(err(format!(
            "unsupported COMTRADE data format '{file_type}' -- only ASCII is supported"
        )));
    }

    // Timestamp multiplier (1999+ only; default 1.0 if absent).
    let timestamp_multiplier: f64 = lines
        .next()
        .and_then(|l| l.trim().parse::<f64>().ok())
        .unwrap_or(1.0);

    // --- .dat: n, timestamp_us, analog_1..analog_A, digital_1..digital_D ---
    let expected_fields = 2 + num_analog as usize + num_status as usize;
    let mut timestamps_us = Vec::new();
    for (row_i, line) in dat_contents.lines().enumerate() {
        let line = line.trim_end_matches(['\r', '\n', '\u{1a}']);
        if line.is_empty() {
            continue;
        }
        let f = split_line(line);
        if f.len() != expected_fields {
            return Err(err(format!(
                ".dat row {row_i} has {} fields, expected {expected_fields}",
                f.len()
            )));
        }
        let ts = parse_f64(f[1], "sample timestamp")? * timestamp_multiplier;
        timestamps_us.push(ts);
        for (ch_i, ch) in analog_channels.iter_mut().enumerate() {
            let raw = parse_f64(f[2 + ch_i], "analog sample value")?;
            ch.data.push(raw * ch.multiplier + ch.offset_adder);
        }
        for (ch_i, ch) in status_channels.iter_mut().enumerate() {
            let raw = parse_u32(f[2 + num_analog as usize + ch_i], "digital sample value")?;
            ch.data.push(raw as u8);
        }
    }

    Ok(Comtrade {
        station_name,
        recording_device_id,
        line_frequency,
        timestamps_us,
        analog_channels,
        status_channels,
    })
}

/// Convert a parsed 3-analog-channel (VA, VB, VC) COMTRADE record into a
/// `phase_model::ThreePhaseWaveform` -- the join point that lets every
/// downstream phasor/detector transform work unmodified.
pub fn to_waveform(record: &Comtrade) -> Result<phase_model::ThreePhaseWaveform, String> {
    if record.analog_channels.len() != 3 {
        return Err(format!(
            "expected exactly 3 analog channels (VA, VB, VC), got {}",
            record.analog_channels.len()
        ));
    }
    let times: Vec<f64> = record.timestamps_us.iter().map(|us| us / 1_000_000.0).collect();
    let va = record.analog_channels[0].data.clone();
    let vb = record.analog_channels[1].data.clone();
    let vc = record.analog_channels[2].data.clone();
    phase_model::ThreePhaseWaveform::new(times, va, vb, vc)
}

#[cfg(test)]
mod tests {
    use super::*;

    const CFG: &str = "STN,,1999\r\n3,3A,0D\r\n1,VA,A,,V,1.0,0.0,0.0,-100000,100000,1.0,1.0,P\r\n2,VB,B,,V,1.0,0.0,0.0,-100000,100000,1.0,1.0,P\r\n3,VC,C,,V,1.0,0.0,0.0,-100000,100000,1.0,1.0,P\r\n50\r\n0\r\n0,4\r\n01/01/2026,00:00:00.000000\r\n01/01/2026,00:00:00.000000\r\nASCII\r\n1.0\r\n";
    const DAT: &str = "1,0,1.0,2.0,3.0\r\n2,200,1.1,2.1,3.1\r\n3,400,1.2,2.2,3.2\r\n4,600,1.3,2.3,3.3\r\n";

    #[test]
    fn parses_ascii_1999_round_trip() {
        let record = parse(CFG, DAT).expect("parse should succeed");
        assert_eq!(record.station_name, "STN");
        assert_eq!(record.line_frequency, 50.0);
        assert_eq!(record.analog_channels.len(), 3);
        assert_eq!(record.analog_channels[0].data, vec![1.0, 1.1, 1.2, 1.3]);
        assert_eq!(record.analog_channels[1].data, vec![2.0, 2.1, 2.2, 2.3]);
        assert_eq!(record.timestamps_us, vec![0.0, 200.0, 400.0, 600.0]);
    }

    #[test]
    fn applies_multiplier_and_offset() {
        let cfg = CFG.replace("1,VA,A,,V,1.0,0.0", "1,VA,A,,V,2.0,5.0");
        let record = parse(&cfg, DAT).expect("parse should succeed");
        assert_eq!(record.analog_channels[0].data[0], 1.0 * 2.0 + 5.0);
    }

    #[test]
    fn rejects_binary_format() {
        let cfg = CFG.replace("ASCII", "BINARY");
        let err = parse(&cfg, DAT).unwrap_err();
        assert!(err.0.contains("only ASCII is supported"));
    }

    #[test]
    fn converts_to_waveform() {
        let record = parse(CFG, DAT).expect("parse should succeed");
        let wave = to_waveform(&record).expect("conversion should succeed");
        assert_eq!(wave.times, vec![0.0, 0.0002, 0.0004, 0.0006]);
        assert_eq!(wave.va, vec![1.0, 1.1, 1.2, 1.3]);
    }
}
