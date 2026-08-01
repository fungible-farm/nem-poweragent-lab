#!/usr/bin/env bash
#
# run_lab4.sh -- the end-to-end proof that Lab 4 Part A works.
#
# Separate from run_labs_1_3.sh (rather than folded in) because Lab 4 has a
# materially different nature: it depends on data this sandbox's egress
# policy cannot reach (nemweb.com.au and github.com both return 403 --
# "destination host not allowed", confirmed via /root/.ccr, not transient),
# so this script proves the mechanism (DUID mapping -> dispatch imposition
# -> AC power flow -> balance check) against a documented, illustrative
# sample rather than a live pull. See reconcile.py's module docstring for
# the full accounting of what's real (snemSA.m, every pandapower.runpp()
# result, the DUID names) versus what's a stand-in (the SCADAVALUE figures).
#
# Only Part A (digital-twin reconciliation) is implemented and proven here.
# Part B (constraint-equation literacy via NEM_constraints) and Part C (the
# 2016 SA Black System case study) both need the same unreachable NEMWeb/
# github.com access and are NOT implemented in this sandbox pass -- see
# labs/04-aemo-digital-twin-reconciliation/README.md "Sandbox notes".
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

section "0/4  uv sync -- install pinned dependencies"
uv sync

section "1/4  Fetch CSIRO Synthetic-NEM-2000-Bus case data (idempotent, checksum-verified)"
run_step "fetch_csiro_nem_data.py" uv run scripts/fetch_csiro_nem_data.py

section "2/4  Lab 4 Part A -- digital-twin reconciliation (snemSA.m, illustrative sample dispatch)"
run_step "Lab 4 --step dispatch"   uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step dispatch
run_step "Lab 4 --step map"        uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step map
run_step "Lab 4 --step reconcile"  uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step reconcile
run_step "Lab 4 --step check (fixture match)" \
    uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step check

section "3/4  pytest -- Lab 4 test"
run_step "pytest labs/04-aemo-digital-twin-reconciliation/" \
    uv run python -m pytest labs/04-aemo-digital-twin-reconciliation/ -q

section "4/4  Summary"
if [ "$FAILED" -eq 0 ]; then
    echo "PASS: Lab 4 Part A ran end to end and matched its committed fixture."
    echo "NOTE: Part A uses an illustrative sample dispatch, not a live NEMOSIS"
    echo "pull -- see reconcile.py's module docstring. Parts B/C are not built."
    exit 0
else
    echo "FAIL: one or more steps above failed -- see the FAIL lines for detail."
    exit 1
fi
