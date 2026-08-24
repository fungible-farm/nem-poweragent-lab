#!/usr/bin/env bash
#
# tour.sh -- narrated replay of `just check-lab5` (the fast golden path).
# The two historical blackout scenarios (SA 2016 / Iberian 2025, ~10 real
# minutes of DPsim each) live behind `just check-lab5-scenarios` instead --
# too slow for a demo GIF, see that lab's own scenarios/ subdirectory.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/tour_lib.sh

banner "Lab 5 -- SPARTAN Chaos-Net: Transient Streams"

narrate "Every other lab assumes the grid has already settled down."
narrate "This one looks at the first fraction of a second after it hasn't --"
narrate "a real 200us-timestep EMT solve in DPsim, not a steady-state guess."
narrate "New topology every run: a real SimBench seed grid, rewired with a"
narrate "NetworkX Watts-Strogatz graph, still checked with a real power flow."

run_cmd "uv run labs/05-spartan-chaosnet-transient-stream/generate_topology.py"
run_cmd "uv run labs/05-spartan-chaosnet-transient-stream/verify_stream.py --step check"

narrate "Now the fun part: a grid-forming stabilizer, measured before/after,"
narrate "then translated back into a steady-state constraint question, then"
narrate "hardened against real cable-length signal delay. Three PRDs, one lab."

run_cmd "uv run labs/05-spartan-chaosnet-transient-stream/grid_forming.py --step check"
run_cmd "uv run labs/05-spartan-chaosnet-transient-stream/headroom_translation.py --step check"
run_cmd "uv run labs/05-spartan-chaosnet-transient-stream/delay_compensation.py --step check"

narrate "(The SA 2016 and Iberian 2025 blackout reproductions live here too --"
narrate "each is ~10 real minutes of solving, so they get their own opt-in"
narrate "'just check-lab5-scenarios' instead of a spot in this GIF.)"

banner "Lab 5: PASS"
