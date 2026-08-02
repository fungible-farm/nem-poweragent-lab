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
#   7. Install the display/demo tools mpv + chafa (apt) if absent -- the
#      "just watch/just peek" animation/static-chart viewers the demo
#      workflow uses (see the root Justfile's `watch`/`peek` recipes).
#   8. scripts/install_smoke_test.py -- prints the final PASS/FAIL gate.
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
log "step 4/8: uv sync"
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
log "step 5/8: fetching CSIRO case data"
uv run scripts/fetch_csiro_nem_data.py

log "step 5/8: fetching Phi-4-mini-instruct GGUF (~2.3GB, one-time)"
uv run scripts/fetch_phi4_model.py

# --- Step 6: bring up the two pods -----------------------------------------
log "step 6/8: podman kube play kube/llamacpp-phi-pod.yaml"
podman kube play kube/llamacpp-phi-pod.yaml --replace

log "step 6/8: podman kube play kube/powermcp-pandapower-pod.yaml"
podman kube play kube/powermcp-pandapower-pod.yaml --replace

# --- Step 7: display/demo tools (mpv, chafa) --------------------------------
# The demo workflow's viewers: `just watch <anim>` (mpv -- mp4 playback,
# windowed over X11/WSLg or --vo=tct in-terminal) and `just peek <chart>`
# (chafa -- true-color ANSI rendering of a committed PNG straight in the
# SSH terminal). Same checks-then-acts rule as the rest of this script:
# never silently reinstall something already present.
#
# BEST-EFFORT, not a gate: the physics labs run headless, so mpv/chafa are
# only needed by the demo/display workflow. The direct `sudo apt-get` below
# is the one invocation that works non-interactively on a box like fung1
# whose sudoers grants NOPASSWD for apt-get specifically; a *declarative*
# pyinfra deploy (scripts/deploy_demo_tools.py, idempotent and extensible)
# is the canonical way to maintain this host state, but pyinfra wraps its
# sudo'd commands in `sh`/`env` and would demand a password on that same
# box -- so the deploy is the `just deploy` path, not this bootstrap. If
# this step cannot install the tools (non-interactive + no NOPASSWD apt),
# it warns and continues rather than failing the physics install.
log "step 7/8: checking display/demo tools (mpv, chafa)"
DISPLAY_TOOLS_MISSING=0
for tool in mpv chafa; do
    if command -v "$tool" >/dev/null 2>&1; then
        log "  $tool already present ($(command -v "$tool")) -- skipping"
    else
        DISPLAY_TOOLS_MISSING=1
    fi
done
if [ "$DISPLAY_TOOLS_MISSING" -eq 1 ]; then
    if command -v apt-get >/dev/null 2>&1; then
        log "installing missing display tools via apt (may prompt for sudo)"
        if ! sudo apt-get install -y mpv chafa; then
            log "WARN: could not install mpv/chafa non-interactively (sudo likely"
            log "  needs a password here). The labs do not need these -- the demo"
            log "  display workflow does. Install them later with:"
            log "    just deploy    # pyinfra, declarative, prompts for sudo once"
        fi
    else
        log "WARN: no apt-get on this system -- cannot auto-install mpv/chafa."
        log "  Install them yourself (Fedora/RHEL: sudo dnf install -y mpv chafa),"
        log "  or run: just deploy"
    fi
    for tool in mpv chafa; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            log "  $tool still not on PATH after the attempt (see WARN above)"
        fi
    done
fi

# --- Step 8: smoke test ------------------------------------------------------
log "step 8/8: smoke test"
uv run scripts/install_smoke_test.py

END_TS=$(date +%s)
ELAPSED=$((END_TS - START_TS))
log "install completed in ${ELAPSED}s (excluding any one-time GGUF download"
log "  time already counted above -- see README.md for the stated baseline)"
