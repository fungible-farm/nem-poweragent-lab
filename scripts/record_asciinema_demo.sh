#!/usr/bin/env bash
#
# record_asciinema_demo.sh -- docs/VISION.md section 11's training recording.
#
# Wraps `asciinema rec` around ./install.sh -> Lab 1 -> Lab 2 -> Lab 3
# summary, with PS1 and terminal width pinned so the .cast file plays back
# consistently regardless of the presenter's own shell config. This is an
# artifact of this repo, not a separate hand-edited video -- re-running this
# script after any lab changes regenerates the recording from the real,
# current code, so the walkthrough can't drift out of sync with the actual
# code the way a slide deck does. Output .cast files are gitignored
# (`*.cast`, matching the pattern already in .gitignore) -- regenerate on
# demand, never commit one and let it go stale.
#
# Usage:
#   ./scripts/record_asciinema_demo.sh [output.cast]
#
# Sandbox note: this records ./install.sh (which brings up the real
# llamacpp/powermcp pods, per kube/README.md) followed by
# ./scripts/run_labs_1_3.sh (Labs 1-3, still running their documented
# in-process stand-ins rather than calling those pods -- see that script's
# own header). Both scripts are idempotent/cached, so re-running this
# recording script doesn't re-download the CSIRO data or the GGUF model
# every time.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

OUTPUT_CAST="${1:-recordings/install_labs123.cast}"
mkdir -p "$(dirname "$OUTPUT_CAST")"

if ! command -v asciinema >/dev/null 2>&1; then
    echo "[record_asciinema_demo.sh] asciinema not found -- installing via 'uv tool install asciinema'"
    uv tool install asciinema
    export PATH="$HOME/.local/bin:$PATH"
    command -v asciinema >/dev/null 2>&1 || {
        echo "[record_asciinema_demo.sh] FAIL: asciinema installer ran but 'asciinema' is still not on PATH" >&2
        exit 1
    }
fi

# Pinned terminal width/height so the .cast plays back the same regardless
# of the presenter's own terminal size at recording time -- 100x30 is wide
# enough that none of this repo's own printed tables/banners
# (scripts/run_labs_1_3.sh's 78-column banners, Lab 4/5's wider status
# lines) wrap mid-word. `asciinema rec --cols/--rows` (not just $COLUMNS/
# $LINES, which asciinema does not reliably honour -- confirmed by direct
# experiment: exporting them alone still recorded the invoking shell's own
# 80x24) is what actually pins the recorded pty size.
REC_COLS=100
REC_ROWS=30

# Pinned, minimal PS1 -- so the recording doesn't leak this machine's own
# prompt (hostname, git branch, conda env, etc.), which would both look
# inconsistent across presenters' machines and be irrelevant noise in
# playback.
export PS1='demo$ '

DEMO_SCRIPT=$(cat <<'INNER'
set -e
echo "=== nem-poweragent-lab: install -> Lab 1 -> Lab 2 -> Lab 3 ==="
echo
./install.sh
echo
./scripts/run_labs_1_3.sh
echo
echo "=== Summary ==="
echo "Lab 1 (simple load-flow fit):        PASS -- see labs/01-simple-loadflow-fit/expected_results.json"
echo "Lab 2 (N-1 interconnection screen):  PASS -- see labs/02-medium-interconnection-screening/expected_contingency_table.json"
echo "Lab 3 (provider bake-off scorecard): PASS -- see benchmarks/power-agent-bench-lite/results/scorecard.json"
INNER
)

echo "[record_asciinema_demo.sh] recording to $OUTPUT_CAST"
asciinema rec --overwrite --cols "$REC_COLS" --rows "$REC_ROWS" \
    --command "bash -c '$DEMO_SCRIPT'" "$OUTPUT_CAST"

echo "[record_asciinema_demo.sh] done. Play back with: asciinema play $OUTPUT_CAST"
