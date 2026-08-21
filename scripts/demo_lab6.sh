#!/usr/bin/env bash
#
# demo_lab6.sh -- Lab 6's chained pipeline: one command running all three
# tracks end to end, per PRD-0006's Definition of Done ("one schema edit ->
# one command -> regenerated artifacts, no manual edits anywhere").
#
# What it does, in order:
#   1. build_k8s_fixture.py     -- re-derive fixtures/k8s_snapshot.json from
#                                   this repo's real kube/*.yaml manifests
#                                   (Track A's own input; a --step check, not
#                                   a --step run, since this is meant to be
#                                   stable unless kube/*.yaml itself changes).
#   2. build_grid_instances.py  -- re-derive schema/grid_instances.yaml from
#                                   the real data/snemSA.m case (Track B's
#                                   own input; a --step check, same rationale
#                                   as step 1 -- stable unless the case or the
#                                   selection algorithm changes).
#   3. generate_sysml.py        -- LinkML instance data -> .sysml text, all
#                                   three tracks.
#   4. validate_sysml.py        -- the named structural syntax gate, all
#                                   three tracks' fixtures.
#   5. translate_iso_ir.py      -- .sysml parts/containment -> iso-IR JSON,
#                                   all three tracks.
#   6. render_diagram.py        -- iso-IR JSON -> deterministic isometric
#                                   SVG, all three tracks.
#   7. generate_sbom.py         -- Track A only: CycloneDX-shaped SBOM stub.
#
# Usage:
#   ./scripts/demo_lab6.sh
#
# To see the live "edit one schema, watch it propagate" demo: edit
# labs/06-sysml-digital-thread/schema/digital_thread_instances.yaml (add one
# Agent/MCPServer/DataSource entry), grid_instances.yaml (add one Bus), or
# pipeline_phases_instances.yaml (add one Phase), then re-run this script --
# the new part appears in the regenerated .sysml/SVG/(Track A) SBOM with no
# other hand edits.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LAB_DIR="labs/06-sysml-digital-thread"
TRACKS=(digital-thread grid pipeline)
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

section "1/7  k8s snapshot fixture (derived from real kube/*.yaml, not a live cluster)"
run_step "build_k8s_fixture.py --step check" \
    uv run "${LAB_DIR}/build_k8s_fixture.py" --step check

section "2/7  grid instances (derived from the real data/snemSA.m case)"
run_step "build_grid_instances.py --step check" \
    uv run "${LAB_DIR}/build_grid_instances.py" --step check

section "3/7  generate .sysml text (all tracks)"
for track in "${TRACKS[@]}"; do
    run_step "generate_sysml.py --track ${track} --step run" \
        uv run "${LAB_DIR}/generate_sysml.py" --track "${track}" --step run
done

section "4/7  syntax gate (named structural stand-in -- see validate_sysml.py's module docstring)"
run_step "validate_sysml.py --step check" \
    uv run "${LAB_DIR}/validate_sysml.py" --step check

section "5/7  translate to iso-IR JSON (all tracks)"
for track in "${TRACKS[@]}"; do
    run_step "translate_iso_ir.py --track ${track} --step run" \
        uv run "${LAB_DIR}/translate_iso_ir.py" --track "${track}" --step run
done

section "6/7  render isometric diagrams (all tracks)"
for track in "${TRACKS[@]}"; do
    run_step "render_diagram.py --track ${track} --step run" \
        uv run "${LAB_DIR}/render_diagram.py" --track "${track}" --step run
done

section "7/7  SBOM stub (Track A only -- see generate_sbom.py's module docstring for why the other tracks have none)"
run_step "generate_sbom.py --step run" \
    uv run "${LAB_DIR}/generate_sbom.py" --step run

section "Summary"
if [ "$FAILED" -eq 0 ]; then
    echo "PASS: Lab 6's pipeline ran end to end for all three tracks."
    echo "Regenerated artifacts: ${LAB_DIR}/output/*.sysml *.svg *.json"
    exit 0
else
    echo "FAIL: one or more steps above failed -- see the FAIL lines for detail."
    exit 1
fi
