#!/usr/bin/env bash
#
# tour.sh -- narrated replay of `just check-lab4`.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/tour_lib.sh

banner "Lab 4 -- Real AEMO Data: Digital-Twin Reconciliation"

narrate "Every other lab in this repo is synthetic and offline -- safe, fast,"
narrate "easy to dismiss as a toy. This one pulls one real day of South"
narrate "Australian dispatch data from AEMO's own public archive and asks a"
narrate "synthetic grid model to reconstruct what actually happened."
narrate "Spoiler: it doesn't, exactly. Explaining *why*, with a real number,"
narrate "is the actual point -- not pretending a synthetic topology is a twin."

run_cmd "uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step check"

banner "Lab 4: PASS"
