#!/usr/bin/env bash
#
# tour.sh -- narrated replay of `just check-lab2`.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/tour_lib.sh

banner "Lab 2 (Medium) -- Interconnection / Asset-Provisioning Screening"

narrate "A new 250 MW generator wants to connect at bus 175. The operator's"
narrate "question isn't 'does it work today' -- it's 'what if a line trips"
narrate "at the exact wrong moment.' That's an N-1 contingency screen."
narrate "21 nearby lines, dropped one at a time, as genuinely parallel OS"
narrate "processes -- not a for-loop wearing a parallel costume."

run_cmd "uv run labs/02-medium-interconnection-screening/workflow.py --step check"
run_cmd "uv run labs/02-medium-interconnection-screening/pypowsybl_cross_check.py --step check"

narrate "Cross-checked against a second, independent solver (PowSyBl) --"
narrate "because agreeing with yourself twice isn't the same as being right."

run_cmd "uv run labs/02-medium-interconnection-screening/render_network_diagram.py"

banner "Lab 2: PASS"
