# Scripts

> Status: `fetch_csiro_nem_data.py`, `run_labs_1_3.sh`, `record_asciinema_demo.sh`, and
> `record_tour.sh` are all **implemented**. See `docs/VISION.md` §9–11.

- `fetch_csiro_nem_data.py` — downloads the CC-BY 4.0 CSIRO Synthetic-NEM-2000-Bus MATPOWER case
  files into `data/`, checksummed (pinned to a specific upstream commit), idempotent.
- `run_labs_1_3.sh` — the end-to-end proof that Labs 1-3 work: `uv sync` → fetch data → every step
  of Labs 1, 2, and 3 → the pytest suite → a final PASS/FAIL summary. This script, not a transcript
  of anyone running commands by hand, is the artifact that proves the labs work — see the root
  `README.md`.
- `record_asciinema_demo.sh` — wraps `asciinema rec` around `./install.sh` → Lab 1 → Lab 2 → Lab 3,
  with a pinned `PS1`/terminal width so the recording is reproducible rather than hand-edited.
  Writes a gitignored `.cast` file (regenerate on demand — never committed).
  `tour_lib.sh`/`record_tour.sh` below are the per-lab, all-9-labs successor to this original
  install→Labs1-3 walkthrough.
- `tour_lib.sh` — sourced by every `labs/0N-.../tour.sh`; provides `narrate`/`run_cmd`/`banner`
  helpers so a recorded tour can carry spoken narration (asciinema records real terminal stdout,
  not a script's `#` comments, so the story has to be `echo`ed on purpose).
- `record_tour.sh <lab-number|all>` — records a lab's narrated `tour.sh` with `asciinema` (same
  pinned-size/`PS1` convention as `record_asciinema_demo.sh`), then renders the `.cast` to a
  committed `tour.gif` (primary — renders inline on GitHub with zero clicks) and `tour.mp4`
  (secondary, smaller/higher quality) via `agg`/`ffmpeg`. The raw `.cast` stays gitignored; only the
  rendered GIF/MP4 are committed, the same "commit the final render, not the pipeline" pattern this
  repo already uses for its committed PNG charts. Memoized as `just tour::tour-record [lab]`
  (`labs/tour.just`).
