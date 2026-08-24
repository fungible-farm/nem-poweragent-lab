#!/usr/bin/env bash
#
# tour_lib.sh -- shared narration helpers for labs/0N-.../tour.sh.
#
# Why this exists: asciinema records real terminal stdout, not a script's
# source text -- a bare `#` comment in tour.sh is invisible to a viewer of
# the recording. `narrate` is what actually puts the story on screen.
#
# Source this, don't execute it:
#   source "$(dirname "${BASH_SOURCE[0]}")/../scripts/tour_lib.sh"

TOUR_PAUSE_SHORT="${TOUR_PAUSE_SHORT:-0.6}"
TOUR_PAUSE_LONG="${TOUR_PAUSE_LONG:-1.0}"

# narrate "<story line>" -- the tour's voiceover, one line at a time.
narrate() {
    printf '\033[2;3m# %s\033[0m\n' "$1"
    sleep "$TOUR_PAUSE_SHORT"
}

# run_cmd "<command string>" -- echoes a fake prompt line, pauses so a
# viewer can read the command, then actually eval's it. Real output, real
# exit code -- set -e (enabled by every tour.sh) propagates real failures.
# A tour that fakes success is worse than no tour.
run_cmd() {
    printf '\033[1;32mdemo$\033[0m %s\n' "$1"
    sleep "$TOUR_PAUSE_SHORT"
    eval "$1"
}

# banner "<title>" -- open/close framing, matches the width of the pinned
# 100-col recording terminal record_tour.sh uses.
banner() {
    local title="$1"
    local line
    line=$(printf '=%.0s' $(seq 1 78))
    printf '\n%s\n%s\n%s\n\n' "$line" "$title" "$line"
    sleep "$TOUR_PAUSE_LONG"
}
