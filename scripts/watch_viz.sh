#!/usr/bin/env bash
# watch_viz.sh -- play a named demo animation (or a direct file path) with
# mpv: windowed by default (the window appears on the local display via
# WSLg/ssh -X), or --in-terminal for truecolor playback inside the SSH
# terminal. Backs the root Justfile's `just watch <name>` / `just watch-tct
# <name>` recipes.
#
# Usage:
#   ./scripts/watch_viz.sh                 # list the named animations available
#   ./scripts/watch_viz.sh list            # same as no argument
#   ./scripts/watch_viz.sh <name>          # named animation from the registry
#   ./scripts/watch_viz.sh path/to.mp4     # any mp4 path
#   ./scripts/watch_viz.sh --in-terminal <name|path>   # play inside the terminal
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Named animation registry (name -> repo-relative path). These are the
# rendered MP4s (gitignored, produced by the labs/*/animate_*.py scripts --
# see the root Justfile's `render` recipes).
declare -A ANIMATIONS=(
  [convergence]="labs/01-simple-loadflow-fit/animate_convergence.mp4"
  [contingencies]="labs/02-medium-interconnection-screening/animate_contingencies.mp4"
  [transient]="labs/05-spartan-chaosnet-transient-stream/animate_transient.mp4"
)

# Window size for windowed playback (mpv --geometry). Override with $WATCH_SIZE.
WATCH_SIZE="${WATCH_SIZE:-960x540}"

IN_TERMINAL=0

list_names() {
    echo "Named animations: ${!ANIMATIONS[*]}"
    echo "Usage: ./scripts/watch_viz.sh [--in-terminal] <name> | <path/to.mp4>"
}

resolve_target() {
    local arg="$1"
    if [[ -n "${ANIMATIONS[$arg]:-}" ]]; then
        printf '%s' "$REPO_ROOT/${ANIMATIONS[$arg]}"
        return 0
    fi
    if [[ "$arg" == *.mp4 && -f "$arg" ]]; then
        printf '%s' "$arg"
        return 0
    fi
    return 1
}

render_hint() {
    # Map an animation name back to the committed script that renders it, so
    # the operator sees the exact command instead of a dead end.
    case "$1" in
        convergence) echo "uv run python labs/01-simple-loadflow-fit/animate_convergence.py" ;;
        contingencies) echo "uv run python labs/02-medium-interconnection-screening/animate_contingencies.py" ;;
        transient) echo "uv run python labs/05-spartan-chaosnet-transient-stream/animate_transient.py" ;;
        *) echo "see the lab's own README" ;;
    esac
}

main() {
    command -v mpv >/dev/null 2>&1 \
        || { echo "watch_viz.sh: mpv is not installed -- re-run ./install.sh (step 7 installs it)" >&2; exit 1; }

    local args=()
    for a in "$@"; do
        if [[ "$a" == "--in-terminal" ]]; then
            IN_TERMINAL=1
        else
            args+=("$a")
        fi
    done

    local arg="${args[0]:-list}"
    if [[ "$arg" == "list" ]]; then
        list_names
        exit 0
    fi

    local target
    if ! target="$(resolve_target "$arg")"; then
        echo "watch_viz.sh: unknown animation '$arg' -- run 'watch_viz.sh list'" >&2
        exit 1
    fi

    if [[ ! -f "$target" ]]; then
        echo "watch_viz.sh: $target not found -- render it first with:" >&2
        echo "  $(render_hint "$arg")" >&2
        exit 1
    fi

    if [[ "$IN_TERMINAL" -eq 1 ]]; then
        mpv --vo=tct "$target"
    else
        mpv --geometry="$WATCH_SIZE" "$target"
    fi
}

main "$@"
