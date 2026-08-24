#!/usr/bin/env bash
#
# tour.sh -- narrated replay of `just check-lab8`'s two CI-gated spikes
# (0b, 0d). 0a/0c/0e need heavy external state (a built grid2op dataset, a
# network clone of sysand, a multi-container OperatorFabric stack) that the
# Justfile itself already excludes from the fast gate -- named here, not
# silently skipped. See labs/08-cim-gridy-phase0-spikes/README.md.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/tour_lib.sh

banner "Lab 8 -- cim-gridy Phase 0: Real-Tool Spikes"

narrate "Before building a grid-operator missions game, five prerequisite"
narrate "questions needed real, timeboxed spikes instead of a slide of"
narrate "vendor claims. All five got an honest verdict -- two run here."
narrate "(0a Grid2Op, 0c sysand, 0e OperatorFabric-vs-Bevy need heavier"
narrate "state than a demo GIF should carry -- see the lab README table.)"

narrate "0b: does a real native-Rust SysML v2 parser survive a 36-fixture"
narrate "GfSE corpus, not just this repo's own Lab 6 output?"

run_cmd "cargo run --manifest-path labs/08-cim-gridy-phase0-spikes/0b-sysml-v2-parser/Cargo.toml --release"

narrate "0d: do ufo-types and scryer-prolog actually coexist in one binary?"

run_cmd "cargo run --manifest-path labs/08-cim-gridy-phase0-spikes/0d-ufo-types-scryer-prolog/Cargo.toml --release"

banner "Lab 8: PASS (0b, 0d)"
