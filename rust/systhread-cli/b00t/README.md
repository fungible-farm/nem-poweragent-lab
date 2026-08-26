# systhread b00t datums

Two datum files for an adopting project's own b00t installation:

- `systhread.cli.toml` — the `systhread` binary itself (build with `cargo build -p systhread-cli --release`).
- `systhread.mcp.toml` — the same binary's stdio MCP transport (`systhread --stdio`), declared as a
  separate datum per b00t convention (one crate, two datums — see `ledgrrr.cli.toml`/`ledgrrr.mcp.toml`
  in the b00t datum registry for the same pattern).

## Install into your project's b00t datum directory

Copy (or symlink, to track upstream changes) both files into your project's `_b00t_/` directory,
then `b00t learn systhread` for discovery and `b00t stack install systhread` to install.

This directory is the *shippable* copy of these datums — systhread's own source of truth for its
b00t packaging — not itself a live b00t installation (this repo, `nem-poweragent-lab`, has no b00t
dependency of its own; see the repo root `.gitignore`'s own b00t-session-artifacts note).
