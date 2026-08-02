#!/usr/bin/env bash
# peek_viz.sh -- render a named chart (or a direct PNG path) with chafa,
# straight into the SSH terminal, so a demo operator over SSH sees the
# committed static charts with zero file transfer. Backs the root Justfile's
# `just peek <name>` recipe.
#
# Usage:
#   ./scripts/peek_viz.sh            # list the named charts available
#   ./scripts/peek_viz.sh list       # same as no argument
#   ./scripts/peek_viz.sh <name>     # named chart from the registry below
#   ./scripts/peek_viz.sh path/to.png  # any PNG path
#
# Why chafa (not just opening the PNG): the operator's terminal already has
# truecolor support (Windows Terminal via WSL), so chafa renders the chart
# inline in the SSH session they're already in -- no window, no file
# download, no context switch. See the repo's demo-tooling notes.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Named chart registry (name -> repo-relative path). These are the static
# renders the demo narrates. `scorecard` is regenerated output that only
# exists after Lab 3's `just report` -- its "not found" hint says so.
declare -A CHARTS=(
  [contingency]="labs/02-medium-interconnection-screening/sample_contingency_chart.png"
  [reconciliation]="labs/04-aemo-digital-twin-reconciliation/sample_reconciliation_chart.png"
  [topology]="labs/05-spartan-chaosnet-transient-stream/sample_topology_plot.png"
  [transient]="labs/05-spartan-chaosnet-transient-stream/sample_transient_plot.png"
  [transient-3d]="labs/05-spartan-chaosnet-transient-stream/sample_transient_3d.png"
  [scorecard]="benchmarks/power-agent-bench-lite/results/scorecard_chart.png"
)

# How large chafa renders the chart, in terminal columns x rows. Defaults to
# something glanceable; override with $PEEK_SIZE if the operator's terminal
# is bigger or smaller.
PEEK_SIZE="${PEEK_SIZE:-120x40}"

list_names() {
    echo "Named charts: ${!CHARTS[*]}"
    echo "Usage: ./scripts/peek_viz.sh <name> | <path/to.png>"
}

resolve_target() {
    local arg="$1"
    if [[ -n "${CHARTS[$arg]:-}" ]]; then
        printf '%s' "$REPO_ROOT/${CHARTS[$arg]}"
        return 0
    fi
    if [[ "$arg" == *.png && -f "$arg" ]]; then
        printf '%s' "$arg"
        return 0
    fi
    return 1
}

main() {
    command -v chafa >/dev/null 2>&1 \
        || { echo "peek_viz.sh: chafa is not installed -- re-run ./install.sh (step 7 installs it)" >&2; exit 1; }

    local arg="${1:-list}"
    if [[ "$arg" == "list" ]]; then
        list_names
        exit 0
    fi

    local target
    if ! target="$(resolve_target "$arg")"; then
        echo "peek_viz.sh: unknown chart '$arg' -- run 'peek_viz.sh list'" >&2
        exit 1
    fi

    if [[ ! -f "$target" ]]; then
        if [[ "$arg" == "scorecard" ]]; then
            echo "peek_viz.sh: $target not found -- it is regenerated output; run 'just report' (Lab 3) first" >&2
        else
            echo "peek_viz.sh: $target not found" >&2
        fi
        exit 1
    fi

    chafa --format symbols --size "$PEEK_SIZE" "$target"
}

main "$@"
