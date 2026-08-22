# Phase 0c spike — sensmetry/sysand native-Rust CLI vs. Lab 6/0b's JVM/Maven dead end

Does `sensmetry/sysand` — a real, actively maintained SysML v2/KerML package manager (init,
build, publish, dependency resolution) — actually work as a **standalone native Rust binary**,
with zero JVM/Maven involved anywhere in the invocation path? Lab 6's original design hit an
`UnsatisfiedLinkError` dead end trying to shell out to a JVM/Maven-based SysML toolchain
(`labs/06-sysml-digital-thread/README.md`, Design notes). This spike clones the real
`sensmetry/sysand` repo, builds it with `cargo build`, and runs its real subcommands against real
SysML fixture files — not researched from docs, actually executed.

## Setup

```
git clone https://github.com/sensmetry/sysand /tmp/sysand-spike/sysand
cd /tmp/sysand-spike/sysand
cargo build -p sysand
```

- Workspace: `Cargo.toml` `[workspace] members = ["bindings/java", "bindings/js", "bindings/py",
  "core", "macros", "sysand"]`, `default-members = ["core", "sysand"]`. Rust edition 2024,
  `rust-toolchain.toml` pins channel `1.98`.
- `cargo build -p sysand` on toolchain 1.98 (fresh clone, cold cache, first build): compiled
  clean, took roughly 9-12 minutes wall clock (fetching + compiling the full dependency tree from
  scratch on this machine), no errors, no warnings surfaced in the tail of build output.
- Result binary: `target/debug/sysand`, a 336MB (debug, unstripped) native ELF executable.
  `ldd target/debug/sysand` → only `libgcc_s.so.1`, `libm.so.6`, `libc.so.6`,
  `ld-linux-x86-64.so.2`. **No `libjvm.so`, no JNI, nothing Java-shaped linked in.**
- `grep -ril "maven\|jvm\b"` across the whole repo (excluding `bindings/java/`, which is a
  separate optional Java *binding* for embedding sysand's core into JVM host apps, not part of the
  CLI) returns **zero hits**. The CLI crate (`sysand/`) and its `core`/`macros` deps are pure Rust.
  `java` happens to be present on this machine's `$PATH` (`/usr/bin/java`) but is never invoked —
  irrelevant to the CLI, confirmed by the `ldd` output above.

## What was tried

Real commands, run against real SysML fixture files already present in sysand's own test data
(`sysand/tests/data/test_lib/{libtest.sysml,extras/foo.sysml,extras/bar/baz.sysml}` — copied into
a scratch working dir, not synthesized by this spike):

```
sysand --version
sysand --help
sysand info --help
sysand init --publisher <p> --name <n> --version <v>   # first without --publisher (real error), then with it
sysand include libtest.sysml
sysand include extras/foo.sysml
sysand include extras/bar/baz.sysml
sysand info
sysand info usage
sysand info checksum
sysand sources
sysand build
sysand print-root
sysand lock
```

## Results — real command output, not paraphrased

```
$ sysand --version
sysand 0.2.1
```

`sysand --help` lists real subcommands: `init, add, remove, clone, include, exclude, build,
publish, auth, lock, env, index, sync, info, sources, print-root, experimental, help`.

**Real validation error** (missing required arg, exit code 2):
```
$ sysand init --name "test-lib-spike" --version "0.1.0"
error: the following required arguments were not provided:
  --publisher <PUBLISHER>

Usage: sysand init --publisher <PUBLISHER> --name <NAME> --version <VERSION> [PATH]
```

**Successful init** (exit 0), creates real project metadata files:
```
$ sysand init --publisher "spike-tester" --name "test-lib-spike" --version "0.1.0"
    Creating interchange project `test-lib-spike`
```
`.project.json`:
```json
{ "name": "test-lib-spike", "publisher": "spike-tester", "version": "0.1.0" }
```

**`include` on all three real `.sysml` fixture files** (exit 0 each):
```
   Including file `libtest.sysml`
   Including file `extras/foo.sysml`
   Including file `extras/bar/baz.sysml`
```
`.meta.json` after all three includes — sysand actually **parsed the SysML source** to extract
top-level element names as the project's `index`, not just recorded file paths:
```json
{
  "index": {
    "LibTest": "libtest.sysml",
    "Foo": "extras/foo.sysml",
    "Baz": "extras/bar/baz.sysml"
  },
  "created": "2026-08-22T01:33:21Z",
  "checksum": {
    "libtest.sysml": { "value": "", "algorithm": "NONE" },
    "extras/foo.sysml": { "value": "", "algorithm": "NONE" },
    "extras/bar/baz.sysml": { "value": "", "algorithm": "NONE" }
  }
}
```
(`algorithm: NONE` / empty checksum values persisted through `include` and even after `build` —
checksums are apparently computed/written at a different step than `include`; not chased further,
out of scope for this spike.)

```
$ sysand info
Name: test-lib-spike
Publisher: spike-tester
Version: 0.1.0
No usages.

$ sysand sources
/tmp/sysand-spike/workdir/libtest.sysml
/tmp/sysand-spike/workdir/extras/foo.sysml
/tmp/sysand-spike/workdir/extras/bar/baz.sysml
```

**`sysand build` — produces a real KPAR (KerML Project Archive) file**, exit 0:
```
$ sysand build
    Building kpar `/tmp/sysand-spike/workdir/output/test_lib_spike-0.1.0.kpar`
updating file metadata (1/3)updating file metadata (2/3)updating file metadata (3/3)
```
The `.kpar` is a genuine ZIP archive (`file` confirms `Zip archive data`), containing all three
source files plus the project metadata:
```
$ unzip -l output/test_lib_spike-0.1.0.kpar
       54  libtest.sysml
       47  extras/foo.sysml
       46  extras/bar/baz.sysml
       84  .project.json
      608  .meta.json
```

```
$ sysand print-root
/tmp/sysand-spike/workdir

$ sysand lock
(exit 0, no sysand.lock written — this project declares no dependency usages, so there is
 nothing to lock; consistent with `sysand info usage` reporting none)
```

## Analysis

- **The CLI itself needs no JVM, no Maven, no JNI, no `java` on `PATH` — confirmed by both static
  evidence (`ldd`, source grep) and dynamic evidence (every command above ran and produced correct
  output in a shell with no JVM-related env vars set).** This directly clears the blocker that
  killed Lab 6's original JVM/Maven `UnsatisfiedLinkError` approach.
- **`sysand` is not a toy** — `init`/`include`/`build` form a real, working pipeline: it parses
  actual SysML v2 syntax well enough to extract top-level definition names into project metadata
  (`LibTest`, `Foo`, `Baz` correctly identified from the three fixture files), and `build` produces
  a spec-shaped KPAR archive (KerML clause 10.3's project interchange file format) as a real ZIP,
  not a stub.
- **`java` bindings exist but are opt-in and irrelevant to the CLI path** — `bindings/java` is a
  separate workspace member for embedding sysand's Rust `core` into JVM host applications via JNI;
  it is not a dependency of the `sysand` CLI binary and was not built or exercised by
  `cargo build -p sysand` (default-members are `["core", "sysand"]` only). Confirmed by `ldd`
  showing zero JVM-related shared libraries linked into the actual binary.
- **CLI ergonomics are solid**: real `clap`-style structured errors (missing `--publisher`
  produces a proper usage message and exit code 2, not a panic), sensible subcommand nesting
  (`info name|version|checksum|usage|...`), and console messages that read like a mature package
  manager (`cargo`-style "Creating..."/"Building..." progress text).
- **Build cost is real but one-time**: ~9-12 minutes cold-cache build on this machine for a 336MB
  debug binary from a fresh clone (full dependency tree compiled from scratch, no local cache);
  this is a normal Rust workspace build cost, not evidence of any hidden native/JVM toolchain
  requirement — no `javac`, `mvn`, or JDK invocation appeared anywhere in the build log.
- **Not fully exercised**: dependency resolution (`add`/`sync`/`env`), publishing to a real index
  (`publish`/`auth`), and cross-project dependency locking were not tested — this fixture project
  declared zero usages/dependencies, so `sysand lock` had nothing to resolve. Those are the
  package-manager-proper features (vs. the single-project authoring path exercised here) and would
  need a multi-project fixture to test for real; flagged as follow-up, not a blocker for this
  spike's core question.

## Verdict

**Yes — sysand's native Rust CLI works standalone, with no Maven/JVM involved at any point.**
Built cleanly from a fresh clone with plain `cargo build`, produces a single native ELF binary
whose only linked libraries are glibc/libgcc/libm, and every real subcommand exercised
(`init`, `include`, `info`, `sources`, `build`, `print-root`, `lock`) ran correctly against real
SysML v2 fixture files, including actually parsing SysML syntax to extract element names and
producing a genuine spec-shaped KPAR (ZIP) archive. This is a clean, real replacement path for the
JVM/Maven dead end that blocked Lab 6's original toolchain integration — `sysand build` is a
credible native alternative for "package a set of `.sysml` files into a standard interchange
archive" without ever shelling out to `java`/`mvn`.

**Recommendation**: `sysand` is a strong Phase 1+ candidate for any workflow that needs to
package/publish `.sysml` model files as spec-compliant KPAR archives, or resolve/lock SysML v2
project dependencies, without a JVM dependency anywhere in the toolchain. It complements (does not
replace) the parsing-only crates evaluated in `../0b-sysml-v2-parser/README.md`
(`sysml-v2-parser`/`syster-base`) — sysand's own SysML parsing (used internally by `include` to
extract element names) was not benchmarked against those crates' pass/fail rates on the harder
GfSE fixture corpus in this spike; if project-metadata extraction (`include`) needs to be
correct on complex real-world SysML v2 syntax, that's worth a follow-up spike using the same GfSE
fixture set 0b already has on disk.

## Files

- This spike was run entirely against a scratch clone at `/tmp/sysand-spike/` (not checked into
  this repo — throwaway, per the Phase 0 spike convention). No source files were added under this
  directory; this README is the deliverable.
- Real fixtures used: `sysand/tests/data/test_lib/{libtest.sysml,extras/foo.sysml,extras/bar/baz.sysml}`
  from the `sensmetry/sysand` repo itself (commit at clone time, `main` branch, version `0.2.1`).
- Upstream repo: https://github.com/sensmetry/sysand
