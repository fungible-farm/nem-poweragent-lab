#!/usr/bin/env bash
#
# tour.sh -- narrated replay of `just check-lab6` (scripts/demo_lab6.sh).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/tour_lib.sh

banner "Lab 6 -- SysML v2 Digital Thread"

narrate "Does a systems-modelling language actually generalize, or does it"
narrate "just work on the one diagram in the vendor's own slide deck?"
narrate "Same generator/validator/renderer, two very different jobs:"
narrate "this repo's own agent/MCP/data-source inventory, and a real"
narrate "bus/generator/line cluster pulled straight out of the CSIRO case."
narrate "One schema edit -> one command -> regenerated artifacts. No hands."

run_cmd "./scripts/demo_lab6.sh"

banner "Lab 6: PASS"
