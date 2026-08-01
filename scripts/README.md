# Scripts

> Status: `fetch_csiro_nem_data.py` and `run_labs_1_3.sh` are **implemented**.
> `record_asciinema_demo.sh` is spec only. See `docs/VISION.md` §9–10.

- `fetch_csiro_nem_data.py` — downloads the CC-BY 4.0 CSIRO Synthetic-NEM-2000-Bus MATPOWER case
  files into `data/`, checksummed (pinned to a specific upstream commit), idempotent.
- `run_labs_1_3.sh` — the end-to-end proof that Labs 1-3 work: `uv sync` → fetch data → every step
  of Labs 1, 2, and 3 → the pytest suite → a final PASS/FAIL summary. This script, not a transcript
  of anyone running commands by hand, is the artifact that proves the labs work — see the root
  `README.md`.
- `record_asciinema_demo.sh` — **not yet built.** Will wrap `asciinema rec` around `./install.sh` →
  Lab 1 → Lab 2 → Lab 3, with a pinned `PS1`/terminal width so the recording is reproducible rather
  than hand-edited.
