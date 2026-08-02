#!/usr/bin/env bash
# demo.sh -- interactive demo launcher: one command, an fzf menu on the
# user's screen, no remembered names (KISS/DMMT). `just demo` runs this.
#
# Presents every lab visualization as a fuzzy-pick list; the chosen item is
# launched with the right viewer: mpv windowed (animation), chafa in-terminal
# (static chart), mpv --vo=tct in-terminal, or mpv audio (the 3-channel
# sonification). Requires fzf + mpv + chafa (install.sh step 7 / just deploy
# installs all three).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Menu rows: <display label>TAB<kind>TAB<target>
#   kind: watch | watch-tct | peek | audio
#   target: a watch_viz.sh / peek_viz.sh registry name, or the WAV path.
# Display uses column 1; kind/target are parsed on selection.
MENU=(
$'Animation\tLab 1 -- bisection convergence\twatch\tconvergence'
$'Animation\tLab 2 -- N-1 contingency screen\twatch\tcontingencies'
$'Animation\tLab 5 -- fault transient\twatch\ttransient'
$'Animation\tLab 5 -- telemetry feeds (raw/phasor/SCADA)\twatch\ttransient-rates'
$'Animation (terminal)\tLab 5 -- fault transient, in-terminal\twatch-tct\ttransient'
$'Audio\tLab 5 -- 3-channel sonification (hear the fault)\taudio\t-'
$'Chart\tLab 2 -- N-1 contingency chart\tpeek\tcontingency'
$'Chart\tLab 4 -- AEMO reconciliation\tpeek\treconciliation'
$'Chart\tLab 5 -- chaos-net topology\tpeek\ttopology'
$'Chart\tLab 5 -- fault transient (static)\tpeek\ttransient'
$'Chart\tLab 5 -- 3D phase-space\tpeek\ttransient-3d'
$'Chart\tLab 5 -- telemetry rates (static)\tpeek\trates'
$'Chart\tLab 3 -- provider scorecard\tpeek\tscorecard'
)

run_demo() {
    local kind="$1" target="$2"
    case "$kind" in
        watch)     "$REPO_ROOT/scripts/watch_viz.sh" "$target" ;;
        watch-tct) "$REPO_ROOT/scripts/watch_viz.sh" --in-terminal "$target" ;;
        peek)      "$REPO_ROOT/scripts/peek_viz.sh" "$target" ;;
        audio)     mpv --no-video \
                       "$REPO_ROOT/labs/05-spartan-chaosnet-transient-stream/dpsim_transient_3ch.wav" ;;
        *)
            echo "demo: unknown kind '$kind'" >&2
            exit 2
            ;;
    esac
}

main() {
    command -v fzf >/dev/null 2>&1 \
        || { echo "demo: fzf is not installed -- re-run ./install.sh (step 7 installs it)" >&2; exit 1; }

    local selection
    selection="$(
        printf '%s\n' "${MENU[@]}" \
            | fzf --height=50% --border --header="nem-poweragent-lab demo -- pick a visualization" \
                  --delimiter=$'\t' --with-nth=1,2 --preview 'echo "$0" | cut -f2-3' --preview-window=bottom:2 \
            || true
    )"

    if [[ -z "$selection" ]]; then
        echo "demo: no selection (cancelled)."
        exit 0
    fi

    # MENU rows are category TAB label TAB kind TAB target -- display shows
    # category+label; the action is fields 3 (kind) and 4 (target).
    IFS=$'\t' read -r _ _ kind target <<< "$selection"
    run_demo "$kind" "$target"
}

main "$@"
