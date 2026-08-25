# systhread Phase 0 — Core Rust Crate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `systhread-core`, a new Rust crate that reproduces Lab 6's (`labs/06-sysml-digital-thread/`) Python pipeline output — `.sysml` text, iso-IR JSON, and isometric SVG diagrams, for all three tracks (digital-thread, grid, pipeline) — byte-identical, from scratch in Rust, with Lab 6's committed Python-era fixtures as the acceptance oracle. Lab 6 itself is not touched.

**Architecture:** A single library crate (`rust/systhread-core/`) with no CLI/MCP surface yet (that's Phase 1). Five internal modules mirror Lab 6's four pipeline stages plus a shared data-loading stage: `instances` (YAML → typed structs), `sysml_gen` (structs → `.sysml` text), `validate` (syntax gate via `sysml-v2-parser`), `iso_ir` (structs → node/edge graph → positioned iso-IR JSON), `layout` (the Cassowary constraint solving that positions nodes), `render` (iso-IR → SVG). Each stage is a pure function chain — no stage reads a previously-generated file, matching Lab 6's own "always reflects current state, never a stale intermediate" discipline.

**Tech Stack:** Rust (edition 2024, matching `rust/mission-engine`), `serde`/`serde_norway` (YAML), `serde_json` (JSON, default features — no `preserve_order`, so object keys serialize alphabetically like Python's `json.dumps(sort_keys=True)`), `sysml-v2-parser = "0.54"` (MIT, already used by `rust/mission-engine`), `kasuari = "0.4"` (MIT, Cassowary constraint solver — the Rust crate `ledgrrr`'s own diagram-layout solver uses, per Lab 6's own code comments naming it as the reference pattern).

**Spec:** `docs/superpowers/specs/2026-08-25-systhread-design.md` (commit `368a466`) — this plan implements **Phase 0 only** (§6). Do not start FR8/FR9 (UfoStereotype declarations, the `ToSysml` trait) — those are Phase 2, explicitly gated on a "dedicated look" at `ledgrrr`'s `sysml-derive` crate that hasn't happened yet.

## Global Constraints

- **Byte-identical output is a hard gate, not "close enough."** Every task that produces `.sysml`, iso-IR JSON, or SVG output MUST assert exact string/byte equality against the copied Lab 6 fixture, not a structural/semantic comparison.
- **Do not touch `labs/06-sysml-digital-thread/`.** Read-only reference. Fixtures used for testing are copied into `rust/systhread-core/tests/fixtures/lab6/` once, in Task 0, and are Rust-crate-owned from that point on.
- **No `ufo-types` dependency in Phase 0.** FR8/FR9's `UfoStereotype` wiring starts in Phase 2. Adding it now with nothing to stereotype yet would be an unused dependency — YAGNI.
- **No regex-based `.sysml` text re-parsing.** Lab 6's Python re-derives node/edge structure by regex-walking the *generated* `.sysml` text (`translate_iso_ir.py`'s `parse_parts`). This Rust port builds node/edge structure directly from the same typed instance data the generator itself consumes (see Task 4) — same output shape, no risk of a second regex dialect drifting from the generator's own template. This is a deliberate, spec-sanctioned divergence in *how* the output is computed, not in *what* it is — the byte-identical gate still applies to every output artifact.
- **`sysml-v2-parser` is the syntax gate, not a hand-rolled line-pattern checker.** Lab 6's `validate_sysml.py` was a structural stand-in adopted only because no working native-Rust parser existed at the time (Java/Maven dead end, documented in that file's own docstring). One now does — already spiked in this repo (`labs/08-cim-gridy-phase0-spikes/0b-sysml-v2-parser/`, confirmed 3/3 pass on Lab 6's own generated output) and confirmed MIT. Task 3 wires it directly; do not port `validate_sysml.py`'s regex patterns.
- **Determinism**: every fixture-comparison test doubles as a determinism check by construction (calling the same pure function twice in one test process and asserting identical output is Task 10's job specifically — don't skip it as "redundant" with the fixture tests).
- **Crate location**: `rust/systhread-core/`, added to the existing `rust/Cargo.toml` workspace `members` list. `edition = "2024"`, `publish = false` (matches `rust/mission-engine`'s convention — this crate isn't yet the standalone, `nem-poweragent-lab`-independent package FR1 requires; that's Phase 1's extraction work).

---

## Task 0: Scaffold the crate and copy the acceptance-oracle fixtures

**Files:**
- Create: `rust/systhread-core/Cargo.toml`
- Create: `rust/systhread-core/src/lib.rs`
- Modify: `rust/Cargo.toml`
- Create (copied, verbatim): `rust/systhread-core/tests/fixtures/lab6/schema/digital_thread_instances.yaml`
- Create (copied, verbatim): `rust/systhread-core/tests/fixtures/lab6/schema/grid_instances.yaml`
- Create (copied, verbatim): `rust/systhread-core/tests/fixtures/lab6/schema/pipeline_phases_instances.yaml`
- Create (copied, verbatim): `rust/systhread-core/tests/fixtures/lab6/expected/expected_digital_thread.sysml`
- Create (copied, verbatim): `rust/systhread-core/tests/fixtures/lab6/expected/expected_grid_topology.sysml`
- Create (copied, verbatim): `rust/systhread-core/tests/fixtures/lab6/expected/expected_pipeline_phases.sysml`
- Create (copied, verbatim): `rust/systhread-core/tests/fixtures/lab6/expected/expected_digital_thread_iso_ir.json`
- Create (copied, verbatim): `rust/systhread-core/tests/fixtures/lab6/expected/expected_grid_topology_iso_ir.json`
- Create (copied, verbatim): `rust/systhread-core/tests/fixtures/lab6/expected/expected_pipeline_phases_iso_ir.json`
- Create (copied, verbatim): `rust/systhread-core/tests/fixtures/lab6/expected/expected_digital_thread.svg`
- Create (copied, verbatim): `rust/systhread-core/tests/fixtures/lab6/expected/expected_grid_topology.svg`
- Create (copied, verbatim): `rust/systhread-core/tests/fixtures/lab6/expected/expected_pipeline_phases.svg`
- Test: `rust/systhread-core/tests/fixtures_present.rs`

**Interfaces:**
- Produces: the crate skeleton every later task builds inside; the fixture directory layout `tests/fixtures/lab6/{schema,expected}/` every later task's tests read from, via a `fixture_path(rel: &str) -> std::path::PathBuf` test helper (defined in this task, in `tests/common/mod.rs`, reused by every later test file).

- [ ] **Step 1: Copy the fixtures verbatim**

```bash
mkdir -p rust/systhread-core/tests/fixtures/lab6/schema
mkdir -p rust/systhread-core/tests/fixtures/lab6/expected

cp labs/06-sysml-digital-thread/schema/digital_thread_instances.yaml \
   rust/systhread-core/tests/fixtures/lab6/schema/
cp labs/06-sysml-digital-thread/schema/grid_instances.yaml \
   rust/systhread-core/tests/fixtures/lab6/schema/
cp labs/06-sysml-digital-thread/schema/pipeline_phases_instances.yaml \
   rust/systhread-core/tests/fixtures/lab6/schema/

cp labs/06-sysml-digital-thread/fixtures/expected_digital_thread.sysml \
   labs/06-sysml-digital-thread/fixtures/expected_grid_topology.sysml \
   labs/06-sysml-digital-thread/fixtures/expected_pipeline_phases.sysml \
   labs/06-sysml-digital-thread/fixtures/expected_digital_thread_iso_ir.json \
   labs/06-sysml-digital-thread/fixtures/expected_grid_topology_iso_ir.json \
   labs/06-sysml-digital-thread/fixtures/expected_pipeline_phases_iso_ir.json \
   labs/06-sysml-digital-thread/fixtures/expected_digital_thread.svg \
   labs/06-sysml-digital-thread/fixtures/expected_grid_topology.svg \
   labs/06-sysml-digital-thread/fixtures/expected_pipeline_phases.svg \
   rust/systhread-core/tests/fixtures/lab6/expected/
```

- [ ] **Step 2: Write the crate manifest**

`rust/systhread-core/Cargo.toml`:

```toml
[package]
name = "systhread-core"
version = "0.1.0"
edition = "2024"
publish = false
description = "Phase 0 of the systhread MBSE capability (docs/superpowers/specs/2026-08-25-systhread-design.md): parse/validate/render for SysML v2 Part/containment models, ported from labs/06-sysml-digital-thread's Python pipeline."

[dependencies]
serde = { version = "1", features = ["derive"] }
serde_json = "1"
serde_norway = "0.9"
sysml-v2-parser = "0.54"
kasuari = "0.4"
```

- [ ] **Step 3: Add the crate to the workspace**

Modify `rust/Cargo.toml`:

```toml
[workspace]
members = ["phase-model", "demo-app", "fft-detector", "lab-launcher", "mission-engine", "systhread-core"]
resolver = "2"
```

- [ ] **Step 4: Write the shared test fixture-path helper**

`rust/systhread-core/tests/common/mod.rs`:

```rust
use std::path::{Path, PathBuf};

/// Resolves a path under `tests/fixtures/lab6/`, e.g. `fixture_path("schema/grid_instances.yaml")`.
pub fn fixture_path(rel: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures/lab6")
        .join(rel)
}
```

- [ ] **Step 5: Write a minimal `lib.rs` and the failing scaffold test**

`rust/systhread-core/src/lib.rs`:

```rust
//! Phase 0 of the systhread MBSE capability. See
//! docs/superpowers/specs/2026-08-25-systhread-design.md.
```

`rust/systhread-core/tests/fixtures_present.rs`:

```rust
mod common;
use common::fixture_path;

#[test]
fn lab6_fixtures_were_copied_verbatim() {
    let grid_instances = std::fs::read_to_string(fixture_path("schema/grid_instances.yaml"))
        .expect("grid_instances.yaml should have been copied in Task 0");
    assert!(grid_instances.contains("bus_4052"));

    let expected_grid_sysml =
        std::fs::read_to_string(fixture_path("expected/expected_grid_topology.sysml"))
            .expect("expected_grid_topology.sysml should have been copied in Task 0");
    assert!(expected_grid_sysml.starts_with("package GridTopology {"));
}
```

- [ ] **Step 6: Run the test and verify it passes**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml`
Expected: PASS (this task has no logic to fail — it's proving the copy step and crate wiring worked).

- [ ] **Step 7: Commit**

```bash
git add rust/Cargo.toml rust/systhread-core/
git commit -m "systhread: scaffold systhread-core crate, copy Lab 6 fixtures as acceptance oracle"
```

---

## Task 1: Instance data model and YAML loader

**Files:**
- Create: `rust/systhread-core/src/instances.rs`
- Modify: `rust/systhread-core/src/lib.rs`
- Test: `rust/systhread-core/tests/instances_test.rs`

**Interfaces:**
- Consumes: `common::fixture_path` (Task 0).
- Produces: `instances::{DigitalThreadInstances, AgentInstance, ServerOrSourceInstance, GridInstances, BusInstance, GeneratorInstance, LineInstance, PipelinePhasesInstances, PhaseInstance}` structs, and `instances::{load_digital_thread, load_grid, load_pipeline}(path: &std::path::Path) -> ...` loader functions — later tasks (2, 4) consume these types and functions directly.

- [ ] **Step 1: Write the failing test**

`rust/systhread-core/tests/instances_test.rs`:

```rust
mod common;
use common::fixture_path;
use systhread_core::instances::{load_digital_thread, load_grid, load_pipeline};

#[test]
fn loads_digital_thread_instances() {
    let inst = load_digital_thread(&fixture_path("schema/digital_thread_instances.yaml"));
    assert_eq!(inst.agents.len(), 2);
    assert_eq!(inst.mcp_servers.len(), 2);
    assert_eq!(inst.data_sources.len(), 3);

    let lab1 = &inst.agents[0];
    assert_eq!(lab1.name, "lab1_bisection_search");
    assert_eq!(lab1.source, "labs/01-simple-loadflow-fit/run.py");
    assert_eq!(lab1.uses.as_deref(), Some("csiro_synthetic_nem_2000bus"));
    assert_eq!(lab1.refresh_cadence, "on every lab run (--step fit)");
    assert_eq!(lab1.owner, "Lab 1 -- load-flow parameter fit");
}

#[test]
fn loads_grid_instances() {
    let inst = load_grid(&fixture_path("schema/grid_instances.yaml"));
    assert_eq!(inst.buses.len(), 15);
    assert_eq!(inst.generators.len(), 5);
    assert!(!inst.lines.is_empty());

    let bus_4052 = inst.buses.iter().find(|b| b.name == "bus_4052").unwrap();
    assert_eq!(bus_4052.voltage_kv, 15.75);
    assert_eq!(
        bus_4052.cim_class_uri,
        "http://iec.ch/TC57/2013/CIM-schema-cim16#TopologicalNode"
    );

    let gen_4052 = inst.generators.iter().find(|g| g.name == "gen_4052").unwrap();
    assert_eq!(gen_4052.bus, "bus_4052");
    assert_eq!(gen_4052.rated_mw, 127.3);
    assert_eq!(
        gen_4052.cim_class_uri,
        "http://iec.ch/TC57/2013/CIM-schema-cim16#SynchronousMachine"
    );
}

#[test]
fn loads_pipeline_instances() {
    let inst = load_pipeline(&fixture_path("schema/pipeline_phases_instances.yaml"));
    assert!(!inst.phases.is_empty());
    let phase0 = &inst.phases[0];
    assert_eq!(phase0.name, "phase0_source_location");
    assert_eq!(phase0.next.as_deref(), Some("phase1_grid_forming"));
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml instances_test`
Expected: FAIL to compile — `systhread_core::instances` does not exist yet.

- [ ] **Step 3: Write the implementation**

`rust/systhread-core/src/instances.rs`:

```rust
use serde::Deserialize;
use std::path::Path;

#[derive(Debug, Deserialize)]
pub struct DigitalThreadInstances {
    #[serde(default)]
    pub agents: Vec<AgentInstance>,
    #[serde(default)]
    pub mcp_servers: Vec<ServerOrSourceInstance>,
    #[serde(default)]
    pub data_sources: Vec<ServerOrSourceInstance>,
}

#[derive(Debug, Deserialize)]
pub struct AgentInstance {
    pub name: String,
    pub source: String,
    #[serde(default)]
    pub uses: Option<String>,
    pub refresh_cadence: String,
    pub owner: String,
}

/// MCPServer and DataSource instances share this exact field set in Lab 6's schema
/// (name/source/refresh_cadence/owner, no `uses`) -- see generate_sysml.py's own
/// render_digital_thread, which reads both kinds through identical dict keys.
#[derive(Debug, Deserialize)]
pub struct ServerOrSourceInstance {
    pub name: String,
    pub source: String,
    pub refresh_cadence: String,
    pub owner: String,
}

#[derive(Debug, Deserialize)]
pub struct GridInstances {
    #[serde(default)]
    pub buses: Vec<BusInstance>,
    #[serde(default)]
    pub generators: Vec<GeneratorInstance>,
    #[serde(default)]
    pub lines: Vec<LineInstance>,
}

#[derive(Debug, Deserialize)]
pub struct BusInstance {
    pub name: String,
    pub source: String,
    pub voltage_kv: f64,
    pub cim_class_uri: String,
}

#[derive(Debug, Deserialize)]
pub struct GeneratorInstance {
    pub name: String,
    pub source: String,
    pub bus: String,
    pub rated_mw: f64,
    pub cim_class_uri: String,
}

#[derive(Debug, Deserialize)]
pub struct LineInstance {
    pub name: String,
    pub source: String,
    pub from_bus: String,
    pub to_bus: String,
    pub kind: String,
    #[serde(default)]
    pub length_km: Option<f64>,
    pub cim_class_uri: String,
}

#[derive(Debug, Deserialize)]
pub struct PipelinePhasesInstances {
    #[serde(default)]
    pub phases: Vec<PhaseInstance>,
}

#[derive(Debug, Deserialize)]
pub struct PhaseInstance {
    pub name: String,
    pub source: String,
    pub role: String,
    #[serde(default)]
    pub next: Option<String>,
}

pub fn load_digital_thread(path: &Path) -> DigitalThreadInstances {
    let text = std::fs::read_to_string(path)
        .unwrap_or_else(|e| panic!("read {}: {e}", path.display()));
    serde_norway::from_str(&text).unwrap_or_else(|e| panic!("parse {}: {e}", path.display()))
}

pub fn load_grid(path: &Path) -> GridInstances {
    let text = std::fs::read_to_string(path)
        .unwrap_or_else(|e| panic!("read {}: {e}", path.display()));
    serde_norway::from_str(&text).unwrap_or_else(|e| panic!("parse {}: {e}", path.display()))
}

pub fn load_pipeline(path: &Path) -> PipelinePhasesInstances {
    let text = std::fs::read_to_string(path)
        .unwrap_or_else(|e| panic!("read {}: {e}", path.display()));
    serde_norway::from_str(&text).unwrap_or_else(|e| panic!("parse {}: {e}", path.display()))
}
```

Modify `rust/systhread-core/src/lib.rs` to add:

```rust
pub mod instances;
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml instances_test`
Expected: PASS. If `role`'s folded YAML block scalar (`role: >-`) doesn't parse identically to PyYAML's folding in `serde_norway`, this is where it would surface — the pipeline test doesn't assert on `role`'s exact text yet (Task 2's fixture-diff test will, since `role` isn't emitted into `.sysml` at all — re-check: `generate_sysml.py`'s `render_pipeline_phases` does NOT emit `role` into the `.sysml` output at all, only `source`/`next`. So `role`'s exact folding behavior is never actually load-bearing for byte-identical output — safe either way.)

- [ ] **Step 5: Commit**

```bash
git add rust/systhread-core/src/instances.rs rust/systhread-core/src/lib.rs rust/systhread-core/tests/instances_test.rs
git commit -m "systhread-core: instance data model and YAML loader for all three Lab 6 tracks"
```

---

## Task 2: SysML v2 text generator (byte-identical against Lab 6's fixtures)

**Files:**
- Create: `rust/systhread-core/src/sysml_gen.rs`
- Modify: `rust/systhread-core/src/lib.rs`
- Test: `rust/systhread-core/tests/sysml_gen_test.rs`

**Interfaces:**
- Consumes: `instances::{DigitalThreadInstances, GridInstances, PipelinePhasesInstances}` (Task 1).
- Produces: `sysml_gen::{render_digital_thread, render_grid_topology, render_pipeline_phases}(inst: &...) -> String` — Task 4 and later tasks that need generated `.sysml` text (none in Phase 0 actually re-parse it, per the Global Constraints note, but Task 3's validator does call these to get text to validate).

**Design note — the one real formatting gotcha in this task:** every numeric field in Lab 6's grid schema (`voltage_kv`, `rated_mw`, `length_km`) is written in YAML with an explicit decimal point (e.g. `275.0`, `127.3`, `0.0` — confirmed by reading `grid_instances.yaml` directly), so Python's f-string `f"{value}"` always prints a `.0`-suffixed value for whole numbers (`275.0`, never `275`). Rust's default `f64` `Display` does **not** do this — `format!("{}", 275.0_f64)` prints `"275"`, not `"275.0"`. Left unfixed, every whole-number attribute in the generated `.sysml` would silently drop its `.0` and fail the byte-identical gate. Fixed with a small formatter, `fmt_real`, tested directly against the real values found in the fixture data.

- [ ] **Step 1: Write the failing test**

`rust/systhread-core/tests/sysml_gen_test.rs`:

```rust
mod common;
use common::fixture_path;
use systhread_core::instances::{load_digital_thread, load_grid, load_pipeline};
use systhread_core::sysml_gen::{render_digital_thread, render_grid_topology, render_pipeline_phases};

#[test]
fn digital_thread_matches_fixture_byte_identical() {
    let inst = load_digital_thread(&fixture_path("schema/digital_thread_instances.yaml"));
    let got = render_digital_thread(&inst);
    let expected = std::fs::read_to_string(fixture_path("expected/expected_digital_thread.sysml")).unwrap();
    assert_eq!(got, expected);
}

#[test]
fn grid_topology_matches_fixture_byte_identical() {
    let inst = load_grid(&fixture_path("schema/grid_instances.yaml"));
    let got = render_grid_topology(&inst);
    let expected = std::fs::read_to_string(fixture_path("expected/expected_grid_topology.sysml")).unwrap();
    assert_eq!(got, expected);
}

#[test]
fn pipeline_phases_matches_fixture_byte_identical() {
    let inst = load_pipeline(&fixture_path("schema/pipeline_phases_instances.yaml"));
    let got = render_pipeline_phases(&inst);
    let expected = std::fs::read_to_string(fixture_path("expected/expected_pipeline_phases.sysml")).unwrap();
    assert_eq!(got, expected);
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml sysml_gen_test`
Expected: FAIL to compile — `systhread_core::sysml_gen` does not exist yet.

- [ ] **Step 3: Write the implementation**

`rust/systhread-core/src/sysml_gen.rs`:

```rust
use crate::instances::{DigitalThreadInstances, GridInstances, PipelinePhasesInstances};

fn esc(value: &str) -> String {
    value.replace('\\', "\\\\").replace('"', "\\\"")
}

/// Formats an f64 the way Python's f"{value}" formats a YAML-sourced float: always includes a
/// decimal point, even for whole numbers (275.0, not 275) -- Rust's default f64 Display omits it.
/// Every numeric value in Lab 6's grid schema is written with an explicit decimal point in YAML,
/// so this path is always exercised, never the bare-integer path.
fn fmt_real(value: f64) -> String {
    let s = format!("{value}");
    if s.contains('.') || s.contains('e') || s.contains('E') {
        s
    } else {
        format!("{s}.0")
    }
}

pub fn render_digital_thread(inst: &DigitalThreadInstances) -> String {
    let mut lines: Vec<String> = vec![
        "package DigitalThread {".to_string(),
        "    // Generated by labs/06-sysml-digital-thread/generate_sysml.py -- do not hand-edit.".to_string(),
        "    // Source: labs/06-sysml-digital-thread/schema/digital_thread_instances.yaml".to_string(),
        String::new(),
    ];

    for def_name in ["Agent", "MCPServer", "DataSource"] {
        lines.push(format!("    part def {def_name} {{"));
        lines.push("        attribute source : String;".to_string());
        if def_name == "Agent" {
            lines.push("        attribute uses : String;".to_string());
        }
        lines.push("        attribute refreshCadence : String;".to_string());
        lines.push("        attribute owner : String;".to_string());
        lines.push("    }".to_string());
        lines.push(String::new());
    }
    lines.push("    part digitalThread {".to_string());

    struct Entry<'a> {
        name: &'a str,
        type_name: &'static str,
        source: &'a str,
        uses: Option<&'a str>,
        refresh_cadence: &'a str,
        owner: &'a str,
    }

    let mut entries: Vec<Entry> = Vec::new();
    for a in &inst.agents {
        entries.push(Entry {
            name: &a.name,
            type_name: "Agent",
            source: &a.source,
            uses: a.uses.as_deref(),
            refresh_cadence: &a.refresh_cadence,
            owner: &a.owner,
        });
    }
    for m in &inst.mcp_servers {
        entries.push(Entry {
            name: &m.name,
            type_name: "MCPServer",
            source: &m.source,
            uses: None,
            refresh_cadence: &m.refresh_cadence,
            owner: &m.owner,
        });
    }
    for d in &inst.data_sources {
        entries.push(Entry {
            name: &d.name,
            type_name: "DataSource",
            source: &d.source,
            uses: None,
            refresh_cadence: &d.refresh_cadence,
            owner: &d.owner,
        });
    }

    let total = entries.len();
    for (i, e) in entries.iter().enumerate() {
        lines.push(format!("        part {} : {} {{", e.name, e.type_name));
        lines.push(format!("            attribute source = \"{}\";", esc(e.source)));
        if let Some(uses) = e.uses {
            lines.push(format!("            attribute uses = \"{}\";", esc(uses)));
        }
        lines.push(format!(
            "            attribute refreshCadence = \"{}\";",
            esc(e.refresh_cadence)
        ));
        lines.push(format!("            attribute owner = \"{}\";", esc(e.owner)));
        lines.push("        }".to_string());
        if i != total - 1 {
            lines.push(String::new());
        }
    }
    lines.push("    }".to_string());
    lines.push("}".to_string());
    lines.join("\n") + "\n"
}

pub fn render_grid_topology(inst: &GridInstances) -> String {
    let mut lines: Vec<String> = vec![
        "package GridTopology {".to_string(),
        "    // Generated by labs/06-sysml-digital-thread/generate_sysml.py -- do not hand-edit.".to_string(),
        "    // Source: labs/06-sysml-digital-thread/schema/grid_instances.yaml".to_string(),
        String::new(),
        "    part def Bus {".to_string(),
        "        attribute source : String;".to_string(),
        "        attribute voltageKV : Real;".to_string(),
        "        attribute cimClassUri : String;".to_string(),
        "    }".to_string(),
        String::new(),
        "    part def Generator {".to_string(),
        "        attribute source : String;".to_string(),
        "        attribute bus : String;".to_string(),
        "        attribute ratedMW : Real;".to_string(),
        "        attribute cimClassUri : String;".to_string(),
        "    }".to_string(),
        String::new(),
        "    part def Line {".to_string(),
        "        attribute source : String;".to_string(),
        "        attribute fromBus : String;".to_string(),
        "        attribute toBus : String;".to_string(),
        "        attribute kind : String;".to_string(),
        "        attribute lengthKM : Real;".to_string(),
        "        attribute cimClassUri : String;".to_string(),
        "    }".to_string(),
        String::new(),
        "    part gridTopology {".to_string(),
    ];

    let total = inst.buses.len() + inst.generators.len() + inst.lines.len();
    let mut i = 0;

    for b in &inst.buses {
        lines.push(format!("        part {} : Bus {{", b.name));
        lines.push(format!("            attribute source = \"{}\";", esc(&b.source)));
        lines.push(format!("            attribute voltageKV = {};", fmt_real(b.voltage_kv)));
        lines.push(format!(
            "            attribute cimClassUri = \"{}\";",
            esc(&b.cim_class_uri)
        ));
        lines.push("        }".to_string());
        i += 1;
        if i != total {
            lines.push(String::new());
        }
    }

    for g in &inst.generators {
        lines.push(format!("        part {} : Generator {{", g.name));
        lines.push(format!("            attribute source = \"{}\";", esc(&g.source)));
        lines.push(format!("            attribute bus = \"{}\";", g.bus));
        lines.push(format!("            attribute ratedMW = {};", fmt_real(g.rated_mw)));
        lines.push(format!(
            "            attribute cimClassUri = \"{}\";",
            esc(&g.cim_class_uri)
        ));
        lines.push("        }".to_string());
        i += 1;
        if i != total {
            lines.push(String::new());
        }
    }

    for l in &inst.lines {
        lines.push(format!("        part {} : Line {{", l.name));
        lines.push(format!("            attribute source = \"{}\";", esc(&l.source)));
        lines.push(format!("            attribute fromBus = \"{}\";", l.from_bus));
        lines.push(format!("            attribute toBus = \"{}\";", l.to_bus));
        lines.push(format!("            attribute kind = \"{}\";", l.kind));
        if let Some(length_km) = l.length_km {
            lines.push(format!("            attribute lengthKM = {};", fmt_real(length_km)));
        }
        lines.push(format!(
            "            attribute cimClassUri = \"{}\";",
            esc(&l.cim_class_uri)
        ));
        lines.push("        }".to_string());
        i += 1;
        if i != total {
            lines.push(String::new());
        }
    }

    lines.push("    }".to_string());
    lines.push("}".to_string());
    lines.join("\n") + "\n"
}

pub fn render_pipeline_phases(inst: &PipelinePhasesInstances) -> String {
    let mut lines: Vec<String> = vec![
        "package PipelinePhases {".to_string(),
        "    // Generated by labs/06-sysml-digital-thread/generate_sysml.py -- do not hand-edit.".to_string(),
        "    // Source: labs/06-sysml-digital-thread/schema/pipeline_phases_instances.yaml".to_string(),
        String::new(),
        "    part def Phase {".to_string(),
        "        attribute source : String;".to_string(),
        "        attribute role : String;".to_string(),
        "        attribute next : String;".to_string(),
        "    }".to_string(),
        String::new(),
        "    part pipelinePhases {".to_string(),
    ];

    let total = inst.phases.len();
    for (i, p) in inst.phases.iter().enumerate() {
        lines.push(format!("        part {} : Phase {{", p.name));
        lines.push(format!("            attribute source = \"{}\";", esc(&p.source)));
        lines.push(format!("            attribute role = \"{}\";", esc(&p.role)));
        if let Some(next) = &p.next {
            lines.push(format!("            attribute next = \"{next}\";"));
        }
        lines.push("        }".to_string());
        if i != total - 1 {
            lines.push(String::new());
        }
    }

    lines.push("    }".to_string());
    lines.push("}".to_string());
    lines.join("\n") + "\n"
}
```

Modify `rust/systhread-core/src/lib.rs` to add:

```rust
pub mod sysml_gen;
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml sysml_gen_test`
Expected: PASS. If it fails on a specific line, diff the actual vs. expected output directly (`cargo test ... -- --nocapture` plus a temporary `eprintln!` of both strings, or write `got`/`expected` to two files and `diff` them) rather than guessing — the most likely failure modes are a stray/missing blank line at a track boundary, or `fmt_real` disagreeing with Python's float formatting on a value not covered by this task's manual review (the concrete grid values found in the fixture data were: `voltage_kv` ∈ {15.75, 275.0, 66.0}, `rated_mw` ∈ {0.0, 127.3, 135.2, 137.6}, `length_km` = 1.0 — all covered).

- [ ] **Step 5: Commit**

```bash
git add rust/systhread-core/src/sysml_gen.rs rust/systhread-core/src/lib.rs rust/systhread-core/tests/sysml_gen_test.rs
git commit -m "systhread-core: SysML v2 text generator, byte-identical against Lab 6's three fixtures"
```

**Milestone A complete.** This is a natural PR boundary: crate scaffold + data model + generator, fully green.

---

## Task 3: Syntax validation via `sysml-v2-parser`

**Files:**
- Create: `rust/systhread-core/src/validate.rs`
- Modify: `rust/systhread-core/src/lib.rs`
- Test: `rust/systhread-core/tests/validate_test.rs`

**Interfaces:**
- Consumes: `sysml_gen::{render_digital_thread, render_grid_topology, render_pipeline_phases}` (Task 2), `sysml_v2_parser::parse` (external crate, confirmed signature `pub fn parse(input: &str) -> Result<RootNamespace, ParseError>`).
- Produces: `validate::is_valid_sysml(text: &str) -> Result<(), String>` — a thin wrapper, not consumed by any other Phase 0 task (Phase 1's `systhread-cli check` subcommand is the real consumer, out of scope here).

- [ ] **Step 1: Write the failing test**

`rust/systhread-core/tests/validate_test.rs`:

```rust
mod common;
use common::fixture_path;
use systhread_core::instances::{load_digital_thread, load_grid, load_pipeline};
use systhread_core::sysml_gen::{render_digital_thread, render_grid_topology, render_pipeline_phases};
use systhread_core::validate::is_valid_sysml;

#[test]
fn accepts_all_three_generated_tracks() {
    let dt = load_digital_thread(&fixture_path("schema/digital_thread_instances.yaml"));
    assert!(is_valid_sysml(&render_digital_thread(&dt)).is_ok());

    let grid = load_grid(&fixture_path("schema/grid_instances.yaml"));
    assert!(is_valid_sysml(&render_grid_topology(&grid)).is_ok());

    let pipeline = load_pipeline(&fixture_path("schema/pipeline_phases_instances.yaml"));
    assert!(is_valid_sysml(&render_pipeline_phases(&pipeline)).is_ok());
}

#[test]
fn rejects_broken_input_with_a_real_error() {
    let broken = "package Broken {\n    part def X {\n";
    let err = is_valid_sysml(broken).expect_err("unterminated block must be rejected");
    assert!(!err.is_empty());
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml validate_test`
Expected: FAIL to compile — `systhread_core::validate` does not exist yet.

- [ ] **Step 3: Write the implementation**

`rust/systhread-core/src/validate.rs`:

```rust
/// Syntax gate for generated `.sysml` text, using the real native-Rust SysML v2 parser
/// (`sysml-v2-parser`, MIT) rather than a hand-rolled structural stand-in -- Lab 6's own
/// `validate_sysml.py` only used a line-pattern checker because no working Rust parser existed
/// at the time; this repo already spiked `sysml-v2-parser` against Lab 6's own generated output
/// with a confirmed 3/3 pass (labs/08-cim-gridy-phase0-spikes/0b-sysml-v2-parser/).
pub fn is_valid_sysml(text: &str) -> Result<(), String> {
    sysml_v2_parser::parse(text)
        .map(|_root_namespace| ())
        .map_err(|e| e.to_string())
}
```

Modify `rust/systhread-core/src/lib.rs` to add:

```rust
pub mod validate;
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml validate_test`
Expected: PASS. If `ParseError` doesn't implement `Display` (needed for `.to_string()`), check `sysml_v2_parser::ParseError`'s actual trait impls (its own README error text shown in the Phase-0b spike write-up strongly suggests it does — real diagnostic text with line/column was printed there) and adjust to `format!("{:?}", e)` if not.

- [ ] **Step 5: Commit**

```bash
git add rust/systhread-core/src/validate.rs rust/systhread-core/src/lib.rs rust/systhread-core/tests/validate_test.rs
git commit -m "systhread-core: wire sysml-v2-parser as the syntax gate for generated SysML v2 text"
```

**Milestone B complete.**

---

## Task 4: iso-IR node/edge structural extraction (no positions yet)

**Files:**
- Create: `rust/systhread-core/src/iso_ir.rs`
- Modify: `rust/systhread-core/src/lib.rs`
- Test: `rust/systhread-core/tests/iso_ir_structure_test.rs`

**Interfaces:**
- Consumes: `instances::{DigitalThreadInstances, GridInstances, PipelinePhasesInstances}` (Task 1).
- Produces: `iso_ir::{Node, Edge}` structs and `iso_ir::{extract_digital_thread, extract_grid, extract_pipeline}(inst: &...) -> (Vec<Node>, Vec<Edge>)` — consumed by Task 6, 7, and 8.

**Design note:** this mirrors `translate_iso_ir.py`'s `parse_parts` output shape exactly (same node ids/labels/types, same edge ids/from/to/type/kind), but is built directly from the typed instance structs rather than regex-walking generated `.sysml` text, per this plan's Global Constraints.

- [ ] **Step 1: Write the failing test**

`rust/systhread-core/tests/iso_ir_structure_test.rs`:

```rust
mod common;
use common::fixture_path;
use systhread_core::instances::{load_digital_thread, load_grid, load_pipeline};
use systhread_core::iso_ir::{extract_digital_thread, extract_grid, extract_pipeline, Edge, Node};

/// Reads a `nodes`/`edges` fixture JSON and returns just the (id, part_type-independent label)
/// pairs and the edges list, both in fixture order -- Task 4 doesn't compute positions/shape/type
/// yet, so this helper strips those fields before comparing.
fn expected_node_ids(fixture_rel: &str) -> Vec<String> {
    let text = std::fs::read_to_string(fixture_path(fixture_rel)).unwrap();
    let json: serde_json::Value = serde_json::from_str(&text).unwrap();
    json["nodes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|n| n["id"].as_str().unwrap().to_string())
        .collect()
}

fn expected_edges(fixture_rel: &str) -> Vec<Edge> {
    let text = std::fs::read_to_string(fixture_path(fixture_rel)).unwrap();
    let json: serde_json::Value = serde_json::from_str(&text).unwrap();
    json.get("edges")
        .and_then(|e| e.as_array())
        .map(|arr| {
            arr.iter()
                .map(|e| Edge {
                    id: e["id"].as_str().unwrap().to_string(),
                    from: e["from"].as_str().unwrap().to_string(),
                    to: e["to"].as_str().unwrap().to_string(),
                    edge_type: e["type"].as_str().unwrap().to_string(),
                    kind: e.get("kind").and_then(|k| k.as_str()).map(String::from),
                })
                .collect()
        })
        .unwrap_or_default()
}

#[test]
fn digital_thread_structure_matches_fixture() {
    let inst = load_digital_thread(&fixture_path("schema/digital_thread_instances.yaml"));
    let (nodes, edges) = extract_digital_thread(&inst);
    let ids: Vec<String> = nodes.iter().map(|n| n.id.clone()).collect();
    assert_eq!(ids, expected_node_ids("expected/expected_digital_thread_iso_ir.json"));
    assert_eq!(edges, expected_edges("expected/expected_digital_thread_iso_ir.json"));
}

#[test]
fn grid_structure_matches_fixture() {
    let inst = load_grid(&fixture_path("schema/grid_instances.yaml"));
    let (nodes, edges) = extract_grid(&inst);
    let ids: Vec<String> = nodes.iter().map(|n| n.id.clone()).collect();
    assert_eq!(ids, expected_node_ids("expected/expected_grid_topology_iso_ir.json"));
    assert_eq!(edges, expected_edges("expected/expected_grid_topology_iso_ir.json"));
}

#[test]
fn pipeline_structure_matches_fixture() {
    let inst = load_pipeline(&fixture_path("schema/pipeline_phases_instances.yaml"));
    let (nodes, edges) = extract_pipeline(&inst);
    let ids: Vec<String> = nodes.iter().map(|n| n.id.clone()).collect();
    assert_eq!(ids, expected_node_ids("expected/expected_pipeline_phases_iso_ir.json"));
    assert_eq!(edges, expected_edges("expected/expected_pipeline_phases_iso_ir.json"));
}
```

Add `serde_json` as a dependency available to tests (already a normal dependency from Task 0, so no `[dev-dependencies]` change needed).

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml iso_ir_structure_test`
Expected: FAIL to compile — `systhread_core::iso_ir` does not exist yet.

- [ ] **Step 3: Write the implementation**

`rust/systhread-core/src/iso_ir.rs`:

```rust
use crate::instances::{DigitalThreadInstances, GridInstances, PipelinePhasesInstances};

#[derive(Debug, Clone, PartialEq)]
pub struct Node {
    pub id: String,
    pub label: String,
    /// The SysML part-def type name this node came from ("Agent" | "MCPServer" | "DataSource" |
    /// "Bus" | "Generator" | "Phase") -- Task 8 maps this to the iso-IR "type"/"shape" fields.
    pub part_type: &'static str,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Edge {
    pub id: String,
    pub from: String,
    pub to: String,
    pub edge_type: String,
    pub kind: Option<String>,
}

pub fn extract_digital_thread(inst: &DigitalThreadInstances) -> (Vec<Node>, Vec<Edge>) {
    let mut nodes = Vec::new();
    let mut edges = Vec::new();

    for a in &inst.agents {
        nodes.push(Node {
            id: a.name.clone(),
            label: a.name.clone(),
            part_type: "Agent",
        });
        if let Some(uses) = &a.uses {
            edges.push(Edge {
                id: format!("{}_attach", a.name),
                from: a.name.clone(),
                to: uses.clone(),
                edge_type: "attachment".to_string(),
                kind: None,
            });
        }
    }
    for m in &inst.mcp_servers {
        nodes.push(Node {
            id: m.name.clone(),
            label: m.name.clone(),
            part_type: "MCPServer",
        });
    }
    for d in &inst.data_sources {
        nodes.push(Node {
            id: d.name.clone(),
            label: d.name.clone(),
            part_type: "DataSource",
        });
    }
    (nodes, edges)
}

pub fn extract_grid(inst: &GridInstances) -> (Vec<Node>, Vec<Edge>) {
    let mut nodes = Vec::new();
    let mut edges = Vec::new();

    for b in &inst.buses {
        nodes.push(Node {
            id: b.name.clone(),
            label: b.name.clone(),
            part_type: "Bus",
        });
    }
    for g in &inst.generators {
        nodes.push(Node {
            id: g.name.clone(),
            label: g.name.clone(),
            part_type: "Generator",
        });
        edges.push(Edge {
            id: format!("{}_attach", g.name),
            from: g.name.clone(),
            to: g.bus.clone(),
            edge_type: "attachment".to_string(),
            kind: None,
        });
    }
    for l in &inst.lines {
        edges.push(Edge {
            id: l.name.clone(),
            from: l.from_bus.clone(),
            to: l.to_bus.clone(),
            edge_type: "branch".to_string(),
            kind: Some(l.kind.clone()),
        });
    }
    (nodes, edges)
}

pub fn extract_pipeline(inst: &PipelinePhasesInstances) -> (Vec<Node>, Vec<Edge>) {
    let mut nodes = Vec::new();
    let mut edges = Vec::new();

    for p in &inst.phases {
        nodes.push(Node {
            id: p.name.clone(),
            label: p.name.clone(),
            part_type: "Phase",
        });
        if let Some(next) = &p.next {
            edges.push(Edge {
                id: format!("{}_next", p.name),
                from: p.name.clone(),
                to: next.clone(),
                edge_type: "sequence".to_string(),
                kind: None,
            });
        }
    }
    (nodes, edges)
}
```

Modify `rust/systhread-core/src/lib.rs` to add:

```rust
pub mod iso_ir;
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml iso_ir_structure_test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rust/systhread-core/src/iso_ir.rs rust/systhread-core/src/lib.rs rust/systhread-core/tests/iso_ir_structure_test.rs
git commit -m "systhread-core: iso-IR node/edge structural extraction, matching Lab 6's parse_parts output"
```

---

## Task 5: Grid (row-major) layout — the no-edges fallback

**Files:**
- Modify: `rust/systhread-core/src/iso_ir.rs`
- Test: (inline `#[cfg(test)]` module in the same file — this function has no fixture to test against, since none of Lab 6's three real tracks ever hits this path; see Design note.)

**Interfaces:**
- Produces: `iso_ir::grid_positions(n: usize) -> Vec<(f64, f64)>` — used by Task 8's dispatch as the third arm (`if no edges at all`), alongside Task 6 and 7's layout functions.

**Design note:** `translate_iso_ir.py`'s `_grid_positions` is Lab 6's fallback for a track with zero edges. None of the three real committed tracks ever hits this branch (digital-thread, grid, and pipeline all have real edges — confirmed by reading all three expected iso-IR fixtures in Task 4). Port it anyway for dispatch completeness (Task 8's `if/else if/else` needs a real third arm, not a `todo!()`), but test it directly with a unit test instead of a fixture comparison, since no fixture exercises it.

- [ ] **Step 1: Write the failing test**

Append to `rust/systhread-core/src/iso_ir.rs`:

```rust
#[cfg(test)]
mod grid_positions_tests {
    use super::grid_positions;

    #[test]
    fn lays_out_row_major_with_spacing_two_per_row_three() {
        // Ports translate_iso_ir.py's _grid_positions(n, per_row=3, spacing=2) defaults exactly:
        // (i % 3) * 2, (i // 3) * 2.
        let positions = grid_positions(5);
        assert_eq!(
            positions,
            vec![(0.0, 0.0), (2.0, 0.0), (4.0, 0.0), (0.0, 2.0), (2.0, 2.0)]
        );
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml --lib grid_positions_tests`
Expected: FAIL to compile — `grid_positions` does not exist yet.

- [ ] **Step 3: Write the implementation**

Add to `rust/systhread-core/src/iso_ir.rs` (above the `#[cfg(test)]` block):

```rust
const PER_ROW: usize = 3;
const SPACING: f64 = 2.0;

/// Deterministic row-major grid layout -- Lab 6's fallback for a track with no edges at all.
/// None of the three real committed tracks currently hits this path (see this task's own
/// docstring in the plan); ported for dispatch completeness.
pub fn grid_positions(n: usize) -> Vec<(f64, f64)> {
    (0..n)
        .map(|i| (((i % PER_ROW) as f64) * SPACING, ((i / PER_ROW) as f64) * SPACING))
        .collect()
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml --lib grid_positions_tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rust/systhread-core/src/iso_ir.rs
git commit -m "systhread-core: port the no-edges grid-positions fallback layout"
```

---

## Task 6: Cassowary anchor/leaf layout via `kasuari`

**Files:**
- Create: `rust/systhread-core/src/layout.rs`
- Modify: `rust/systhread-core/src/lib.rs`
- Test: `rust/systhread-core/tests/layout_cassowary_test.rs`

**Interfaces:**
- Consumes: `iso_ir::{Node, Edge}` (Task 4).
- Produces: `layout::cassowary_positions(nodes: &[Node], edges: &[Edge]) -> Vec<(f64, f64)>` (one `(x, y)` per node, in `nodes` order) — consumed by Task 8.

**Design note — the real API this task depends on** (verified directly against `kasuari 0.4.12`'s source, not assumed from the Python port's docstring, since `kasuari`'s constraint syntax differs from `kiwisolver`'s):
- `kasuari::Variable::new()` creates an opaque handle (no name argument — unlike `kiwi.Variable(name)`).
- A constraint is built as `expr | RELATION(strength) | rhs`, e.g. `(x_vars[left] + BUS_GAP) | LE(Strength::REQUIRED) | x_vars[right]`, using `kasuari::WeightedRelation::{EQ, LE, GE}` and `kasuari::Strength::{REQUIRED, STRONG, WEAK}`.
- `solver.add_constraints([...])` takes an iterator of built constraints and returns `Result<(), AddConstraintError>`.
- `solver.get_value(variable) -> f64` reads a variable's current solved value directly (this task uses this, not `fetch_changes`, since Phase 0 only cares about final values, not incremental diffs).
- Values are read via `Expression`/`Term` arithmetic on `Variable`s (`+`, `-`, `*`) exactly as in the Python port's own `kiwisolver` usage — the algebra is the same Cassowary primitives, only the Rust operator-overload spelling differs.

- [ ] **Step 1: Write the failing test**

`rust/systhread-core/tests/layout_cassowary_test.rs`:

```rust
mod common;
use common::fixture_path;
use systhread_core::instances::{load_digital_thread, load_grid};
use systhread_core::iso_ir::{extract_digital_thread, extract_grid};
use systhread_core::layout::cassowary_positions;

fn expected_positions(fixture_rel: &str) -> Vec<(f64, f64)> {
    let text = std::fs::read_to_string(fixture_path(fixture_rel)).unwrap();
    let json: serde_json::Value = serde_json::from_str(&text).unwrap();
    json["nodes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|n| {
            (
                n["position"]["x"].as_f64().unwrap(),
                n["position"]["y"].as_f64().unwrap(),
            )
        })
        .collect()
}

#[test]
fn digital_thread_positions_match_fixture() {
    let inst = load_digital_thread(&fixture_path("schema/digital_thread_instances.yaml"));
    let (nodes, edges) = extract_digital_thread(&inst);
    let got = cassowary_positions(&nodes, &edges);
    assert_eq!(got, expected_positions("expected/expected_digital_thread_iso_ir.json"));
}

#[test]
fn grid_topology_positions_match_fixture() {
    let inst = load_grid(&fixture_path("schema/grid_instances.yaml"));
    let (nodes, edges) = extract_grid(&inst);
    let got = cassowary_positions(&nodes, &edges);
    assert_eq!(got, expected_positions("expected/expected_grid_topology_iso_ir.json"));
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml layout_cassowary_test`
Expected: FAIL to compile — `systhread_core::layout` does not exist yet.

- [ ] **Step 3: Write the implementation**

`rust/systhread-core/src/layout.rs`:

```rust
use crate::iso_ir::{Edge, Node};
use kasuari::WeightedRelation::{EQ, GE, LE};
use kasuari::{Solver, Strength, Variable};
use std::collections::{BTreeMap, BTreeSet, VecDeque};

pub const ROW_SPACING: f64 = 2.0;
pub const BUS_GAP: f64 = 2.0;

fn round6(v: f64) -> f64 {
    (v * 1_000_000.0).round() / 1_000_000.0
}

/// BFS forest over the real anchor-to-anchor `branch` graph -- one tree per connected component,
/// rooted at that component's own highest-real-degree anchor (ties broken by id for determinism).
/// Ports translate_iso_ir.py's `_anchor_forest` exactly, including its tie-break rule.
fn anchor_forest(
    anchor_ids: &[String],
    adjacency: &BTreeMap<String, BTreeSet<String>>,
) -> (BTreeMap<String, u32>, BTreeMap<String, String>, Vec<String>) {
    let mut depth: BTreeMap<String, u32> = BTreeMap::new();
    let mut parent: BTreeMap<String, String> = BTreeMap::new();
    let mut roots: Vec<String> = Vec::new();
    let mut remaining: BTreeSet<String> = anchor_ids.iter().cloned().collect();

    while !remaining.is_empty() {
        let root = remaining
            .iter()
            .min_by_key(|b| {
                let degree = adjacency.get(*b).map(|n| n.intersection(&remaining).count()).unwrap_or(0);
                (std::cmp::Reverse(degree), (*b).clone())
            })
            .unwrap()
            .clone();
        roots.push(root.clone());
        depth.insert(root.clone(), 0);
        remaining.remove(&root);

        let mut queue: VecDeque<String> = VecDeque::new();
        queue.push_back(root);
        while let Some(current) = queue.pop_front() {
            let neighbours = adjacency.get(&current).cloned().unwrap_or_default();
            for neighbour in neighbours {
                if remaining.contains(&neighbour) {
                    let d = depth[&current] + 1;
                    depth.insert(neighbour.clone(), d);
                    parent.insert(neighbour.clone(), current.clone());
                    remaining.remove(&neighbour);
                    queue.push_back(neighbour);
                }
            }
        }
    }
    (depth, parent, roots)
}

/// Solves each depth level's x positions with `kasuari`, one level at a time. Ports
/// translate_iso_ir.py's `_level_x_positions` exactly: depth 0 (component roots) get REQUIRED
/// gaps plus a WEAK pin on the first root at x=0; each deeper level gets REQUIRED sibling gaps
/// plus a REQUIRED centroid-equals-parent constraint, sibling *groups* also kept BUS_GAP apart.
fn level_x_positions(
    anchor_ids: &[String],
    depth: &BTreeMap<String, u32>,
    parent: &BTreeMap<String, String>,
    roots: &[String],
) -> BTreeMap<String, f64> {
    let mut x_by_anchor: BTreeMap<String, f64> = BTreeMap::new();
    if anchor_ids.is_empty() {
        return x_by_anchor;
    }

    let mut ordered_roots: Vec<String> = roots.to_vec();
    ordered_roots.sort();

    {
        let mut solver = Solver::new();
        let root_vars: BTreeMap<String, Variable> =
            ordered_roots.iter().map(|r| (r.clone(), Variable::new())).collect();
        for pair in ordered_roots.windows(2) {
            let (left, right) = (&pair[0], &pair[1]);
            solver
                .add_constraints([(root_vars[left] + BUS_GAP) | LE(Strength::REQUIRED) | root_vars[right]])
                .unwrap();
        }
        if let Some(first) = ordered_roots.first() {
            solver
                .add_constraints([root_vars[first] | EQ(Strength::WEAK) | 0.0])
                .unwrap();
        }
        for r in &ordered_roots {
            x_by_anchor.insert(r.clone(), round6(solver.get_value(root_vars[r])));
        }
    }

    let max_depth = depth.values().copied().max().unwrap_or(0);
    for d in 1..=max_depth {
        let level: Vec<String> = anchor_ids
            .iter()
            .filter(|b| depth.get(*b) == Some(&d))
            .cloned()
            .collect();
        if level.is_empty() {
            continue;
        }
        let mut groups: BTreeMap<String, Vec<String>> = BTreeMap::new();
        for b in &level {
            groups.entry(parent[b].clone()).or_default().push(b.clone());
        }
        let mut ordered_parents: Vec<String> = groups.keys().cloned().collect();
        ordered_parents.sort_by(|a, b| x_by_anchor[a].total_cmp(&x_by_anchor[b]));

        let mut solver = Solver::new();
        let mut x_vars: BTreeMap<String, Variable> = BTreeMap::new();
        let mut previous_group_last: Option<Variable> = None;
        for p in &ordered_parents {
            let siblings = &groups[p];
            for b in siblings {
                x_vars.insert(b.clone(), Variable::new());
            }
            for pair in siblings.windows(2) {
                let (left, right) = (&pair[0], &pair[1]);
                solver
                    .add_constraints([(x_vars[left] + BUS_GAP) | LE(Strength::REQUIRED) | x_vars[right]])
                    .unwrap();
            }
            let mut total = kasuari::Expression::from_variable(x_vars[&siblings[0]]);
            for b in &siblings[1..] {
                total = total + x_vars[b];
            }
            let target = siblings.len() as f64 * x_by_anchor[p];
            solver.add_constraints([total | EQ(Strength::REQUIRED) | target]).unwrap();
            if let Some(prev_last) = previous_group_last {
                solver
                    .add_constraints([(prev_last + BUS_GAP) | LE(Strength::REQUIRED) | x_vars[&siblings[0]]])
                    .unwrap();
            }
            previous_group_last = Some(x_vars[siblings.last().unwrap()]);
        }
        for (b, var) in &x_vars {
            x_by_anchor.insert(b.clone(), round6(solver.get_value(*var)));
        }
    }
    x_by_anchor
}

/// Ports translate_iso_ir.py's `_cassowary_positions` exactly: anchors (nodes that are not the
/// `from` side of an `attachment` edge) are laid out by their real `branch`-edge graph; leaves
/// (nodes that are the `from` side of an `attachment` edge) are pulled to their target anchor's x,
/// one row below, grouped/centered the same way anchors are.
pub fn cassowary_positions(nodes: &[Node], edges: &[Edge]) -> Vec<(f64, f64)> {
    let attach_target: BTreeMap<String, String> = edges
        .iter()
        .filter(|e| e.edge_type == "attachment")
        .map(|e| (e.from.clone(), e.to.clone()))
        .collect();
    let leaf_ids: BTreeSet<&String> = attach_target.keys().collect();
    let anchor_ids: Vec<String> = nodes
        .iter()
        .map(|n| &n.id)
        .filter(|id| !leaf_ids.contains(id))
        .cloned()
        .collect();

    let mut adjacency: BTreeMap<String, BTreeSet<String>> =
        anchor_ids.iter().map(|a| (a.clone(), BTreeSet::new())).collect();
    for e in edges {
        if e.edge_type == "branch" && adjacency.contains_key(&e.from) && adjacency.contains_key(&e.to) {
            adjacency.get_mut(&e.from).unwrap().insert(e.to.clone());
            adjacency.get_mut(&e.to).unwrap().insert(e.from.clone());
        }
    }

    let (depth, parent, roots) = anchor_forest(&anchor_ids, &adjacency);
    let x_by_anchor = level_x_positions(&anchor_ids, &depth, &parent, &roots);

    let leaf_order: Vec<String> = nodes
        .iter()
        .map(|n| &n.id)
        .filter(|id| leaf_ids.contains(id))
        .cloned()
        .collect();
    let mut groups: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let mut unattached: Vec<String> = Vec::new();
    for leaf in &leaf_order {
        match attach_target.get(leaf) {
            Some(target) if x_by_anchor.contains_key(target) => {
                groups.entry(target.clone()).or_default().push(leaf.clone());
            }
            _ => unattached.push(leaf.clone()),
        }
    }

    let mut solver = Solver::new();
    let mut leaf_x_vars: BTreeMap<String, Variable> = BTreeMap::new();
    for (target, siblings) in &groups {
        for leaf in siblings {
            leaf_x_vars.insert(leaf.clone(), Variable::new());
        }
        for pair in siblings.windows(2) {
            let (left, right) = (&pair[0], &pair[1]);
            solver
                .add_constraints([(leaf_x_vars[left] + BUS_GAP) | LE(Strength::REQUIRED) | leaf_x_vars[right]])
                .unwrap();
        }
        let mut total = kasuari::Expression::from_variable(leaf_x_vars[&siblings[0]]);
        for leaf in &siblings[1..] {
            total = total + leaf_x_vars[leaf];
        }
        let centroid = siblings.len() as f64 * x_by_anchor[target];
        solver.add_constraints([total | EQ(Strength::REQUIRED) | centroid]).unwrap();
    }
    for leaf in &unattached {
        let v = Variable::new();
        leaf_x_vars.insert(leaf.clone(), v);
        solver.add_constraints([v | EQ(Strength::WEAK) | 0.0]).unwrap();
    }

    let mut positions: BTreeMap<String, (f64, f64)> = BTreeMap::new();
    for a in &anchor_ids {
        positions.insert(a.clone(), (x_by_anchor[a], depth[a] as f64 * ROW_SPACING));
    }
    for id in &leaf_order {
        let target = attach_target.get(id);
        let row = match target.and_then(|t| depth.get(t)) {
            Some(d) => (*d as f64 + 1.0) * ROW_SPACING,
            None => ROW_SPACING,
        };
        let x = round6(solver.get_value(leaf_x_vars[id]));
        positions.insert(id.clone(), (x, row));
    }

    nodes.iter().map(|n| positions[&n.id]).collect()
}
```

Note: `GE` is imported but unused by this specific port (Python's `_cassowary_positions`/`_level_x_positions` only ever use `<=` and `==`, never `>=`) — remove the unused `GE` import if `cargo build` warns, or leave it if Task 7 needs it (it doesn't either; both layout functions only use `LE`/`EQ`). Import only `{EQ, LE}`.

Modify `rust/systhread-core/src/lib.rs` to add:

```rust
pub mod layout;
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml layout_cassowary_test`
Expected: PASS. If a position is off by a small floating-point epsilon rather than matching Cassowary's exact rational-arithmetic result, check whether `kasuari`'s simplex implementation and `kiwisolver`'s produce identical results for this constraint shape — both implement the same published Cassowary algorithm (Badros et al. 2001) so they should, but if a test shows a genuine (not rounding-only) divergence, treat it as a real finding to investigate, not something to loosen the assertion around (per this plan's Global Constraints: byte/value-identical is a hard gate).

- [ ] **Step 5: Commit**

```bash
git add rust/systhread-core/src/layout.rs rust/systhread-core/src/lib.rs rust/systhread-core/tests/layout_cassowary_test.rs
git commit -m "systhread-core: Cassowary anchor/leaf layout via kasuari, matching Lab 6's kiwisolver positions"
```

---

## Task 7: Sequence (ordered-chain) layout via `kasuari`

**Files:**
- Modify: `rust/systhread-core/src/layout.rs`
- Test: `rust/systhread-core/tests/layout_sequence_test.rs`

**Interfaces:**
- Consumes: `iso_ir::{Node, Edge}` (Task 4), the same `kasuari` primitives as Task 6.
- Produces: `layout::sequence_positions(nodes: &[Node], edges: &[Edge]) -> Vec<(f64, f64)>` — consumed by Task 8.

- [ ] **Step 1: Write the failing test**

`rust/systhread-core/tests/layout_sequence_test.rs`:

```rust
mod common;
use common::fixture_path;
use systhread_core::instances::load_pipeline;
use systhread_core::iso_ir::extract_pipeline;
use systhread_core::layout::sequence_positions;

#[test]
fn pipeline_positions_match_fixture() {
    let inst = load_pipeline(&fixture_path("schema/pipeline_phases_instances.yaml"));
    let (nodes, edges) = extract_pipeline(&inst);
    let got = sequence_positions(&nodes, &edges);

    let text = std::fs::read_to_string(fixture_path("expected/expected_pipeline_phases_iso_ir.json")).unwrap();
    let json: serde_json::Value = serde_json::from_str(&text).unwrap();
    let expected: Vec<(f64, f64)> = json["nodes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|n| (n["position"]["x"].as_f64().unwrap(), n["position"]["y"].as_f64().unwrap()))
        .collect();

    assert_eq!(got, expected);
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml layout_sequence_test`
Expected: FAIL to compile — `sequence_positions` does not exist yet.

- [ ] **Step 3: Write the implementation**

Add to `rust/systhread-core/src/layout.rs`:

```rust
/// Ports translate_iso_ir.py's `_sequence_positions` exactly: walks the real declared `next`
/// order (starting from nodes with no incoming `sequence` edge, sorted for determinism), lays
/// the resulting chain out left-to-right with REQUIRED consecutive gaps and a WEAK pin on the
/// first element -- a real ordered relationship, not an undirected hub/star.
pub fn sequence_positions(nodes: &[Node], edges: &[Edge]) -> Vec<(f64, f64)> {
    let next_of: BTreeMap<String, String> = edges
        .iter()
        .filter(|e| e.edge_type == "sequence")
        .map(|e| (e.from.clone(), e.to.clone()))
        .collect();
    let has_incoming: BTreeSet<&String> = next_of.values().collect();

    let mut starts: Vec<String> = nodes
        .iter()
        .map(|n| &n.id)
        .filter(|id| !has_incoming.contains(id))
        .cloned()
        .collect();
    starts.sort();

    let mut order: Vec<String> = Vec::new();
    let mut seen: BTreeSet<String> = BTreeSet::new();
    for start in &starts {
        let mut current = Some(start.clone());
        while let Some(c) = current {
            if seen.contains(&c) {
                break;
            }
            order.push(c.clone());
            seen.insert(c.clone());
            current = next_of.get(&c).cloned();
        }
    }
    let mut rest: Vec<String> = nodes
        .iter()
        .map(|n| &n.id)
        .filter(|id| !seen.contains(id))
        .cloned()
        .collect();
    rest.sort();
    order.extend(rest);

    let mut solver = Solver::new();
    let x_vars: BTreeMap<String, Variable> = order.iter().map(|id| (id.clone(), Variable::new())).collect();
    for pair in order.windows(2) {
        let (left, right) = (&pair[0], &pair[1]);
        solver
            .add_constraints([(x_vars[left] + BUS_GAP) | LE(Strength::REQUIRED) | x_vars[right]])
            .unwrap();
    }
    if let Some(first) = order.first() {
        solver
            .add_constraints([x_vars[first] | EQ(Strength::WEAK) | 0.0])
            .unwrap();
    }

    let positions: BTreeMap<String, (f64, f64)> = order
        .iter()
        .map(|id| (id.clone(), (round6(solver.get_value(x_vars[id])), 0.0)))
        .collect();

    nodes.iter().map(|n| positions[&n.id]).collect()
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml layout_sequence_test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rust/systhread-core/src/layout.rs rust/systhread-core/tests/layout_sequence_test.rs
git commit -m "systhread-core: sequence layout for Track C's ordered Phase.next chain"
```

---

## Task 8: iso-IR JSON assembly (the real `MATCH` gate)

**Files:**
- Modify: `rust/systhread-core/src/iso_ir.rs`
- Modify: `rust/systhread-core/src/lib.rs`
- Test: `rust/systhread-core/tests/iso_ir_full_test.rs`

**Interfaces:**
- Consumes: `iso_ir::{extract_digital_thread, extract_grid, extract_pipeline}` (Task 4), `iso_ir::grid_positions` (Task 5), `layout::{cassowary_positions, sequence_positions}` (Tasks 6–7).
- Produces: `iso_ir::{build_digital_thread_iso_ir, build_grid_iso_ir, build_pipeline_iso_ir}(inst: &...) -> serde_json::Value` — the byte-identical JSON artifact.

**Design note — why `serde_json::Value` and not a typed `#[derive(Serialize)]` struct:** Python's `json.dumps(spec, indent=2, sort_keys=True)` emits every object's keys in **alphabetical order**, not field-declaration order. A typed Rust struct serializes fields in declaration order regardless of name — matching that would mean hand-ordering every struct's fields alphabetically and re-checking it on every future field addition, a fragile approach. `serde_json::Map` is a `BTreeMap` under the hood *unless* the crate's `preserve_order` feature is enabled (it is not, per Task 0's `Cargo.toml` — do not add that feature), so building the output as `serde_json::Value::Object` via the `json!()` macro gets alphabetical key ordering for free, structurally guaranteed rather than manually maintained.

- [ ] **Step 1: Write the failing test**

`rust/systhread-core/tests/iso_ir_full_test.rs`:

```rust
mod common;
use common::fixture_path;
use systhread_core::instances::{load_digital_thread, load_grid, load_pipeline};
use systhread_core::iso_ir::{build_digital_thread_iso_ir, build_grid_iso_ir, build_pipeline_iso_ir};

fn expected(fixture_rel: &str) -> String {
    std::fs::read_to_string(fixture_path(fixture_rel)).unwrap()
}

#[test]
fn digital_thread_iso_ir_matches_fixture_byte_identical() {
    let inst = load_digital_thread(&fixture_path("schema/digital_thread_instances.yaml"));
    let got = serde_json::to_string_pretty(&build_digital_thread_iso_ir(&inst)).unwrap() + "\n";
    assert_eq!(got, expected("expected/expected_digital_thread_iso_ir.json"));
}

#[test]
fn grid_iso_ir_matches_fixture_byte_identical() {
    let inst = load_grid(&fixture_path("schema/grid_instances.yaml"));
    let got = serde_json::to_string_pretty(&build_grid_iso_ir(&inst)).unwrap() + "\n";
    assert_eq!(got, expected("expected/expected_grid_topology_iso_ir.json"));
}

#[test]
fn pipeline_iso_ir_matches_fixture_byte_identical() {
    let inst = load_pipeline(&fixture_path("schema/pipeline_phases_instances.yaml"));
    let got = serde_json::to_string_pretty(&build_pipeline_iso_ir(&inst)).unwrap() + "\n";
    assert_eq!(got, expected("expected/expected_pipeline_phases_iso_ir.json"));
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml iso_ir_full_test`
Expected: FAIL to compile — the three `build_*_iso_ir` functions don't exist yet.

- [ ] **Step 3: Write the implementation**

Add to `rust/systhread-core/src/iso_ir.rs`:

```rust
use crate::layout::{cassowary_positions, sequence_positions};
use serde_json::{json, Value};

fn type_by_part_type(part_type: &str) -> &'static str {
    match part_type {
        "Agent" => "generic",
        "MCPServer" => "server",
        "DataSource" => "database",
        "Bus" => "router",
        "Generator" => "warehouse",
        "Phase" => "generic",
        _ => "generic",
    }
}

fn shape_by_type(node_type: &str) -> &'static str {
    match node_type {
        "router" => "bar",
        "warehouse" => "circle",
        _ => "box",
    }
}

/// Dispatches by real edge shape, exactly like translate_iso_ir.py's `_iso_positions`: a
/// `sequence` edge means a real declared order; any other edges mean an undirected hub/star
/// graph; no edges at all keeps the plain row-major grid.
fn positions_for(nodes: &[Node], edges: &[Edge]) -> Vec<(f64, f64)> {
    if edges.iter().any(|e| e.edge_type == "sequence") {
        sequence_positions(nodes, edges)
    } else if !edges.is_empty() {
        cassowary_positions(nodes, edges)
    } else {
        grid_positions(nodes.len())
    }
}

fn assemble(title: &str, nodes: &[Node], edges: &[Edge]) -> Value {
    let positions = positions_for(nodes, edges);
    let node_values: Vec<Value> = nodes
        .iter()
        .zip(positions.iter())
        .map(|(n, (x, y))| {
            let node_type = type_by_part_type(n.part_type);
            json!({
                "id": n.id,
                "label": n.label,
                "type": node_type,
                "shape": shape_by_type(node_type),
                "position": { "x": x, "y": y },
            })
        })
        .collect();

    let mut spec = json!({
        "title": title,
        "type": "generic",
        "nodes": node_values,
    });

    if !edges.is_empty() {
        let edge_values: Vec<Value> = edges
            .iter()
            .map(|e| {
                let mut v = json!({
                    "id": e.id,
                    "from": e.from,
                    "to": e.to,
                    "type": e.edge_type,
                });
                if let Some(kind) = &e.kind {
                    v["kind"] = json!(kind);
                }
                v
            })
            .collect();
        spec["edges"] = json!(edge_values);
    }

    spec
}

pub fn build_digital_thread_iso_ir(inst: &DigitalThreadInstances) -> Value {
    let (nodes, edges) = extract_digital_thread(inst);
    assemble("Lab 6 Track A -- Digital Thread", &nodes, &edges)
}

pub fn build_grid_iso_ir(inst: &GridInstances) -> Value {
    let (nodes, edges) = extract_grid(inst);
    assemble("Lab 6 Track B -- Grid Topology", &nodes, &edges)
}

pub fn build_pipeline_iso_ir(inst: &PipelinePhasesInstances) -> Value {
    let (nodes, edges) = extract_pipeline(inst);
    assemble("Lab 6 Track C -- Pipeline Phases", &nodes, &edges)
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml iso_ir_full_test`
Expected: PASS. If `serde_json::to_string_pretty`'s indentation width or separator spacing doesn't match Python's `json.dumps(..., indent=2)` exactly, diff the actual vs. expected bytes directly (write both to files, `diff -u`) rather than guessing at the mismatch — the two formatters are both "standard 2-space pretty JSON" but have not been verified byte-for-byte against each other before this task runs for real.

- [ ] **Step 5: Commit**

```bash
git add rust/systhread-core/src/iso_ir.rs rust/systhread-core/tests/iso_ir_full_test.rs
git commit -m "systhread-core: iso-IR JSON assembly, byte-identical against all three Lab 6 fixtures"
```

**Milestone C complete.** PR boundary: full iso-IR pipeline (structure + both layouts + assembly), green.

---

## Task 9: Isometric SVG renderer

**Files:**
- Create: `rust/systhread-core/src/render.rs`
- Modify: `rust/systhread-core/src/lib.rs`
- Test: `rust/systhread-core/tests/render_test.rs`

**Interfaces:**
- Consumes: `serde_json::Value` iso-IR specs from `iso_ir::{build_digital_thread_iso_ir, build_grid_iso_ir, build_pipeline_iso_ir}` (Task 8).
- Produces: `render::render_svg(spec: &serde_json::Value) -> String` — the final Phase 0 artifact type.

**Design note:** this is a direct, mechanical port of `render_diagram.py`'s `render_svg` — pure arithmetic on the iso-IR spec's own node positions, no font-shaping/DOM/browser involved (same "no source of variance" property Lab 6's own docstring names as what makes it trivially re-run-deterministic). Every constant (`TILE_W`, `BOX_HEIGHT`, colors, etc.) and every formatting call (`{:.1}` matching Python's `:.1f`) is copied verbatim from the Python source.

- [ ] **Step 1: Write the failing test**

`rust/systhread-core/tests/render_test.rs`:

```rust
mod common;
use common::fixture_path;
use systhread_core::instances::{load_digital_thread, load_grid, load_pipeline};
use systhread_core::iso_ir::{build_digital_thread_iso_ir, build_grid_iso_ir, build_pipeline_iso_ir};
use systhread_core::render::render_svg;

#[test]
fn digital_thread_svg_matches_fixture_byte_identical() {
    let inst = load_digital_thread(&fixture_path("schema/digital_thread_instances.yaml"));
    let got = render_svg(&build_digital_thread_iso_ir(&inst));
    let expected = std::fs::read_to_string(fixture_path("expected/expected_digital_thread.svg")).unwrap();
    assert_eq!(got, expected);
}

#[test]
fn grid_svg_matches_fixture_byte_identical() {
    let inst = load_grid(&fixture_path("schema/grid_instances.yaml"));
    let got = render_svg(&build_grid_iso_ir(&inst));
    let expected = std::fs::read_to_string(fixture_path("expected/expected_grid_topology.svg")).unwrap();
    assert_eq!(got, expected);
}

#[test]
fn pipeline_svg_matches_fixture_byte_identical() {
    let inst = load_pipeline(&fixture_path("schema/pipeline_phases_instances.yaml"));
    let got = render_svg(&build_pipeline_iso_ir(&inst));
    let expected = std::fs::read_to_string(fixture_path("expected/expected_pipeline_phases.svg")).unwrap();
    assert_eq!(got, expected);
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml render_test`
Expected: FAIL to compile — `systhread_core::render` does not exist yet.

- [ ] **Step 3: Write the implementation**

`rust/systhread-core/src/render.rs`:

```rust
use serde_json::Value;

const TILE_W: f64 = 120.0;
const TILE_H: f64 = 60.0;
const BOX_HEIGHT: f64 = 40.0;
const PADDING: f64 = 60.0;
const FONT_SIZE: f64 = 13.0;
const CHAR_WIDTH: f64 = FONT_SIZE * 0.6;
const GEN_RX: f64 = TILE_W * 0.28;
const GEN_RY: f64 = TILE_H * 0.28;
const XFMR_GLYPH_R: f64 = 4.0;
const BOW_HEIGHT: f64 = TILE_H;

const BACKGROUND: &str = "#0f172a";
const LABEL_FILL: &str = "#e2e8f0";
const TRANSMISSION_STROKE: &str = "#38bdf8";
const TRANSFORMER_STROKE: &str = "#f59e0b";
const ATTACHMENT_STROKE: &str = "#a78bfa";
const SEQUENCE_STROKE: &str = "#34d399";
const SEQUENCE_ARROW_LEN: f64 = 10.0;
const SEQUENCE_ARROW_WIDTH: f64 = 6.0;

#[derive(Clone, Copy)]
struct Point {
    x: f64,
    y: f64,
}

fn fill_by_type(node_type: &str) -> &'static str {
    match node_type {
        "generic" => "#6b7280",
        "server" => "#2563eb",
        "database" => "#059669",
        "router" => "#d97706",
        "warehouse" => "#7c3aed",
        _ => "#6b7280",
    }
}

fn tile_center(col: f64, row: f64) -> Point {
    Point {
        x: (col - row) * TILE_W / 2.0,
        y: (col + row) * TILE_H / 2.0,
    }
}

fn box_faces(center: Point) -> (Vec<Point>, Vec<Point>, Vec<Point>) {
    let top_apex = Point { x: center.x, y: center.y - TILE_H / 2.0 };
    let right_apex = Point { x: center.x + TILE_W / 2.0, y: center.y };
    let bottom_apex = Point { x: center.x, y: center.y + TILE_H / 2.0 };
    let left_apex = Point { x: center.x - TILE_W / 2.0, y: center.y };
    let down = |p: Point| Point { x: p.x, y: p.y + BOX_HEIGHT };

    let top_face = vec![top_apex, right_apex, bottom_apex, left_apex];
    let left_face = vec![left_apex, bottom_apex, down(bottom_apex), down(left_apex)];
    let right_face = vec![right_apex, bottom_apex, down(bottom_apex), down(right_apex)];
    (top_face, left_face, right_face)
}

fn bar_face(center: Point) -> Vec<Point> {
    vec![
        Point { x: center.x, y: center.y - TILE_H / 2.0 },
        Point { x: center.x + TILE_W / 2.0, y: center.y },
        Point { x: center.x, y: center.y + TILE_H / 2.0 },
        Point { x: center.x - TILE_W / 2.0, y: center.y },
    ]
}

fn poly(points: &[Point], fill: &str, opacity: f64, stroke: &str, stroke_width: f64) -> String {
    let pts: Vec<String> = points.iter().map(|p| format!("{:.1},{:.1}", p.x, p.y)).collect();
    format!(
        "<polygon points=\"{}\" fill=\"{}\" fill-opacity=\"{}\" stroke=\"{}\" stroke-width=\"{}\"/>",
        pts.join(" "),
        fill,
        opacity,
        stroke,
        fmt_g(stroke_width)
    )
}

/// Python's `{:g}` format -- shortest representation, no trailing zeros. Only used for
/// stroke-width in `poly` (matching render_diagram.py's `{stroke_width:g}`).
fn fmt_g(v: f64) -> String {
    let s = format!("{v}");
    s
}

fn edge_skips_node(from: &str, to: &str, positions_by_id: &std::collections::BTreeMap<String, (f64, f64)>) -> bool {
    let (Some(&a), Some(&b)) = (positions_by_id.get(from), positions_by_id.get(to)) else {
        return false;
    };
    if a.1 != b.1 {
        return false;
    }
    let (lo, hi) = if a.0 <= b.0 { (a.0, b.0) } else { (b.0, a.0) };
    positions_by_id.iter().any(|(nid, pos)| {
        nid != from && nid != to && pos.1 == a.1 && lo < pos.0 && pos.0 < hi
    })
}

fn quad_point(p0: Point, ctrl: Point, p1: Point, t: f64) -> Point {
    Point {
        x: (1.0 - t).powi(2) * p0.x + 2.0 * (1.0 - t) * t * ctrl.x + t.powi(2) * p1.x,
        y: (1.0 - t).powi(2) * p0.y + 2.0 * (1.0 - t) * t * ctrl.y + t.powi(2) * p1.y,
    }
}

fn edge_style(edge_type: &str, kind: Option<&str>) -> (&'static str, &'static str) {
    if edge_type == "attachment" {
        return (ATTACHMENT_STROKE, "stroke-width=\"1.5\" stroke-dasharray=\"1,3\" stroke-linecap=\"round\"");
    }
    if edge_type == "sequence" {
        return (SEQUENCE_STROKE, "stroke-width=\"3\" stroke-linecap=\"round\"");
    }
    if kind == Some("transformer") {
        return (TRANSFORMER_STROKE, "stroke-width=\"3\"");
    }
    (TRANSMISSION_STROKE, "stroke-width=\"3\"")
}

fn arrowhead(tip: Point, tail_direction: Point, fill: &str) -> String {
    let dx = tip.x - tail_direction.x;
    let dy = tip.y - tail_direction.y;
    let length = (dx * dx + dy * dy).sqrt();
    if length == 0.0 {
        return String::new();
    }
    let (ux, uy) = (dx / length, dy / length);
    let (px, py) = (-uy, ux);
    let base = Point { x: tip.x - ux * SEQUENCE_ARROW_LEN, y: tip.y - uy * SEQUENCE_ARROW_LEN };
    let left = Point { x: base.x + px * SEQUENCE_ARROW_WIDTH / 2.0, y: base.y + py * SEQUENCE_ARROW_WIDTH / 2.0 };
    let right = Point { x: base.x - px * SEQUENCE_ARROW_WIDTH / 2.0, y: base.y - py * SEQUENCE_ARROW_WIDTH / 2.0 };
    format!(
        "<polygon points=\"{:.1},{:.1} {:.1},{:.1} {:.1},{:.1}\" fill=\"{}\"/>",
        tip.x, tip.y, left.x, left.y, right.x, right.y, fill
    )
}

pub fn render_svg(spec: &Value) -> String {
    let nodes = spec["nodes"].as_array().cloned().unwrap_or_default();
    let edges = spec.get("edges").and_then(|e| e.as_array()).cloned().unwrap_or_default();

    let mut centers: std::collections::BTreeMap<String, Point> = std::collections::BTreeMap::new();
    let mut positions_by_id: std::collections::BTreeMap<String, (f64, f64)> = std::collections::BTreeMap::new();
    for n in &nodes {
        let id = n["id"].as_str().unwrap().to_string();
        let x = n["position"]["x"].as_f64().unwrap();
        let y = n["position"]["y"].as_f64().unwrap();
        centers.insert(id.clone(), tile_center(x, y));
        positions_by_id.insert(id, (x, y));
    }

    let mut node_body: Vec<String> = Vec::new();
    let mut all_points: Vec<Point> = Vec::new();

    for node in &nodes {
        let id = node["id"].as_str().unwrap();
        let x = node["position"]["x"].as_f64().unwrap();
        let y = node["position"]["y"].as_f64().unwrap();
        let center = tile_center(x, y);
        let node_type = node["type"].as_str().unwrap_or("generic");
        let fill = fill_by_type(node_type);
        let shape = node["shape"].as_str().unwrap_or("box");
        let label = node["label"].as_str().unwrap();

        node_body.push(format!("<g data-node-id=\"{id}\">"));
        let label_y: f64;
        match shape {
            "bar" => {
                let bar = bar_face(center);
                all_points.extend(&bar);
                node_body.push(poly(&bar, fill, 1.0, LABEL_FILL, 1.5));
                label_y = center.y + TILE_H / 2.0 + FONT_SIZE;
            }
            "circle" => {
                node_body.push(format!(
                    "<ellipse cx=\"{:.1}\" cy=\"{:.1}\" rx=\"{:.1}\" ry=\"{:.1}\" fill=\"{}\" stroke=\"{}\" stroke-width=\"1.5\"/>",
                    center.x, center.y, GEN_RX, GEN_RY, fill, LABEL_FILL
                ));
                node_body.push(format!(
                    "<text x=\"{:.1}\" y=\"{:.1}\" font-family=\"monospace\" font-weight=\"bold\" font-size=\"{:.0}\" fill=\"{}\" text-anchor=\"middle\">G</text>",
                    center.x, center.y + FONT_SIZE * 0.35, FONT_SIZE, LABEL_FILL
                ));
                all_points.push(Point { x: center.x - GEN_RX, y: center.y - GEN_RY });
                all_points.push(Point { x: center.x + GEN_RX, y: center.y + GEN_RY });
                label_y = center.y + GEN_RY + FONT_SIZE;
            }
            _ => {
                let (top_face, left_face, right_face) = box_faces(center);
                all_points.extend(&top_face);
                all_points.extend(&left_face);
                all_points.extend(&right_face);
                node_body.push(poly(&left_face, fill, 0.7, "#0f172a", 1.0));
                node_body.push(poly(&right_face, fill, 0.55, "#0f172a", 1.0));
                node_body.push(poly(&top_face, fill, 1.0, "#0f172a", 1.0));
                label_y = center.y + BOX_HEIGHT + TILE_H / 2.0 + FONT_SIZE;
            }
        }

        node_body.push(format!(
            "<text x=\"{:.1}\" y=\"{:.1}\" font-family=\"monospace\" font-size=\"{:.0}\" fill=\"{}\" text-anchor=\"middle\">{}</text>",
            center.x, label_y, FONT_SIZE, LABEL_FILL, label
        ));
        node_body.push("</g>".to_string());
        all_points.push(Point { x: center.x - label.chars().count() as f64 * CHAR_WIDTH / 2.0, y: label_y });
        all_points.push(Point { x: center.x + label.chars().count() as f64 * CHAR_WIDTH / 2.0, y: label_y });
    }

    let mut edge_body: Vec<String> = Vec::new();
    for edge in &edges {
        let from = edge["from"].as_str().unwrap();
        let to = edge["to"].as_str().unwrap();
        let edge_type = edge["type"].as_str().unwrap_or("");
        let kind = edge.get("kind").and_then(|k| k.as_str());
        let a = centers[from];
        let b = centers[to];
        let (stroke, extra_attrs) = edge_style(edge_type, kind);

        let glyph_points: Vec<Point>;
        if edge_skips_node(from, to, &positions_by_id) {
            let ctrl = Point { x: (a.x + b.x) / 2.0, y: (a.y + b.y) / 2.0 - BOW_HEIGHT };
            all_points.push(ctrl);
            edge_body.push(format!(
                "<path d=\"M {:.1} {:.1} Q {:.1} {:.1} {:.1} {:.1}\" fill=\"none\" stroke=\"{}\" {}/>",
                a.x, a.y, ctrl.x, ctrl.y, b.x, b.y, stroke, extra_attrs
            ));
            glyph_points = [1.0 / 3.0, 2.0 / 3.0].iter().map(|&t| quad_point(a, ctrl, b, t)).collect();
        } else {
            edge_body.push(format!(
                "<line x1=\"{:.1}\" y1=\"{:.1}\" x2=\"{:.1}\" y2=\"{:.1}\" stroke=\"{}\" {}/>",
                a.x, a.y, b.x, b.y, stroke, extra_attrs
            ));
            glyph_points = [1.0 / 3.0, 2.0 / 3.0]
                .iter()
                .map(|&frac| Point { x: a.x + (b.x - a.x) * frac, y: a.y + (b.y - a.y) * frac })
                .collect();
        }
        if kind == Some("transformer") {
            for gp in &glyph_points {
                edge_body.push(format!(
                    "<circle cx=\"{:.1}\" cy=\"{:.1}\" r=\"{:.1}\" fill=\"{}\" stroke=\"{}\" stroke-width=\"2\"/>",
                    gp.x, gp.y, XFMR_GLYPH_R, BACKGROUND, stroke
                ));
            }
        }
        if edge_type == "sequence" {
            edge_body.push(arrowhead(b, a, stroke));
        }
    }

    let min_x = all_points.iter().map(|p| p.x).fold(f64::INFINITY, f64::min) - PADDING;
    let max_x = all_points.iter().map(|p| p.x).fold(f64::NEG_INFINITY, f64::max) + PADDING;
    let min_y = all_points.iter().map(|p| p.y).fold(f64::INFINITY, f64::min) - PADDING;
    let max_y = all_points.iter().map(|p| p.y).fold(f64::NEG_INFINITY, f64::max) + PADDING;
    let width = max_x - min_x;
    let height = max_y - min_y;

    let title = spec["title"].as_str().unwrap_or("");

    let mut svg: Vec<String> = vec![
        format!(
            "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"{:.1} {:.1} {:.1} {:.1}\" width=\"{:.0}\" height=\"{:.0}\">",
            min_x, min_y, width, height, width, height
        ),
        format!(
            "<rect x=\"{:.1}\" y=\"{:.1}\" width=\"{:.1}\" height=\"{:.1}\" fill=\"{}\"/>",
            min_x, min_y, width, height, BACKGROUND
        ),
        format!("<title>{title}</title>"),
    ];
    svg.extend(node_body);
    svg.extend(edge_body);
    svg.push("</svg>".to_string());
    svg.join("\n") + "\n"
}
```

Modify `rust/systhread-core/src/lib.rs` to add:

```rust
pub mod render;
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml render_test`
Expected: PASS. The most likely mismatch sources, in order of likelihood: (a) `fmt_g`'s stroke-width formatting not matching Python's `{:g}` for a non-1.0/1.5/3.0 value (there are none in the current fixtures — all stroke widths are fixed literals — so this is low-risk but worth a direct diff if it fails), (b) iteration order of `positions_by_id` in `edge_skips_node`'s scan not mattering (it shouldn't — it's an `any()`/existence check, order-independent), (c) `BTreeMap` iteration order in `centers`/`positions_by_id` construction not mattering for the byte output (it shouldn't — both are only used for id-keyed lookup, never iterated positionally into the SVG). If a real diff appears, diff the two SVG strings directly (write to files, `diff -u`) to localize it to a specific element rather than re-reading the whole function.

- [ ] **Step 5: Commit**

```bash
git add rust/systhread-core/src/render.rs rust/systhread-core/src/lib.rs rust/systhread-core/tests/render_test.rs
git commit -m "systhread-core: isometric SVG renderer, byte-identical against all three Lab 6 fixtures"
```

**Milestone D complete.** PR boundary: the full four-stage pipeline (generate → validate → iso-IR → render) reproduces Lab 6's Python output byte-for-byte, for all three tracks.

---

## Task 10: Determinism test — repeated runs, all tracks, all artifact kinds

**Files:**
- Create: `rust/systhread-core/tests/determinism_test.rs`

**Interfaces:**
- Consumes: every public function from Tasks 1–9.

- [ ] **Step 1: Write the failing test**

`rust/systhread-core/tests/determinism_test.rs`:

```rust
mod common;
use common::fixture_path;
use systhread_core::instances::{load_digital_thread, load_grid, load_pipeline};
use systhread_core::iso_ir::{build_digital_thread_iso_ir, build_grid_iso_ir, build_pipeline_iso_ir};
use systhread_core::render::render_svg;
use systhread_core::sysml_gen::{render_digital_thread, render_grid_topology, render_pipeline_phases};

/// This is the spec's own hard gate (docs/superpowers/specs/2026-08-25-systhread-design.md §2,
/// "Deterministic, CI-diffable output"): every artifact MUST be byte-identical across repeated
/// runs on unchanged input. Each fixture-comparison test in Tasks 2/8/9 already proves the output
/// matches Lab 6's Python fixture once; this test proves systhread-core's own output doesn't drift
/// against *itself* across repeated in-process runs -- the actual re-run property the spec names,
/// not just a restatement of the fixture tests.
#[test]
fn all_three_tracks_all_three_artifact_kinds_are_stable_across_repeated_runs() {
    let dt = load_digital_thread(&fixture_path("schema/digital_thread_instances.yaml"));
    let grid = load_grid(&fixture_path("schema/grid_instances.yaml"));
    let pipeline = load_pipeline(&fixture_path("schema/pipeline_phases_instances.yaml"));

    for _ in 0..3 {
        assert_eq!(render_digital_thread(&dt), render_digital_thread(&dt));
        assert_eq!(render_grid_topology(&grid), render_grid_topology(&grid));
        assert_eq!(render_pipeline_phases(&pipeline), render_pipeline_phases(&pipeline));

        let dt_ir_a = build_digital_thread_iso_ir(&dt);
        let dt_ir_b = build_digital_thread_iso_ir(&dt);
        assert_eq!(dt_ir_a, dt_ir_b);
        let grid_ir_a = build_grid_iso_ir(&grid);
        let grid_ir_b = build_grid_iso_ir(&grid);
        assert_eq!(grid_ir_a, grid_ir_b);
        let pipeline_ir_a = build_pipeline_iso_ir(&pipeline);
        let pipeline_ir_b = build_pipeline_iso_ir(&pipeline);
        assert_eq!(pipeline_ir_a, pipeline_ir_b);

        assert_eq!(render_svg(&dt_ir_a), render_svg(&dt_ir_b));
        assert_eq!(render_svg(&grid_ir_a), render_svg(&grid_ir_b));
        assert_eq!(render_svg(&pipeline_ir_a), render_svg(&pipeline_ir_b));
    }
}
```

- [ ] **Step 2: Run the test to verify it fails or passes immediately**

Run: `cargo test -p systhread-core --manifest-path rust/Cargo.toml determinism_test`
Expected: this test should PASS immediately if Tasks 1–9 are correctly implemented (there's no new production code in this task — it's a property test over existing pure functions). If it fails, that's a real, serious finding: something in `kasuari`'s solver or this crate's own code has non-deterministic behavior (e.g. iterating a `HashMap` instead of a `BTreeMap` somewhere, or relying on `Variable::new()`'s global atomic counter in a way that makes output depend on call order across *different* specs built in the same process). Do not weaken this test to make it pass — find and fix the actual source of non-determinism, since this is the spec's own named hard requirement.

- [ ] **Step 3: (only if Step 2 failed) Fix the source of non-determinism, then re-run**

- [ ] **Step 4: Commit**

```bash
git add rust/systhread-core/tests/determinism_test.rs
git commit -m "systhread-core: determinism test — repeated in-process runs, all tracks, all artifact kinds"
```

---

## Task 11: Wire into the workspace `check` aggregate

**Files:**
- Modify: `Justfile`

**Interfaces:**
- None — this is CI/convenience wiring only, not a code change.

**Design note:** this repo's `Justfile` aggregates every lab's own check under one `check:` target (`check: check-lab1 check-lab2 ... check-lab9`). `systhread-core` isn't a "lab" and FR4's real justfile *module* is Phase 1 scope (out of bounds here) — but leaving a brand-new, tested Rust crate with zero `just check` coverage would silently regress this repo's own "everything runs via `just check`" invariant. Add exactly one line, no new recipe.

- [ ] **Step 1: Read the current `check:` target**

Run: `grep -n "^check:" /home/brianh/promptexecution/aemo/nem-poweragent-lab/Justfile`

- [ ] **Step 2: Add `systhread-core`'s test run to the aggregate**

Modify the `Justfile`'s `check:` line to also run `cargo test -p systhread-core --manifest-path rust/Cargo.toml`. The exact edit depends on the current line's shape (read in Step 1) — if `check:` is a dependency list of other recipes (`check: check-lab1 check-lab2 ...`), add a new one-line recipe:

```just
check-systhread-core:
    cargo test -p systhread-core --manifest-path rust/Cargo.toml

check: check-lab1 check-lab2 check-lab3 check-lab4 check-lab5 check-lab6 check-lab7 check-lab8 check-lab9 check-systhread-core
```

(Keep every existing `check-labN` dependency exactly as-is — only append `check-systhread-core`.)

- [ ] **Step 3: Run the full aggregate to confirm nothing else broke**

Run: `just check` (this will take a while — it runs every lab's own check too; if that's impractical in this environment, at minimum run `just check-systhread-core` directly and confirm it passes, and visually confirm the `Justfile` diff only appends, never removes, an existing dependency)

- [ ] **Step 4: Commit**

```bash
git add Justfile
git commit -m "systhread-core: wire cargo test into the workspace's just check aggregate"
```

**Milestone E complete.** Phase 0 acceptance criteria (spec §6): `systhread-core` reproduces Lab 6's `.sysml`/iso-IR JSON/SVG output byte-identical for all three tracks, is deterministic across repeated runs, and runs under this repo's normal `just check`.

---

## Plan Self-Review Notes (for the executing agent, not a task)

- **Spec coverage**: Tasks 0–9 cover Phase 0's stated scope (§6: "parse, validate, iso-IR translate, render... depending on ufo-types for stereotyping" — the `ufo-types` half is explicitly deferred, per Global Constraints, since Phase 0's generator emits fixed templates with no `ToSysml`/`UfoStereotype` declarations to make yet). Task 10 covers the determinism principle (§2). Task 11 covers CI integration without reaching into Phase 1's justfile-module scope.
- **What Phase 0 does NOT include, by design**: a CLI (`systhread check`/`render`/`explore`), an MCP transport, a `b00t stack` definition, the ledgrrr artifact-contract manifest, the explorer, drift tracking, or any `ufo-types`/`ToSysml` code. All of that is Phase 1+ in the spec and belongs in a separate plan.
- **Real risk flagged honestly, not hidden**: Task 6/7's `kasuari` port is the highest-risk task in this plan — it's translating a verified-working Python/`kiwisolver` algorithm to a different Rust crate's API, and while both implement the same published Cassowary algorithm, this plan has not actually run the Rust code end-to-end before handing it to execution. If Task 6 or 7's fixture test fails on a genuine numeric divergence (not a typo), that is real, load-bearing information for whoever executes this plan — investigate it, don't paper over it with a looser assertion.
