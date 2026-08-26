#!/usr/bin/env bash
#
# tour.sh -- narrated replay of the real systhread CLI, Phase 1's shipped capability.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/tour_lib.sh

banner "systhread -- SysML v2 digital-thread CLI (Phase 1)"

narrate "Phase 0 built the core Rust library. Phase 1 is what makes it a real"
narrate "tool: a CLI, an MCP server (same binary, --stdio), b00t packaging,"
narrate "a just module any project can import, and a manifest ledgrrr can read."
narrate "One instance-data file in, a validated model and rendered artifacts out."

run_cmd "cargo build -p systhread-cli --manifest-path rust/Cargo.toml --release"

TOUR_OUT="$(mktemp -d)"
export PATH="$PWD/rust/target/release:$PATH"

narrate "First: check. Generate the .sysml text, validate it, nothing written to disk."
run_cmd "systhread check --track pipeline rust/systhread-cli/tests/fixtures/pipeline_phases_instances.yaml"

narrate "Now: render. Same generation, plus iso-IR translation, SVG rendering,"
narrate "and a content-hashed manifest.json -- the whole ledgrrr contract."
run_cmd "systhread render --track pipeline rust/systhread-cli/tests/fixtures/pipeline_phases_instances.yaml --out ${TOUR_OUT}"

narrate "What got written:"
run_cmd "ls ${TOUR_OUT}"

narrate "And the manifest -- what ledgrrr actually reads, no systhread-internal knowledge required:"
run_cmd "cat ${TOUR_OUT}/manifest.json"

rm -rf "$TOUR_OUT"

banner "systhread Phase 1: PASS"
