#!/usr/bin/env bash
#
# record_tour.sh -- records a lab's narrated tour.sh with asciinema (pinned
# terminal size/PS1, same convention as record_asciinema_demo.sh), then
# renders the .cast to a committed tour.gif (primary, renders inline on
# GitHub) and tour.mp4 (secondary, smaller/higher quality). The .cast itself
# stays gitignored/regenerate-on-demand -- see .gitignore's *.cast rule.
#
# Usage:
#   ./scripts/record_tour.sh <lab-number>   # e.g. 1, or 01
#   ./scripts/record_tour.sh all            # every lab, 1..9
#
# `just tour-record <lab>` is the memoized entry point (labs/tour.just).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

REC_COLS=100
REC_ROWS=30

if ! asciinema --version >/dev/null 2>&1; then
    echo "[record_tour.sh] asciinema missing or broken -- (re)installing via 'uv tool install --force asciinema'"
    uv tool install --force asciinema
    export PATH="$HOME/.local/bin:$PATH"
fi
if ! command -v agg >/dev/null 2>&1; then
    echo "[record_tour.sh] agg not found -- installing via 'cargo install --locked --git https://github.com/asciinema/agg'"
    cargo install --locked --git https://github.com/asciinema/agg
    export PATH="$HOME/.cargo/bin:$PATH"
fi
asciinema --version >/dev/null 2>&1 || { echo "[record_tour.sh] FAIL: asciinema still broken after install attempt" >&2; exit 1; }
agg --version >/dev/null 2>&1 || { echo "[record_tour.sh] FAIL: agg still broken after install attempt" >&2; exit 1; }
ffmpeg -version >/dev/null 2>&1 || { echo "[record_tour.sh] FAIL: ffmpeg not available" >&2; exit 1; }

record_one() {
    local num="$1"
    local dir
    dir=$(find labs -maxdepth 1 -type d -name "0${num}-*" | head -1)
    if [[ -z "$dir" ]]; then
        echo "[record_tour.sh] FAIL: no labs/0${num}-* directory found" >&2
        exit 1
    fi
    local cast="recordings/lab${num}_tour.cast"
    local gif="${dir}/tour.gif"
    local mp4="${dir}/tour.mp4"
    mkdir -p recordings

    echo "[record_tour.sh] recording ${dir}/tour.sh -> ${cast}"
    PS1='demo$ ' asciinema rec --overwrite --cols "$REC_COLS" --rows "$REC_ROWS" \
        --command "bash ${dir}/tour.sh" "$cast"

    echo "[record_tour.sh] rendering ${cast} -> ${gif}"
    agg --font-size 16 --speed 1.0 "$cast" "$gif"

    echo "[record_tour.sh] rendering ${gif} -> ${mp4}"
    ffmpeg -y -loglevel error -i "$gif" -movflags faststart -pix_fmt yuv420p \
        -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" "$mp4"

    echo "[record_tour.sh] done: ${gif} ($(du -h "$gif" | cut -f1)), ${mp4} ($(du -h "$mp4" | cut -f1))"
}

record_dir() {
    local dir="$1"
    if [[ ! -f "${dir}/tour.sh" ]]; then
        echo "[record_tour.sh] FAIL: no ${dir}/tour.sh found" >&2
        exit 1
    fi
    local slug
    slug=$(basename "$dir")
    local cast="recordings/${slug}_tour.cast"
    local gif="${dir}/tour.gif"
    local mp4="${dir}/tour.mp4"
    mkdir -p recordings

    echo "[record_tour.sh] recording ${dir}/tour.sh -> ${cast}"
    PS1='demo$ ' asciinema rec --overwrite --cols "$REC_COLS" --rows "$REC_ROWS" \
        --command "bash ${dir}/tour.sh" "$cast"

    echo "[record_tour.sh] rendering ${cast} -> ${gif}"
    agg --font-size 16 --speed 1.0 "$cast" "$gif"

    echo "[record_tour.sh] rendering ${gif} -> ${mp4}"
    ffmpeg -y -loglevel error -i "$gif" -movflags faststart -pix_fmt yuv420p \
        -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" "$mp4"

    echo "[record_tour.sh] done: ${gif} ($(du -h "$gif" | cut -f1)), ${mp4} ($(du -h "$mp4" | cut -f1))"
}

target="${1:-all}"
if [[ "$target" == "all" ]]; then
    for n in 1 2 3 4 5 6 7 8 9; do
        record_one "$n"
    done
elif [[ "$target" == */* ]]; then
    record_dir "$target"
else
    record_one "$((10#$target))"
fi
