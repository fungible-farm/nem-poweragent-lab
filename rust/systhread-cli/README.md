# systhread-cli — Phase 1 of the systhread MBSE capability

> Phase 0 (`../systhread-core/`) is the pure library: generate/validate/translate/render, proven
> byte-identical against Lab 6's Python fixtures. This crate is what makes it a real, installable
> tool. Full scope: [`docs/superpowers/specs/2026-08-25-systhread-design.md`](../../docs/superpowers/specs/2026-08-25-systhread-design.md).

## See it run

![systhread-cli tour](tour.gif)

A narrated replay of the real `systhread check`/`systhread render` commands against a committed
fixture. Higher-quality version: [tour.mp4](tour.mp4). Regenerate it yourself:
`./scripts/record_tour.sh rust/systhread-cli` (re-records + re-renders) or run `./tour.sh` directly
for a live, unrecorded walkthrough.

## Commands

- `systhread check --track <digital-thread|grid|pipeline> <instances.yaml>` — generate + validate, no files written.
- `systhread render --track <track> <instances.yaml> --out <dir>` — generate, validate, translate to
  iso-IR, render SVG, write a content-hashed `manifest.json` (FR6's ledgrrr contract).
  **Current limitation:** `manifest.json` describes only the most recent `render` invocation's
  3 artifacts for that `--out` directory — it has no `track` field. Rendering two different tracks
  into the same `--out` directory silently overwrites the manifest with the latest track's entries
  (the earlier track's `.sysml`/`.svg`/`_iso_ir.json` files remain on disk, just undescribed by the
  manifest). Use a separate `--out` directory per track — one `render` invocation per output
  directory — until the manifest format itself grows multi-track support.
- `systhread --stdio` — the same binary as an MCP server (stdio transport), exposing `systhread_check`
  and `systhread_render` as tools. No separate code path from the CLI above (FR2).
- `systhread explore` / `systhread drift` — not yet implemented; ship in Phase 3 (FR7) / Phase 4 (FR10)
  respectively. Present now only so the packaging below has something real to wire to.

## b00t packaging (FR1)

See [`b00t/README.md`](b00t/README.md) — two datum files (`systhread.cli.toml`, `systhread.mcp.toml`)
an adopting project copies into its own b00t datum directory.

## `just` module (FR4)

`systhread.just` ships flat recipes (`sysml-check`, `sysml-render`, `sysml-explore`, `sysml-drift`) —
import with `mod systhread "path/to/rust/systhread-cli/systhread.just"`. This repo dogfoods it in its
own root `Justfile`: `just systhread::sysml-check digital-thread <path>`.
