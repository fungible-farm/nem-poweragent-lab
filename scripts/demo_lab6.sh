#!/usr/bin/env bash
#
# demo_lab6.sh -- Lab 6's chained pipeline: one command running both tracks
# end to end, per PRD-0006's Definition of Done ("one schema edit -> one
# command -> three regenerated artifacts, no manual edits anywhere").
#
# What it does, in order:
#   1. build_k8s_fixture.py   -- re-derive fixtures/k8s_snapshot.json from
#                                 this repo's real kube/*.yaml manifests
#                                 (Track A's own input; a --step check, not
#                                 a --step run, since this is meant to be
#                                 stable unless kube/*.yaml itself changes).
#   2. generate_sysml.py      -- LinkML instance data -> .sysml text, both
#                                 tracks.
#   3. validate_sysml.py      -- the named structural syntax gate, both
#                                 tracks' fixtures.
#   4. translate_iso_ir.py    -- .sysml parts/containment -> iso-IR JSON,
#                                 both tracks.
#   5. render_diagram.py      -- iso-IR JSON -> deterministic isometric SVG,
#                                 both tracks.
#   6. generate_sbom.py       -- Track A only: CycloneDX-shaped SBOM stub.
#
# Usage:
#   ./scripts/demo_lab6.sh
#
# To see the live "edit one schema, watch it propagate" demo: edit
# labs/06-sysml-digital-thread/schema/digital_thread_instances.yaml (add one
# Agent/MCPServer/DataSource entry) or grid_instances.yaml (add one Bus),
# then re-run this script -- the new part appears in the regenerated
# .sysml/SVG/(Track A) SBOM with no other hand edits.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LAB_DIR="labs/06-sysml-digital-thread"
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

section "1/6  k8s snapshot fixture (derived from real kube/*.yaml, not a live cluster)"
run_step "build_k8s_fixture.py --step check" \
    uv run "${LAB_DIR}/build_k8s_fixture.py" --step check

section "2/6  generate .sysml text (both tracks)"
run_step "generate_sysml.py --track digital-thread --step run" \
    uv run "${LAB_DIR}/generate_sysml.py" --track digital-thread --step run
run_step "generate_sysml.py --track grid --step run" \
    uv run "${LAB_DIR}/generate_sysml.py" --track grid --step run

section "3/6  syntax gate (named structural stand-in -- see validate_sysml.py's module docstring)"
run_step "validate_sysml.py --step check" \
    uv run "${LAB_DIR}/validate_sysml.py" --step check

section "4/6  translate to iso-IR JSON (both tracks)"
run_step "translate_iso_ir.py --track digital-thread --step run" \
    uv run "${LAB_DIR}/translate_iso_ir.py" --track digital-thread --step run
run_step "translate_iso_ir.py --track grid --step run" \
    uv run "${LAB_DIR}/translate_iso_ir.py" --track grid --step run

section "5/6  render isometric diagrams (both tracks)"
run_step "render_diagram.py --track digital-thread --step run" \
    uv run "${LAB_DIR}/render_diagram.py" --track digital-thread --step run
run_step "render_diagram.py --track grid --step run" \
    uv run "${LAB_DIR}/render_diagram.py" --track grid --step run

section "6/6  SBOM stub (Track A only -- see generate_sbom.py's module docstring for why Track B has none)"
run_step "generate_sbom.py --step run" \
    uv run "${LAB_DIR}/generate_sbom.py" --step run

section "Summary"
if [ "$FAILED" -eq 0 ]; then
    echo "PASS: Lab 6's pipeline ran end to end for both tracks."
    echo "Regenerated artifacts: ${LAB_DIR}/output/*.sysml *.svg *.json"
    exit 0
else
    echo "FAIL: one or more steps above failed -- see the FAIL lines for detail."
    exit 1
fi
