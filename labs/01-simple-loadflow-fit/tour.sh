#!/usr/bin/env bash
#
# tour.sh -- narrated replay of `just check-lab1`. Runs the same command the
# real gate runs, nothing new. See scripts/tour_lib.sh for why the story
# has to be `echo`ed rather than just left as comments.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/tour_lib.sh

banner "Lab 1 (Simple) -- Load-Flow Parameter Fit"

narrate "Your SCADA meter says one thing. Your model says another. Someone"
narrate "has to be wrong, and it's usually not the meter."
narrate "This lab bisection-searches for a load-scaling factor until a real"
narrate "pandapower.runpp() agrees with a fixed field measurement at bus 2008."

run_cmd "uv run labs/01-simple-loadflow-fit/run.py --step check"

narrate "No LLM guessed that number. A bisection search proposed it, physics graded it."
banner "Lab 1: PASS"
