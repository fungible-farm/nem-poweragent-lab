#!/bin/sh
# One-command install for this repo, per docs/VISION.md section 10's spec.
#
# POSIX sh, checks-then-acts -- never silently reinstalls something already
# present (docs/DEFINITION_OF_DONE.md's "Install" section, bullet 2).
#
# Steps (numbered to match docs/VISION.md section 10 verbatim):
#   1. Check for uv; install via the official installer if absent.
#   2. Check for podman; print distro instructions and stop if absent (we do
#      not install a container runtime with root on the user's behalf).
#   3. Check for cargo/rustc, warn (non-fatal) if absent -- only fatal if
#      step 4's `uv sync` actually needs a source build of `powerio` and
#      fails without them; see the SANDBOX NOTE below.
#   4. `uv sync`.
#   5. scripts/fetch_csiro_nem_data.py (CSIRO case files) and
#      scripts/fetch_phi4_model.py (Phi-4-mini GGUF).
#   6. `podman kube play` both kube/llamacpp-phi-pod.yaml and
#      kube/powermcp-pandapower-pod.yaml.
#   7. scripts/install_smoke_test.py -- prints the final PASS/FAIL gate.
#
# SANDBOX NOTE (AGENTS.md "sandbox stand-ins must be named" rule): step 3 as
# literally specified in docs/VISION.md section 10 is "check for cargo/rustc
# only if powerio needs a source build on this platform; skip if a prebuilt
# wheel is available" -- that requires knowing in advance whether PyPI has a
# wheel for the current platform/Python ABI, which `uv sync` itself already
# resolves internally (it just picks a wheel if one matches, or falls back
# to building from an sdist if not). Duplicating that resolution logic here
# would either be wrong or a straight re-implementation of what `uv` already
# does correctly. This script instead: warns (non-fatal) if cargo/rustc are
# absent, then lets step 4's `uv sync` run; if `uv sync` fails and cargo/
# rustc were absent, it prints a specific "this was likely a missing source
# build toolchain" hint before exiting non-zero, rather than silently
# swallowing a confusing pip/maturin backtrace.
set -eu

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

log() { printf '[install.sh] %s\n' "$1"; }
fail() { printf '[install.sh] FAIL: %s\n' "$1" >&2; exit 1; }

START_TS=$(date +%s)

# --- Step 1: uv --------------------------------------------------------
if command -v uv >/dev/null 2>&1; then
    log "uv already present ($(uv --version)) -- skipping install"
else
    log "uv not found -- installing via the official installer"
    log "running: curl -LsSf https://astral.sh/uv/install.sh | sh"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    command -v uv >/dev/null 2>&1 || fail "uv installer ran but 'uv' is still not on PATH"
fi

# --- Step 2: podman ------------------------------------------------------
if command -v podman >/dev/null 2>&1; then
    log "podman already present ($(podman --version)) -- skipping"
else
    fail "podman is required and was not found. This script does not install a
container runtime with root on your behalf -- install it yourself first:
  Ubuntu/Debian:  sudo apt-get install -y podman
  Fedora/RHEL:    sudo dnf install -y podman
Then re-run ./install.sh."
fi

# --- Step 3: cargo/rustc (advisory only -- see SANDBOX NOTE above) -------
CARGO_PRESENT=1
if command -v cargo >/dev/null 2>&1 && command -v rustc >/dev/null 2>&1; then
    log "cargo/rustc already present ($(rustc --version)) -- skipping"
else
    CARGO_PRESENT=0
    log "cargo/rustc not found -- continuing; powerio only needs these if no"
    log "  prebuilt wheel matches this platform (uv sync will tell us)"
fi

# --- Step 4: uv sync -------------------------------------------------------
log "step 4/7: uv sync"
if ! uv sync; then
    if [ "$CARGO_PRESENT" -eq 0 ]; then
        fail "uv sync failed, and cargo/rustc were not present -- this is
likely powerio needing a source build with no prebuilt wheel for this
platform. Install a Rust toolchain (https://rustup.rs) and re-run
./install.sh."
    fi
    fail "uv sync failed -- see the output above."
fi

# --- Step 5: data + model fetch -------------------------------------------
log "step 5/7: fetching CSIRO case data"
uv run scripts/fetch_csiro_nem_data.py

log "step 5/7: fetching Phi-4-mini-instruct GGUF (~2.3GB, one-time)"
uv run scripts/fetch_phi4_model.py

# --- Step 6: bring up the two pods -----------------------------------------
log "step 6/7: podman kube play kube/llamacpp-phi-pod.yaml"
podman kube play kube/llamacpp-phi-pod.yaml --replace

log "step 6/7: podman kube play kube/powermcp-pandapower-pod.yaml"
podman kube play kube/powermcp-pandapower-pod.yaml --replace

# --- Step 7: smoke test -----------------------------------------------------
log "step 7/7: smoke test"
uv run scripts/install_smoke_test.py

END_TS=$(date +%s)
ELAPSED=$((END_TS - START_TS))
log "install completed in ${ELAPSED}s (excluding any one-time GGUF download"
log "  time already counted above -- see README.md for the stated baseline)"
