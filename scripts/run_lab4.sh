#!/usr/bin/env bash
#
# run_lab4.sh -- the end-to-end proof that Lab 4 (Part A + Part B required,
# Part C optional) works.
#
# Separate from run_labs_1_3.sh (rather than folded in) because Lab 4 has a
# materially different nature: it depends on live external data (AEMO's
# public NEMWeb MMS archive via NEMOSIS, and the vendored NEM_constraints
# decoder), not just the CSIRO case files every other lab uses. This script
# fetches one real day of SA1 dispatch data, maps real DUIDs onto snemSA.m's
# synthetic generators, runs a real pandapower.runpp() reconciliation against
# AEMO's actual reported flow, decodes a real binding constraint, and checks
# both against committed fixtures -- see
# labs/04-aemo-digital-twin-reconciliation/README.md for the full walkthrough
# and "Sandbox notes" for what's real versus a documented stand-in.
#
# Part C (the 2016 SA Black System case study) is optional and not run by
# this script by default -- see the README's step 6 to run it separately.
#
# Usage:
#   ./scripts/run_lab4.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

FAILED=0
BANNER_WIDTH=78

section() {
    printf '\n%s\n' "$(printf '=%.0s' $(seq 1 "$BANNER_WIDTH"))"
    printf '%s\n' "$1"
    printf '%s\n' "$(printf '=%.0s' $(seq 1 "$BANNER_WIDTH"))"
}

run_step() {
    local description="$1"
    shift
    echo "--- ${description}"
    if "$@"; then
        echo "    PASS: ${description}"
    else
        echo "    FAIL: ${description}"
        FAILED=1
    fi
}

section "0/5  uv sync -- install pinned dependencies"
uv sync

section "1/5  Fetch CSIRO Synthetic-NEM-2000-Bus case data (idempotent, checksum-verified)"
run_step "fetch_csiro_nem_data.py" uv run scripts/fetch_csiro_nem_data.py

section "2/5  Lab 4 Part A -- fetch real SA1 dispatch data and map real DUIDs"
run_step "fetch_day.py --region SA1 --date 2026-06-15" \
    uv run labs/04-aemo-digital-twin-reconciliation/fetch_day.py --region SA1 --date 2026-06-15
run_step "map_duids.py" \
    uv run labs/04-aemo-digital-twin-reconciliation/map_duids.py

section "3/5  Lab 4 Part A -- digital-twin reconciliation (real pandapower.runpp())"
run_step "reconcile.py" \
    uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py
run_step "reconcile.py --step check (fixture match)" \
    uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step check

section "4/5  Lab 4 Part B -- binding constraint decode (real NEM_constraints)"
run_step "explain_constraint.py" \
    uv run labs/04-aemo-digital-twin-reconciliation/explain_constraint.py

section "5/5  pytest -- Lab 4 test"
run_step "pytest labs/04-aemo-digital-twin-reconciliation/" \
    uv run python -m pytest labs/04-aemo-digital-twin-reconciliation/ -q

echo
if [ "$FAILED" -eq 0 ]; then
    echo "PASS: Lab 4 (Part A + Part B) ran end to end against real live NEMWeb data and"
    echo "matched its committed fixtures. Part C (2016 SA Black System, optional) is not"
    echo "run by this script -- see the lab's README step 6 to run it separately."
    exit 0
else
    echo "FAIL: one or more steps above failed -- see the FAIL lines for detail."
    exit 1
fi
