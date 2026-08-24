#!/usr/bin/env bash
#
# tour.sh -- narrated replay of `just check-lab9` (the fixture-based fast
# path; `just lab9-live` runs the real grid2op subprocess but needs a
# locally-built dataset first, so it's out of scope for a demo GIF).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/tour_lib.sh

banner "Lab 9 -- cim-gridy Phases 1-3: One Real Vertical Slice"

narrate "Lab 8 asked 'does each piece work alone?' This lab asks the"
narrate "harder question: does the whole chain work *together*?"
narrate "Grid2Op observation -> Bevy ECS -> a real SysML v2 type layer ->"
narrate "ufo-types' Satisfies<C> backed by an actual scryer-prolog query ->"
narrate "a Rhai mission FSM -> a DARE optimizer. One process, one grid,"
narrate "one contingency, exact assertions -- not five demos stapled together."

run_cmd "cargo test --manifest-path rust/Cargo.toml -p mission-engine --release"

narrate "(--release isn't a preference here -- scryer-prolog's debug build"
narrate "panics on an internal UB check unrelated to any of this code.)"

banner "Lab 9: PASS"
