#!/usr/bin/env bash
#
# tour.sh -- narrated build of the systhread 3D/2D explorer's self-contained
# web bundle. A terminal recording can't show the WebGL canvas itself (see
# the README's "See it run" section for that), so this tour proves the real
# pipeline that gets you there: render a PositionedGraph JSON, bundle the
# Bevy/wasm viewer around it, and serve the result.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/tour_lib.sh

banner "systhread-explorer -- 2D/3D SysML digital-thread viewer"

narrate "Phase 1 shipped systhread render. This explorer is the other half:"
narrate "a Bevy-native viewer -- runs in a browser (wasm) or as a desktop"
narrate "window -- for the same PositionedGraph JSON systhread already emits."
narrate "One build script turns it into a self-contained, servable bundle."

narrate "Render a track with --explorer to get a PositionedGraph JSON:"
TOUR_OUT="$(mktemp -d)"
run_cmd "cargo run -p systhread-cli --manifest-path rust/Cargo.toml --release -- render --track pipeline rust/systhread-cli/tests/fixtures/pipeline_phases_instances.yaml --out ${TOUR_OUT} --explorer --explorer-layout 3d"

narrate "What got written -- notice the explorer's own JSON artifact:"
run_cmd "ls ${TOUR_OUT}"

narrate "Now build the explorer's wasm bundle around that graph:"
run_cmd "just systhread-explorer-bundle ${TOUR_OUT}/pipeline_explorer.json"

narrate "The bundle is a plain static site -- index.html, the wasm binary,"
narrate "and the graph JSON as an asset. Serve it and open it in a browser:"
run_cmd "ls rust/systhread-explorer/dist"
narrate "  just systhread-explorer-serve"

rm -rf "$TOUR_OUT"

banner "systhread-explorer: bundle PASS"
