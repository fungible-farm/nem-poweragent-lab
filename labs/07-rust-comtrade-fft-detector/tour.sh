#!/usr/bin/env bash
#
# tour.sh -- narrated replay of `just check-lab7`.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/tour_lib.sh

banner "Lab 7 -- Rust FFT/COMTRADE Oscillation Detector"

narrate "Everything so far ran in Python. Real relays and DFRs don't run"
narrate "Python -- they write COMTRADE files (IEEE C37.111), the same"
narrate "format substation hardware has used for decades."
narrate "This lab writes a real COMTRADE file from Python, then reads it"
narrate "back with an independent Rust FFT pipeline (realfft/rustfft, no"
narrate "invented libraries) and checks it recovers the same oscillation."

run_cmd "cargo run --manifest-path rust/Cargo.toml -p fft-detector --release -- \\
    labs/07-rust-comtrade-fft-detector/fixtures/local_mode.cfg \\
    labs/07-rust-comtrade-fft-detector/fixtures/local_mode.dat \\
    --check labs/07-rust-comtrade-fft-detector/fixtures/local_mode.expected.json"
run_cmd "cargo run --manifest-path rust/Cargo.toml -p fft-detector --release -- \\
    labs/07-rust-comtrade-fft-detector/fixtures/inter_area_mode.cfg \\
    labs/07-rust-comtrade-fft-detector/fixtures/inter_area_mode.dat \\
    --check labs/07-rust-comtrade-fft-detector/fixtures/inter_area_mode.expected.json"

narrate "Two languages, one file format, one answer. That's the whole point."
banner "Lab 7: PASS"
