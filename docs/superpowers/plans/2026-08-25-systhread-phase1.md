# systhread Phase 1 (FR1-FR6: CLI, MCP transport, b00t packaging, justfile module, ledgrrr manifest) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `systhread-cli` — a single Rust binary (`systhread`) that wraps Phase 0's `systhread-core` library with a real CLI (`systhread check`/`render`/`explore`/`drift`) and a stdio MCP transport (`systhread --stdio`), b00t-installable, `just`-importable by any adopting project, and able to hand its rendered output to `ledgrrr` via a documented JSON manifest — then prove all of it works with a real recorded demo.

**Architecture:** `systhread-cli` is a thin orchestration layer: it never re-implements generation/validation/iso-IR/rendering logic (that's `systhread-core`, unchanged), it only wires CLI args / MCP tool calls to `systhread-core`'s existing public functions and writes their output to disk. The MCP transport is the same binary as the CLI (FR2's "no logic fork") — `--stdio` is a dispatch flag, exactly mirroring the real, working `just-mcp` binary already vendored on this machine. `explore`/`drift` are honest stubs (their real logic is FR7/Phase 3 and FR10/Phase 4) that exist now only so the packaging/wiring surface (b00t datums, the `just` module) is complete and testable in Phase 1.

**Tech Stack:** Rust 2024 edition, `clap` 4 (derive API) for CLI parsing, `rmcp` 3.1.4 (`server`/`macros`/`transport-io`/`schemars` features) for the MCP server, `tokio` 1 (`full`) for the async runtime `rmcp` needs, `sha2` 0.10 for the manifest's content hashes — all new to this crate; `systhread-core`'s existing `serde`/`serde_json`/`serde_norway` stay in `systhread-core` only.

> **Correction (2026-08-25, mid-execution, before Task 5 ran):** this plan was originally drafted citing `~/.dotfiles/vendor/just-mcp`'s vendored `rmcp = "0.3.0"` as the real ground-truth precedent — correct as "a real, working example on this machine" but stale as a version choice; crates.io's current `rmcp` is `3.1.4`, ten-plus releases ahead. Task 1 (already executed) added `rmcp = { version = "0.3.0", ... }` to `rust/systhread-cli/Cargo.toml` before this correction landed — **Task 5 owns bumping it to `3.1.4`** as part of its own commit, alongside the API fixes below, rather than a stray mid-stream edit. Verified by downloading and reading the real `rmcp-3.1.4` source from crates.io directly (not docs, not assumption): `#[tool_router]`/`#[tool_handler]` bare macros, `ServiceExt`, `rmcp::transport::stdio`, `ErrorData`/`ErrorCode` (same fields), `CallToolResult::success`, and `Implementation::from_build_env()` are all unchanged from 0.3.0 and match this plan's Task 5 code as originally written. Three things did change and Task 5's code below reflects the fix: (1) `Content` is renamed `ContentBlock` (`ContentBlock::text(...)`); (2) the `Parameters` extractor moved from `handler::server::tool::Parameters` to `handler::server::wrapper::Parameters`; (3) `ServerInfo` is now `pub type ServerInfo = InitializeResult`, which gained a `meta: Option<MetaObject>` field — a bare struct literal omitting it won't compile, so Task 5 now builds it via `ServerInfo::new(capabilities).with_protocol_version(...).with_instructions(...)` instead of a struct literal.

**Spec:** `docs/superpowers/specs/2026-08-25-systhread-design.md` (Phase 1 = FR1-FR6, spec §6). Executors read both this plan and the spec — the spec is the binding authority, this plan is its argument.

## Global Constraints

- **Phase 0 (`rust/systhread-core/`) is done and merged to `main` at commit `29549f8`.** Do not modify its logic. The one exception, made explicit as Task 0 below: `instances::load_{digital_thread,grid,pipeline}` change from panicking to `Result<T, String>` — a deliberate, scoped fix to the exact "no crate-wide error-handling convention" gap the Phase 0 final review flagged as a Phase 1 entry condition, needed because a real CLI cannot let a bad user-supplied file path crash the process.
- **Rust-first, no Python** (spec §2) — this entire plan is Rust.
- **Deterministic, byte-identical output** (spec §2) — this applies to the manifest's JSON too: `serde_json::Value`/`json!()` construction (never `preserve_order`), sha256 content hashes computed over real written bytes, no timestamps or absolute machine paths in any artifact.
- **Still Part/containment-only, no Port/Flow syntax** (spec §6 Phase 1 bullet) — `systhread-cli` calls `systhread-core`'s existing three tracks (digital-thread, grid, pipeline) exactly as they exist; no new SysML constructs.
- **No `ufo-types` dependency** — still Phase 2 territory (FR8/FR9), not touched here.
- **`systhread-service` (remote/HTTP transport) is Phase 5, not built here.** The MCP transport dispatch (Task 4) should leave room for an HTTP/SSE variant later (e.g. a place a second flag/enum arm could go) but must not invent a fake "existing pattern" for it — no real HTTP/SSE MCP example exists anywhere on this machine, confirmed by direct search.
- **`explore`/`drift` are honest stubs in Phase 1** (Task 9) — they print a clear "not yet implemented, ships in Phase 3/Phase 4" message and exit non-zero. This is not a placeholder left in the plan; it is the actual, deliberate, tested behavior these subcommands MUST have in Phase 1, per the spec's "kill-gate phased delivery" principle (§2: a later phase never patches over an earlier phase's unresolved finding — an honest stub that fails clearly is not that kind of patch).
- **Every b00t/MCP claim in this plan is grounded in a real file already on this machine**, read directly during planning (not assumed): `~/.dotfiles/_b00t_/ledgrrr.cli.toml`, `~/.dotfiles/_b00t_/ledgrrr.mcp.toml`, `~/.dotfiles/_b00t_/sysml-v2-lsp.mcp.toml`, `~/.dotfiles/_b00t_/ai-dev-stack.stack.toml`, `~/.dotfiles/vendor/just-mcp/src/main.rs`, `~/.dotfiles/vendor/just-mcp/just-mcp-lib/src/mcp_server.rs`, `~/.dotfiles/vendor/just-mcp/Cargo.toml`. Tasks 7 and 5 tell the implementer to re-read these directly rather than trusting a hand-copy — they are outside this repo and could differ slightly from what's quoted here.

---

## Milestone A: `systhread-core` error-handling fix + CLI scaffold + real `check`/`render`

### Task 0: `instances::load_*` — panic to `Result<T, String>`

**Files:**
- Modify: `rust/systhread-core/src/instances.rs:89-105`
- Modify (append `.unwrap()` at each call site — 23 total, listed in Step 3): `rust/systhread-core/tests/layout_sequence_test.rs`, `rust/systhread-core/tests/layout_cassowary_test.rs`, `rust/systhread-core/tests/iso_ir_structure_test.rs`, `rust/systhread-core/tests/sysml_gen_test.rs`, `rust/systhread-core/tests/instances_test.rs`, `rust/systhread-core/tests/determinism_test.rs`, `rust/systhread-core/tests/iso_ir_full_test.rs`, `rust/systhread-core/tests/render_test.rs`, `rust/systhread-core/tests/validate_test.rs`
- Test: `rust/systhread-core/tests/instances_test.rs` (extend with new negative-path tests)

**Interfaces:**
- Consumes: nothing new.
- Produces: `instances::load_digital_thread(path: &Path) -> Result<DigitalThreadInstances, String>`, `instances::load_grid(path: &Path) -> Result<GridInstances, String>`, `instances::load_pipeline(path: &Path) -> Result<PipelinePhasesInstances, String>` — Task 2/3 (the CLI's `check`/`render` commands) consume these directly and propagate the `Err(String)` as a clean CLI error message instead of a panic.

- [ ] **Step 1: Write the failing tests**

Append to `rust/systhread-core/tests/instances_test.rs` (read the existing file first — it already has `mod common; use common::fixture_path;` and imports; add these two functions alongside the existing ones, using the same `load_digital_thread` import already there):

```rust
#[test]
fn load_digital_thread_returns_err_not_panic_on_missing_file() {
    let result = load_digital_thread(&std::path::PathBuf::from("does/not/exist.yaml"));
    assert!(result.is_err());
    assert!(result.unwrap_err().contains("does/not/exist.yaml"));
}

#[test]
fn load_digital_thread_returns_err_not_panic_on_malformed_yaml() {
    let bad = std::env::temp_dir().join("systhread_test_malformed.yaml");
    std::fs::write(&bad, "not: [valid, yaml: at all: {{{").unwrap();
    let result = load_digital_thread(&bad);
    std::fs::remove_file(&bad).ok();
    assert!(result.is_err());
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml load_digital_thread_returns_err -- --test-threads=1`
Expected: FAIL to compile — the whole crate fails to build once these two tests call `.is_err()`/`.unwrap_err()` on what is currently a bare struct return, not a `Result`. (This is a whole-crate compile failure, not an isolated test failure — expected and correct at this step, since Step 3 changes the function signature everyone else calls too.)

- [ ] **Step 3: Change the three loaders' signatures, then fix every call site the compiler flags**

Replace `rust/systhread-core/src/instances.rs:89-105` with:

```rust
pub fn load_digital_thread(path: &Path) -> Result<DigitalThreadInstances, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("read {}: {e}", path.display()))?;
    serde_norway::from_str(&text).map_err(|e| format!("parse {}: {e}", path.display()))
}

pub fn load_grid(path: &Path) -> Result<GridInstances, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("read {}: {e}", path.display()))?;
    serde_norway::from_str(&text).map_err(|e| format!("parse {}: {e}", path.display()))
}

pub fn load_pipeline(path: &Path) -> Result<PipelinePhasesInstances, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("read {}: {e}", path.display()))?;
    serde_norway::from_str(&text).map_err(|e| format!("parse {}: {e}", path.display()))
}
```

Now run `cargo build --tests -p systhread-core --manifest-path rust/Cargo.toml` and fix every resulting compile error. Every error will be a type mismatch at a call site of the shape `let inst = load_digital_thread(&fixture_path(...));` (or `load_grid`/`load_pipeline`) — the fix at every one of these 23 call sites (spread across the 9 test files listed in Files above) is the same: append `.unwrap()` right after the call, e.g. `let inst = load_digital_thread(&fixture_path("schema/digital_thread_instances.yaml")).unwrap();`. Do this file by file, re-running `cargo build --tests` after each file, until the whole crate compiles clean. This is mechanical but must be exact — trust the compiler's own error list over trying to `grep`/`sed` all 23 sites blindly, since a missed or misplaced `.unwrap()` is a real compile error you'd otherwise have to hunt for by hand.

- [ ] **Step 4: Run the full test suite to verify everything passes**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml`
Expected: PASS — all existing tests (now with `.unwrap()` appended at their loader calls) plus the two new negative tests from Step 1, zero warnings.

- [ ] **Step 5: Commit**

```bash
git add rust/systhread-core/src/instances.rs rust/systhread-core/tests/
git commit -m "systhread-core: load_{digital_thread,grid,pipeline} return Result instead of panicking"
```

---

### Task 1: `systhread-cli` crate scaffold

**Files:**
- Modify: `rust/Cargo.toml` (add `"systhread-cli"` to `[workspace] members`)
- Create: `rust/systhread-cli/Cargo.toml`
- Create: `rust/systhread-cli/src/main.rs`
- Create: `rust/systhread-cli/src/track.rs`
- Test: `rust/systhread-cli/tests/cli_smoke_test.rs`

**Interfaces:**
- Consumes: `systhread_core::instances::{load_digital_thread, load_grid, load_pipeline}` (Task 0's new `Result`-returning signatures).
- Produces: the `systhread` binary itself (built by `cargo build -p systhread-cli`); `track::Track` enum (`DigitalThread`, `Grid`, `Pipeline`) — Task 2/3's `check`/`render` commands and Task 5's MCP tool params both use this same enum, so its exact name and variants are load-bearing for every later task.

- [ ] **Step 1: Write the failing test**

`rust/systhread-cli/tests/cli_smoke_test.rs`:

```rust
use std::process::Command;

fn systhread_bin() -> &'static str {
    env!("CARGO_BIN_EXE_systhread")
}

#[test]
fn help_flag_exits_zero_and_prints_usage() {
    let output = Command::new(systhread_bin()).arg("--help").output().unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("systhread"));
}

#[test]
fn no_args_exits_nonzero() {
    let output = Command::new(systhread_bin()).output().unwrap();
    assert!(!output.status.success());
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo test -p systhread-cli --manifest-path rust/Cargo.toml`
Expected: FAIL — the `systhread-cli` package/binary doesn't exist yet, so `cargo` itself errors before any test runs ("package ID specification `systhread-cli` matched no packages").

- [ ] **Step 3: Write the scaffold**

Add `"systhread-cli"` to `rust/Cargo.toml`'s `[workspace] members` list (keep every existing member, only append):

```toml
[workspace]
members = ["phase-model", "demo-app", "fft-detector", "lab-launcher", "mission-engine", "systhread-core", "systhread-cli"]
resolver = "2"
```

`rust/systhread-cli/Cargo.toml`:

```toml
[package]
name = "systhread-cli"
version = "0.1.0"
edition = "2024"
publish = false
description = "Phase 1 of the systhread MBSE capability: CLI + stdio MCP transport over systhread-core (docs/superpowers/specs/2026-08-25-systhread-design.md)."

[[bin]]
name = "systhread"
path = "src/main.rs"

[dependencies]
systhread-core = { path = "../systhread-core" }
clap = { version = "4", features = ["derive"] }
tokio = { version = "1", features = ["full"] }
rmcp = { version = "0.3.0", features = ["server", "macros", "transport-io", "schemars"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
sha2 = "0.10"
```

`rust/systhread-cli/src/track.rs`:

```rust
#[derive(Clone, Copy, Debug, clap::ValueEnum, serde::Deserialize, rmcp::schemars::JsonSchema)]
#[serde(rename_all = "kebab-case")]
pub enum Track {
    DigitalThread,
    Grid,
    Pipeline,
}
```

`rust/systhread-cli/src/main.rs` (scaffold only — `Commands::Check`/`Render`/`Explore`/`Drift` variants exist but their handlers are `todo!()` until Tasks 2/3/9 fill them in; `--help`/no-args already work via `clap`'s own generated behavior, which is what Step 1's test checks):

```rust
mod track;

use clap::{Parser, Subcommand};
use std::path::PathBuf;
use track::Track;

#[derive(Parser)]
#[command(name = "systhread", version, about = "SysML v2 digital-thread tooling (systhread-core Phase 1 CLI)")]
struct Cli {
    /// Run as an MCP server over stdio transport instead of a CLI subcommand.
    #[arg(long)]
    stdio: bool,

    #[command(subcommand)]
    command: Option<Commands>,
}

#[derive(Subcommand)]
enum Commands {
    /// Generate the .sysml text for one track and validate it.
    Check {
        #[arg(long, value_enum)]
        track: Track,
        path: PathBuf,
    },
    /// Generate, validate, translate to iso-IR, and render SVG + a ledgrrr manifest.
    Render {
        #[arg(long, value_enum)]
        track: Track,
        path: PathBuf,
        #[arg(long)]
        out: PathBuf,
    },
    /// Interactive model explorer (FR7 — ships in Phase 3, not yet implemented).
    Explore,
    /// Per-commit drift check (FR10 — ships in Phase 4, not yet implemented).
    Drift,
}

fn main() -> std::process::ExitCode {
    let cli = Cli::parse();

    if cli.stdio {
        todo!("Task 4 wires this to the MCP stdio server");
    }

    match cli.command {
        Some(Commands::Check { .. }) => todo!("Task 2"),
        Some(Commands::Render { .. }) => todo!("Task 3"),
        Some(Commands::Explore) => todo!("Task 9"),
        Some(Commands::Drift) => todo!("Task 9"),
        None => {
            eprintln!("systhread: no command given (try --help)");
            std::process::ExitCode::FAILURE
        }
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cargo test -p systhread-cli --manifest-path rust/Cargo.toml`
Expected: PASS — both smoke tests green (clap's derive `Parser` generates a working `--help` and correctly exits non-zero when no subcommand and no `--stdio` are given, via the `None` arm above). `cargo build -p systhread-cli --manifest-path rust/Cargo.toml` must also succeed (the `todo!()` bodies are fine — they only panic if actually reached, and Step 1's tests never reach them).

- [ ] **Step 5: Commit**

```bash
git add rust/Cargo.toml rust/systhread-cli/
git commit -m "systhread-cli: crate scaffold, Track enum, CLI arg parsing (check/render/explore/drift + --stdio)"
```

---

### Task 2: `systhread check`

**Files:**
- Create: `rust/systhread-cli/src/commands/mod.rs`
- Create: `rust/systhread-cli/src/commands/check.rs`
- Modify: `rust/systhread-cli/src/main.rs`
- Test: `rust/systhread-cli/tests/check_test.rs`

**Interfaces:**
- Consumes: `track::Track`; `systhread_core::instances::{load_digital_thread, load_grid, load_pipeline}`; `systhread_core::sysml_gen::{render_digital_thread, render_grid_topology, render_pipeline_phases}`; `systhread_core::validate::is_valid_sysml`.
- Produces: `commands::check::run(track: Track, path: &Path) -> Result<(), String>` — prints `PASS`/`FAIL: <reason>` to stdout itself and returns `Ok(())`/`Err(reason)` so `main.rs` can map it to an exit code; Task 3's `render` reuses the same generate-then-validate sequence internally (not this function directly — see Task 3's own code) and Task 5's MCP tool calls this exact function.

- [ ] **Step 1: Write the failing test**

Need a real fixture to test against — reuse Phase 0's own committed fixtures (already in `rust/systhread-core/tests/fixtures/lab6/schema/`, but that path is private to the `systhread-core` crate's own test tree; `systhread-cli`'s tests need their own copy). Copy the three schema YAML files into `systhread-cli`'s own fixture directory first:

```bash
mkdir -p rust/systhread-cli/tests/fixtures
cp rust/systhread-core/tests/fixtures/lab6/schema/digital_thread_instances.yaml rust/systhread-cli/tests/fixtures/
cp rust/systhread-core/tests/fixtures/lab6/schema/grid_instances.yaml rust/systhread-cli/tests/fixtures/
cp rust/systhread-core/tests/fixtures/lab6/schema/pipeline_phases_instances.yaml rust/systhread-cli/tests/fixtures/
```

`rust/systhread-cli/tests/check_test.rs`:

```rust
use std::path::PathBuf;
use std::process::Command;

fn systhread_bin() -> &'static str {
    env!("CARGO_BIN_EXE_systhread")
}

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures").join(name)
}

#[test]
fn check_passes_on_a_real_valid_track() {
    let output = Command::new(systhread_bin())
        .args(["check", "--track", "digital-thread"])
        .arg(fixture("digital_thread_instances.yaml"))
        .output()
        .unwrap();
    assert!(output.status.success(), "stderr: {}", String::from_utf8_lossy(&output.stderr));
    assert!(String::from_utf8_lossy(&output.stdout).contains("PASS"));
}

#[test]
fn check_fails_cleanly_on_a_missing_file() {
    let output = Command::new(systhread_bin())
        .args(["check", "--track", "digital-thread", "does/not/exist.yaml"])
        .output()
        .unwrap();
    assert!(!output.status.success());
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo test -p systhread-cli --manifest-path rust/Cargo.toml check_test`
Expected: PASS on `check_fails_cleanly_on_a_missing_file` (the `todo!()` panics, which is still a non-success exit) but the panic also prints a `thread panicked` message rather than a clean error, and `check_passes_on_a_real_valid_track` FAILS (panics before printing `PASS`). Confirm real failure output, not just assume it.

- [ ] **Step 3: Write the implementation**

`rust/systhread-cli/src/commands/mod.rs`:

```rust
pub mod check;
```

`rust/systhread-cli/src/commands/check.rs`:

```rust
use crate::track::Track;
use std::path::Path;
use systhread_core::{instances, sysml_gen, validate};

/// Generates the .sysml text for `track` from the instance YAML at `path`, then validates it.
/// Prints PASS/FAIL to stdout (the CLI's user-facing output) and returns Ok/Err (main.rs's exit-code signal) —
/// two different audiences for the same result, kept as two return channels rather than one.
pub fn run(track: Track, path: &Path) -> Result<(), String> {
    let sysml_text = match track {
        Track::DigitalThread => {
            let inst = instances::load_digital_thread(path)?;
            sysml_gen::render_digital_thread(&inst)
        }
        Track::Grid => {
            let inst = instances::load_grid(path)?;
            sysml_gen::render_grid_topology(&inst)
        }
        Track::Pipeline => {
            let inst = instances::load_pipeline(path)?;
            sysml_gen::render_pipeline_phases(&inst)
        }
    };

    match validate::is_valid_sysml(&sysml_text) {
        Ok(()) => {
            println!("PASS");
            Ok(())
        }
        Err(reason) => {
            println!("FAIL: {reason}");
            Err(reason)
        }
    }
}
```

Update `rust/systhread-cli/src/main.rs`: add `mod commands;` near the top (alongside `mod track;`), and replace the `Commands::Check { .. } => todo!("Task 2")` arm with:

```rust
        Some(Commands::Check { track, path }) => match commands::check::run(track, &path) {
            Ok(()) => std::process::ExitCode::SUCCESS,
            Err(e) => {
                eprintln!("systhread check: {e}");
                std::process::ExitCode::FAILURE
            }
        },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cargo test -p systhread-cli --manifest-path rust/Cargo.toml check_test`
Expected: PASS — both tests green.

- [ ] **Step 5: Commit**

```bash
git add rust/systhread-cli/
git commit -m "systhread-cli: real 'systhread check' command"
```

---

### Task 3: `systhread render`

**Files:**
- Create: `rust/systhread-cli/src/commands/render.rs`
- Modify: `rust/systhread-cli/src/commands/mod.rs`
- Modify: `rust/systhread-cli/src/main.rs`
- Test: `rust/systhread-cli/tests/render_test.rs`

**Interfaces:**
- Consumes: everything Task 2 consumes, plus `systhread_core::iso_ir::{build_digital_thread_iso_ir, build_grid_iso_ir, build_pipeline_iso_ir}` and `systhread_core::render::render_svg`.
- Produces: `commands::render::run(track: Track, path: &Path, out: &Path) -> Result<Vec<PathBuf>, String>` — on success, returns the list of file paths it wrote (`<out>/<track-slug>.sysml`, `<out>/<track-slug>.svg`, `<out>/<track-slug>_iso_ir.json`), in that order. Task 6 (the ledgrrr manifest) extends this exact function to also write a `manifest.json` describing those same three files — Task 6's implementer needs this function's file-naming convention (`<track-slug>.sysml`/`.svg`/`_iso_ir.json`) to match exactly, so don't rename these without updating Task 6's own description too.

- [ ] **Step 1: Write the failing test**

`rust/systhread-cli/tests/render_test.rs`:

```rust
use std::path::PathBuf;
use std::process::Command;

fn systhread_bin() -> &'static str {
    env!("CARGO_BIN_EXE_systhread")
}

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures").join(name)
}

#[test]
fn render_writes_sysml_svg_and_iso_ir_json() {
    let out_dir = std::env::temp_dir().join(format!("systhread_render_test_{}", std::process::id()));
    std::fs::create_dir_all(&out_dir).unwrap();

    let output = Command::new(systhread_bin())
        .args(["render", "--track", "pipeline"])
        .arg(fixture("pipeline_phases_instances.yaml"))
        .args(["--out"])
        .arg(&out_dir)
        .output()
        .unwrap();
    assert!(output.status.success(), "stderr: {}", String::from_utf8_lossy(&output.stderr));

    assert!(out_dir.join("pipeline.sysml").exists());
    assert!(out_dir.join("pipeline.svg").exists());
    assert!(out_dir.join("pipeline_iso_ir.json").exists());

    let sysml = std::fs::read_to_string(out_dir.join("pipeline.sysml")).unwrap();
    assert!(sysml.contains("part def"), "rendered .sysml doesn't look like real output: {sysml}");

    std::fs::remove_dir_all(&out_dir).ok();
}

#[test]
fn render_fails_cleanly_on_invalid_track_data() {
    let out_dir = std::env::temp_dir().join(format!("systhread_render_fail_test_{}", std::process::id()));
    let output = Command::new(systhread_bin())
        .args(["render", "--track", "digital-thread", "does/not/exist.yaml", "--out"])
        .arg(&out_dir)
        .output()
        .unwrap();
    assert!(!output.status.success());
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo test -p systhread-cli --manifest-path rust/Cargo.toml render_test`
Expected: FAIL — `render_fails_cleanly_on_invalid_track_data` passes (the `todo!()` panic is still non-zero exit), `render_writes_sysml_svg_and_iso_ir_json` fails (panics, writes nothing).

- [ ] **Step 3: Write the implementation**

`rust/systhread-cli/src/commands/render.rs`:

```rust
use crate::track::Track;
use std::path::{Path, PathBuf};
use systhread_core::{instances, iso_ir, render as core_render, sysml_gen, validate};

fn track_slug(track: Track) -> &'static str {
    match track {
        Track::DigitalThread => "digital-thread",
        Track::Grid => "grid",
        Track::Pipeline => "pipeline",
    }
}

/// Generates, validates, translates to iso-IR, and renders SVG for `track`, writing all three
/// artifacts into `out` (created if missing). Returns the paths written, in write order, so
/// Task 6's manifest step can hash exactly these files without re-deriving the naming scheme.
pub fn run(track: Track, path: &Path, out: &Path) -> Result<Vec<PathBuf>, String> {
    std::fs::create_dir_all(out).map_err(|e| format!("create {}: {e}", out.display()))?;
    let slug = track_slug(track);

    let (sysml_text, iso_ir_value) = match track {
        Track::DigitalThread => {
            let inst = instances::load_digital_thread(path)?;
            (sysml_gen::render_digital_thread(&inst), iso_ir::build_digital_thread_iso_ir(&inst))
        }
        Track::Grid => {
            let inst = instances::load_grid(path)?;
            (sysml_gen::render_grid_topology(&inst), iso_ir::build_grid_iso_ir(&inst))
        }
        Track::Pipeline => {
            let inst = instances::load_pipeline(path)?;
            (sysml_gen::render_pipeline_phases(&inst), iso_ir::build_pipeline_iso_ir(&inst))
        }
    };

    validate::is_valid_sysml(&sysml_text)?;

    let svg_text = core_render::render_svg(&iso_ir_value);
    let iso_ir_text = serde_json::to_string_pretty(&iso_ir_value).map_err(|e| e.to_string())? + "\n";

    let sysml_path = out.join(format!("{slug}.sysml"));
    let svg_path = out.join(format!("{slug}.svg"));
    let iso_ir_path = out.join(format!("{slug}_iso_ir.json"));

    std::fs::write(&sysml_path, &sysml_text).map_err(|e| format!("write {}: {e}", sysml_path.display()))?;
    std::fs::write(&svg_path, &svg_text).map_err(|e| format!("write {}: {e}", svg_path.display()))?;
    std::fs::write(&iso_ir_path, &iso_ir_text).map_err(|e| format!("write {}: {e}", iso_ir_path.display()))?;

    Ok(vec![sysml_path, svg_path, iso_ir_path])
}
```

Add `pub mod render;` to `rust/systhread-cli/src/commands/mod.rs`. Update `rust/systhread-cli/src/main.rs`'s `Commands::Render { .. } => todo!("Task 3")` arm:

```rust
        Some(Commands::Render { track, path, out }) => match commands::render::run(track, &path, &out) {
            Ok(paths) => {
                for p in paths {
                    println!("wrote {}", p.display());
                }
                std::process::ExitCode::SUCCESS
            }
            Err(e) => {
                eprintln!("systhread render: {e}");
                std::process::ExitCode::FAILURE
            }
        },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cargo test -p systhread-cli --manifest-path rust/Cargo.toml render_test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rust/systhread-cli/
git commit -m "systhread-cli: real 'systhread render' command (.sysml + .svg + iso-IR JSON)"
```

**Milestone A complete.** PR boundary: a real, working `systhread` binary with `check`/`render` fully functional against all three tracks.

---

## Milestone B: MCP stdio transport (FR2)

### Task 4: `--stdio` dispatch wiring

**Files:**
- Create: `rust/systhread-cli/src/mcp.rs`
- Modify: `rust/systhread-cli/src/main.rs`
- Test: `rust/systhread-cli/tests/mcp_dispatch_test.rs`

**Interfaces:**
- Consumes: nothing from earlier tasks yet — this task only wires the dispatch point; Task 5 fills in the actual server.
- Produces: `mcp::run_stdio() -> Result<(), String>` (async fn) — an empty-but-real async function for now (Task 5 gives it a body); `main.rs`'s `#[tokio::main] async fn main()` — main.rs itself becomes async in this task, since `run_stdio` needs an async runtime and FR2 requires no logic fork between transports (the CLI subcommands from Tasks 2/3 stay synchronous internally, just called from within the same async `main`).

**Before starting, read `~/.dotfiles/vendor/just-mcp/src/main.rs` directly** (not from memory of this plan's summary) — it is the real, working precedent for exactly this dispatch shape (a `--stdio` flag on an otherwise-normal CLI, `#[tokio::main] async fn main()`, `if stdio_flag { serve } else { normal CLI }`).

- [ ] **Step 1: Write the failing test**

`rust/systhread-cli/tests/mcp_dispatch_test.rs`:

```rust
use std::io::Write;
use std::process::{Command, Stdio};
use std::time::Duration;

fn systhread_bin() -> &'static str {
    env!("CARGO_BIN_EXE_systhread")
}

/// `--stdio` should start a long-running process (the MCP server), not exit immediately like
/// every other flag combination does -- confirmed by giving it a short-lived stdin (closed
/// immediately) and checking it doesn't exit within a tight deadline, then killing it.
#[test]
fn stdio_flag_starts_a_long_running_process() {
    let mut child = Command::new(systhread_bin())
        .arg("--stdio")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();

    std::thread::sleep(Duration::from_millis(300));
    let still_running = child.try_wait().unwrap().is_none();
    child.kill().ok();
    child.wait().ok();

    assert!(still_running, "systhread --stdio exited immediately instead of serving");
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo test -p systhread-cli --manifest-path rust/Cargo.toml mcp_dispatch_test`
Expected: FAIL — the `todo!("Task 4 wires this...")` panics immediately, so the process exits right away instead of staying alive.

- [ ] **Step 3: Write the implementation**

`rust/systhread-cli/src/mcp.rs`:

```rust
/// Task 5 replaces this body with a real rmcp `ServerHandler` + `stdio()` transport serve loop.
/// Kept as its own async fn (not inlined into main) so main.rs's dispatch stays a one-line call
/// regardless of how much the real server implementation grows.
pub async fn run_stdio() -> Result<(), String> {
    std::future::pending::<()>().await;
    Ok(())
}
```

Update `rust/systhread-cli/src/main.rs`: add `mod mcp;`, make `main` async, and replace the `--stdio` dispatch:

```rust
#[tokio::main]
async fn main() -> std::process::ExitCode {
    let cli = Cli::parse();

    if cli.stdio {
        return match mcp::run_stdio().await {
            Ok(()) => std::process::ExitCode::SUCCESS,
            Err(e) => {
                eprintln!("systhread --stdio: {e}");
                std::process::ExitCode::FAILURE
            }
        };
    }

    match cli.command {
        Some(Commands::Check { track, path }) => match commands::check::run(track, &path) {
            Ok(()) => std::process::ExitCode::SUCCESS,
            Err(e) => {
                eprintln!("systhread check: {e}");
                std::process::ExitCode::FAILURE
            }
        },
        Some(Commands::Render { track, path, out }) => match commands::render::run(track, &path, &out) {
            Ok(paths) => {
                for p in paths {
                    println!("wrote {}", p.display());
                }
                std::process::ExitCode::SUCCESS
            }
            Err(e) => {
                eprintln!("systhread render: {e}");
                std::process::ExitCode::FAILURE
            }
        },
        Some(Commands::Explore) => todo!("Task 9"),
        Some(Commands::Drift) => todo!("Task 9"),
        None => {
            eprintln!("systhread: no command given (try --help)");
            std::process::ExitCode::FAILURE
        }
    }
}
```

(Everything except the `#[tokio::main]` attribute, the `async fn main()` signature, and the new `if cli.stdio { ... }` block at the top is unchanged from Task 3's end state — copied here in full because `main.rs` is a single file and partial diffs invite a bad merge.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cargo test -p systhread-cli --manifest-path rust/Cargo.toml mcp_dispatch_test`
Expected: PASS. Also re-run `cargo test -p systhread-cli --manifest-path rust/Cargo.toml` (full crate) to confirm Tasks 1-3's tests still pass now that `main` is async — `Command::new(...).output()`/`.spawn()` from `std::process` work identically regardless of whether the spawned binary's own `main` is async, so no other test should need changes.

- [ ] **Step 5: Commit**

```bash
git add rust/systhread-cli/
git commit -m "systhread-cli: --stdio dispatch wiring (async main, mcp::run_stdio placeholder)"
```

---

### Task 5: real MCP server — `systhread_check` and `systhread_render` tools

**Files:**
- Modify: `rust/systhread-cli/src/mcp.rs`
- Test: `rust/systhread-cli/tests/mcp_server_test.rs`

**Interfaces:**
- Consumes: `commands::check::run`, `commands::render::run`, `track::Track` (Tasks 2/3/1); `rmcp`'s real 0.3.0 API (see below).
- Produces: `mcp::SysthreadMcpServer` (the `ServerHandler` implementation) and `mcp::run_stdio()`'s real body (replacing Task 4's placeholder).

**Before starting, read this directly** — it confirms the dispatch shape (`server.serve(stdio()).await?`, `running_service.waiting().await?`) still applies: `~/.dotfiles/vendor/just-mcp/src/main.rs`. Do NOT copy `~/.dotfiles/vendor/just-mcp/just-mcp-lib/src/mcp_server.rs`'s exact code — it targets rmcp 0.3.0, and this task targets `rmcp = "3.1.4"` (bumped from Task 1's `0.3.0` as part of this task's own commit — see the plan header's "Correction" note). The code below has already been verified against the real, downloaded `rmcp-3.1.4` source and is the one to use.

- [ ] **Step 1: Write the failing test**

`rust/systhread-cli/tests/mcp_server_test.rs` — this tests the `ServerHandler`/tool methods directly (constructing `SysthreadMcpServer` and calling its async methods in a `#[tokio::test]`), not by spawning a subprocess and speaking the wire protocol — faster and just as real a test of the actual logic, since the wire-protocol framing is `rmcp`'s own already-tested code, not something this crate needs to re-verify:

```rust
use systhread_cli::mcp::SysthreadMcpServer;
use rmcp::handler::server::ServerHandler;

#[test]
fn get_info_reports_real_server_identity() {
    let server = SysthreadMcpServer::new();
    let info = server.get_info();
    assert!(info.instructions.unwrap().contains("systhread"));
}
```

This test needs `systhread_cli::mcp` to be a *public* module reachable from an integration test, which means `rust/systhread-cli/src/main.rs`'s crate needs a `lib.rs` alongside it (a binary-only crate has no externally-testable module path). Before Step 3, restructure: create `rust/systhread-cli/src/lib.rs` with `pub mod commands; pub mod mcp; pub mod track;`, then trim `main.rs` down to only `mod` re-declarations it still needs plus `fn main`, changing its internal `use`s from bare `commands::`/`mcp::`/`track::` to `use systhread_cli::{commands, mcp, track};` (or add `use systhread_cli::track::Track;` etc. — either works, pick one and be consistent). Update `rust/systhread-cli/Cargo.toml` to declare both targets explicitly:

```toml
[lib]
name = "systhread_cli"
path = "src/lib.rs"

[[bin]]
name = "systhread"
path = "src/main.rs"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo test -p systhread-cli --manifest-path rust/Cargo.toml mcp_server_test`
Expected: FAIL to compile — `SysthreadMcpServer` doesn't exist yet.

- [ ] **Step 3: Write the implementation**

First, bump `rust/systhread-cli/Cargo.toml`'s `rmcp` dependency (Task 1 added it pinned to `0.3.0`, which predates this correction) to:

```toml
rmcp = { version = "3.1.4", features = ["server", "macros", "transport-io", "schemars"] }
```

Then replace `rust/systhread-cli/src/mcp.rs` entirely:

```rust
use crate::track::Track;
use rmcp::handler::server::{ServerHandler, router::tool::ToolRouter, wrapper::Parameters};
use rmcp::model::{CallToolResult, ContentBlock, ErrorCode, ErrorData as McpError, Implementation, ProtocolVersion, ServerCapabilities, ServerInfo};
use rmcp::schemars::{self, JsonSchema};
use rmcp::{ServiceExt, tool, tool_handler, tool_router, transport::stdio};
use serde::Deserialize;

#[derive(Debug, Deserialize, JsonSchema)]
pub struct CheckParams {
    pub track: Track,
    pub path: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct RenderParams {
    pub track: Track,
    pub path: String,
    pub out: String,
}

fn to_mcp_error(reason: String) -> McpError {
    McpError { code: ErrorCode::INTERNAL_ERROR, message: reason.into(), data: None }
}

#[derive(Clone)]
pub struct SysthreadMcpServer {
    tool_router: ToolRouter<Self>,
}

impl SysthreadMcpServer {
    pub fn new() -> Self {
        Self { tool_router: Self::tool_router() }
    }
}

#[tool_router]
impl SysthreadMcpServer {
    #[tool(description = "Generate the .sysml text for one systhread track and validate it")]
    async fn systhread_check(
        &self,
        Parameters(params): Parameters<CheckParams>,
    ) -> Result<CallToolResult, McpError> {
        let path = std::path::PathBuf::from(&params.path);
        crate::commands::check::run(params.track, &path).map_err(to_mcp_error)?;
        Ok(CallToolResult::success(vec![ContentBlock::text("PASS")]))
    }

    #[tool(description = "Generate, validate, translate, and render one systhread track to a manifest-described output directory")]
    async fn systhread_render(
        &self,
        Parameters(params): Parameters<RenderParams>,
    ) -> Result<CallToolResult, McpError> {
        let path = std::path::PathBuf::from(&params.path);
        let out = std::path::PathBuf::from(&params.out);
        let written = crate::commands::render::run(params.track, &path, &out).map_err(to_mcp_error)?;
        let summary = written.iter().map(|p| p.display().to_string()).collect::<Vec<_>>().join("\n");
        Ok(CallToolResult::success(vec![ContentBlock::text(summary)]))
    }
}

#[tool_handler]
impl ServerHandler for SysthreadMcpServer {
    fn get_info(&self) -> ServerInfo {
        ServerInfo::new(ServerCapabilities::builder().enable_tools().build())
            .with_protocol_version(ProtocolVersion::V_2024_11_05)
            .with_server_info(Implementation::from_build_env())
            .with_instructions(
                "systhread MCP server: generate/validate/render SysML v2 digital-thread models. \
                 Tools: systhread_check, systhread_render.",
            )
    }
}

pub async fn run_stdio() -> Result<(), String> {
    let server = SysthreadMcpServer::new();
    let running = server.serve(stdio()).await.map_err(|e| e.to_string())?;
    running.waiting().await.map_err(|e| e.to_string())?;
    Ok(())
}
```

`ServerInfo` is `pub type ServerInfo = InitializeResult` in rmcp 3.1.4, which carries a `meta: Option<MetaObject>` field the plan's earlier struct-literal draft omitted — building it via `InitializeResult::new(capabilities).with_protocol_version(...).with_server_info(...).with_instructions(...)` (all real methods on `InitializeResult`, verified against the downloaded 3.1.4 source) avoids that field entirely rather than requiring `..Default::default()`.

`track::Track` needs `#[derive(serde::Deserialize, rmcp::schemars::JsonSchema)]` (or the crate's own direct `schemars::JsonSchema` — Task 1 ended up using a direct `schemars = "0.8"` dependency instead of `rmcp::schemars`'s re-export, which is equally valid: Cargo unifies the resolved `schemars` version across the graph since rmcp 3.1.4 also declares a compatible `schemars` range) for `CheckParams`/`RenderParams` to derive `JsonSchema` themselves — confirm Task 1's `track.rs` already has the derive (it does); if this task's implementer finds it missing, that's a real gap in Task 1's output to fix directly, not a reason to duplicate the enum.

- [ ] **Step 4: Run test to verify it passes**

Run: `cargo test -p systhread-cli --manifest-path rust/Cargo.toml`
Expected: PASS — the new `mcp_server_test` plus every earlier task's tests (Task 4's `stdio_flag_starts_a_long_running_process` test now exercises the *real* server, which should still stay alive waiting for stdio input, same as the placeholder did).

- [ ] **Step 5: Commit**

```bash
git add rust/systhread-cli/
git commit -m "systhread-cli: real MCP stdio server (systhread_check, systhread_render tools)"
```

**Milestone B complete.** PR boundary: `systhread --stdio` is a real, working MCP server exposing `systhread_check`/`systhread_render`.

---

## Milestone C: ledgrrr artifact manifest (FR6)

### Task 6: `manifest.json` — content-hashed artifact contract

**Files:**
- Modify: `rust/systhread-cli/src/commands/render.rs`
- Test: `rust/systhread-cli/tests/manifest_test.rs`

**Interfaces:**
- Consumes: Task 3's `commands::render::run`'s existing file-writing logic (extended, not replaced).
- Produces: `<out>/manifest.json` — a JSON object `{"artifacts": [{"path": "<filename>", "kind": "sysml"|"svg"|"iso_ir_json", "content_hash": "sha256:<64-hex-chars>"}, ...]}`, `path` values are filenames only (relative to `out`, not absolute — the manifest must be portable and the whole render must stay byte-identical across machines per spec §2). `commands::render::run`'s return type changes from `Vec<PathBuf>` to also include the manifest path itself (it becomes the 4th written file) — Task 5's `systhread_render` MCP tool already just joins whatever paths come back with `\n`, so no change needed there.

- [ ] **Step 1: Write the failing test**

`rust/systhread-cli/tests/manifest_test.rs`:

```rust
use std::path::PathBuf;
use std::process::Command;

fn systhread_bin() -> &'static str {
    env!("CARGO_BIN_EXE_systhread")
}

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures").join(name)
}

#[test]
fn render_writes_a_manifest_with_real_content_hashes() {
    let out_dir = std::env::temp_dir().join(format!("systhread_manifest_test_{}", std::process::id()));
    std::fs::create_dir_all(&out_dir).unwrap();

    let output = Command::new(systhread_bin())
        .args(["render", "--track", "pipeline"])
        .arg(fixture("pipeline_phases_instances.yaml"))
        .args(["--out"])
        .arg(&out_dir)
        .output()
        .unwrap();
    assert!(output.status.success(), "stderr: {}", String::from_utf8_lossy(&output.stderr));

    let manifest_text = std::fs::read_to_string(out_dir.join("manifest.json")).unwrap();
    let manifest: serde_json::Value = serde_json::from_str(&manifest_text).unwrap();
    let artifacts = manifest["artifacts"].as_array().unwrap();
    assert_eq!(artifacts.len(), 3, "manifest should describe exactly the 3 rendered files, not itself");

    let sysml_entry = artifacts.iter().find(|a| a["kind"] == "sysml").unwrap();
    assert_eq!(sysml_entry["path"], "pipeline.sysml");
    let hash = sysml_entry["content_hash"].as_str().unwrap();
    assert!(hash.starts_with("sha256:"));
    assert_eq!(hash.len(), "sha256:".len() + 64);

    // The hash must be over the real bytes on disk, not a placeholder.
    use sha2::{Digest, Sha256};
    let real_bytes = std::fs::read(out_dir.join("pipeline.sysml")).unwrap();
    let expected = format!("sha256:{:x}", Sha256::digest(&real_bytes));
    assert_eq!(hash, expected);

    std::fs::remove_dir_all(&out_dir).ok();
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo test -p systhread-cli --manifest-path rust/Cargo.toml manifest_test`
Expected: FAIL — no `manifest.json` is written yet.

- [ ] **Step 3: Write the implementation**

Modify `rust/systhread-cli/src/commands/render.rs`: add `use sha2::{Digest, Sha256};` and `use serde_json::json;` to the top, then replace the tail of `run` (from `Ok(vec![sysml_path, svg_path, iso_ir_path])` onward) with:

```rust
    let artifacts = [
        (&sysml_path, "sysml"),
        (&svg_path, "svg"),
        (&iso_ir_path, "iso_ir_json"),
    ];

    let mut manifest_artifacts = Vec::new();
    for (artifact_path, kind) in &artifacts {
        let bytes = std::fs::read(artifact_path).map_err(|e| format!("read back {}: {e}", artifact_path.display()))?;
        let hash = format!("sha256:{:x}", Sha256::digest(&bytes));
        let filename = artifact_path
            .file_name()
            .and_then(|n| n.to_str())
            .ok_or_else(|| format!("{} has no valid filename", artifact_path.display()))?
            .to_string();
        manifest_artifacts.push(json!({ "path": filename, "kind": kind, "content_hash": hash }));
    }

    let manifest = json!({ "artifacts": manifest_artifacts });
    let manifest_path = out.join("manifest.json");
    let manifest_text = serde_json::to_string_pretty(&manifest).map_err(|e| e.to_string())? + "\n";
    std::fs::write(&manifest_path, &manifest_text).map_err(|e| format!("write {}: {e}", manifest_path.display()))?;

    Ok(vec![sysml_path, svg_path, iso_ir_path, manifest_path])
```

(Everything above this point in `run` — from the function signature through building `iso_ir_path` and writing the three original files — is unchanged from Task 3.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cargo test -p systhread-cli --manifest-path rust/Cargo.toml`
Expected: PASS — the new manifest test, plus Task 3's `render_writes_sysml_svg_and_iso_ir_json` (still checks only the original three files exist, which remains true — a 4th file existing doesn't break that assertion).

- [ ] **Step 5: Commit**

```bash
git add rust/systhread-cli/
git commit -m "systhread-cli: FR6 ledgrrr artifact manifest (manifest.json, sha256 content hashes)"
```

**Milestone C complete.** PR boundary: `systhread render`'s output directory is now a complete, ledgrrr-consumable contract.

---

## Milestone D: b00t packaging + `just` module (FR1, FR4)

### Task 7: b00t datum files

**Files:**
- Create: `rust/systhread-cli/b00t/systhread.cli.toml`
- Create: `rust/systhread-cli/b00t/systhread.mcp.toml`
- Create: `rust/systhread-cli/b00t/README.md`

**Interfaces:**
- Consumes: nothing (declarative TOML only, no code).
- Produces: two b00t datum files an adopting project copies into its own `_b00t_/` directory (or wherever their b00t installation expects datums) to make `systhread` discoverable via `b00t learn systhread` and installable via `b00t stack install`.

**Before starting, read these two real files directly** (they are outside this repo, on this machine, and are the actual precedent — do not trust only this plan's excerpt below, which is abbreviated): `~/.dotfiles/_b00t_/ledgrrr.cli.toml` (a `type = "cli"` datum with `[[b00t.usage]]` examples) and `~/.dotfiles/_b00t_/sysml-v2-lsp.mcp.toml` (a `type = "mcp"` datum with `[[b00t.mcp.stdio]]`, `[b00t.install]`, `[[b00t.gate]]`, `[[b00t.references]]` — this one is the cleaner, more minimal template of the two; prefer its shape over `ledgrrr.mcp.toml`'s, which carries a lot of ledgrrr-specific "polyseme"/FOCUS content that does not apply to systhread).

There is no test step for this task — TOML datum files aren't executable code this crate's test suite can run, and there is no b00t CLI installed in the CI environment to validate against. Verification is: the files parse as valid TOML (`Step 2` below), and a human/reviewer checks the shape against the two real precedent files.

- [ ] **Step 1: Write `systhread.cli.toml`**

`rust/systhread-cli/b00t/systhread.cli.toml`:

```toml
[b00t]
name = "systhread"
type = "cli"
hint = "SysML v2 digital-thread tooling: generate/validate/render a project's .sysml model from committed instance data. Rust binary, no external service dependency (docs/superpowers/specs/2026-08-25-systhread-design.md)."

detect = [
    "command -v systhread",
]

[[b00t.usage]]
description = "Validate one track's generated .sysml against sysml-v2-parser"
command = "systhread check --track digital-thread <instances.yaml>"

[[b00t.usage]]
description = "Render one track's .sysml, SVG, iso-IR JSON, and ledgrrr manifest"
command = "systhread render --track grid <instances.yaml> --out <dir>"

[[b00t.references]]
name = "systhread design spec"
url = "docs/superpowers/specs/2026-08-25-systhread-design.md"
```

- [ ] **Step 2: Write `systhread.mcp.toml`**

`rust/systhread-cli/b00t/systhread.mcp.toml`:

```toml
[b00t]
name = "systhread"
type = "mcp"
hint = "systhread MCP tools over stdio: systhread_check, systhread_render — same binary as the systhread CLI, --stdio transport flag."
depends_on = ["systhread.cli"]

[[b00t.mcp.stdio]]
priority = 0
command = "systhread"
args = ["--stdio"]
transport = "stdio"

[[b00t.gate]]
rhai = "command_exists(\"systhread\")"
hint = "build from source: cargo build -p systhread-cli --manifest-path rust/Cargo.toml --release"

[[b00t.usage]]
description = "Run stdio transport directly (what an MCP client spawns)"
command = "systhread --stdio"

[[b00t.references]]
name = "systhread design spec"
url = "docs/superpowers/specs/2026-08-25-systhread-design.md"

# b00t:map v1
# summary: systhread MCP tools (systhread_check, systhread_render) over stdio, same binary as the CLI
# tags: mcp, sysml, mbse, stdio, rust
# tier: ch0nky
# cmds: systhread --stdio
# complexity: 3
```

Run: `python3 -c "import tomllib; tomllib.load(open('rust/systhread-cli/b00t/systhread.cli.toml','rb')); tomllib.load(open('rust/systhread-cli/b00t/systhread.mcp.toml','rb')); print('valid TOML')"` — Python's stdlib `tomllib` is the quickest available TOML validator on this machine; this only checks syntax, not b00t's own schema, which is why Step 1's note says no automated schema test exists.
Expected: `valid TOML` printed, no exception.

- [ ] **Step 3: Write the installation README**

`rust/systhread-cli/b00t/README.md`:

```markdown
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
```

- [ ] **Step 4: Commit**

```bash
git add rust/systhread-cli/b00t/
git commit -m "systhread-cli: b00t stack packaging (FR1) — systhread.cli.toml + systhread.mcp.toml"
```

---

### Task 8: `systhread.just` module + dogfood import

**Files:**
- Create: `rust/systhread-cli/systhread.just`
- Modify: `Justfile` (repo root)
- Test: manual (`just --list` + a real recipe invocation, per Step 2 below — `just` module wiring isn't something `cargo test` can exercise)

**Interfaces:**
- Consumes: the `systhread` binary (must be built — `cargo build -p systhread-cli --manifest-path rust/Cargo.toml --release` — before these recipes can run for real).
- Produces: a `just` module importable by any adopting project via `mod systhread "path/to/systhread.just"`; this repo's own root `Justfile` becomes the first (dogfooding) adopter, proving the module actually works rather than just existing as unverified text.

- [ ] **Step 1: Write `systhread.just`**

FR4 requires flat recipe names (`sysml-check`, `sysml-render`, `sysml-explore`, `sysml-drift`) and "no logic in the `just` recipes themselves, all logic lives in `systhread-cli`" — every recipe here is a one-line call into the `systhread` binary, with `just`'s own `{{...}}` variable interpolation for the two recipes that need real arguments (`sysml-check`/`sysml-render` need a track and a path; `sysml-explore`/`sysml-drift` take none in Phase 1, since their subcommands are Task 9's stubs).

`rust/systhread-cli/systhread.just`:

```just
# systhread.just -- import into any adopting project's own Justfile with:
#   mod systhread "path/to/systhread.just"
# then call `just systhread::sysml-check <track> <path>` etc. No logic lives here --
# every recipe is a thin one-line call into the systhread binary (FR4).

# Generate + validate one track's .sysml (track: digital-thread | grid | pipeline).
sysml-check track path:
    systhread check --track {{track}} {{path}}

# Generate, validate, translate, and render one track to a manifest-described output directory.
sysml-render track path out:
    systhread render --track {{track}} {{path}} --out {{out}}

# Interactive model explorer (FR7 -- ships in Phase 3).
sysml-explore:
    systhread explore

# Per-commit drift check (FR10 -- ships in Phase 4).
sysml-drift:
    systhread drift
```

- [ ] **Step 2: Import it into this repo's own root Justfile and verify it for real**

This repo becomes systhread's own first adopting project — the dogfooding proof the module actually works, matching this repo's own "the proof scripts are the proof, not a transcript" convention. Add one line to the repo root `Justfile`, immediately after the existing `mod tour "labs/tour.just"` line (around line 394 — read the file first to confirm the exact current line number, since earlier tasks in other work may have shifted it):

```just
mod systhread "rust/systhread-cli/systhread.just"
```

Run these three commands for real and confirm the output described:

```bash
just --list | grep systhread
```
Expected: lists `systhread::sysml-check`, `systhread::sysml-render`, `systhread::sysml-explore`, `systhread::sysml-drift`.

```bash
cargo build -p systhread-cli --manifest-path rust/Cargo.toml --release
export PATH="$PWD/rust/target/release:$PATH"
just systhread::sysml-check digital-thread rust/systhread-cli/tests/fixtures/digital_thread_instances.yaml
```
Expected: prints `PASS`, exits 0 — a real, working recipe call through the module, into the real binary, against a real fixture.

- [ ] **Step 3: Commit**

```bash
git add Justfile rust/systhread-cli/systhread.just
git commit -m "systhread-cli: FR4 just module (systhread.just), dogfooded via this repo's own Justfile"
```

---

### Task 9: `explore`/`drift` stubs

**Files:**
- Create: `rust/systhread-cli/src/commands/explore.rs`
- Create: `rust/systhread-cli/src/commands/drift.rs`
- Modify: `rust/systhread-cli/src/commands/mod.rs`
- Modify: `rust/systhread-cli/src/main.rs` (the `match cli.command` dispatch arms for `Explore`/`Drift`, currently `todo!("Task 9")` — Task 5's Step 1 introduced `lib.rs` to hold `pub mod commands; pub mod mcp; pub mod track;` only, so `main.rs` still owns the `match cli.command` block itself; confirm by reading the file first)
- Test: `rust/systhread-cli/tests/stub_commands_test.rs`

**Interfaces:**
- Consumes: nothing.
- Produces: `commands::explore::run() -> Result<(), String>`, `commands::drift::run() -> Result<(), String>` — both always return `Err(...)` with a clear phase-pointer message; Task 8's `sysml-explore`/`sysml-drift` `just` recipes already call these via the `systhread explore`/`systhread drift` subcommands, so this task is what makes those recipes exercise real (if deliberately unimplemented) code instead of a `todo!()` panic.

- [ ] **Step 1: Write the failing test**

`rust/systhread-cli/tests/stub_commands_test.rs`:

```rust
use std::process::Command;

fn systhread_bin() -> &'static str {
    env!("CARGO_BIN_EXE_systhread")
}

#[test]
fn explore_fails_with_a_clear_not_yet_implemented_message() {
    let output = Command::new(systhread_bin()).arg("explore").output().unwrap();
    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("Phase 3"), "stderr should name the phase that ships this: {stderr}");
}

#[test]
fn drift_fails_with_a_clear_not_yet_implemented_message() {
    let output = Command::new(systhread_bin()).arg("drift").output().unwrap();
    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("Phase 4"), "stderr should name the phase that ships this: {stderr}");
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo test -p systhread-cli --manifest-path rust/Cargo.toml stub_commands_test`
Expected: FAIL — both currently panic via `todo!()`, which exits non-zero (satisfying the first assertion) but the panic message ("not yet implemented: Task 9") does not contain "Phase 3"/"Phase 4" (failing the second assertion).

- [ ] **Step 3: Write the implementation**

`rust/systhread-cli/src/commands/explore.rs`:

```rust
/// FR7 (the interactive explorer) is explicitly Phase 3 in the spec -- this command exists in
/// Phase 1 only so the b00t/just packaging surface (Task 7/8) has something real to wire to and
/// test, not to pretend the explorer is built. See docs/superpowers/specs/2026-08-25-systhread-design.md §6.
pub fn run() -> Result<(), String> {
    Err("systhread explore: not yet implemented -- ships in Phase 3 (FR7, the interactive model explorer)".to_string())
}
```

`rust/systhread-cli/src/commands/drift.rs`:

```rust
/// FR10 (per-commit drift tracking) is explicitly Phase 4 in the spec -- see explore.rs's doc
/// comment for the same reasoning applied to FR7/Phase 3.
pub fn run() -> Result<(), String> {
    Err("systhread drift: not yet implemented -- ships in Phase 4 (FR10, per-commit modelled-shape drift tracking)".to_string())
}
```

Add `pub mod explore; pub mod drift;` to `rust/systhread-cli/src/commands/mod.rs`. Replace the `Explore`/`Drift` dispatch arms (wherever the `match cli.command` block actually lives after Task 5 — read the file first):

```rust
        Some(Commands::Explore) => match commands::explore::run() {
            Ok(()) => std::process::ExitCode::SUCCESS,
            Err(e) => {
                eprintln!("{e}");
                std::process::ExitCode::FAILURE
            }
        },
        Some(Commands::Drift) => match commands::drift::run() {
            Ok(()) => std::process::ExitCode::SUCCESS,
            Err(e) => {
                eprintln!("{e}");
                std::process::ExitCode::FAILURE
            }
        },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cargo test -p systhread-cli --manifest-path rust/Cargo.toml`
Expected: PASS — full crate suite green, zero warnings, zero remaining `todo!()` calls anywhere in `systhread-cli` (confirm with `grep -rn "todo!" rust/systhread-cli/src/` — should print nothing).

- [ ] **Step 5: Commit**

```bash
git add rust/systhread-cli/
git commit -m "systhread-cli: explore/drift honest stubs (FR7/Phase 3, FR10/Phase 4 not yet implemented)"
```

**Milestone D complete.** PR boundary: `systhread` is fully b00t-installable and `just`-importable, with zero remaining scaffolding placeholders.

---

## Milestone E: docs + demo

### Task 10: generalize `record_tour.sh` for a non-`labs/` crate

**Files:**
- Modify: `scripts/record_tour.sh`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces: `scripts/record_tour.sh`'s `record_one()` function gains the ability to record a tour from an explicit directory (not just `labs/0N-*`), used by Task 11.

**No automated test for this task** — `record_tour.sh` drives real `asciinema`/`agg`/`ffmpeg` processes and writes real media files; its own header already documents it as a manually-invoked tool (`just tour-record <lab>` / `just tour::tour-record <lab>`), not something the CI test suite runs. Verification is Task 11's Step 2, where this generalized script is actually run for real and its output is inspected.

- [ ] **Step 1: Read the current script and add an explicit-directory mode**

Read `scripts/record_tour.sh` in full first (it's short, ~72 lines). Its `record_one()` function currently takes a *lab number* and derives `dir`/`cast`/`gif`/`mp4` paths from it via `find labs -maxdepth 1 -type d -name "0${num}-*"`. Add a second function, `record_dir()`, that takes an explicit directory directly (no numbering assumption) and writes `tour.gif`/`tour.mp4` inside that same directory (matching the existing per-lab convention of colocating `tour.gif`/`tour.mp4` with `tour.sh`, just without the `labs/0N-*` requirement) and the `.cast` into `recordings/` (matching the existing convention of keeping raw `.cast` files out of the tracked source tree, gitignored):

```bash
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
```

Update the script's final dispatch block (currently `target="${1:-all}"; if [[ "$target" == "all" ]]; then ... else record_one "$((10#$target))"; fi`) to also accept a path — if `$1` contains a `/`, treat it as a directory and call `record_dir`; otherwise keep the existing numeric-lab behavior unchanged:

```bash
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
```

- [ ] **Step 2: Update `.gitignore`**

The current tour-media exemption (`.gitignore`, near the `*.mp4`/`*.cast` rules) is scoped to `!labs/*/tour.gif` / `!labs/*/tour.mp4` — add the same exemption for `systhread-cli`'s tour location:

```gitignore
!rust/systhread-cli/tour.gif
!rust/systhread-cli/tour.mp4
```

Place these two lines directly after the existing `!labs/*/tour.gif` / `!labs/*/tour.mp4` lines, so the exemption block stays together with its explanatory comment rather than scattered.

- [ ] **Step 3: Commit**

```bash
git add scripts/record_tour.sh .gitignore
git commit -m "scripts: generalize record_tour.sh for crates outside labs/ (record_dir)"
```

---

### Task 11: `systhread-cli` README + real tour

**Files:**
- Create: `rust/systhread-cli/README.md`
- Create: `rust/systhread-cli/tour.sh`
- Create (generated, committed per the tour-media exemption from Task 10): `rust/systhread-cli/tour.gif`, `rust/systhread-cli/tour.mp4`
- Delete: `recordings/systhread_core_demo.cast`, `recordings/systhread_core_demo.gif`, `recordings/systhread_core_demo.mp4` (an earlier, throwaway ad-hoc demo of `just check-systhread-core` — it only shows the test suite passing, not the real capability this plan ships; these files are untracked/gitignored already, so "delete" here just means removing the local scratch files, not a git operation)

**Interfaces:**
- Consumes: the real, working `systhread` binary (Milestones A-D) and `scripts/record_tour.sh`'s new `record_dir` mode (Task 10).
- Produces: nothing further tasks depend on — this is the plan's terminal deliverable.

- [ ] **Step 1: Write `tour.sh`**

Follows the exact convention of `labs/06-sysml-digital-thread/tour.sh` (source `scripts/tour_lib.sh` for `banner`/`narrate`/`run_cmd`), but exercises the real `systhread` CLI end-to-end against Lab 6's own committed pipeline-phases fixture (reusing `rust/systhread-cli/tests/fixtures/pipeline_phases_instances.yaml`, copied into this crate's own test fixtures back in Task 2 — a real, already-proven-valid input, not a fresh example that needs separate validation):

`rust/systhread-cli/tour.sh`:

```bash
#!/usr/bin/env bash
#
# tour.sh -- narrated replay of the real systhread CLI, Phase 1's shipped capability.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source scripts/tour_lib.sh

banner "systhread -- SysML v2 digital-thread CLI (Phase 1)"

narrate "Phase 0 built the core Rust library. Phase 1 is what makes it a real"
narrate "tool: a CLI, an MCP server (same binary, --stdio), b00t packaging,"
narrate "a just module any project can import, and a manifest ledgrrr can read."
narrate "One instance-data file in, a validated model and rendered artifacts out."

run_cmd "cargo build -p systhread-cli --manifest-path rust/Cargo.toml --release"

TOUR_OUT="$(mktemp -d)"
export PATH="$PWD/rust/target/release:$PATH"

narrate "First: check. Generate the .sysml text, validate it, nothing written to disk."
run_cmd "systhread check --track pipeline rust/systhread-cli/tests/fixtures/pipeline_phases_instances.yaml"

narrate "Now: render. Same generation, plus iso-IR translation, SVG rendering,"
narrate "and a content-hashed manifest.json -- the whole ledgrrr contract."
run_cmd "systhread render --track pipeline rust/systhread-cli/tests/fixtures/pipeline_phases_instances.yaml --out ${TOUR_OUT}"

narrate "What got written:"
run_cmd "ls ${TOUR_OUT}"

narrate "And the manifest -- what ledgrrr actually reads, no systhread-internal knowledge required:"
run_cmd "cat ${TOUR_OUT}/manifest.json"

rm -rf "$TOUR_OUT"

banner "systhread Phase 1: PASS"
```

Make it executable: `chmod +x rust/systhread-cli/tour.sh`.

- [ ] **Step 2: Record it for real**

```bash
./scripts/record_tour.sh rust/systhread-cli
```

Expected: `rust/systhread-cli/tour.gif` and `rust/systhread-cli/tour.mp4` are created, non-empty, and (per Task 10's `record_dir`) `recordings/systhread-cli_tour.cast` is created too (gitignored — don't commit it). Play back or otherwise inspect the `.gif` to confirm it actually shows the real `check`/`render` output, not an error — this is the same discipline `tour_lib.sh`'s own `run_cmd` doc comment names: "A tour that fakes success is worse than no tour," so `set -e` in `tour.sh` means a real failure would have already stopped the recording with a visible error, but confirm visually anyway.

- [ ] **Step 3: Write the README**

`rust/systhread-cli/README.md` — follow `labs/06-sysml-digital-thread/README.md`'s "## See it run" section structure exactly (embed the gif, link the mp4, name the regenerate command):

```markdown
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
```

- [ ] **Step 4: Delete the throwaway ad-hoc demo**

```bash
rm -f recordings/systhread_core_demo.cast recordings/systhread_core_demo.gif recordings/systhread_core_demo.mp4
```

These were never tracked by git (confirmed untracked during the Phase 0 session), so this is a local cleanup, not a commit.

- [ ] **Step 5: Commit**

```bash
git add rust/systhread-cli/README.md rust/systhread-cli/tour.sh rust/systhread-cli/tour.gif rust/systhread-cli/tour.mp4
git commit -m "systhread-cli: README + real recorded tour of check/render/manifest"
```

**Milestone E complete.** Phase 1 acceptance criteria (spec §6): `systhread` is a real b00t-installable, `just`-importable CLI+MCP binary with FR1-FR6 all wired and demonstrated on camera.

---

## Self-Review Notes (for the executing agent, not a task)

- **Spec coverage**: FR1 (Task 7), FR2 (Tasks 4-5), FR3 (already true — `systhread check`/`render` operate on whatever `.sysml`-instance file the caller points at, no separate model repo, nothing new needed), FR4 (Task 8, with Task 9's stubs making all 4 recipes real), FR5 (already fully built in Phase 0, `systhread render` just calls it — no new task needed), FR6 (Task 6). Docs/demo (this session's other stated goal) is Milestone E, folded in rather than left as a separate afterthought.
- **The Task 0 breaking change is real and deliberate, not scope creep**: it directly closes the exact gap ("no crate-wide error-handling convention... settle before building the CLI") the Phase 0 final review flagged as a named Phase 1 entry condition — this plan is that settling, not a new discovery.
- **Real risk flagged honestly**: Task 5 (the `rmcp` `#[tool_router]`/`#[tool_handler]` macro usage) is this plan's highest-uncertainty task, the same way Phase 0's Cassowary port was — the code above is modeled closely on a real, compiling, working example (`just-mcp-lib/src/mcp_server.rs`) rather than invented from `rmcp`'s docs alone, but it has not been compiled as part of writing this plan. If it doesn't compile cleanly, that is real, load-bearing information — the implementer should diff against the real source file (already named in Task 5's "before starting" note) rather than guessing at a fix.
- **`systhread-service` (remote/HTTP transport) is genuinely out of scope** — not a single task in this plan touches it, matching the spec's own Phase 5 placement, and Task 4's dispatch is written so a future flag/enum arm could be added without restructuring what's here.
