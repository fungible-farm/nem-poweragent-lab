# Scripts

> Status: **spec only**. See `docs/VISION.md` §9–10.

- `fetch_csiro_nem_data.py` — downloads the CC-BY 4.0 CSIRO Synthetic-NEM-2000-Bus MATPOWER case
  files into `data/`, checksummed, idempotent.
- `record_asciinema_demo.sh` — wraps `asciinema rec` around `./install.sh` → Lab 1 → Lab 2 → Lab 3,
  with a pinned `PS1`/terminal width so the recording is reproducible rather than hand-edited.
