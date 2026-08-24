# labs/tour.just -- narrated lab-tour module, imported via `mod tour` in the
# root Justfile. Recipes here dispatch to committed scripts (tour_lib.sh,
# each lab's own tour.sh, scripts/record_tour.sh) -- this file is the index,
# not a re-implementation, same philosophy as the root Justfile's own header.

# Run a lab's narrated tour live in your terminal, no recording.
# `just tour` (no args) runs all 9 in order; `just tour 5` runs just Lab 5.
tour lab="all":
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    if [ "{{lab}}" = "all" ]; then
        for n in 1 2 3 4 5 6 7 8 9; do
            dir=$(find labs -maxdepth 1 -type d -name "0${n}-*" | head -1)
            bash "$dir/tour.sh"
        done
    else
        n=$(printf '%d' "{{lab}}")
        dir=$(find labs -maxdepth 1 -type d -name "0${n}-*" | head -1)
        bash "$dir/tour.sh"
    fi

# Record a lab's tour with asciinema and render it to a committed
# tour.gif/tour.mp4. `just tour-record` (no args) does all 9 labs.
tour-record lab="all":
    "{{justfile_directory()}}/scripts/record_tour.sh" {{lab}}

# Re-render an already-recorded lab's .cast to gif/mp4 without re-recording
# (e.g. after tweaking agg's theme/font-size). Needs recordings/labN_tour.cast
# to already exist locally -- run tour-record first if it doesn't.
tour-render lab:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    n=$(printf '%d' "{{lab}}")
    dir=$(find labs -maxdepth 1 -type d -name "0${n}-*" | head -1)
    cast="recordings/lab${n}_tour.cast"
    [ -f "$cast" ] || { echo "no $cast -- run 'just tour-record {{lab}}' first" >&2; exit 1; }
    agg --font-size 16 --speed 1.0 "$cast" "$dir/tour.gif"
    ffmpeg -y -loglevel error -i "$dir/tour.gif" -movflags faststart -pix_fmt yuv420p \
        -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" "$dir/tour.mp4"
