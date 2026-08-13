# Canonical command entry point for nem-poweragent-lab -- the repo's "just
# does this" truth (see AGENTS.md "Running the labs"). Recipes are the
# canonical example commands; anything non-trivial lives in a committed
# script (./install.sh, scripts/run_labs_1_3.sh, scripts/deploy_demo_tools.sh,
# scripts/peek_viz.sh, scripts/watch_viz.sh) that a recipe simply RUNS -- just
# is the index, not a re-implementation. `just --list` for everything.
#
# Written against the `b00t learn just` gospel: simple recipes stay one line,
# env vars are $VAR, just vars are {{var}}, complex logic goes in scripts.

set dotenv-load
set shell := ["bash", "-c"]

# --- aliases ---------------------------------------------------------------
alias s := sync
alias f := fetch
alias t := test
alias p := proof
alias d := deploy
alias r := render

# --- setup -----------------------------------------------------------------
# One-command install -- RUNS ./install.sh (the committed checks-then-acts
# script owns the logic; this recipe is just the canonical pointer).
install:
    ./install.sh

# Install pinned deps from pyproject.toml/uv.lock.
sync:
    uv sync

# Fetch + checksum-verify the CSIRO case data into data/ (idempotent).
fetch:
    uv run scripts/fetch_csiro_nem_data.py

# Declarative host-state deploy for the demo/display tools.
#
# Per-command authorization model (scoped sudoers, no password anywhere):
# the ONLY NOPASSWD root surface is the committed, reviewed
# scripts/deploy_demo_tools.sh (see scripts/sudoers.d/nem-poweragent-lab,
# installed by `just authorize`). `deploy` runs that script as root and, if
# the rule isn't installed yet, tells you exactly what to run instead of
# stopping dead -- the just workflow is never the blocker.
#
# Future-just note: this pattern is a candidate for an upstream `just`
# feature -- a recipe attribute like `[elevated]` that routes a recipe's
# commands through a configured elevation boundary (the authorized script
# here). Filed as an idea, not needed for today.
deploy args="":
    #!/usr/bin/env bash
    set -euo pipefail
    script="{{justfile_directory()}}/scripts/deploy_demo_tools.sh"
    if ! sudo -n "$script" {{args}}; then
        echo "deploy: not authorized to run the deploy script as root (yet)."
        echo "  One-time setup -- run:  just authorize"
        echo "  (installs scripts/sudoers.d/nem-poweragent-lab: NOPASSWD for"
        echo "   exactly $script and nothing else.)"
        exit 1
    fi

# One-time install of the scoped sudoers rule (prompts for your sudo password
# once). Fills the <REPO_USER>/<REPO_ROOT> placeholders from this checkout and
# validates the result with visudo. Re-run after moving the repo.
authorize:
    #!/usr/bin/env bash
    set -euo pipefail
    repo_root="{{justfile_directory()}}"
    tmp="/tmp/nem-poweragent-lab.sudoers.$$"
    sed -e "s|<REPO_USER>|$(id -un)|" -e "s|<REPO_ROOT>|${repo_root}|g" \
        "$repo_root/scripts/sudoers.d/nem-poweragent-lab" > "$tmp"
    sudo cp "$tmp" /etc/sudoers.d/nem-poweragent-lab
    sudo chmod 0440 /etc/sudoers.d/nem-poweragent-lab
    rm -f "$tmp"
    sudo visudo -c

# --- proof / test ----------------------------------------------------------
# The committed end-to-end proofs (the proof scripts are the proof, not a
# transcript -- AGENTS.md).
proof: proof-labs-1-3 proof-lab4

proof-labs-1-3:
    ./scripts/run_labs_1_3.sh

proof-lab4:
    ./scripts/run_lab4.sh

# pytest across every lab.
test:
    uv run python -m pytest labs/ -q

# --- per-lab self-check gates ----------------------------------------------
check: check-lab1 check-lab2 check-lab3 check-lab4 check-lab5

check-lab1:
    uv run labs/01-simple-loadflow-fit/run.py --step check

check-lab2:
    uv run labs/02-medium-interconnection-screening/workflow.py --step check

check-lab3:
    uv run labs/03-advanced-provider-bakeoff/orchestrator.py --step check

check-lab4:
    uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step check

check-lab5:
    uv run labs/05-spartan-chaosnet-transient-stream/generate_topology.py
    uv run labs/05-spartan-chaosnet-transient-stream/verify_stream.py --step check

# --- per-lab walkthrough steps (canonical examples) -------------------------
# e.g. `just lab2 base`, `just lab2 memo -- APPROVE`, `just lab3 report`
lab1 step="check":
    uv run labs/01-simple-loadflow-fit/run.py --step {{step}}

lab2 step="check":
    uv run labs/02-medium-interconnection-screening/workflow.py --step {{step}}

lab3 step="check":
    uv run labs/03-advanced-provider-bakeoff/orchestrator.py --step {{step}}

lab4:
    uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step check

lab5:
    uv run labs/05-spartan-chaosnet-transient-stream/generate_topology.py

# --- demo: render the animations (PowerPoint-friendly MP4s) -----------------
render: render-lab1 render-lab2 render-lab5

render-lab1:
    uv run python labs/01-simple-loadflow-fit/animate_convergence.py

render-lab2:
    uv run python labs/02-medium-interconnection-screening/animate_contingencies.py

render-lab5:
    uv run python labs/05-spartan-chaosnet-transient-stream/animate_transient.py

# Lab 5 KISS viewer: isometric 3D phase-space PNG (committed sample) + a
# 3-channel WAV sonification (playable with mpv) + prints the peak-deviation
# anomaly bins (per 1 s / 5 s) that seed the anomaly classifier.
view-lab5:
    uv run python labs/05-spartan-chaosnet-transient-stream/view_3d_audio.py

# Lab 5 telemetry-rate views: static stacked still (sample_telemetry_rates.png,
# committed) + the animated isolated time-aligned feeds MP4 (gitignored).
view-lab5-rates:
    uv run python labs/05-spartan-chaosnet-transient-stream/view_telemetry_rates.py
    uv run python labs/05-spartan-chaosnet-transient-stream/animate_telemetry_rates.py

# Lab 5 time-frequency view: STFT spectrogram of the fault transient
# (sample_spectrogram.png, committed -- docs/backlog/0006 option 3).
view-lab5-spectrogram:
    uv run python labs/05-spartan-chaosnet-transient-stream/view_spectrogram.py

# --- Lab 5 VILLASnode stream tap (real podman pod, see README "Sandbox
# notes" 4-6 and kube/villasnode-tap-pod.yaml's own header) ------------------
# `run_dpsim.py` must have run at least once first -- it writes the real
# villas/chaos_stream.csv the pod reads. `just lab5-villasnode` runs the
# full up -> verify -> down round trip in one shot; the three split recipes
# below are for stepping through it by hand (e.g. to `podman logs`/`podman
# ps` against a pod left running between `up` and `down`).
villasnode-up:
    podman kube play {{justfile_directory()}}/kube/villasnode-tap-pod.yaml

villasnode-verify node="sub-3-tap":
    uv run labs/05-spartan-chaosnet-transient-stream/verify_stream.py --node {{node}}

villasnode-down:
    podman kube play --down {{justfile_directory()}}/kube/villasnode-tap-pod.yaml

lab5-villasnode: villasnode-up villasnode-verify villasnode-down

# --- Rust / WASM (the oxidized phase_model, PSCADOSSE) -----------------------
# Native tests (includes real_log_matches_python: the Rust port must match
# the Python numbers exactly on the real DPsim log).
rust-test:
    cargo test --manifest-path rust/Cargo.toml

# Build the simulation crate to WASM (the "sim compiled into wasm, shipped to
# the browser" piece the Dioxus UI will load client-side).
rust-wasm:
    cargo build --manifest-path rust/Cargo.toml -p phase-model --target wasm32-unknown-unknown

# Build the Dioxus web app -> scripts/demo_dist/ (served by `just demo`).
# Requires trunk + wasm-bindgen-cli (see docs/PSCADOSSE.md).
rust-web:
    trunk build --manifest-path rust/demo-app/Trunk.toml

# --- demo: browser dashboard + display without file transfer ----------------
# One command: starts a local HTTP server and opens the demo dashboard in your
# browser (WSL3/Windows capable -- no X, no WSLg dependency, full-res video +
# audio). `just demo-stop` stops it; `just demo-tui` is the terminal fzf
# fallback for an SSH-only session.
demo:
    #!/usr/bin/env bash
    set -euo pipefail
    pkill -f serve_demo.py 2>/dev/null || true
    nohup python3 -u scripts/serve_demo.py --open >/tmp/demo_server.log 2>&1 &
    sleep 1
    grep -m1 "http://" /tmp/demo_server.log

demo-stop:
    pkill -f serve_demo.py 2>/dev/null || true
    echo "demo server stopped (if it was running)."

# Terminal fallback: fzf menu of every visualization, launched in the SSH
# terminal (no browser needed).
demo-tui:
    ./scripts/demo.sh

# chafa-render a named committed chart straight into the SSH terminal.
# `just peek` lists the named charts; `just peek <name>` renders one.
peek name="list":
    ./scripts/peek_viz.sh {{name}}

# Play a named animation with mpv -- windowed over X11/WSLg by default.
# `just watch` lists the named animations; `just watch <name>` plays one.
watch name="list":
    ./scripts/watch_viz.sh {{name}}

# Same, but truecolor playback inside the SSH terminal (mpv --vo=tct).
watch-tct name="list":
    ./scripts/watch_viz.sh --in-terminal {{name}}

# --- help -------------------------------------------------------------------
default:
    @just --list
