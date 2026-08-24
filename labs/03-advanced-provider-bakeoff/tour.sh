#!/usr/bin/env bash
#
# tour.sh -- narrated replay of `just check-lab3`.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/tour_lib.sh

banner "Lab 3 (Advanced) -- Multi-Provider Bake-off"

narrate "\"Which provider is actually good enough for this?\" is usually"
narrate "answered with a vibe. This lab answers it with a scorecard:"
narrate "the same three fitting tasks, the same tolerances, the same"
narrate "scorer, run against every provider policy -- apples to apples."
narrate "(Read the README before trusting the word 'provider' too much.)"

run_cmd "uv run labs/03-advanced-provider-bakeoff/orchestrator.py --step check"
run_cmd "uv run labs/03-advanced-provider-bakeoff/spike_pypowsybl.py --step check"

narrate "Scorecard, chart, and receipts -- not an anecdote."
banner "Lab 3: PASS"
