#!/usr/bin/env bash
# Phase 0c spike: does sensmetry/sysand's native Rust CLI work standalone,
# bypassing the JVM/Maven/JNI layer entirely?
#
# This script reproduces the exact commands run for this spike. It clones
# sysand to a scratch dir (NOT vendored into this repo), builds it natively
# with cargo, and exercises the CLI against a real .sysml file copied from
# this repo's own labs/06-sysml-digital-thread/output/.
#
# Run from anywhere; it only writes under /tmp.
set -euo pipefail

SCRATCH=/tmp/sysand-spike
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
LAB6_OUTPUT="$REPO_ROOT/labs/06-sysml-digital-thread/output"

rm -rf "$SCRATCH"
mkdir -p "$SCRATCH"

echo "== clone sensmetry/sysand (dual MIT/Apache-2.0) =="
git clone https://github.com/sensmetry/sysand "$SCRATCH/sysand"

echo "== native cargo build of the sysand CLI crate (no JVM/Maven involved) =="
cd "$SCRATCH/sysand"
cargo build -p sysand
BIN="$SCRATCH/sysand/target/debug/sysand"

echo "== version / help =="
"$BIN" --version
"$BIN" --help

echo "== init a real project =="
mkdir -p "$SCRATCH/test-project"
cd "$SCRATCH/test-project"
"$BIN" init --version 0.1.0 --publisher "nem-poweragent-lab" grid_topology

echo "== copy real Lab 6 .sysml output in as source =="
cp "$LAB6_OUTPUT/grid_topology.sysml" grid_topology/

echo "== include (extracts symbol index via sysand's own lightweight lexer) =="
cd grid_topology
"$BIN" include grid_topology.sysml
cat .meta.json

echo "== build a KPAR (KerML Project Archive == real ZIP) =="
"$BIN" build ./grid_topology.kpar
file grid_topology.kpar
unzip -l grid_topology.kpar

echo "== info on the built KPAR =="
"$BIN" info --path grid_topology.kpar

echo "== lock / env / sync / sources (dependency-management surface, no deps here) =="
"$BIN" lock
cat sysand-lock.toml
"$BIN" env
"$BIN" sync
"$BIN" sources

echo "== negative test: garbage .sysml is rejected by include's own lexer =="
echo 'not valid sysml at all garbage {{{' > garbage.sysml
"$BIN" include garbage.sysml || echo "(rejected as expected)"

echo "Spike complete."
